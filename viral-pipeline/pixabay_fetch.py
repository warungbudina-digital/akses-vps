#!/usr/bin/env python3
"""
pixabay_fetch.py — jembatan IR/blueprint -> footage stok Pixabay.

Sama persis strukturnya dengan `pexels_fetch.py` (lihat file itu utk penjelasan
lengkap kenapa level FASE, fidelitas struktural, dst) -- provider KEDUA, cocok
dipakai sbg pelengkap/fallback saat Pexels tak dapat hasil bagus utk suatu
fase (query beda provider = peluang beda). Peta semantic->query DIPAKAI SAMA
dari `stock_common.py`, jadi hasil pencarian antar-provider tetap konsisten.

Beda teknis dari Pexels:
- Auth: `key` sbg QUERY PARAM (bukan header Authorization).
- Tak ada param `orientation` di API -- filter orientasi dilakukan client-side
  dari width/height tiap kualitas video (sama pola `pick_file` Pexels).
- Video hit punya 4 kualitas tetap: large/medium/small/tiny (bukan daftar
  video_files bebas) -- field `videos.<kualitas>.{url,width,height,size}`.
- TAK ADA header rate-limit di respons (beda dr Pexels x-ratelimit-remaining)
  -- limit didokumentasikan API Pixabay 100 req/menit, kami jaga via --sleep
  default lebih longgar drpd pexels_fetch (0.3 -> 0.7).
- Lisensi Pixabay: bebas komersial, TANPA WAJIB atribusi (beda Pexels yg
  "dianjurkan") -- tetap dicatat `attributions` utk jejak/etika.

stdlib-only (urllib) — tanpa pip. Kunci API dari env PIXABAY_API_KEY atau
~/.config/pixabay/credentials.env (chmod 600, JANGAN di repo).

Pemakaian:
  python3 pixabay_fetch.py <base>.vn-blueprint.json --out plan.json
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

from stock_common import (
    DEFAULT_FALLBACK,
    download,
    load_key as _load_key,
    make_log,
    pick_video,
    ratio_to_orientation,
    semantic_to_query,
)

API_BASE = "https://pixabay.com/api/videos/"
QUALITIES = ("large", "medium", "small", "tiny")  # urut besar->kecil

log = make_log("pixabay_fetch")


def load_key():
    return _load_key("PIXABAY_API_KEY", "~/.config/pixabay/credentials.env")


def pixabay_search(key, query, per_page):
    params = {"key": key, "q": query, "per_page": max(3, min(per_page, 200))}
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "viral-pipeline/pixabay_fetch"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("hits", [])


def pick_file(video, orientation, max_h):
    """Pilih 1 kualitas dari videos.{large,medium,small,tiny}: orientasi cocok,
    tinggi <= cap (ambil terbesar yg lolos cap; kalau tak ada yg lolos, ambil
    kualitas terkecil yg tersedia -- sama pola pick_file() Pexels."""
    files = []
    for q in QUALITIES:
        f = video.get("videos", {}).get(q)
        if f and f.get("width") and f.get("height") and f.get("url"):
            files.append(f)
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


def main():
    ap = argparse.ArgumentParser(description="IR/blueprint -> footage stok Pixabay per fase.")
    ap.add_argument("blueprint", help="path <base>.vn-blueprint.json")
    ap.add_argument("--out", help="path rencana JSON output (default <base>.pixabay-plan.json)")
    ap.add_argument("--cache", default=os.path.expanduser("~/pixabay-cache"),
                    help="direktori cache klip (default ~/pixabay-cache)")
    ap.add_argument("--orientation", default="auto",
                    choices=["auto", "portrait", "landscape", "square"])
    ap.add_argument("--max-height", type=int, default=1920, help="cap tinggi klip (default 1920)")
    ap.add_argument("--per-page", type=int, default=15, help="3-200 (batas API Pixabay)")
    ap.add_argument("--max-phases", type=int, default=0, help="0 = semua fase")
    ap.add_argument("--sleep", type=float, default=0.7,
                    help="jeda antar-request (Pixabay 100 req/menit, lebih ketat dr Pexels)")
    ap.add_argument("--dry-run", action="store_true", help="cari+rencana saja, tanpa unduh")
    a = ap.parse_args()

    key = load_key()
    if not key:
        log("GAGAL: PIXABAY_API_KEY kosong (set env atau ~/.config/pixabay/credentials.env).")
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
    errors = 0

    for i, p in enumerate(phases):
        sem = p.get("semantic")
        need = float(p.get("dur_sec") or max(0.0, (p.get("end", 0) - p.get("start", 0))))
        query = semantic_to_query(sem)
        entry = {"i": i, "start": p.get("start"), "end": p.get("end"),
                 "dur_sec": round(need, 2), "semantic": sem, "query": query,
                 "pixabay_video_id": None, "local_path": None, "status": "empty"}
        try:
            hits = pixabay_search(key, query, a.per_page)
            if not hits and query != DEFAULT_FALLBACK:
                # fallback query generik kalau semantic tak menghasilkan apa-apa
                entry["query_fallback"] = DEFAULT_FALLBACK
                hits = pixabay_search(key, DEFAULT_FALLBACK, a.per_page)
            vid = pick_video(hits, need, used_ids)
            if not vid:
                log(f"  fase{i} '{query}': 0 hasil")
                out_phases.append(entry)
                continue
            used_ids.add(vid["id"])
            f = pick_file(vid, orientation, a.max_height)
            if not f:
                log(f"  fase{i} id={vid['id']}: tak ada kualitas video cocok")
                out_phases.append(entry)
                continue
            photographer = vid.get("user")
            entry.update({
                "pixabay_video_id": vid["id"], "pixabay_url": vid.get("pageURL"),
                "photographer": photographer, "clip_dur": vid.get("duration"),
                "file": {"w": f["width"], "h": f["height"], "size": f.get("size"),
                         "link": f["url"]},
                "status": "planned",
            })
            attributions.append({"video_id": vid["id"], "photographer": photographer,
                                 "url": vid.get("pageURL")})
            if not a.dry_run:
                dest = os.path.join(a.cache, f"pixabay_{vid['id']}_{f['height']}.mp4")
                if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                    entry["local_path"] = dest
                    entry["status"] = "cached"
                    log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} (cache)")
                else:
                    sz = download(f["url"], dest)
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
        "phases": out_phases,
        "attributions": attributions,
        "note": "Footage Pixabay (lisensi bebas komersial, atribusi TAK wajib tapi dicatat). "
                "Fidelitas struktural, bukan makna piksel.",
    }
    out = a.out or (re.sub(r"\.vn-blueprint\.json$", "", a.blueprint) + ".pixabay-plan.json")
    json.dump(plan, open(out, "w"), ensure_ascii=False, indent=2)

    ok = sum(1 for e in out_phases if e["status"] in ("downloaded", "cached", "planned"))
    log(f"SELESAI: {ok}/{len(out_phases)} fase dapat klip · {errors} error · plan -> {out}")
    return 3 if errors and ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
