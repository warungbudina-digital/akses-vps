# Peta kapabilitas Figma REST API — apa yang BENAR-BENAR bisa ditulis/diedit via script

> Dipetakan 2026-08-23 via pengujian LANGSUNG ke `api.figma.com` (bukan baca dokumentasi doang — tiap klaim "bisa"/"tidak bisa" di bawah dibuktikan lewat panggilan API nyata pakai token `akses-vps-full-access`, 14/14 scope PAT maksimal yang Figma tawarkan). Lihat memori Claude [[project_figma_api_key]] utk riwayat token.

## Kesimpulan inti (baca ini dulu)

**Figma REST API TIDAK PUNYA endpoint apa pun untuk mengedit konten desain** — tidak ada cara membuat/memindah/resize/reshape/ganti-warna/ganti-teks elemen di kanvas lewat HTTP call, walau token py scope maksimal. Ini **bukan batasan token/scope**, tapi memang begitu arsitektur resmi Figma: satu-satunya jalan memanipulasi node/layer secara programatik adalah **Figma Plugin API** (kode JS/TS yang jalan DI DALAM sesi editor Figma yang sedang terbuka — Desktop app atau tab browser figma.com — dipicu manual via menu "Plugins > Run", bukan dipanggil headless dari luar).

**Jadi untuk "editing kreatif via AI/script":**
- ✅ **BISA** (dibuktikan langsung, lihat tabel §1): komentar/anotasi, lampiran dev-resource, render gambar, baca metadata/versi, webhook reaktif.
- ❌ **TIDAK BISA** lewat REST API sama sekali: ubah teks, pindah/resize shape, ganti warna, tambah elemen baru, apa pun yang menyentuh isi kanvas.
- 🟡 **Kemungkinan bisa, TAPI TERKUNCI di akun ini**: Variables API (§2) — endpointnya ADA (dikonfirmasi respons 403 spesifik, bukan 404), tapi butuh scope `file_variables:read`/`write` yang **tidak ditawarkan sama sekali** di form generate token akun ini (kemungkinan fitur/plan-gated, belum dikonfirmasi pasti kenapa).
- 🔴 Kalau memang butuh editing kanvas sungguhan via otomasi: satu-satunya jalan realistis adalah **pipeline gambar Figma→Canva yang sudah dibuat** ([[project_figma_api_key]], `figma_to_canva.py`) — karena Canva PUNYA tool editing lengkap, Figma API tidak.

## §1. Yang TERBUKTI bisa ditulis/dipakai (live-tested 2026-08-23)

| Kemampuan | Endpoint | Bukti | Script |
|---|---|---|---|
| **Tambah komentar** (anotasi/review kreatif dari AI) | `POST /v1/files/:key/comments` | Live: `id=1895966864` & `1895967090` berhasil dibuat, HTTP 200 | `figma_comment.py add` |
| **Hapus komentar** | `DELETE /v1/files/:key/comments/:id` | Live: HTTP 200, hilang dari `list` sesudahnya | `figma_comment.py delete` |
| **Baca komentar** | `GET /v1/files/:key/comments` | Live: balikin array `comments[]` | `figma_comment.py list` |
| **Render gambar** (fondasi pipeline Canva) | `GET /v1/images/:key?ids=&format=png` | Live: composite 5760×3120 dari file Buzz | `figma_to_canva.py` |
| **Baca metadata file** | `GET /v1/files/:key/meta` | Live: nama+editorType balik benar, termasuk file Buzz yg `/v1/files` biasa ditolak | `figma_to_canva.py` |
| Baca versi file | `GET /v1/files/:key/versions` | Scope `file_versions:read` dimiliki, belum di-live-test tapi scope terkonfirmasi ada | — belum ada script |
| Tulis link dev-resource ke node | `POST /v1/files/:key/dev_resources` | Scope `file_dev_resources:write` dimiliki; GET percobaan balik 404 utk file Buzz ini (kemungkinan tipe file tak didukung, BUKAN scope — belum dikonfirmasi di file desain biasa) | — belum ada script |
| Kelola webhook (trigger reaktif) | `POST/GET/DELETE /v2/webhooks` | Scope `webhooks:read`+`webhooks:write` dimiliki, belum di-live-test (butuh `team_id`, belum diuji sesi ini) | — belum ada script |

**Ide pakai nyata dari yang TERBUKTI di atas:** bikin AI reviewer yang baca file desain (via `/v1/images` utk "lihat" visualnya, kirim ke model vision), lalu **tulis kritik/saran sebagai komentar Figma** via `figma_comment.py add` — ini genuinely "editing kreatif dari AI" dalam bentuk anotasi, bukan mengubah desain langsung, tapi tetap value nyata utk workflow review/QA desain otomatis.

## §2. Yang ADA endpoint-nya tapi TERKUNCI di akun ini

**Variables API** (`GET/POST /v1/files/:key/variables`, juga `/local` utk baca): ini fitur Figma utk kelola "Variables" (nilai bernama — warna/angka/teks/boolean — yang dipakai berulang di desain, semacam design-token). KALAU token py akses ini, AI/script BISA mengubah nilai variable (mis. ganti semua warna brand sekaligus, ganti semua teks placeholder jadi versi lain) — ini yang PALING DEKAT dengan "editing kreatif via API" yang sungguhan menyentuh desain.

**Status dikonfirmasi:** endpoint ini BUKAN 404 (bukan tak-ada/salah-path) — respons **403 dengan pesan eksplisit "This endpoint requires the file_variables:read scope"** (utk GET) dan **"...file_variables:write scope"** (utk POST). Artinya endpoint resmi ADA & aktif, tapi scope `file_variables:*` **tidak muncul sama sekali** di 14 checkbox form generate Personal Access Token akun ini (dicek ulang 2026-08-21, 6 section: Users/Files/Design systems/Development/Folders/Webhooks — tak ada section "Variables"). **Kemungkinan penyebab (belum dikonfirmasi pasti):** fitur Variables API PAT mungkin di-gate ke plan Enterprise/Organization, sedangkan akun ini kemungkinan plan lebih rendah — TAPI ini dugaan, bukan fakta terverifikasi (Figma tak selalu jelas soal ini di UI). **Kalau butuh kepastian:** cek Settings→Plan akun Figma langsung, atau coba generate OAuth app (bukan PAT) yang kadang py cakupan scope beda dari PAT.

## §3. Kalau BENAR-BENAR butuh editing kanvas sungguhan (bukan komentar/variable)

Satu-satunya jalan resmi: **Figma Plugin API**. Cara kerjanya beda total dari REST API di atas:
- Ditulis dalam TypeScript/JavaScript, punya akses penuh ke `figma.currentPage`, bisa `figma.createRectangle()`, ubah `node.fills`, `node.characters` (teks), dst — INI yang setara "editing" sungguhan.
- **TAPI cuma jalan DI DALAM sesi editor Figma yang aktif** (Desktop app atau browser figma.com dengan file terbuka) — dipicu manual lewat menu Plugins, ATAU via **Figma REST API "Plugin" trigger** kalau plugin itu dipublish sbg "Figma Widget"/otomasi tertentu (masih butuh sesi UI aktif, tidak murni headless).
- **Konsekuensi praktis:** utk otomasi penuh, ini butuh **browser automation figma.com** (drive Chrome/CDP membuka file, jalankan plugin custom yg sudah ditulis+di-install ke akun) — jauh lebih berat drpd panggilan REST biasa, kurang lebih setara kompleksitas automasi Canva yg sudah dipetakan (`canva-automation-map.md`), TAPI belum pernah dicoba sama sekali di proyek ini. **Belum dikerjakan** — kalau user mau ini dikejar, perlu sesi terpisah khusus utk itu (bukan perpanjangan pipeline REST API yg ada).

## Ringkasan keputusan

| Kebutuhan | Jalan yang tersedia SEKARANG |
|---|---|
| AI kasih review/komentar di desain Figma | ✅ `figma_comment.py` — siap pakai |
| Ganti warna/teks brand di banyak file sekaligus via variable | 🟡 Perlu scope `file_variables:*` dulu — cek plan akun, belum bisa hari ini |
| Reaktif otomatis saat file di-update org lain | 🟡 Webhook API ada scope-nya, belum di-script-kan/diuji |
| Edit desain sungguhan (pindah shape, ganti layout) via AI/script | ❌ REST API TAK BISA. Pakai `figma_to_canva.py` → edit di Canva, ATAU (proyek besar terpisah) bangun Figma Plugin + browser automation |
