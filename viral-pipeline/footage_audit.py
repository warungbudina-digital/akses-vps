#!/usr/bin/env python3
"""footage_audit.py — audit footage (rekaman sendiri / stok) terhadap blueprint IR.

Alur: ambil klip (dir lokal akses-vps ATAU inbox Gdrive rclone) -> jalankan lewat
analyzer V2 di .50 (CLIP semantic + probe meta + lighting) -> cocokkan tiap klip ke
FASE blueprint -> hitung AUDIT (kecocokan semantic, fit durasi, fit rasio, delta
pencahayaan) -> emit:
  <base>.footage-plan.json  (fase->klip->ops VN, siap orchestrator repro / assemble)
  <base>.footage-audit.md   (laporan manusiawi + flag masalah konkret)

Tujuan: bikin footage PRESISI & SESUAI SCRIPT sebelum masuk VN (VN = executor buta).
Analisis nyata di analyzer .50 (bukan tebakan). stdlib-only; shell out ke ssh/rclone.

Contoh:
  # klip lokal di akses-vps, nama babak-01.mp4 ...
  python3 footage_audit.py reel.vn-blueprint.json --clips-dir ~/footage-in --out reel
  # tarik dari inbox Gdrive (stream ke .50, tak mendarat di disk VPS)
  python3 footage_audit.py reel.vn-blueprint.json --gdrive gfootage: --out reel
"""
import argparse, json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone

# --- CLIP label -> query stok (SAMA dgn pexels_fetch.py; utk 'related' & saran) ---
SEMANTIC_QUERY_MAP = {
    "youtube talking head": "person talking to camera",
    "person talking": "person speaking closeup",
    "reaction face": "person surprised expression",
    "gameplay footage": "video game gaming screen",
    "product showcase": "product display studio",
    "food closeup": "food closeup cooking",
    "outdoor scenery": "nature landscape scenery",
    "dancing": "person dancing",
    "text on screen": "abstract motion background",
    "tutorial screen recording": "laptop typing technology",
    "street interview": "city street people walking",
    "pet animal": "pet animal",
    "car vehicle": "car driving road",
    "unknown": "cinematic b roll background",
}
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def aspect_label(w, h):
    if not w or not h:
        return None
    r = w / h
    if r < 0.85:
        return "9:16"
    if r < 1.15:
        return "1:1"
    return "16:9"


def guess_phase_index(name):
    """Ekstrak indeks fase (0-based) dari nama file konvensi babak/fase/phase/scene-NN
    atau angka di depan (01_...). None kalau tak ada."""
    b = os.path.basename(name).lower()
    m = re.search(r'(?:babak|fase|phase|scene|seg|part)[ _-]*0*(\d+)', b)
    if not m:
        m = re.match(r'0*(\d+)[ _.-]', b)
    if m:
        n = int(m.group(1))
        return n - 1 if n >= 1 else 0
    return None


def sanitize(name, idx):
    base = re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(name))
    return f"fa_{idx}_{base}"


class Analyzer:
    """Kirim klip ke .50 (host input dir bind-mount) -> POST /analyze -> IR JSON."""

    def __init__(self, sock, host, url, host_input, analyze_timeout, keep):
        self.sock, self.host, self.url = sock, host, url
        self.host_input, self.timeout, self.keep = host_input, analyze_timeout, keep

    def _ssh(self, remote_cmd, **kw):
        return run(["ssh", "-o", f"ControlPath={self.sock}", "-p", "22", self.host,
                    remote_cmd], **kw)

    def preflight(self):
        r = self._ssh(f"curl -s -m8 {self.url}/healthz")
        try:
            h = json.loads(r.stdout)
        except Exception:
            return False, f"healthz tak terjawab ({r.stdout[:80]} {r.stderr[:80]})"
        if not (h.get("asr") and h.get("semantic")):
            return False, f"analyzer BUKAN V2 (asr={h.get('asr')} semantic={h.get('semantic')})"
        self._ssh(f"mkdir -p {self.host_input}")
        return True, "V2 siap"

    def _push_local(self, local, remote_name):
        dest = f"{self.host_input}/{remote_name}"
        with open(local, "rb") as fh:
            p = subprocess.run(
                ["ssh", "-o", f"ControlPath={self.sock}", "-p", "22", self.host,
                 f"cat > {dest}"], stdin=fh, capture_output=True)
        return p.returncode == 0

    def _push_gdrive(self, remote_path, remote_name):
        dest = f"{self.host_input}/{remote_name}"
        cat = subprocess.Popen(["rclone", "cat", remote_path, "--timeout", "30s",
                                "--retries", "3"], stdout=subprocess.PIPE)
        ssh = subprocess.Popen(
            ["ssh", "-o", f"ControlPath={self.sock}", "-p", "22", self.host,
             f"cat > {dest}"], stdin=cat.stdout)
        cat.stdout.close()
        ssh.communicate()
        cat.wait()
        return ssh.returncode == 0 and cat.returncode == 0

    def analyze(self, source, remote_name, gdrive=False):
        ok = (self._push_gdrive(source, remote_name) if gdrive
              else self._push_local(source, remote_name))
        if not ok:
            return None, "gagal transfer klip ke .50"
        try:
            body = '{"video_path":"/data/input/%s"}' % remote_name
            r = self._ssh(f"curl -s -m {self.timeout} -XPOST {self.url}/analyze "
                          f"-H 'Content-Type: application/json' --data-raw '{body}'")
            try:
                resp = json.loads(r.stdout)
            except Exception:
                return None, f"respons /analyze tak valid: {r.stdout[:120]}{r.stderr[:120]}"
            if "analysis" not in resp:
                return None, f"analyze gagal: {resp.get('detail') or resp.get('status') or r.stdout[:120]}"
            return resp["analysis"], None
        finally:
            if not self.keep:
                self._ssh(f"rm -f {self.host_input}/{remote_name}")


def clip_facts(ir):
    """Ringkas IR 1 klip -> fakta yg dipakai audit."""
    scenes = ir.get("scene_analysis") or []
    w, h = ir.get("width"), ir.get("height")
    ar = ir.get("aspect_ratio") or aspect_label(w, h)
    dur = ir.get("duration_sec")
    if dur is None:
        dur = round(sum((s.get("end", 0) or 0) - (s.get("start", 0) or 0) for s in scenes), 2)
    # semantic dominan berbobot durasi
    acc = {}
    for s in scenes:
        sem = s.get("semantic") or "unknown"
        d = (s.get("duration") or ((s.get("end", 0) or 0) - (s.get("start", 0) or 0)) or 0)
        acc[sem] = acc.get(sem, 0) + d
    dom_sem = max(acc, key=acc.get) if acc else (scenes[0].get("semantic") if scenes else "unknown")
    # lighting agregat + label dominan
    lit = [s.get("lighting") for s in scenes if s.get("lighting")]
    lighting = {}
    if lit:
        def dom(k):
            c = {}
            for l in lit:
                v = l.get(k)
                if v:
                    c[v] = c.get(v, 0) + 1
            return max(c, key=c.get) if c else None
        lighting = {
            "brightness": dom("brightness_label"),
            "contrast": dom("contrast_label"),
            "temperature": dom("temperature_label"),
            "avg_brightness": round(sum(l.get("brightness", 0) for l in lit) / len(lit), 3),
        }
    cams = {}
    for s in scenes:
        cm = s.get("camera_movement")
        if cm:
            cams[cm] = cams.get(cm, 0) + 1
    return {
        "width": w, "height": h, "fps": ir.get("fps"), "aspect_ratio": ar,
        "duration_sec": dur, "n_scenes": len(scenes),
        "semantic": dom_sem, "semantic_mix": sorted(acc, key=acc.get, reverse=True)[:4],
        "lighting": lighting,
        "camera": max(cams, key=cams.get) if cams else None,
        "has_audio": bool(ir.get("subtitle_segments")) or ir.get("has_audio"),
    }


def adjust_from_lighting(lighting):
    """Saran op VN Adjust utk normalisasi (peta sama ir_to_vn._adjust_from_lighting)."""
    acts = []
    if not lighting:
        return acts
    bl, cl, tl = lighting.get("brightness"), lighting.get("contrast"), lighting.get("temperature")
    if bl == "dark":
        acts.append("KECERAHAN naik")
    elif bl == "bright":
        acts.append("KECERAHAN turun")
    if cl == "low":
        acts.append("KONTRAS naik")
    elif cl == "high":
        acts.append("KONTRAS turun")
    if tl == "warm":
        acts.append("SUHU dingin")
    elif tl == "cool":
        acts.append("SUHU hangat")
    return acts


def audit(phase, cf, target_ar):
    """Bandingkan klip (cf) vs fase target -> verdikt + flags + skor."""
    flags = []
    p_sem = phase.get("semantic") or "unknown"
    c_sem = cf.get("semantic") or "unknown"
    if c_sem == p_sem:
        sem_v, sem_s = "match", 1.0
    elif c_sem in ("unknown", None):
        sem_v, sem_s = "unknown", 0.3
        flags.append("semantic klip tak terdeteksi (unknown)")
    elif SEMANTIC_QUERY_MAP.get(c_sem) == SEMANTIC_QUERY_MAP.get(p_sem):
        sem_v, sem_s = "related", 0.6
    else:
        sem_v, sem_s = "mismatch", 0.0
        flags.append(f"semantic '{c_sem}' ≠ target '{p_sem}'")

    tgt = phase.get("dur_sec") or 0
    cd = cf.get("duration_sec") or 0
    if cd >= tgt:
        dur_v, dur_s = "ok", 1.0
    else:
        dur_v, dur_s = "short", max(0.0, cd / tgt if tgt else 0)
        flags.append(f"durasi kurang {round(tgt - cd, 2)}s (klip {cd}s < target {tgt}s)")

    c_ar = cf.get("aspect_ratio")
    if not target_ar or c_ar == target_ar:
        ar_v, ar_s = "ok", 1.0
    else:
        ar_v, ar_s = "crop_needed", 0.5
        flags.append(f"rasio {c_ar} ≠ target {target_ar} → perlu crop")

    lg = cf.get("lighting") or {}
    adj = adjust_from_lighting(lg)
    if lg.get("brightness") == "dark":
        flags.append("footage gelap → naikkan KECERAHAN di VN")
    if lg.get("contrast") == "low":
        flags.append("kontras rendah → naikkan KONTRAS di VN")

    score = round(sem_s * 0.5 + dur_s * 0.3 + ar_s * 0.2, 3)
    verdict = "OK" if (sem_v in ("match", "related") and dur_v == "ok" and score >= 0.8) \
        else ("WARN" if score >= 0.5 else "FAIL")
    return {
        "verdict": verdict, "score": score,
        "semantic": {"clip": c_sem, "target": p_sem, "match": sem_v},
        "duration": {"clip_sec": cd, "target_sec": tgt, "fit": dur_v},
        "aspect": {"clip": c_ar, "target": target_ar, "fit": ar_v},
        "lighting": lg, "vn_adjust": adj,
        "flags": flags,
    }


def collect_clips(a):
    """Kembalikan list (source, display_name, is_gdrive)."""
    items = []
    if a.clips_dir:
        for f in sorted(os.listdir(a.clips_dir)):
            if f.lower().endswith(VIDEO_EXT):
                items.append((os.path.join(a.clips_dir, f), f, False))
    if a.gdrive:
        r = run(["rclone", "lsf", a.gdrive, "--timeout", "30s", "--retries", "3"])
        if r.returncode != 0:
            log(f"WARN rclone lsf gagal: {r.stderr[:120]}")
        for line in r.stdout.splitlines():
            f = line.strip().rstrip("/")
            if f and f.lower().endswith(VIDEO_EXT):
                items.append((a.gdrive + f, f, True))
    return items


def main():
    ap = argparse.ArgumentParser(description="Audit footage terhadap blueprint IR via analyzer .50")
    ap.add_argument("blueprint", help="<base>.vn-blueprint.json dari ir_to_vn.py")
    ap.add_argument("--clips-dir", help="dir klip lokal di akses-vps")
    ap.add_argument("--gdrive", help="remote:path inbox Gdrive (mis. gfootage:)")
    ap.add_argument("--match", choices=["filename", "semantic", "order"], default="filename",
                    help="strategi cocokkan klip->fase (default filename, fallback order)")
    ap.add_argument("--out", help="prefix output (default: basis blueprint)")
    ap.add_argument("--c50-sock", default="/tmp/c50.sock")
    ap.add_argument("--c50-host", default="warungbudina@10.66.66.50")
    ap.add_argument("--analyzer-url", default="http://127.0.0.1:9021")
    ap.add_argument("--host-input", default="~/tool-analisa-video/data/input")
    ap.add_argument("--analyze-timeout", type=int, default=600)
    ap.add_argument("--keep", action="store_true", help="jangan hapus klip dari .50 stlh analisa")
    ap.add_argument("--no-analyze", action="store_true", help="hanya cocokkan+kerangka, tanpa .50")
    a = ap.parse_args()

    bp = json.load(open(a.blueprint))
    phases = bp.get("phases", [])
    if not phases:
        log("GAGAL: blueprint tanpa 'phases'.")
        sys.exit(2)
    target_ar = (bp.get("source", {}).get("aspect_ratio")
                 or bp.get("format", {}).get("orientation_hint")
                 or bp.get("aspect_ratio"))
    base = a.out or re.sub(r'\.vn-blueprint\.json$|\.json$', '', a.blueprint)

    clips = collect_clips(a)
    if not clips:
        log("GAGAL: tak ada klip (pakai --clips-dir dan/atau --gdrive).")
        sys.exit(2)
    log(f"{len(clips)} klip · {len(phases)} fase · rasio target={target_ar} · match={a.match}")

    an = None
    if not a.no_analyze:
        an = Analyzer(a.c50_sock, a.c50_host, a.analyzer_url,
                      a.host_input, a.analyze_timeout, a.keep)
        ok, msg = an.preflight()
        if not ok:
            log(f"GAGAL preflight .50: {msg}")
            sys.exit(3)
        log(f"analyzer .50: {msg}")

    # analisa tiap klip
    analyzed = []
    for idx, (src, name, is_g) in enumerate(clips):
        cf, err = ({}, None)
        if an:
            rname = sanitize(name, idx)
            log(f"  analisa [{idx}] {name}{' (gdrive)' if is_g else ''} ...")
            ir, err = an.analyze(src, rname, gdrive=is_g)
            cf = clip_facts(ir) if ir else {}
            if err:
                log(f"    ERROR: {err}")
        analyzed.append({"i": idx, "name": name, "source": src, "is_gdrive": is_g,
                         "facts": cf, "error": err,
                         "hint_phase": guess_phase_index(name)})

    # --- cocokkan klip -> fase ---
    assign = {}  # phase_index -> clip dict
    used = set()
    if a.match == "filename":
        for c in analyzed:
            hp = c["hint_phase"]
            if hp is not None and 0 <= hp < len(phases) and hp not in assign:
                assign[hp] = c
                used.add(c["i"])
    if a.match == "semantic":
        for pi, ph in enumerate(phases):
            for c in analyzed:
                if c["i"] in used:
                    continue
                if c["facts"].get("semantic") == ph.get("semantic"):
                    assign[pi] = c
                    used.add(c["i"])
                    break
    # sisa: isi fase kosong berurutan
    leftover = [c for c in analyzed if c["i"] not in used]
    for pi in range(len(phases)):
        if pi not in assign and leftover:
            assign[pi] = leftover.pop(0)
            used.add(assign[pi]["i"])

    # --- bangun plan + audit ---
    out_phases = []
    n_ok = n_warn = n_fail = n_empty = 0
    for pi, ph in enumerate(phases):
        entry = {"i": pi, "start": ph.get("start"), "end": ph.get("end"),
                 "dur_sec": ph.get("dur_sec"), "semantic": ph.get("semantic"),
                 "n_cuts": ph.get("n_cuts"), "clip": None, "audit": None,
                 "status": "empty"}
        c = assign.get(pi)
        if c:
            cf = c["facts"]
            entry["clip"] = {"name": c["name"], "source": c["source"],
                             "is_gdrive": c["is_gdrive"], "matched_by": a.match,
                             **{k: cf.get(k) for k in
                                ("width", "height", "fps", "aspect_ratio",
                                 "duration_sec", "semantic", "camera", "lighting")}}
            if c["error"] or not cf:
                entry["status"] = "analyze_error"
                entry["audit"] = {"verdict": "FAIL", "flags": [c["error"] or "tak teranalisa"]}
                n_fail += 1
            else:
                au = audit(ph, cf, target_ar)
                entry["audit"] = au
                entry["status"] = "matched"
                n_ok += au["verdict"] == "OK"
                n_warn += au["verdict"] == "WARN"
                n_fail += au["verdict"] == "FAIL"
        else:
            n_empty += 1
            entry["audit"] = {"verdict": "EMPTY", "flags": ["tak ada footage utk fase ini"]}
        out_phases.append(entry)

    unmatched = [{"name": c["name"], "semantic": c["facts"].get("semantic"),
                  "duration_sec": c["facts"].get("duration_sec")}
                 for c in analyzed if c["i"] not in used]

    plan = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_blueprint": os.path.abspath(a.blueprint),
        "aspect_ratio_target": target_ar,
        "srt_file": bp.get("captions", {}).get("srt_file"),
        "bpm": bp.get("beat", {}).get("bpm") or bp.get("source", {}).get("bpm"),
        "match_strategy": a.match,
        "n_phases": len(phases), "n_clips": len(analyzed),
        "summary": {"ok": n_ok, "warn": n_warn, "fail": n_fail,
                    "empty_phases": n_empty, "unmatched_clips": len(unmatched)},
        "phases": out_phases,
        "unmatched_clips": unmatched,
    }
    plan_path = base + ".footage-plan.json"
    json.dump(plan, open(plan_path, "w"), ensure_ascii=False, indent=2)

    # --- laporan markdown ---
    md = [f"# Audit Footage — {os.path.basename(base)}", "",
          f"- Blueprint: `{os.path.basename(a.blueprint)}` · {len(phases)} fase · rasio target **{target_ar}**",
          f"- Footage: {len(analyzed)} klip (strategi cocok: **{a.match}**)",
          f"- Ringkas: **{n_ok} OK · {n_warn} WARN · {n_fail} FAIL · {n_empty} fase kosong · {len(unmatched)} klip tak terpakai**",
          "", "| Fase | Target (semantic / durasi) | Klip | Verdikt | Flag utama |",
          "|---|---|---|---|---|"]
    for e in out_phases:
        cl = e["clip"]
        au = e["audit"] or {}
        cname = cl["name"] if cl else "—"
        cinfo = (f"{cl.get('semantic')} / {cl.get('duration_sec')}s / {cl.get('aspect_ratio')}"
                 if cl else "")
        flags = "; ".join((au.get("flags") or [])[:2]) or "—"
        md.append(f"| {e['i']+1} | {e['semantic']} / {e['dur_sec']}s | {cname}<br>{cinfo} | "
                  f"{au.get('verdict','—')} ({au.get('score','')}) | {flags} |")
    md += ["", "## Rincian per fase & arahan koreksi", ""]
    for e in out_phases:
        au = e["audit"] or {}
        md.append(f"### Fase {e['i']+1} — target `{e['semantic']}`, {e['dur_sec']}s "
                  f"({e['start']}s–{e['end']}s)")
        if not e["clip"]:
            md.append(f"- ⚠️ **{au.get('verdict')}**: {'; '.join(au.get('flags', []))}")
            md.append(f"- Rekam sesuai `.story-script.md` babak {e['i']+1}, atau ambil stok "
                      f"(`pexels_fetch.py`).")
            md.append("")
            continue
        cl = e["clip"]
        md.append(f"- Klip: **{cl['name']}** — semantic `{cl.get('semantic')}`, "
                  f"{cl.get('duration_sec')}s, {cl.get('width')}x{cl.get('height')} "
                  f"({cl.get('aspect_ratio')}), kamera {cl.get('camera')}")
        md.append(f"- Verdikt: **{au.get('verdict')}** (skor {au.get('score')})")
        if au.get("flags"):
            for fl in au["flags"]:
                md.append(f"  - ⚠️ {fl}")
        if au.get("vn_adjust"):
            md.append(f"- Koreksi VN Adjust: {', '.join(au['vn_adjust'])}")
        md.append("")
    if unmatched:
        md += ["## Klip tak terpakai", ""]
        for u in unmatched:
            md.append(f"- {u['name']} (semantic `{u['semantic']}`, {u['duration_sec']}s)")
        md.append("")
    md_path = base + ".footage-audit.md"
    open(md_path, "w").write("\n".join(md))

    log(f"SELESAI: {n_ok} OK / {n_warn} WARN / {n_fail} FAIL / {n_empty} kosong")
    log(f"  plan   -> {plan_path}")
    log(f"  report -> {md_path}")


if __name__ == "__main__":
    main()
