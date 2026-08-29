#!/usr/bin/env python3
"""
stock_common.py — bagian bersama antar-fetcher footage stok (`pexels_fetch.py`,
`pixabay_fetch.py`). Dipisah 2026-08-29 (sebelumnya SEMANTIC_QUERY_MAP dkk
terduplikasi persis di `pexels_fetch.py` -- risiko drift kalau label semantic
analyzer berubah tapi cuma satu file yg diupdate). stdlib-only.
"""
import os
import re
import urllib.request

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


def download(url, dest):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "viral-pipeline/stock-fetch"})
    with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    return os.path.getsize(dest)
