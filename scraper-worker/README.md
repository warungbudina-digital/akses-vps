# scraper-worker — worker riset tren (CS .61)

Scraper TikTok **requests-only** (tanpa browser/Chromium) untuk lapisan riset
pipeline Viral Scorecard. Menggantikan jalur browser `.60` yang berat.

## Kenapa ringan (beban HUB minimal)
- **Scraping jalan di CS .61**, bukan di hub. Requests-only = unduh ~300–430 KB/halaman,
  parse 1 JSON, I/O-bound (mayoritas waktu = jeda antar-request). Nol Chromium.
- **HUB hanya:** `ssh` orkestrasi + parse JSONL + suap `psql`. Ini beda jauh dari
  browser `.60` yang pernah 150% CPU. Footprint hub ~beberapa MB RAM, CPU sekejap.
- Kalau .61 mati (Cloud Shell laptop-gated) → `run.sh` **SKIP** (bukan error),
  pola sama `tiktok_trend.py`.

## Komponen
| File | Jalan di | Tugas |
|------|----------|-------|
| `tiktok_scraper.py` | .61 (atau mana saja) | fetch+parse embed & video-detail (requests-only), DB-agnostik |
| `run_worker.py` | **.61** | iterasi watchlist → emit JSONL (stateless, tanpa DB) |
| `ingest.py` | **HUB** | baca JSONL → tulis DB-VPS `trend.*` via `ssh db-vps \| psql` |
| `run.sh` | **HUB** | orkestrasi: rsync→.61, jalankan, stream JSONL→ingest; guard + lock + last_ok_day |

Skema DB dipakai bersama: `../social-analytics/tiktok_trend_schema.sql`
(`trend.tiktok_account_snapshot` / `tiktok_video` / `tiktok_video_snapshot`).
Watchlist dipakai bersama: `../social-analytics/tiktok_watchlist.json`.

## Aliran
```
hub cron → run.sh → rsync kode → ssh .61 `run_worker.py` → JSONL
        → ingest.py (hub) → ssh db-vps psql → DB-VPS trend.*
        → viral_scorecard.py (hub, terpisah) → trend.viral_score → Laporan Senin
```

## Status (27/9)
- Langkah-0 **TERBUKTI** dari IP hub: embed + video-detail keduanya HTTP 200 + JSON asli
  (@sazporto 86,6rb follower; video play 43.700/save 324 → save-rate 0,74%).
- ✅ **DEPLOYED ke .61 + tervalidasi dari IP CS**: file di `~/scraper-worker` (`gogobuda65@10.66.66.61`,
  key `~/.ssh/akses-vps-cloudshell-admin`). Embed **jalan** dari IP CS; video-detail **jalan** dari IP CS
  (parse penuh: save 324, save-rate 0,741%).
- ⭐ **UA DESKTOP WAJIB**: embed jalan UA apa pun, tapi **video-detail hanya kembalikan itemStruct utk UA
  desktop** — UA mobile dapat shell tanpa data (status `no_data`). Sudah difix di `tiktok_scraper.py`.
- ⚠️ **Throttle nyata**: request beruntun tanpa jeda → HTTP 503 (status `captcha`). `delay_min_s/max_s`
  (25–45s) di watchlist WAJIB dipatuhi (backoff sudah ada di `_get`). Jangan pakai jeda kecil saat uji.

## Jadwal cron (hub, WITA)
```
12:40 / 15:40   run.sh            scrape .61 -> trend.*        (offset dari .60 lama 11:10/14:10/17:10)
13:20 / 16:20   scorecard-cron.sh viral_scorecard -> trend.viral_score
   tiap 10mnt   analyzer-pipeline-trigger.sh (existing) drain enqueue analyzer .50 saat .50 aktif
```
Auto-deploy .61: `deploy_gogobuda` (lib-cs-deploy.sh, dipanggil cs-auto-deploy */5) push kode ini
tiap laptop boot & .61 naik. run-1 scorecard enqueue top-10 ke analyzer; run-2 (setelah drain) isi
dim analyzer. Gemini via ai_wiki_query->RN7 (graceful kalau RN7 mati -> dim pending).

## TODO deploy
1. Alias ssh `.61` di hub (`WORKER_SSH`, ControlMaster spt `c50`/`c60`).
2. MTU route `10.66.66.61/32 mtu 1380` di wg0.conf (bug laten spt `.60`).
3. Bersihkan `known_hosts` .61 (host-key berubah) → `accept-new`.
4. `pip install requests` di .61 (deploy hook / cs-auto-deploy).
5. Tambah slot cron hub (mis. samakan dgn `tiktok-trend-cron.sh`), pertimbangkan **pensiunkan jalur TikTok `.60`** kalau requests-only stabil dari IP CS.
6. `viral_scorecard.py` (lapisan keputusan) = pekerjaan terpisah berikutnya.
