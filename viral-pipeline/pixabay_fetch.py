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
    ClipTooLargeError,
    DEFAULT_FALLBACK,
    DiskGuardError,
    PER_CLIP_CAP_MB,
    download,
    load_key as _load_key,
    load_queries_file,
    make_log,
    parse_exclude_ids,
    pick_video,
    ratio_to_orientation,
    resolve_query,
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
    ap.add_argument("--queries-file", help="path JSON override query manual per fase "
                     '{"<idx 0-based>": "keyword", ...} -- menang atas semantic_to_query() otomatis')
    ap.add_argument("--phases", help="indeks fase 0-based dipisah koma utk dibatasi run ini "
                     '(mis. "3,7,12") -- default semua fase di blueprint')
    ap.add_argument("--exclude-ids", help="video id dipisah koma utk DIHINDARI (dedup lintas-"
                     "panggilan -- manual_fetch_api.py isi ini dari master plan sblm tiap chunk)")
    a = ap.parse_args()

    overrides = load_queries_file(a.queries_file) if a.queries_file else {}
    phase_filter = set(int(x) for x in a.phases.split(",")) if a.phases else None

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

    used_ids = parse_exclude_ids(a.exclude_ids)
    out_phases = []
    attributions = []
    errors = 0

    for i, p in enumerate(phases):
        if phase_filter is not None and i not in phase_filter:
            continue
        sem = p.get("semantic")
        need = float(p.get("dur_sec") or max(0.0, (p.get("end", 0) - p.get("start", 0))))
        is_override = i in overrides
        query = resolve_query(sem, i, overrides)
        entry = {"i": i, "start": p.get("start"), "end": p.get("end"),
                 "dur_sec": round(need, 2), "semantic": sem, "query": query,
                 "query_is_override": is_override,
                 "pixabay_video_id": None, "local_path": None, "status": "empty"}
        skip_too_large = set()  # id video yg kelebihan cap/tanpa kualitas cocok, DI FASE INI SAJA
        placed = False
        try:
            hits = pixabay_search(key, query, a.per_page)
            if not hits and query != DEFAULT_FALLBACK:
                if is_override:
                    log(f"  fase{i} override '{query}': 0 hasil (tak di-fallback)")
                    out_phases.append(entry)
                    continue
                # fallback query generik kalau semantic tak menghasilkan apa-apa
                entry["query_fallback"] = DEFAULT_FALLBACK
                hits = pixabay_search(key, DEFAULT_FALLBACK, a.per_page)
            if not hits:
                log(f"  fase{i} '{query}': 0 hasil")
                out_phases.append(entry)
                continue

            # Coba kandidat berturut-turut: ClipTooLargeError -> klip INI dilewati,
            # cari video lain (BUKAN hentikan fase) -- sama pola pexels_fetch.py.
            while True:
                vid = pick_video(hits, need, used_ids | skip_too_large)
                if not vid or vid["id"] in skip_too_large:
                    break
                f = pick_file(vid, orientation, a.max_height)
                if not f:
                    skip_too_large.add(vid["id"])
                    continue
                photographer = vid.get("user")
                file_entry = {"w": f["width"], "h": f["height"], "size": f.get("size"), "link": f["url"]}
                if a.dry_run:
                    entry.update({"pixabay_video_id": vid["id"], "pixabay_url": vid.get("pageURL"),
                                  "photographer": photographer, "clip_dur": vid.get("duration"),
                                  "file": file_entry, "status": "planned"})
                    attributions.append({"video_id": vid["id"], "photographer": photographer,
                                         "url": vid.get("pageURL")})
                    used_ids.add(vid["id"])
                    log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} (dry)")
                    placed = True
                    break
                dest = os.path.join(a.cache, f"pixabay_{vid['id']}_{f['height']}.mp4")
                try:
                    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                        sz, status = os.path.getsize(dest), "cached"
                    else:
                        sz, status = download(f["url"], dest), "downloaded"
                except ClipTooLargeError as e:
                    skip_too_large.add(vid["id"])
                    log(f"  fase{i} id={vid['id']} {f['height']}p: {e} -- coba kandidat lain")
                    continue
                entry.update({"pixabay_video_id": vid["id"], "pixabay_url": vid.get("pageURL"),
                              "photographer": photographer, "clip_dur": vid.get("duration"),
                              "file": file_entry, "local_path": dest, "status": status})
                attributions.append({"video_id": vid["id"], "photographer": photographer,
                                     "url": vid.get("pageURL")})
                used_ids.add(vid["id"])
                log(f"  fase{i} '{query}' -> id={vid['id']} {f['width']}x{f['height']} "
                    f"{sz//1024}KB ({status})")
                placed = True
                break

            if not placed:
                if skip_too_large:
                    entry["status"] = "too_large"
                    entry["error"] = f"{len(skip_too_large)} kandidat dilewati (semua > cap {PER_CLIP_CAP_MB}MB)"
                    log(f"  fase{i} '{query}': {entry['error']}")
                else:
                    log(f"  fase{i} '{query}': tak ada kandidat cocok")
        except DiskGuardError as e:
            entry["status"] = "disk_guard"
            entry["error"] = str(e)
            log(f"  fase{i} DISK GUARD: {e} -- hentikan sisa fase run ini")
            out_phases.append(entry)
            break
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
