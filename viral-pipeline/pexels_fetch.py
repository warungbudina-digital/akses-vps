#!/usr/bin/env python3
"""
pexels_fetch.py — jembatan IR/blueprint -> footage stok Pexels.

Baca <base>.vn-blueprint.json (dari ir_to_vn.py), lalu untuk TIAP FASE naratif
cari + unduh 1 klip Pexels yang cocok (orientasi 9:16/16:9 mengikuti rasio
sumber, durasi >= panjang fase supaya bisa dipotong pas). Output rencana JSON
(fase -> klip lokal + timing) yang bisa dirakit ffmpeg/viral_editor jadi video,
TANPA syuting ulang.

Kenapa level FASE (bukan per micro-cut): 1 b-roll = 1 beat cerita; footage stok
generik cocok untuk beat, bukan untuk mengganti tiap potongan 1-2 detik.

Sumber kebenaran fidelitas = STRUKTURAL (rasio/durasi/ritme/caption), BUKAN
makna piksel — footage stok = perkiraan tema (lihat catatan proyek).

stdlib-only (urllib) — tanpa pip. Kunci API dari env PEXELS_API_KEY atau
~/.config/pexels/credentials.env (chmod 600, JANGAN di repo).

Pemakaian:
  python3 pexels_fetch.py <base>.vn-blueprint.json --out plan.json
  [--cache DIR] [--orientation auto|portrait|landscape|square]
  [--max-height 1920] [--per-page 15] [--max-phases N] [--dry-run]

Exit: 0 sukses · 2 argumen/kunci · 3 error API/jaringan.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

API_BASE = "https://api.pexels.com/videos/search"

# CLIP zero-shot semantic (analyzer semantic.py) -> query stok yang searchable.
# Label CLIP kadang aneh utk pencarian stok -> dipetakan ke kata kunci b-roll.
SEMANTIC_QUERY_MAP = {
    "youtube talking head":     "person talking to camera",
    "person talking":           "person speaking closeup",
    "reaction face":            "person surprised expression",
    "gameplay footage":         "video game gaming screen",
    "product showcase":         "product display studio",
    "food closeup":             "food closeup cooking",
    "outdoor scenery":          "nature landscape scenery",
    "dancing":                  "person dancing",
    "text on screen":           "abstract motion background",
    "tutorial screen recording":"laptop typing technology",
    "street interview":         "city street people walking",
    "pet animal":               "pet animal",
    "car vehicle":              "car driving road",
    "unknown":                  "cinematic b roll background",
}
DEFAULT_FALLBACK = "cinematic b roll background"


def log(*a):
    print("[pexels_fetch]", *a, file=sys.stderr)


def load_key():
    k = os.environ.get("PEXELS_API_KEY", "").strip()
    if k:
        return k
    cred = os.path.expanduser("~/.config/pexels/credentials.env")
    if os.path.isfile(cred):
        for line in open(cred):
            line = line.strip()
            if line.startswith("PEXELS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def ratio_to_orientation(hint):
    """'9:16 (652x1158)' / '16:9' / '1:1' -> portrait|landscape|square."""
    if not hint:
        return "portrait"  # default: target Reels/Shorts
    m = re.search(r"(\d+)\s*:\s*(\d+)", str(hint))
    if not m:
        return "portrait"
    w, h = int(m.group(1)), int(m.group(2))
    if h > w:
        return "portrait"
    if w > h:
        return "landscape"
    return "square"


def semantic_to_query(sem):
    sem = (sem or "unknown").strip().lower()
    if sem in SEMANTIC_QUERY_MAP:
        return SEMANTIC_QUERY_MAP[sem]
    # passthrough: buang kata isian, sisakan yg bermakna
    words = [w for w in re.findall(r"[a-z]+", sem) if w not in ("a", "the", "on", "of")]
    return " ".join(words) if words else DEFAULT_FALLBACK


def pexels_search(key, query, orientation, per_page):
    params = {"query": query, "per_page": per_page, "size": "medium"}
    if orientation in ("portrait", "landscape", "square"):
        params["orientation"] = orientation
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": key,
                                               "User-Agent": "viral-pipeline/pexels_fetch"})
    with urllib.request.urlopen(req, timeout=25) as r:
        remaining = r.headers.get("x-ratelimit-remaining")
        data = json.loads(r.read().decode("utf-8"))
    return data.get("videos", []), remaining


def pick_video(videos, need_dur, used_ids):
    """Pilih klip: durasi >= kebutuhan (paling pas/pendek), hindari id terpakai."""
    fresh = [v for v in videos if v.get("id") not in used_ids] or videos
    fit = [v for v in fresh if (v.get("duration") or 0) >= need_dur]
    if fit:
        return min(fit, key=lambda v: v.get("duration", 0))
    if fresh:
        return max(fresh, key=lambda v: v.get("duration", 0))
    return None


def pick_file(video, orientation, max_h):
    """Pilih 1 video_file mp4: orientasi cocok, tinggi <= cap (ambil terbesar)."""
    files = [f for f in video.get("video_files", [])
             if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
    if not files:
        return None

    def ok_orient(f):
        w, h = f["width"], f["height"]
        if orientation == "portrait":
            return h >= w
        if orientation == "landscape":
            return w >= h
        return True

    cand = [f for f in files if ok_orient(f)] or files
    under = [f for f in cand if f["height"] <= max_h]
    return max(under, key=lambda f: f["height"]) if under \
        else min(cand, key=lambda f: f["height"])


def download(url, dest):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "viral-pipeline/pexels_fetch"})
    with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    return os.path.getsize(dest)


def main():
    ap = argparse.ArgumentParser(description="IR/blueprint -> footage stok Pexels per fase.")
    ap.add_argument("blueprint", help="path <base>.vn-blueprint.json")
    ap.add_argument("--out", help="path rencana JSON output (default <base>.pexels-plan.json)")
    ap.add_argument("--cache", default=os.path.expanduser("~/pexels-cache"),
                    help="direktori cache klip (default ~/pexels-cache)")
    ap.add_argument("--orientation", default="auto",
                    choices=["auto", "portrait", "landscape", "square"])
    ap.add_argument("--max-height", type=int, default=1920, help="cap tinggi klip (default 1920)")
    ap.add_argument("--per-page", type=int, default=15)
    ap.add_argument("--max-phases", type=int, default=0, help="0 = semua fase")
    ap.add_argument("--sleep", type=float, default=0.3, help="jeda antar-request (sopan)")
    ap.add_argument("--dry-run", action="store_true", help="cari+rencana saja, tanpa unduh")
    a = ap.parse_args()

    key = load_key()
    if not key:
        log("GAGAL: PEXELS_API_KEY kosong (set env atau ~/.config/pexels/credentials.env).")
        return 2
    if not os.path.isfile(a.blueprint):
        log(f"GAGAL: blueprint tak ada: {a.blueprint}")
        return 2

    bp = json.load(open(a.blueprint))
    phases = bp.get("phases", [])
    if not phases:
        log("GAGAL: blueprint tanpa 'phases'.")
        return 2

    hint = (bp.get("format", {}).get("orientation_hint")
            or bp.get("source", {}).get("aspect_ratio"))
    orientation = a.orientation if a.orientation != "auto" else ratio_to_orientation(hint)
    if a.max_phases > 0:
        phases = phases[:a.max_phases]

    os.makedirs(a.cache, exist_ok=True)
    log(f"orientasi={orientation} (dari '{hint}') · {len(phases)} fase · cache={a.cache}"
        + (" · DRY-RUN" if a.dry_run else ""))

    used_ids = set()
    out_phases = []
    attributions = []
    remaining = None
    errors = 0

    for i, p in enumerate(phases):
        sem = p.get("semantic")
        need = float(p.get("dur_sec") or max(0.0, (p.get("end", 0) - p.get("start", 0))))
        query = semantic_to_query(sem)
        entry = {"i": i, "start": p.get("start"), "end": p.get("end"),
                 "dur_sec": round(need, 2), "semantic": sem, "query": query,
                 "pexels_video_id": None, "local_path": None, "status": "empty"}
        try:
            videos, remaining = pexels_search(key, query, orientation, a.per_page)
            if not videos and query != DEFAULT_FALLBACK:
                # fallback query generik kalau semantic tak menghasilkan apa-apa
                entry["query_fallback"] = DEFAULT_FALLBACK
                videos, remaining = pexels_search(key, DEFAULT_FALLBACK, orientation, a.per_page)
            vid = pick_video(videos, need, used_ids)
            if not vid:
                log(f"  fase{i} '{query}': 0 hasil")
                out_phases.append(entry)
                continue
            used_ids.add(vid["id"])
            f = pick_file(vid, orientation, a.max_height)
            if not f:
                log(f"  fase{i} id={vid['id']}: tak ada file mp4 cocok")
                out_phases.append(entry)
                continue
            photographer = vid.get("user", {}).get("name")
            entry.update({
                "pexels_video_id": vid["id"], "pexels_url": vid.get("url"),
                "photographer": photographer, "clip_dur": vid.get("duration"),
                "file": {"w": f["width"], "h": f["height"], "fps": f.get("fps"),
                         "quality": f.get("quality"), "link": f["link"]},
                "status": "planned",
            })
            attributions.append({"video_id": vid["id"], "photographer": photographer,
                                 "url": vid.get("url")})
            if not a.dry_run:
                dest = os.path.join(a.cache, f"pexels_{vid['id']}_{f['height']}.mp4")
                if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                    entry["local_path"] = dest
                    entry["status"] = "cached"
                    log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} (cache)")
                else:
                    sz = download(f["link"], dest)
                    entry["local_path"] = dest
                    entry["status"] = "downloaded"
                    log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} "
                        f"{sz//1024}KB")
            else:
                log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} (dry)")
        except Exception as e:
            errors += 1
            entry["status"] = "error"
            entry["error"] = str(e)
            log(f"  fase{i} ERROR: {e}")
        out_phases.append(entry)
        time.sleep(a.sleep)

    plan = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_blueprint": os.path.abspath(a.blueprint),
        "aspect_ratio": hint, "orientation": orientation,
        "srt_file": bp.get("captions", {}).get("srt_file"),
        "bpm": bp.get("beat", {}).get("bpm"),
        "n_phases": len(out_phases),
        "pexels_ratelimit_remaining": remaining,
        "phases": out_phases,
        "attributions": attributions,
        "note": "Footage Pexels (lisensi bebas komersial, atribusi dianjurkan). "
                "Fidelitas struktural, bukan makna piksel.",
    }
    out = a.out or (re.sub(r"\.vn-blueprint\.json$", "", a.blueprint) + ".pexels-plan.json")
    json.dump(plan, open(out, "w"), ensure_ascii=False, indent=2)

    ok = sum(1 for e in out_phases if e["status"] in ("downloaded", "cached", "planned"))
    log(f"SELESAI: {ok}/{len(out_phases)} fase dapat klip · {errors} error · "
        f"sisa-kuota={remaining} · plan -> {out}")
    return 3 if errors and ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
