# social-analytics

Skrip analisa akun media sosial (Facebook, dkk) lewat browser laptop
SUARAHATI yang sudah login persisten — **tanpa API resmi**, tanpa perlu App
Review/Page Token per platform. Dibangun 2026-08-25.

## `fb_analyze.py`

Analisa akun Facebook Business/Creator (Dasbor Profesional): follower count,
insight 28 hari (tayangan/interaksi), dan data per-postingan (buat cari ide
konten dari post yang performanya bagus).

```bash
python3 fb_analyze.py --account "Go Go Bud"
```

Output JSON ke stdout, contoh (ringkas):
```json
{
  "ok": true,
  "insight": {
    "followers_total": "664",
    "views_total": "646", "views_growth": "409%",
    "engagement_total": "22", "engagement_growth": "100%"
  },
  "posts": [
    {"caption": "...", "views": "230", "reach": "196", "engagement": "8", ...}
  ],
  "raw_text_dump": { ... }
}
```

`raw_text_dump` SELALU ada, lossless — kalau parser terstruktur (`insight`/
`posts`) meleset karena FB ubah UI, data mentahnya tetap bisa dibaca ulang
manual atau di-reparse.

### Cara pakai untuk akun lain

1. Login akun target di Chrome laptop SUARAHATI (lihat profil yang ada via
   `powershell -File C:\chrome-cdp\list-profiles.ps1` dari hub, atau minta
   user login baru di profil Chrome pilihan).
2. Pastikan akun itu muncul di pemilih-akun Facebook (klik avatar kanan-atas
   di profil Chrome itu → daftar "profil" yang bisa dipilih). Kalau belum,
   akun itu perlu ditautkan dulu lewat Settingan Facebook > Lihat semua
   profil.
3. Jalankan: `python3 fb_analyze.py --account "Nama Persis Akun" --profile "Profile N"`

### Cara pakai dari n8n (gogobuda, `.61`)

n8n **tidak bisa** SSH langsung ke laptop (beda mesin/kredensial). Panggil
lewat HUB — node "Execute Command" di n8n perlu SSH ke hub dulu:

```bash
ssh -i <admin-key-yg-bisa-reach-hub> warungbudina@10.66.66.1 \
  "python3 ~/akses-vps/social-analytics/fb_analyze.py --account 'Go Go Bud'"
```

**Belum di-set:** kredensial SSH agar container n8n (di VM gogobuda) bisa
reach hub. Opsi lanjutan (belum dikerjakan, follow-up kalau mau
diotomasi penuh):
- (a) generate keypair baru khusus, taruh public key di
  `~/.ssh/authorized_keys` hub (scoped `from="10.66.66.61"` spt pola admin
  key lain di proyek ini), private key di n8n via Credential SSH; atau
  (b) bungkus skrip ini jadi endpoint HTTP kecil di hub (Flask/FastAPI
  ringan) yang dipanggil n8n via node "HTTP Request" ke `10.66.66.1:<port>`
  — hindari SSH sama sekali dari sisi n8n, lebih simpel utk node non-teknis.

### `--post-detail` — data lebih dalam per-postingan

```bash
python3 fb_analyze.py --account "Go Go Bud" --post-detail --post-detail-count 2
```

Klik masuk ke halaman "Insight Postingan" tiap post (bukan cuma baris ringkasan
tabel Galeri Konten), dapat data yang TIDAK ada di tabel biasa:

- `shares` (Frekuensi Dibagikan) — jawaban utk "Shares-to-Views Ratio"
- `reactions_by_type` — breakdown 7 jenis reaksi Facebook
- `followers_reach_pct`/`non_followers_reach_pct` — versi Facebook dari
  konsep "FYP%"/discovery reach (makin tinggi % non-follower = makin luas
  disebar algoritma ke luar audiens sendiri)
- `age_breakdown` — demografi usia penonton
- `monetization` — status kelayakan 5 kategori (Bintang, Monetisasi konten,
  Iklan instream, Iklan di reel, Langganan)
- `traffic_source_available`/`link_clicks_available` — Facebook sering
  belum cukup data utk akun kecil (ditandai `false`, bukan silently kosong)

Hasil masuk ke `result["post_detail"]` (list, 1 entry per caption yang
dicoba, tiap entry punya `parsed` terstruktur + fallback `note` kalau klik
gagal ketemu elemen).

### Reliabilitas & keterbatasan (baca sebelum percaya buta)

- **Ini scraping UI, bukan API resmi.** Kalau Facebook ubah tampilan Dasbor
  Profesional, parser `posts`/`insight` bisa meleset. `raw_text_dump` selalu
  jadi fallback lossless.
- **`followers_total` best-effort, kadang `null`.** Setelah investigasi
  panjang (lihat memori Claude sesi 2026-08-25): navigasi FB dari
  "Beranda/feed" ke "halaman profil sendiri" (satu-satunya tempat "N
  pengikut" nampak langsung) TERBUKTI tak konsisten timing-nya, bahkan
  dengan retry. Field lain (`views_total`/`engagement_total`/`posts`) TIDAK
  bergantung ke langkah ini, jadi tetap reliable walau followers gagal.
- **Setiap panggilan buka 1 tab Chrome baru** di laptop, dan **SELALU
  ditutup** di akhir (baik sukses maupun gagal, lewat `finally`) — PENTING
  jangan hapus/ubah bagian ini kalau edit skrip; tab menumpuk dari
  percobaan gagal TERBUKTI bikin laptop lambat & percobaan berikutnya makin
  sering gagal juga (efek bola salju, kejadian nyata saat perancangan).
- **Retry beruntun dalam waktu singkat berisiko** — kalau akun sama dipanggil
  berkali-kali dalam hitungan menit (mis. saat debugging), Facebook bisa
  memperlambat/mengubah perilaku dropdown pemilih-akun (belum dipastikan
  ini genuinely rate-limit atau cuma kebetulan CPU laptop kewalahan). Jangan
  jadwalkan lebih sering dari beberapa kali/hari per akun.
- Semua helper CDP kecil (`cdp-eval.py`, `cdp-click-text.py`,
  `cdp-click-aria.py`, `write-launch-params.py`, `list-tabs-full.ps1`)
  **auto-deploy ke laptop** kalau belum ada (`ensure_generic_launcher()`) —
  file ini SATU-SATUNYA yang perlu dibawa/di-commit.

### SOP terkait

Lihat memori Claude: `feedback_social_login_use_laptop_browser.md` (SOP
login medsos WAJIB lewat browser laptop SUARAHATI, bukan tempat lain) dan
`project_medsos_agent.md` bagian 2026-08-25 (kronologi lengkap perancangan
+ semua bug yang ditemukan/difix selama membangun skrip ini).

## Riset tren TikTok (`tiktok_trend.py`) — ditambahkan 2026-09-25

Pantau watchlist kreator niche AI/tech → statistik video ke DB-VPS schema
`trend` → laporan Markdown mingguan (+ ringkasan Telegram). Tujuannya bahan ide
konten Go Go Bud: hook, format (video vs carousel), durasi, hashtag, jam posting
yang sedang bekerja di niche ini.

| File | Fungsi |
|---|---|
| `tiktok_watchlist.json` | daftar akun dipantau + setelan volume/jeda |
| `tiktok_trend.py` | pengumpul (browser API Cloud Shell .60 → DB-VPS) |
| `tiktok_trend_report.py` | laporan → `reports/tiktok-trend-<tgl>.md` (`--telegram` = ringkasan) |
| `tiktok-trend-cron.sh` | entrypoint cron: maks 1 run sukses/hari, laporan Telegram tiap Senin |
| `tiktok_trend_schema.sql` | skema `trend.*` (idempoten) |

```bash
python3 tiktok_trend.py --check @handle1 @handle2   # cek akun sebelum masuk watchlist
python3 tiktok_trend.py --dry-run --only tommythings # uji tanpa tulis DB
python3 tiktok_trend_report.py --days 30             # buat laporan sekarang
tail -f ~/tiktok-trend.log                           # log cron
```

**Jalur data (diuji dari IP Cloud Shell, pengunjung anonim):** `/tag/` & `/discover/`
ditolak; halaman profil memicu CAPTCHA saat memuat daftar video; **widget embed
`/embed/@handle`** memberi info user + ±13 video tanpa CAPTCHA → dipakai; halaman
video memberi statistik lengkap (SSR). Waktu unggah juga bisa dari ID (`id >> 32`).

**Jebakan yg sudah ditangani:**
- **MTU hub→.60**: wg0 hub 1420 vs .60 1380 → body HTTP >~1.3KB ke .60 menggantung
  selamanya. Butuh rute `10.66.66.60/32 mtu 1380` di hub (permanen via
  `~/akses-vps/wireguard/persist-mtu-cloudshell60.sh`). Collector memeriksa ini di
  awal dan GAGAL dgn pesan jelas kalau rutenya hilang.
- **Baca halaman sebelumnya**: jeda tetap setelah navigate pernah membaca halaman
  lama → sekarang tunggu sampai URL cocok target + cek handle/ID hasil = target.
- **Carousel foto** (Photo Mode) durasinya 0 → dicatat `media_type=photo`, durasi NULL.
- Akun tak ada: embed `isError:true`. CAPTCHA → run berhenti (exit 2), bukan dipaksa.
- **Profil remote-cdp .60 berbagi SATU halaman** & video autoplay yg ditinggal membuat
  .60 150% CPU → collector `quiet()` (pause+kosongkan `<video>`) tiap video dan `park()`
  tab ke about:blank di akhir run. Kalau tetap lambat: restart container browser .60.
- `wait` kadang 500 saat TikTok redirect internal → diulang 3×; error per-video tak
  menggagalkan akun. `resource-block` API tak bisa dipakai via HTTP (schema buang `types`).
- Video "not available in your country" = diblokir wilayah IP .60 (Singapura), bukan error.
- Status per akun membedakan `ok`/`no_videos` (terukur) dari `captcha`/`error`/`not_found`
  (gagal mengukur) — laporan menampilkan kesehatan pengumpulan di bagian atas.

### Instagram + YouTube (`social_trend.py`) — ditambahkan 2026-09-25
5 akun teratas per platform di `social_watchlist.json` (niche AI/tech/skill digital
Indonesia, aktif, urut pengikut, tanpa media berita). Jalan penuh dari hub — TIDAK
butuh .60/laptop:
- **Instagram:** Graph API *Business Discovery* dgn token Page gogobud
  (`~/.config/meta-gogobud/app.env`). Resmi. Hanya akun Business/Creator (pribadi →
  "Invalid user id"). Reels ada `view_count`; carousel tanpa views; like bisa
  tersembunyi (NULL) kalau kreator menyembunyikan like.
- **YouTube:** `/@handle/about` (en-US: subscriber/views/jumlah video) + RSS
  `feeds/videos.xml` (15 video terbaru, views, likes). Shorts = `/shorts/<id>` 200
  (video biasa 303). ID channel WAJIB dari `<link rel=canonical>` — kemunculan
  `"channelId"` pertama di HTML bisa milik channel lain.
- **Facebook: belum.** Graph API utk Page orang lain butuh App Review (Page Public
  Content Access); .60 kena login-wall; laptop hanya punya tab Cloud Shell (profil
  Budayana yg login FB tak terbuka).

Tabel: `trend.social_account_snapshot`, `trend.social_post`, `trend.social_post_snapshot`.
Laporan memakai metrik ÷ pengikut (views/pengikut, (like+komentar)/pengikut) supaya
akun raksasa tak otomatis menang, plus uji ajakan "komen …" di caption.
`tiktok-trend-cron.sh` menjalankan IG/YT dulu (penanda harian sendiri), lalu TikTok;
laporan Senin tetap terkirim di slot terakhir walau TikTok gagal.

```bash
python3 social_trend.py --check instagram akun1 akun2   # seleksi akun
python3 social_trend.py --check youtube HandleChannel
python3 social_trend.py --dry-run --only youtube
```
