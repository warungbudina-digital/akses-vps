#!/usr/bin/env python3
"""vu_templates — katalog VARIASI TEMPLATE untuk video-use (helpers/render.py).

Kenapa: tanpa ini tiap reel keluar identik (blurred-pad 9:16 + grade neutral +
subtitle bold-center). Katalog ini memberi beberapa "look" siap pakai —
kombinasi REFRAME (aspek/komposisi) × COLOR (grade) × SUBTITLE style — supaya
output bervariasi (bagus utk brand & algoritma) tanpa menulis filter ffmpeg
manual tiap kali.

Cara kerja: semua REFRAME ditulis sebagai filter mentah yang DITEMPEL ke slot
EDL `grade` (render.py meng-append grade SETELAH `scale=1920:-2`, jadi input
reframe = 1920x1080 utk sumber landscape 16:9 — kasus umum YouTube). Variasi
subtitle lewat field EDL `subtitle_style` (perlu patch mini render.py; lihat
render-subtitle-style.patch). TAK mengubah arsitektur video-use.

Pakai:
  python3 vu_templates.py list
  python3 vu_templates.py apply <edl.json> <template> [-o out.json]
  python3 vu_templates.py suggest <content_type>     # -> nama template
  python3 vu_templates.py rotate <n>                 # -> template ke-n (anti-ulang)

Catatan: render.py ambil fps dari flag --fps (bukan EDL). Tiap template punya
`fps` sebagai saran; `apply` mencetak perintah render lengkap.
"""
import sys, json, argparse

# ---------- blok warna (grade) ----------
COLOR = {
    "punch": "eq=contrast=1.06:saturation=1.10:brightness=0.01",
    "warm":  "eq=saturation=1.05,colorbalance=rm=0.04:bm=-0.04",
    "clean": "eq=contrast=1.03",
    "none":  "",
}

# ---------- reframe core (input 1920x1080 dari scale render.py; TANPA setsar) ----------
# Blur latar = trik downscale→upscale (bilinear), BUKAN gblur: gblur sigma besar
# sangat lambat di ARM lemah (SD660 ~menit/klip). Scale-trick nyaris gratis + mirip.
_BLUR916 = ("split=2[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,scale=-2:240,scale=1080:1920[b];[fg]scale=1080:-2[f];"
            "[b][f]overlay=(W-w)/2:(H-h)/2")
_ZOOM916 = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
_TOPCAP  = "scale=1080:-2,pad=1080:1920:(ow-iw)/2:200:color=0x0E1116"
_FEED45  = ("split=2[bg][fg];[bg]scale=1080:1350:force_original_aspect_ratio=increase,"
            "crop=1080:1350,scale=-2:170,scale=1080:1350[b];[fg]scale=1080:-2[f];"
            "[b][f]overlay=(W-w)/2:(H-h)/2")
_SQ11    = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
_LAND169 = ""  # pertahankan 1920x1080

# ---------- gaya subtitle (ASS force_style; MarginV >=75 = safe-zone UI, jangan turun) ----------
SUB_BOLD = ("FontName=Helvetica,FontSize=18,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BackColour=&H00000000,BorderStyle=1,"
            "Outline=2,Shadow=0,Alignment=2,MarginV=90")
SUB_BIG  = ("FontName=Helvetica,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BackColour=&H00000000,BorderStyle=1,"
            "Outline=3,Shadow=0,Alignment=2,MarginV=80")


def _grade(reframe: str, color_key: str) -> str:
    parts = [p for p in (reframe, COLOR[color_key]) if p]
    return (",".join(parts) + ",setsar=1") if parts else "setsar=1"


TEMPLATES = {
    "reels_blur":   {"aspect": "1080x1920", "fps": 30, "subtitle_style": SUB_BOLD,
                     "grade": _grade(_BLUR916, "punch"),
                     "note": "9:16 blurred-pad. Umum/b-roll/scenery — frame penuh, tak ada yang terpotong."},
    "reels_zoom":   {"aspect": "1080x1920", "fps": 30, "subtitle_style": SUB_BOLD,
                     "grade": _grade(_ZOOM916, "punch"),
                     "note": "9:16 center-crop (isi penuh, tanpa bar). Talking-head/aksi — sisi terpotong."},
    "reels_topcap": {"aspect": "1080x1920", "fps": 30, "subtitle_style": SUB_BIG,
                     "grade": _grade(_TOPCAP, "clean"),
                     "note": "9:16 video di atas + band gelap brand di bawah + caption besar. Kutipan/edukasi."},
    "feed_45":      {"aspect": "1080x1350", "fps": 30, "subtitle_style": SUB_BOLD,
                     "grade": _grade(_FEED45, "clean"),
                     "note": "4:5 blurred-pad. Untuk IG feed (bukan reel) — makan lebih banyak layar."},
    "square_11":    {"aspect": "1080x1080", "fps": 30, "subtitle_style": SUB_BOLD,
                     "grade": _grade(_SQ11, "clean"),
                     "note": "1:1 center-crop. Cover carousel / grid."},
    "land_169":     {"aspect": "1920x1080", "fps": 30, "subtitle_style": SUB_BOLD,
                     "grade": _grade(_LAND169, "warm"),
                     "note": "16:9 dipertahankan + warm grade. Untuk YouTube / FB landscape."},
}

# konten -> template yang pas
SUGGEST = {
    "talking_head": "reels_zoom", "wajah": "reels_zoom", "interview": "reels_zoom",
    "quote": "reels_topcap", "kutipan": "reels_topcap", "edukasi": "reels_topcap",
    "explainer": "reels_topcap", "text": "reels_topcap",
    "broll": "reels_blur", "scenery": "reels_blur", "aksi": "reels_blur", "demo": "reels_blur",
    "feed": "feed_45", "carousel": "square_11", "cover": "square_11", "grid": "square_11",
    "landscape": "land_169", "youtube": "land_169", "fb": "land_169",
}
# urutan rotasi anti-ulang utk reel vertikal
ROTATE = ["reels_blur", "reels_zoom", "reels_topcap"]


def apply_template(edl_path: str, name: str, out_path: str | None) -> None:
    if name not in TEMPLATES:
        sys.exit(f"template tak dikenal: {name}. Tersedia: {', '.join(TEMPLATES)}")
    t = TEMPLATES[name]
    edl = json.loads(open(edl_path).read())
    edl["grade"] = t["grade"]
    edl["subtitle_style"] = t["subtitle_style"]
    out = out_path or edl_path
    with open(out, "w") as f:
        json.dump(edl, f, indent=2, ensure_ascii=False)
    print(f"✓ template '{name}' ({t['aspect']}) diterapkan ke {out}")
    print(f"  {t['note']}")
    print(f"  render: python3 helpers/render.py {out} -o out.mp4 --build-subtitles --fps {t['fps']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Katalog variasi template video-use")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    a = sub.add_parser("apply"); a.add_argument("edl"); a.add_argument("template"); a.add_argument("-o", "--output")
    s = sub.add_parser("suggest"); s.add_argument("content_type")
    r = sub.add_parser("rotate"); r.add_argument("n", type=int)
    args = ap.parse_args()

    if args.cmd == "list":
        for n, t in TEMPLATES.items():
            print(f"{n:13s} {t['aspect']:>9s}  {t['note']}")
    elif args.cmd == "apply":
        apply_template(args.edl, args.template, args.output)
    elif args.cmd == "suggest":
        print(SUGGEST.get(args.content_type.lower(), "reels_blur"))
    elif args.cmd == "rotate":
        print(ROTATE[args.n % len(ROTATE)])
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
