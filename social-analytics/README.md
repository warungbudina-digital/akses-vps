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

## ⛔ Riset tren TikTok — DIHAPUS TOTAL 2026-10-16 (keputusan user)

Dulu ada `tiktok_trend.py`/`tiktok_trend_report.py`/`tiktok-trend-cron.sh`/
`tiktok_watchlist.json`/`tiktok_trend_schema.sql` di sini (scraping anonim via
browser Cloud Shell `.60`, lihat riwayat git kalau perlu detail teknis). **Dibuang
bersama dokumentasinya**, bukan sekadar dinonaktifkan, dengan 2 alasan nyata:
1. Scraping anonim terus-menerus kena CAPTCHA/WAF — rapuh secara struktural,
   bukan bug yang bisa difix sekali.
2. **Jadi akar bug tersembunyi 48 hari**: lapisan keputusan (`viral_scorecard.py`)
   selalu meng-enqueue video TikTok ke analyzer `.50`, tapi `orchestrator.py`
   (`~/akses-vps/viral-pipeline/`) TAK PERNAH mendukung TikTok — jadi 15/15 job
   berakhir `dead`, nol analisa baru sejak 29 Agustus, meski cron lapor sukses
   setiap hari (lihat memori `project_viral_analyzer.md`, audit 16/10).

Diganti sepenuhnya oleh `social_trend.py` (Instagram+YouTube) di bawah, yang
akses platformnya LANGSUNG via akun Go Go Bud sendiri (token Page Graph API,
YouTube publik) — bukan menyamar sebagai pengunjung anonim, jadi bebas dari
hambatan firewall/anti-bot, DAN `orchestrator.py` sudah mendukung kedua
platform ini sejak awal (memperbaiki bug #2 di atas sebagai efek samping).

## Instagram + YouTube (`social_trend.py`) — ditambahkan 2026-09-25, SATU-SATUNYA sumber tren sejak 16/10
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
`social-trend-cron.sh` (bukan lagi `tiktok-trend-cron.sh` yang sudah dihapus) jalan
11:10/14:10/17:10 WITA — 1x sukses/hari sudah cukup (penanda `last_ok_day`); laporan
mingguan (Senin, via `social_trend_report.py --telegram`) jalan 1x/minggu di cron yang sama.

```bash
python3 social_trend.py --check instagram akun1 akun2   # seleksi akun
python3 social_trend.py --check youtube HandleChannel
python3 social_trend.py --dry-run --only youtube
```

### Durasi video (✅ 2026-10-17)

Ditangkap tanpa butuh API/field baru. **Instagram**: gratis, dari param `efg=`
(JSON base64 internal) di `media_url` yang sudah ikut diminta dari Business
Discovery — carousel/image tetap `NULL` (wajar, bukan video). **YouTube**: satu-
satunya sumber = scrape halaman watch (`"lengthSeconds"`, tak ada di RSS/oEmbed/
about) — di-cache per video_id ke DB supaya video lama tak di-scrape ulang tiap
cron. Dipakai `viral_scorecard.py` (G4 KecepatanEksekusi, dulu selalu `pending`).

### Pengawas harian (✅ 2026-10-17): `social-trend-healthcheck.sh`

Cron terpisah (`45 9 * * *`, bahasa laporan SENGAJA awam) yang mengecek 2 hal
yang TAK tertangkap cron utama sendiri: (1) kesegaran data **per-platform**
(exit-code `social-trend-cron.sh` digabung IG+YT — satu platform bisa total
gagal berhari-hari tanpa ketahuan selama platform lain masih ok), (2) rasio akun
sukses pada run terakhir. Alert Telegram hanya saat status berubah (anti-spam).
