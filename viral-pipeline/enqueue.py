#!/usr/bin/env python3
"""enqueue.py — masukkan URL video berkategori ke antrean media.video_ingest (DB-VPS).

Jalan di akses-vps (gateway ke DB-VPS via `ssh db-vps`). Auto-deteksi platform +
external_id dari URL. Dedup lewat UNIQUE(source_url) + ON CONFLICT DO NOTHING.
Dipakai integrasi browser (hulu) atau manual.

  enqueue.py <category> <url> [<url> ...]      # N url, satu kategori
  cat list.txt | enqueue.py --stdin            # tiap baris: "<category> <url>"

category: viral_video | menuju_viral_video
"""
import sys, re, subprocess, argparse
from urllib.parse import urlparse, parse_qs

DBVPS = "db-vps"
CATS  = {"viral_video", "menuju_viral_video"}

def detect(url):
    """(platform, external_id) best-effort dari URL. external_id boleh kosong
    (dedup utama tetap source_url)."""
    u = urlparse(url)
    host = u.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    path, q = u.path, parse_qs(u.query)
    if "youtu.be" in host:
        return "youtube", path.strip("/").split("/")[0]
    if "youtube.com" in host:
        if q.get("v"): return "youtube", q["v"][0]
        m = re.search(r"/(?:shorts|embed|live)/([^/?&]+)", path)
        return "youtube", (m.group(1) if m else "")
    if "facebook.com" in host or "fb.watch" in host:
        if q.get("v"): return "facebook", q["v"][0]
        m = re.search(r"/(?:reel|videos|watch)/(\d+)", path) or re.search(r"(\d{6,})", path)
        return "facebook", (m.group(1) if m else "")
    if "instagram.com" in host:
        m = re.search(r"/(?:reel|reels|p|tv)/([^/?&]+)", path)
        return "instagram", (m.group(1) if m else "")
    if "tiktok.com" in host:
        m = re.search(r"/video/(\d+)", path)
        return "tiktok", (m.group(1) if m else "")
    return "", ""

def esc(s):
    return s.replace("'", "''")

def lit(s):
    return "NULL" if not s else "'" + esc(s) + "'"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category", nargs="?")
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--stdin", action="store_true", help="baca '<category> <url>' per baris dari stdin")
    ap.add_argument("--dry-run", action="store_true", help="tampilkan deteksi, jangan insert")
    a = ap.parse_args()

    rows = []
    if a.stdin:
        for ln in sys.stdin:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split(None, 1)
            if len(parts) != 2:
                print("lewati (format salah):", ln); continue
            rows.append((parts[0], parts[1]))
    else:
        if not a.category or not a.urls:
            ap.error("butuh <category> <url> ... (atau --stdin)")
        rows = [(a.category, u) for u in a.urls]

    bad = sorted({c for c, _ in rows if c not in CATS})
    if bad:
        sys.exit(f"kategori tak valid: {bad} (harus salah satu: {sorted(CATS)})")
    if not rows:
        print("tak ada URL."); return

    vals = []
    for cat, url in rows:
        plat, eid = detect(url)
        print(f"  [{cat}] {plat or '?'}:{eid or '?'}  {url[:64]}")
        vals.append(f"('{esc(cat)}',{lit(plat)},'{esc(url)}',{lit(eid)},'browser')")

    if a.dry_run:
        print(f"[dry-run] {len(rows)} URL (tak di-insert).")
        return

    sql = ("INSERT INTO media.video_ingest (category,platform,source_url,external_id,enqueued_by) VALUES "
           + ", ".join(vals) + " ON CONFLICT (source_url) DO NOTHING RETURNING id;")
    # -q (quiet): tekan tag status perintah ("INSERT 0 N") agar TIDAK ikut ke stdout —
    # tanpa ini token digit dari "INSERT 0 N" mencemari hitungan (id RETURNING saja yang boleh).
    r = subprocess.run(["ssh", DBVPS, "sudo -n -u postgres psql -d scraper -tAq"],
                       input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("enqueue gagal: " + r.stderr.strip()[:300])
    inserted = [x for x in r.stdout.split() if x.strip().isdigit()]
    print(f"ENQUEUE: {len(rows)} diminta -> {len(inserted)} baru, {len(rows) - len(inserted)} duplikat/skip.")

if __name__ == "__main__":
    main()
