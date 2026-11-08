#!/usr/bin/env python3
"""manual_fetch_api.py — backend form manual-fetch.html (pipeline.obc-crypto.com).

(2026-11-04, permintaan user — plan crispy-mapping-cherny.md) orchestrator.py
sekarang cuma --dry-run pexels_fetch.py/pixabay_fetch.py per job (query+plan
JSON saja, nol download/push -- lihat fetch_and_push_footage()). Query
otomatis dari semantic label CLIP sering tak relevan dgn analisa video, jadi
download+push NYATA dipindah ke sini: user review .story-script.md + plan
dry-run via manual-fetch.html, edit keyword per fase kalau perlu, baru klip
BENAR diunduh+push ke RN7 (/sdcard/Movies/Seal/, sama target otomatis dulu).

Disk hub pernah 97% penuh (cache klip stok tak pernah dihapus) -- jadi alur
ini: (1) chunked (CHUNK_SIZE fase/siklus fetch+push, bukan sekali semua),
(2) disk-guard per-klip (lihat stock_common.py DiskGuardError), (3) hapus
local_path SETELAH rn7_path terkonfirmasi (retensi hapus-setelah-terkirim,
beda dari push_raw_footage.py sendiri yg defaultnya cache permanen -- policy
ini SENGAJA cuma di sini, push_raw_footage.py tetap generik/retensi-agnostic).

Auth: reuse DASHBOARD_TOKEN dari ~/.config/viral-dashboard/credentials.env
(trust boundary + domain sama persis dashboard_api.py/input.html -- user
cukup 1x paste token, berlaku jg di manual-fetch.html krn localStorage key
sama). Bind 172.19.0.1:<PORT> (gateway docker, nginx jalan di container --
pola sama dashboard_api.py). Jalan via systemd viral-manual-fetch-api
(lihat install-manual-fetch-api.sh).

Env: MANUAL_FETCH_API_PORT (default 8098), MANUAL_FETCH_API_BIND (default 172.19.0.1).
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import push_raw_footage as prf  # reuse resolve_udid/job_id_of, jangan duplikasi

REPRO_DIR        = os.path.expanduser("~/viral-pipeline/reproductions")
PEXELS_FETCH     = os.path.expanduser("~/viral-pipeline/pexels_fetch.py")
PIXABAY_FETCH    = os.path.expanduser("~/viral-pipeline/pixabay_fetch.py")
PUSH_RAW_FOOTAGE = os.path.expanduser("~/viral-pipeline/push_raw_footage.py")
FOOTAGE_TIMEOUT  = int(os.getenv("FOOTAGE_TIMEOUT", "600"))
CHUNK_SIZE       = 5     # fase/siklus fetch+push+hapus -- batasi puncak pemakaian disk
DISK_FLOOR_MB    = 700   # sama dgn stock_common.DISK_FLOOR_MB, duplikat kecil drpd cross-import

BIND = os.getenv("MANUAL_FETCH_API_BIND", "172.19.0.1")
PORT = int(os.getenv("MANUAL_FETCH_API_PORT", "8098"))
TOKEN_FILE = os.path.expanduser("~/.config/viral-dashboard/credentials.env")

_lock = threading.Lock()
_busy = {"job_id": None}


def log(*a):
    print("[manual_fetch_api]", *a, file=sys.stderr, flush=True)


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DASHBOARD_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


TOKEN = load_token()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _disk_avail_mb(path="/"):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize // (1024 * 1024)


def _job_dir(num_id):
    return os.path.join(REPRO_DIR, f"job-{num_id}")


def _manual_dir(num_id):
    return os.path.join(_job_dir(num_id), "manual")


def _auto_plan_path(num_id, provider="pexels"):
    return os.path.join(_job_dir(num_id), f"job-{num_id}.{provider}-plan.json")


def _manual_plan_path(num_id, provider):
    return os.path.join(_manual_dir(num_id), f"job-{num_id}.{provider}-plan.json")


def _status_path(num_id):
    return os.path.join(_manual_dir(num_id), f"job-{num_id}.manual-status.json")


def _write_status(num_id, status):
    os.makedirs(_manual_dir(num_id), exist_ok=True)
    json.dump(status, open(_status_path(num_id), "w"), ensure_ascii=False, indent=2)


def _read_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def list_jobs():
    out = []
    for d in sorted(glob.glob(os.path.join(REPRO_DIR, "job-*"))):
        m = re.match(r"job-(\d+)$", os.path.basename(d))
        if not m or not os.path.isdir(d):
            continue
        num_id = m.group(1)
        blueprint = os.path.join(d, f"job-{num_id}.vn-blueprint.json")
        auto_plan = _read_json(_auto_plan_path(num_id, "pexels")) or \
                    _read_json(_auto_plan_path(num_id, "pixabay"))
        if not os.path.isfile(blueprint) or not auto_plan:
            continue  # belum ada plan dry-run (bagian A) -- belum siap difetch manual
        status = _read_json(_status_path(num_id))
        out.append({
            "job_id": f"job-{num_id}",
            "n_phases": auto_plan.get("n_phases"),
            "generated_utc": auto_plan.get("generated_utc"),
            "manual_status": status.get("state") if status else None,
        })
    return out


_BABAK_RE = re.compile(r"^### Babak (\d+) — (.*)$", re.MULTILINE)


def _parse_story_script(path):
    """{0: (title, body), 1: (title, body), ...} -- Babak N (1-based) -> index N-1."""
    if not os.path.isfile(path):
        return {}
    text = open(path, encoding="utf-8").read()
    matches = list(_BABAK_RE.finditer(text))
    out = {}
    for j, m in enumerate(matches):
        n = int(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[j + 1].start() if j + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        out[n - 1] = (title, body)
    return out


def _current_overrides(num_id):
    """Override yg SUDAH tersimpan dari run sebelumnya (queries.json) --
    dipakai job_detail() supaya UI prefill nilai TERKINI, bukan cuma
    auto_query, saat user reload halaman/lanjutkan run (lihat finding
    advisor: Lanjutkan jangan buang keyword yg sudah diketik)."""
    return _read_json(os.path.join(_manual_dir(num_id), f"job-{num_id}.queries.json"), {}) or {}


def job_detail(num_id):
    d = _job_dir(num_id)
    auto_plan = _read_json(_auto_plan_path(num_id, "pexels")) or \
                _read_json(_auto_plan_path(num_id, "pixabay"))
    if not auto_plan:
        return None, "job tak ditemukan atau belum ada plan dry-run"
    story_path = os.path.join(d, f"job-{num_id}.story-script.md")
    babak = _parse_story_script(story_path)
    overrides = _current_overrides(num_id)
    phases = sorted(auto_plan.get("phases", []), key=lambda p: p["i"])
    mismatch = len(babak) != len(phases)
    out_phases = []
    for p in phases:
        title, body = babak.get(p["i"], ("", ""))
        out_phases.append({
            "i": p["i"], "dur_sec": p.get("dur_sec"), "semantic": p.get("semantic"),
            "auto_query": p.get("query"), "current_query": overrides.get(str(p["i"]), p.get("query")),
            "babak_title": title, "babak_text": body,
        })
    return {"job_id": f"job-{num_id}", "n_phases": len(phases),
            "story_script_mismatch": mismatch, "phases": out_phases}, None


def _already_pushed(num_id):
    """Indeks fase yg di SALAH SATU master plan manual sudah punya rn7_path --
    dipakai /start utk filter Lanjutkan supaya tak fetch ulang yg sudah jadi."""
    done = set()
    for provider in ("pexels", "pixabay"):
        plan = _read_json(_manual_plan_path(num_id, provider))
        if plan:
            for p in plan.get("phases", []):
                if p.get("rn7_path"):
                    done.add(p["i"])
    return done


def _used_ids(num_id, provider):
    """Video id yg SUDAH kepilih di master plan provider ini -- dipakai
    --exclude-ids tiap chunk supaya dedup used_ids tetap jalan LINTAS-CHUNK.
    Tanpa ini, tiap panggilan pexels_fetch.py/pixabay_fetch.py mulai dari
    used_ids kosong (proses baru) -> fase2 beda dgn semantic/query sama bisa
    kepilih klip IDENTIK (temuan advisor)."""
    plan = _read_json(_manual_plan_path(num_id, provider))
    if not plan:
        return set()
    key = f"{provider}_video_id"
    return {p[key] for p in plan.get("phases", []) if p.get(key) is not None}


def _n_phases(num_id):
    auto_plan = _read_json(_auto_plan_path(num_id, "pexels")) or \
                _read_json(_auto_plan_path(num_id, "pixabay"))
    return auto_plan.get("n_phases", 0) if auto_plan else 0


def _merge_plan(master_path, chunk_path):
    """Gabung hasil 1 chunk ke master plan manual (akumulasi lintas-chunk) --
    pexels_fetch.py/pixabay_fetch.py selalu nulis plan BARU tiap dipanggil
    (nol mode merge bawaan), jadi penggabungan lintas-chunk HARUS di sini,
    bukan di fetcher-nya sendiri (satu tempat, bukan dobel pexels+pixabay)."""
    chunk = _read_json(chunk_path, {})
    master = _read_json(master_path) or {k: v for k, v in chunk.items() if k != "phases"}
    by_i = {p["i"]: p for p in master.get("phases", [])}
    for p in chunk.get("phases", []):
        by_i[p["i"]] = p  # chunk ini menang utk index yg sama (fetch ulang/override baru)
    master["phases"] = [by_i[k] for k in sorted(by_i)]
    master["n_phases"] = len(master["phases"])
    for k in ("generated_utc", "pexels_ratelimit_remaining"):
        if k in chunk:
            master[k] = chunk[k]
    attrs = {a.get("video_id"): a for a in master.get("attributions", [])}
    for a in chunk.get("attributions", []):
        attrs[a.get("video_id")] = a
    master["attributions"] = list(attrs.values())
    json.dump(master, open(master_path, "w"), ensure_ascii=False, indent=2)
    return master


def _phase_status(pe, px):
    if (pe and pe.get("rn7_path")) or (px and px.get("rn7_path")):
        return "pushed"
    if (pe and pe.get("status") == "disk_guard") or (px and px.get("status") == "disk_guard"):
        return "disk_guard"
    if (pe and pe.get("local_path")) or (px and px.get("local_path")):
        return "awaiting_push"
    if (pe and pe.get("status") == "too_large") or (px and px.get("status") == "too_large"):
        return "too_large"
    if (pe and pe.get("status") == "error") or (px and px.get("status") == "error"):
        return "error"
    if (pe and pe.get("status") == "empty") or (px and px.get("status") == "empty"):
        return "empty"
    return "pending"


def _run_fetch(num_id, target_phases):
    jid = f"job-{num_id}"
    blueprint = os.path.join(_job_dir(num_id), f"{jid}.vn-blueprint.json")
    manual_dir = _manual_dir(num_id)
    os.makedirs(manual_dir, exist_ok=True)
    queries_file = os.path.join(manual_dir, f"{jid}.queries.json")
    master = {"pexels": _manual_plan_path(num_id, "pexels"),
              "pixabay": _manual_plan_path(num_id, "pixabay")}
    scripts = {"pexels": PEXELS_FETCH, "pixabay": PIXABAY_FETCH}

    chunks = [target_phases[i:i + CHUNK_SIZE] for i in range(0, len(target_phases), CHUNK_SIZE)]
    status = {"state": "running", "job_id": jid, "started_utc": _now(), "updated_utc": _now(),
              "target_phases": target_phases, "chunks_total": len(chunks), "chunks_done": 0,
              "phases": {}, "message": ""}
    _write_status(num_id, status)
    log(f"[{jid}] mulai fetch manual: {len(target_phases)} fase, {len(chunks)} chunk")

    try:
        for ci, chunk in enumerate(chunks):
            phases_arg = ",".join(str(x) for x in chunk)
            for name, script in scripts.items():
                chunk_out = os.path.join(manual_dir, f"{jid}.{name}-plan.chunk.json")
                exclude_arg = ",".join(str(x) for x in _used_ids(num_id, name))
                cmd = ["python3", script, blueprint, "--out", chunk_out,
                       "--queries-file", queries_file, "--phases", phases_arg]
                if exclude_arg:
                    cmd += ["--exclude-ids", exclude_arg]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=FOOTAGE_TIMEOUT)
                if os.path.isfile(chunk_out):
                    _merge_plan(master[name], chunk_out)
                    os.remove(chunk_out)
                else:
                    log(f"  [{jid}] {name} chunk {chunk}: gagal, rc={r.returncode}:",
                        (r.stderr or r.stdout or "").strip()[-300:])

            # push TERPISAH per provider -- fix 2026-10-29 orchestrator.py:
            # timeout jangan dibagi 2 provider, satu lambat tak boleh potong jatah lainnya.
            for name in ("pexels", "pixabay"):
                if os.path.isfile(master[name]):
                    subprocess.run(["python3", PUSH_RAW_FOOTAGE, master[name]],
                                    capture_output=True, text=True, timeout=FOOTAGE_TIMEOUT)

            pe_plan = _read_json(master["pexels"], {"phases": []})
            px_plan = _read_json(master["pixabay"], {"phases": []})
            pe_by_i = {p["i"]: p for p in pe_plan.get("phases", [])}
            px_by_i = {p["i"]: p for p in px_plan.get("phases", [])}

            stuck = False
            for i in chunk:
                pe, px = pe_by_i.get(i), px_by_i.get(i)
                # retensi: hapus local_path SETELAH rn7_path terkonfirmasi (keputusan
                # user -- disk hub tak boleh jadi cache permanen lagi, lihat plan).
                for entry in (pe, px):
                    if entry and entry.get("rn7_path") and entry.get("local_path"):
                        try:
                            if os.path.isfile(entry["local_path"]):
                                os.remove(entry["local_path"])
                        except OSError as e:
                            log(f"  [{jid}] gagal hapus {entry['local_path']}: {e!r}")
                        entry["local_path"] = None
                st = _phase_status(pe, px)
                status["phases"][str(i)] = st
                if st == "awaiting_push":
                    stuck = True

            json.dump(pe_plan, open(master["pexels"], "w"), ensure_ascii=False, indent=2)
            json.dump(px_plan, open(master["pixabay"], "w"), ensure_ascii=False, indent=2)

            status["chunks_done"] = ci + 1
            status["updated_utc"] = _now()
            _write_status(num_id, status)

            if stuck:
                status["state"] = "paused_rn7_offline"
                status["message"] = ("RN7 tak terjangkau saat push -- klip chunk ini TETAP "
                                      "lokal (tak dihapus), klik \"Lanjutkan\" setelah RN7 online.")
                _write_status(num_id, status)
                log(f"[{jid}] PAUSED (RN7 offline) di chunk {ci+1}/{len(chunks)}")
                return

        # "done" HANYA kalau SEMUA fase target benar2 "pushed" -- status
        # mentah lain (empty/too_large/error/pending) tak boleh disamarkan
        # jadi "selesai" (lihat memori feedback_kegagalan_menyamar_sukses:
        # bug paling sering = status sukses tapi isi sebenarnya gagal/kosong).
        counts = {}
        for i in target_phases:
            st = status["phases"].get(str(i), "pending")
            counts[st] = counts.get(st, 0) + 1
        n_pushed = counts.get("pushed", 0)
        if n_pushed == len(target_phases):
            status["state"] = "done"
            status["message"] = f"Semua {n_pushed} fase terkirim ke RN7."
        else:
            status["state"] = "done_partial"
            detail = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()) if k != "pushed")
            status["message"] = (f"{n_pushed}/{len(target_phases)} fase terkirim ke RN7 -- "
                                  f"sisanya: {detail}. Edit keyword fase yg gagal lalu Lanjutkan.")
        _write_status(num_id, status)
        log(f"[{jid}] {status['state'].upper()}, {len(chunks)} chunk: {counts}")
    except Exception as e:
        status["state"] = "error"
        status["message"] = repr(e)[:300]
        _write_status(num_id, status)
        log(f"[{jid}] ERROR: {e!r}")
    finally:
        with _lock:
            _busy["job_id"] = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        if not TOKEN:
            return False
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/manual-fetch/health":
            self._send(200, {"ok": True}); return
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"}); return
        if path == "/api/manual-fetch/jobs":
            self._send(200, {"ok": True, "jobs": list_jobs()}); return
        m = re.match(r"^/api/manual-fetch/jobs/(\d+)/status$", path)
        if m:
            status = _read_json(_status_path(m.group(1)))
            if status is None:
                self._send(404, {"ok": False, "error": "belum ada run utk job ini"}); return
            self._send(200, {"ok": True, "status": status}); return
        m = re.match(r"^/api/manual-fetch/jobs/(\d+)$", path)
        if m:
            detail, err = job_detail(m.group(1))
            if err:
                self._send(404, {"ok": False, "error": err}); return
            self._send(200, {"ok": True, "job": detail}); return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"}); return
        m = re.match(r"^/api/manual-fetch/jobs/(\d+)/start$", self.path.split("?")[0])
        if not m:
            self._send(404, {"ok": False, "error": "not found"}); return
        num_id = m.group(1)

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw or b"{}")
        except Exception:
            self._send(400, {"ok": False, "error": "JSON tak valid"}); return

        n_phases = _n_phases(num_id)
        if not n_phases:
            self._send(404, {"ok": False, "error": "job tak ditemukan atau belum ada plan dry-run"}); return

        overrides_raw = data.get("overrides") or {}
        overrides = {}
        for k, v in overrides_raw.items():
            try:
                ik = int(k)
            except (TypeError, ValueError):
                self._send(400, {"ok": False, "error": f"index override tak valid: {k!r}"}); return
            if not (0 <= ik < n_phases):
                self._send(400, {"ok": False, "error": f"index override di luar jangkauan: {ik}"}); return
            v = (v or "").strip()
            if v:
                overrides[str(ik)] = v[:200]

        phases_req = data.get("phases")
        if phases_req is None:
            target_phases = list(range(n_phases))
        else:
            try:
                target_phases = sorted(set(int(x) for x in phases_req))
            except (TypeError, ValueError):
                self._send(400, {"ok": False, "error": "phases harus daftar integer"}); return
            if any(not (0 <= x < n_phases) for x in target_phases):
                self._send(400, {"ok": False, "error": "ada index phases di luar jangkauan"}); return

        # resume-aware: fase yg SUDAH rn7_path (chunk sebelumnya) tak diulang --
        # bikin tombol "Lanjutkan" (re-POST payload sama) otomatis cuma lanjut yg stuck.
        target_phases = sorted(set(target_phases) - _already_pushed(num_id))
        if not target_phases:
            self._send(200, {"ok": True, "message": "semua fase yg diminta sudah terkirim ke RN7."}); return

        with _lock:
            if _busy["job_id"] is not None:
                self._send(409, {"ok": False, "error": f"run lain sedang jalan (job-{_busy['job_id']})"}); return
            _busy["job_id"] = num_id

        avail = _disk_avail_mb()
        if avail < DISK_FLOOR_MB:
            with _lock:
                _busy["job_id"] = None
            self._send(507, {"ok": False, "error": f"disk hub tersisa {avail}MB, di bawah floor {DISK_FLOOR_MB}MB"}); return

        udid = prf.resolve_udid("tool-appium-appium-1", "10.66.66.6")
        if not udid:
            with _lock:
                _busy["job_id"] = None
            self._send(503, {"ok": False, "error": "RN7 tak terjangkau adb (Doze/tak dicas) -- coba lagi nanti"}); return

        # MERGE ke queries.json yg sudah ada (jangan overwrite) -- "Lanjutkan"
        # kirim overrides={} (tak ada edit baru), kalau overwrite keyword
        # dari run sebelumnya HILANG & fase stuck fallback ke auto_query
        # (temuan advisor: persis yg fitur ini mau hindari).
        os.makedirs(_manual_dir(num_id), exist_ok=True)
        queries_path = os.path.join(_manual_dir(num_id), f"job-{num_id}.queries.json")
        merged_overrides = dict(_read_json(queries_path, {}) or {})
        merged_overrides.update(overrides)
        json.dump(merged_overrides, open(queries_path, "w"), ensure_ascii=False, indent=2)

        t = threading.Thread(target=_run_fetch, args=(num_id, target_phases), daemon=True)
        t.start()
        self._send(202, {"ok": True, "status_url": f"/api/manual-fetch/jobs/{num_id}/status"})

    def log_message(self, fmt, *args):
        pass  # pakai log() sendiri, jangan dobel access-log bawaan


def _recover_interrupted():
    """Service restart di tengah fetch -> status 'running' nyangkut selamanya
    (tak ada thread yg nulis update lagi). Tandai 'interrupted' saat startup."""
    for sf in glob.glob(os.path.join(REPRO_DIR, "job-*", "manual", "job-*.manual-status.json")):
        st = _read_json(sf)
        if st and st.get("state") == "running":
            st["state"] = "interrupted"
            st["message"] = "Service manual-fetch-api restart di tengah run -- klik Lanjutkan."
            json.dump(st, open(sf, "w"), ensure_ascii=False, indent=2)
            log("recover: tandai interrupted ->", sf)


def main():
    if not TOKEN:
        sys.exit(f"DASHBOARD_TOKEN tak ketemu di {TOKEN_FILE} -- buat file berisi baris 'DASHBOARD_TOKEN=<acak>' (mode 600)")
    _recover_interrupted()
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    log(f"listen {BIND}:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
