#!/usr/bin/env python3
"""
stock_common.py — bagian bersama antar-fetcher footage stok (`pexels_fetch.py`,
`pixabay_fetch.py`). Dipisah 2026-08-29 (sebelumnya SEMANTIC_QUERY_MAP dkk
terduplikasi persis di `pexels_fetch.py` -- risiko drift kalau label semantic
analyzer berubah tapi cuma satu file yg diupdate). stdlib-only.
"""
import json
import os
import re
import urllib.request

# (2026-11-04) Disk hub pernah 97% penuh krn cache klip stok tak pernah
# dihapus (lihat plan crispy-mapping-cherny.md) -- guard baru utk alur
# manual-fetch: DISK_FLOOR_MB di atas RAW_MIN_DISK_MB=500 orchestrator.py,
# PER_CLIP_CAP_MB krn cache sudah punya outlier nyata hingga 671MB.
DISK_FLOOR_MB = 700
PER_CLIP_CAP_MB = 200


class DiskGuardError(Exception):
    """Disk hub nyaris penuh (di bawah DISK_FLOOR_MB) -- HARUS hentikan
    seluruh run (fase lain pun tak akan muat), beda dari ClipTooLargeError."""


class ClipTooLargeError(Exception):
    """1 klip tunggal melampaui PER_CLIP_CAP_MB -- klip ini SAJA dilewati,
    pemanggil (pexels_fetch.py/pixabay_fetch.py) harus coba kandidat lain,
    BUKAN hentikan fase/run (beda dari DiskGuardError)."""

# CLIP zero-shot semantic (analyzer semantic.py) -> query stok yang searchable.
# Label CLIP kadang aneh utk pencarian stok -> dipetakan ke kata kunci b-roll.
# Dipakai SAMA oleh semua provider (Pexels/Pixabay/dst) -- kalau analyzer
# nambah/ubah label, cukup update di SINI, bukan per-file provider.
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


def make_log(tag):
    """log = make_log('pexels_fetch') -> log('pesan') cetak '[pexels_fetch] pesan' ke stderr."""
    import sys

    def log(*a):
        print("[%s]" % tag, *a, file=sys.stderr)

    return log


def load_key(env_var, cred_path):
    """Kunci dari env dulu, lalu file credentials.env (baris `ENV_VAR=nilai`)."""
    k = os.environ.get(env_var, "").strip()
    if k:
        return k
    cred_path = os.path.expanduser(cred_path)
    if os.path.isfile(cred_path):
        prefix = env_var + "="
        for line in open(cred_path):
            line = line.strip()
            if line.startswith(prefix):
                return line[len(prefix):].strip().strip('"').strip("'")
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


def resolve_query(sem, i, overrides=None):
    """Override manual (keyed by indeks fase 0-based) menang atas
    semantic_to_query() otomatis. overrides=None/{} -> identik perilaku lama."""
    if overrides and i in overrides:
        return overrides[i]
    return semantic_to_query(sem)


def load_queries_file(path):
    """Baca override query manual: JSON {"<idx>": "keyword", ...} -> {int: str}.
    Validasi (panjang, strip, buang kosong) disatukan di sini -- bukan dobel
    di pexels_fetch.py/pixabay_fetch.py, alasan modul ini dipisah 2026-08-29."""
    if not path or not os.path.isfile(path):
        return {}
    data = json.load(open(path))
    out = {}
    for k, v in data.items():
        v = (v or "").strip()
        if v:
            out[int(k)] = v[:200]
    return out


def disk_avail_mb(path="/"):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize // (1024 * 1024)


def parse_exclude_ids(raw):
    """'123,456' -> {123,456} -- dipakai --exclude-ids CLI biar dedup
    used_ids tetap jalan LINTAS-CHUNK (manual_fetch_api.py panggil fetcher
    per chunk 5 fase, proses baru = used_ids kosong tiap panggilan; tanpa
    ini klip yg sama kepilih berulang utk fase2 beda semantic yg sama)."""
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}


def pick_video(videos, need_dur, used_ids):
    """Pilih klip: durasi >= kebutuhan (paling pas/pendek), hindari id terpakai.
    Generik lintas provider -- Pexels & Pixabay sama2 punya 'id'+'duration' per hit."""
    fresh = [v for v in videos if v.get("id") not in used_ids] or videos
    fit = [v for v in fresh if (v.get("duration") or 0) >= need_dur]
    if fit:
        return min(fit, key=lambda v: v.get("duration", 0))
    if fresh:
        return max(fresh, key=lambda v: v.get("duration", 0))
    return None


def download(url, dest, disk_floor_mb=DISK_FLOOR_MB, per_clip_cap_mb=PER_CLIP_CAP_MB):
    """Unduh ke <dest>.part lalu rename atomik. Guard disk DUA lapis: (1)
    Content-Length (kalau server kirim) dicek SEBELUM nulis byte apa pun;
    (2) selama streaming, cek ulang tiap chunk -- server kadang tak kirim
    Content-Length, dan klip nyata di cache pernah 671MB (jauh di atas
    perkiraan awal puluhan MB). Exception apa pun (termasuk DiskGuardError)
    menghapus .part yg nyangkut sebelum re-raise -- tanpa ini, error
    kehabisan disk di tengah stream nyisakan .part yg makan disk yg sama.
    ClipTooLargeError (klip > cap) vs DiskGuardError (disk hub < floor) BEDA
    SENGAJA -- pemanggil harus coba kandidat lain utk yg pertama, hentikan
    run penuh utk yg kedua (lihat definisi masing-masing kelas di atas)."""
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "viral-pipeline/stock-fetch"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            try:
                clen_mb = int(r.headers.get("Content-Length") or 0) / (1024 * 1024)
            except (TypeError, ValueError):
                clen_mb = 0
            if clen_mb > per_clip_cap_mb:
                raise ClipTooLargeError(f"klip {clen_mb:.0f}MB > cap {per_clip_cap_mb}MB")
            if disk_avail_mb() - clen_mb < disk_floor_mb:
                raise DiskGuardError(f"disk hub tersisa {disk_avail_mb()}MB, di bawah floor {disk_floor_mb}MB")
            written = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if written > per_clip_cap_mb * 1024 * 1024:
                        raise ClipTooLargeError(f"klip > cap {per_clip_cap_mb}MB saat streaming")
                    if disk_avail_mb() < disk_floor_mb:
                        raise DiskGuardError(f"disk hub < floor {disk_floor_mb}MB saat streaming, dihentikan")
    except Exception:
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise
    os.replace(tmp, dest)
    return os.path.getsize(dest)
