# Variasi template video-use

Tanpa ini tiap reel keluar identik (blurred-pad 9:16 + grade neutral + subtitle
bold-center). Katalog `vu_templates.py` memberi beberapa "look" siap pakai —
kombinasi **REFRAME** (aspek/komposisi) × **COLOR** (grade) × **SUBTITLE** — supaya
output bervariasi (bagus utk brand & algoritma) tanpa menulis filter ffmpeg manual.

## Katalog

| Template | Aspek | Untuk |
|---|---|---|
| `reels_blur` | 1080×1920 | Umum / b-roll / scenery — blurred-pad, frame penuh tak terpotong |
| `reels_zoom` | 1080×1920 | Talking-head / aksi — center-crop isi penuh (sisi terpotong) |
| `reels_topcap` | 1080×1920 | Kutipan / edukasi — video di atas + band gelap brand + caption besar |
| `feed_45` | 1080×1350 | IG feed (bukan reel) — 4:5 blurred-pad |
| `square_11` | 1080×1080 | Cover carousel / grid — 1:1 center-crop |
| `land_169` | 1920×1080 | YouTube / FB landscape — 16:9 dipertahankan + warm grade |

Asumsi sumber **landscape 16:9** (kasus umum YouTube): render.py meng-append
`grade` SETELAH `scale=1920:-2`, jadi reframe memproses 1920×1080.

## Pakai

```bash
python3 vu_templates.py list                       # lihat semua
python3 vu_templates.py suggest talking_head        # -> reels_zoom
python3 vu_templates.py rotate 2                     # anti-ulang: blur/zoom/topcap
python3 vu_templates.py apply edl.json reels_topcap  # inject grade + subtitle_style ke EDL
# lalu:
python3 helpers/render.py edl.json -o out.mp4 --build-subtitles --fps 30
```

`apply` mengisi dua field EDL: `grade` (reframe+warna) dan `subtitle_style`
(ASS force_style). Pilih manual, dari `suggest <content_type>`, atau `rotate <n>`
(putar reels_blur → reels_zoom → reels_topcap agar post beruntun tak seragam).

## Patch render.py (wajib utk variasi subtitle)

render.py upstream memakai `SUB_FORCE_STYLE` yang hardcoded. `vu_render_subtitle_patch.py`
menyisipkan override idempoten: bila EDL punya `subtitle_style`, itu dipakai.

```bash
# di RN7 (atau node mana pun yg punya video-use):
python3 vu_render_subtitle_patch.py ~/video-use/helpers/render.py
```

Idempoten + aman: tanpa field `subtitle_style`, perilaku default tak berubah.
Jalankan ulang setelah `git pull` video-use (clone publik menimpa patch).

## Teruji

`reels_topcap` + astra_h264 (range 55–59s) → render draft → **1080×1920**, master.srt
7 cue, subtitle style BIG (FontSize=22) terbaca. Reframe + patch subtitle terbukti E2E
(2026-10-04).
