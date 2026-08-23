#!/usr/bin/env python3
"""
figma_to_canva.py — jembatan headless Figma -> Canva.

KENAPA INI ADA: app mobile Figma resmi (`com.figma.mirror`, "View, Comment &
Mirror") TIDAK BISA mengedit desain sama sekali — cuma lihat/komentar/mirror
(dikonfirmasi langsung 2026-08-23, lihat memori `project_figma_api_key`).
Editing sungguhan cuma bisa di Canva (app yang memang punya tool lengkap) atau
Figma desktop/browser. Script ini otomatiskan sisi Figma+transfer device dari
pipeline "convert Figma -> Canva" yang sudah terbukti manual sebelumnya:

    Figma REST API --(export gambar)--> crop per-elemen --(adb push)--> RN7

Sisi Canva (upload + "Buka di editor") masih perlu automasi UI terpisah
(lihat CANVA_STEPS di bawah dan tool-appium/docs/figma-to-canva-pipeline.md)
karena Canva TIDAK punya API upload publik untuk akun personal/tim biasa.

Prasyarat:
  - Token Figma personal access token di ~/.config/figma/warungbudina_api-key.txt
    (scope minimal: file_content:read, file_metadata:read)
  - `pip install requests pillow`
  - adb terhubung ke device tujuan (default RN7 lavender, 10.66.66.6:5555)

Contoh pakai:
  # Grid rata eksplisit (PALING ANDAL) -- file 7-frame carousel jadi 7 crop:
  python3 figma_to_canva.py "https://www.figma.com/buzz/1uwIvuxXnOx9SBxNkHxOMW/..." \\
      --cols 7 --rows 1 --name aiviral

  # Auto-detect kolom (fallback, TAK dijamin akurat utk layout kompleks):
  python3 figma_to_canva.py 1uwIvuxXnOx9SBxNkHxOMW --name motivasi

  # Cuma render+crop, jangan push ke device (mis. mau upload manual/cek dulu):
  python3 figma_to_canva.py <file_key> --no-push --out ./preview
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image

TOKEN_PATH = Path.home() / ".config" / "figma" / "warungbudina_api-key.txt"
API = "https://api.figma.com/v1"
DEFAULT_SERIAL = "10.66.66.6:5555"       # RN7 lavender, adb-over-WireGuard permanen
DEFAULT_PUSH_DIR = "/sdcard/DCIM/Camera"  # biar muncul di album "Camera" Canva picker

# Ringkasan sisi Canva (manual atau lanjutan automasi terpisah) -- koordinat
# persis ada di tool-appium/docs/canva-automation-map.md, sengaja TIDAK
# di-hardcode di sini karena UI Canva context-sensitive & rawan drift versi.
CANVA_STEPS = """
Langkah sisi Canva (RN7), setelah gambar ter-push ke device:
  1. Buka Canva -> tab "Unggahan" (bottom nav, sudah dipetakan di
     canva-automation-map.md) -> tombol "Unggah file".
  2. Pilih media -> album "Camera" (BUKAN "File terbaru", rawan kepilih
     screenshot lain -- lihat jebakan di project_figma_api_key memori).
  3. Multi-select semua file `<name>-partN.png` yang baru di-push -> centang.
  4. Tunggu toast "N item berhasil diunggah" -> masuk folder "Unggahan".
  5. Tiap gambar -> tap preview -> tombol "Buka di editor" -> Canva bikin
     desain baru berisi gambar itu sbg elemen, siap diedit (resize/tambah
     elemen/teks lain via toolbar Ganti/Pilih/Sesuaikan/Alat Gambar).
"""


def load_token() -> str:
    if not TOKEN_PATH.exists():
        sys.exit(f"Token Figma tak ditemukan di {TOKEN_PATH}")
    return TOKEN_PATH.read_text().strip()


def parse_file_key(url_or_key: str) -> str:
    """Terima link penuh figma.com/file|design|buzz/<key>/... atau bare key."""
    m = re.search(r"figma\.com/(?:file|design|buzz)/([a-zA-Z0-9]+)", url_or_key)
    return m.group(1) if m else url_or_key.strip()


def get_meta(key: str, token: str) -> dict:
    r = requests.get(f"{API}/files/{key}/meta", headers={"X-Figma-Token": token}, timeout=20)
    r.raise_for_status()
    return r.json().get("file", {})


def fetch_composite_png(key: str, node: str, token: str, scale: int) -> bytes:
    r = requests.get(
        f"{API}/images/{key}",
        params={"ids": node, "format": "png", "scale": scale},
        headers={"X-Figma-Token": token},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("err"):
        raise RuntimeError(f"Figma /v1/images error: {data['err']}")
    img_url = (data.get("images") or {}).get(node)
    if not img_url:
        raise RuntimeError(
            f"Node '{node}' tak ada di respons images ({data}). "
            "Coba node lain (mis. --node 0:2) atau screenshot manual dari browser."
        )
    img_r = requests.get(img_url, timeout=60)
    img_r.raise_for_status()
    return img_r.content


def crop_grid(img: Image.Image, cols: int, rows: int, pad: int) -> list[Image.Image]:
    """Potong rata cols x rows -- ANDAL untuk carousel/kartu berjajar rapi."""
    w, h = img.size
    cell_w, cell_h = w // cols, h // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            box = (
                max(0, c * cell_w - pad),
                max(0, r * cell_h - pad),
                min(w, (c + 1) * cell_w + pad),
                min(h, (r + 1) * cell_h + pad),
            )
            out.append(img.crop(box))
    return out


def detect_bg_color(px, w: int, h: int) -> tuple[int, int, int]:
    """Tebak warna background dari 4 sudut (mayoritas) -- BUKAN asumsi putih,
    krn banyak file Figma (mis. Buzz) pakai kanvas gelap/hitam."""
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    # ambil yg paling sering muncul; kalau semua beda, pakai sudut kiri-atas
    return max(set(corners), key=corners.count)


def autocrop_columns(img: Image.Image, bg_thresh: int, pad: int) -> list[Image.Image]:
    """
    Deteksi otomatis kolom non-background: warna bg ditebak dari 4 sudut
    gambar (adaptif, bukan asumsi putih), lalu kolom dianggap 'berisi' kalau
    ADA pixel yg beda cukup jauh (--bg-thresh = ambang jarak channel maks)
    dari warna bg itu. TERBUKTI jalan utk kasus sederhana (2 kartu berdampingan
    di kanvas hitam, lihat project_figma_api_key) tapi TAK DIJAMIN akurat utk
    layout kompleks (overlap, elemen nempel tepi, background gradient/non-solid)
    -- kalau hasil aneh (crop kepotong/kegabung), pakai --cols/--rows eksplisit.
    """
    w, h = img.size
    rgb = img.convert("RGB")
    px = rgb.load()
    bg = detect_bg_color(px, w, h)
    tol = 255 - bg_thresh  # --bg-thresh tinggi (default 250) -> toleransi ketat (5)
    col_has_content = []
    for x in range(w):
        has_content = False
        for y in range(0, h, max(1, h // 200)):  # sample tiap ~0.5% tinggi, cukup cepat
            r, g, b = px[x, y]
            if abs(r - bg[0]) > tol or abs(g - bg[1]) > tol or abs(b - bg[2]) > tol:
                has_content = True
                break
        col_has_content.append(has_content)

    boxes = []
    in_box = False
    start = 0
    for x, has in enumerate(col_has_content + [False]):
        if has and not in_box:
            start = x
            in_box = True
        elif not has and in_box:
            boxes.append((max(0, start - pad), 0, min(w, x + pad), h))
            in_box = False

    if not boxes:
        raise RuntimeError(
            "Auto-detect kolom tak menemukan elemen apa pun -- pakai --cols/--rows eksplisit."
        )
    return [img.crop(b) for b in boxes]


def adb_push(files: list[Path], serial: str, dest: str) -> None:
    for f in files:
        remote = f"{dest}/{f.name}"
        subprocess.run(["adb", "-s", serial, "push", str(f), remote], check=True)
        subprocess.run(
            [
                "adb", "-s", serial, "shell", "am", "broadcast",
                "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file://{remote}",
            ],
            check=True,
        )
        print(f"  -> pushed & media-scanned: {remote}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("figma_url_or_key", help="Link Figma penuh atau file key mentah")
    ap.add_argument("--node", default="0:1", help="Node id di-export (default '0:1' = root/page, trik generik)")
    ap.add_argument("--scale", type=int, default=2, help="Skala render PNG (default 2x, makin tinggi makin tajam+besar)")
    ap.add_argument("--cols", type=int, default=None, help="Jumlah kolom grid-crop eksplisit (paling andal)")
    ap.add_argument("--rows", type=int, default=1, help="Jumlah baris grid-crop eksplisit (dipakai bareng --cols)")
    ap.add_argument("--bg-thresh", type=int, default=250, help="Ambang deteksi background utk auto-crop (0-255, default 250)")
    ap.add_argument("--pad", type=int, default=6, help="Padding px tiap crop (default 6)")
    ap.add_argument("--name", default="figma-export", help="Prefix nama file output, mis. 'motivasi' -> motivasi-part1.png dst")
    ap.add_argument("--out", default="/tmp/figma-to-canva", help="Folder kerja lokal (hub)")
    ap.add_argument("--serial", default=DEFAULT_SERIAL, help=f"adb serial tujuan (default {DEFAULT_SERIAL} = RN7)")
    ap.add_argument("--push-dir", default=DEFAULT_PUSH_DIR, help=f"Folder tujuan di device (default {DEFAULT_PUSH_DIR})")
    ap.add_argument("--no-push", action="store_true", help="Cuma render+crop lokal, jangan adb push")
    args = ap.parse_args()

    token = load_token()
    key = parse_file_key(args.figma_url_or_key)
    print(f"[1/4] File key: {key}")

    try:
        meta = get_meta(key, token)
        print(f"      name={meta.get('name')!r} editorType={meta.get('editor_type')}")
    except requests.HTTPError as e:
        print(f"      WARN: /meta gagal ({e}) -- lanjut coba /images langsung.")

    print(f"[2/4] Fetch composite PNG (node={args.node}, scale={args.scale}x)...")
    png_bytes = fetch_composite_png(key, args.node, token, args.scale)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    composite_path = out_dir / f"{args.name}-composite.png"
    composite_path.write_bytes(png_bytes)
    img = Image.open(composite_path)
    print(f"      composite: {composite_path} ({img.size[0]}x{img.size[1]})")

    print(f"[3/4] Crop jadi elemen individual...")
    if args.cols:
        crops = crop_grid(img, args.cols, args.rows, args.pad)
        print(f"      grid-crop {args.cols}x{args.rows} -> {len(crops)} bagian")
    else:
        crops = autocrop_columns(img, args.bg_thresh, args.pad)
        print(f"      auto-detect kolom -> {len(crops)} bagian (verifikasi manual dianjurkan)")

    out_files = []
    for i, c in enumerate(crops, 1):
        p = out_dir / f"{args.name}-part{i}.png"
        c.save(p)
        out_files.append(p)
        print(f"      part{i}: {p} ({c.size[0]}x{c.size[1]})")

    if args.no_push:
        print("[4/4] --no-push diset, lewati adb push.")
    else:
        print(f"[4/4] adb push ke {args.serial}:{args.push_dir} ...")
        adb_push(out_files, args.serial, args.push_dir)

    print("\nSelesai. Lanjut sisi Canva (manual/UI-automation terpisah):")
    print(CANVA_STEPS)


if __name__ == "__main__":
    main()
