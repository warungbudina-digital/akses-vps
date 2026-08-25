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
