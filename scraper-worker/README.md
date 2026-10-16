# scraper-worker — lapisan keputusan Viral Scorecard

⛔ **2026-10-16 (keputusan user): scraper TikTok requests-only (CS `.61`) yang
dulu ada di sini DIHAPUS TOTAL** (`tiktok_scraper.py`/`run_worker.py`/
`ingest.py`/`run.sh`) — bukan sekadar dinonaktifkan. Dua alasan nyata:
1. Scraping anonim (walau requests-only dari IP Cloud Shell) tetap kena
   throttle/CAPTCHA (`HTTP 503`) secara struktural.
2. **Jadi akar bug tersembunyi 48 hari**: `viral_scorecard.py` selalu
   meng-enqueue video TikTok ke analyzer `.50`, tapi `orchestrator.py`
   (`~/akses-vps/viral-pipeline/`) **tak pernah mendukung platform TikTok** —
   jadi 15/15 job berakhir `dead`, nol analisa baru sejak 2026-08-29, meski
   cron scorecard lapor sukses setiap hari. Lihat memori
   `project_viral_analyzer.md` (audit 16/10) untuk detail penuh.

Sumber Tier-1 sekarang **Instagram + YouTube** via `../social-analytics/
social_trend.py` — akses LANGSUNG lewat akun Go Go Bud sendiri (Graph API
Business Discovery + YouTube publik), bukan menyamar sebagai pengunjung
anonim, jadi bebas dari hambatan firewall/anti-bot. Tak ada lagi worker di
Cloud Shell `.61` sama sekali — `social_trend.py` jalan murni dari hub.

## `viral_scorecard.py` — satu-satunya skrip aktif di folder ini

Baca `trend.social_post`+`trend.social_post_snapshot` (ditulis
`social_trend.py`) → skor tertimbang 4-grup → zonasi 🟢🟡🔴 → tulis
`trend.viral_score`. Top-K (default 10) dapat Tier-2: enqueue video ke
analyzer `.50` (`viral-pipeline/orchestrator.py`, yang SUDAH mendukung
youtube+instagram sejak awal) + Gemini via `ai_wiki_query` (RN7).

```bash
python3 viral_scorecard.py --dry-run --no-llm   # cetak tabel, nol API call/DB write
python3 viral_scorecard.py                      # run normal (tulis DB, enqueue Tier-2, Gemini)
```

Detail model skor, sumber tiap dimensi, dan catatan perubahan (like/comment-rate
menggantikan save/share-rate yang tak tersedia di IG/YouTube) ada di docstring
`viral_scorecard.py` sendiri — baca itu, jangan andalkan README ini soal detail
skor (bisa basi lebih cepat drpd docstring yang di-commit bersama kode).

## Jadwal cron (hub, WITA)
```
11:10 / 14:10 / 17:10   social-trend-cron.sh (../social-analytics/)   scrape IG+YT -> trend.social_*
13:20 / 16:20           scorecard-cron.sh                            viral_scorecard -> trend.viral_score
   tiap 10mnt            analyzer-pipeline-trigger.sh (existing)       drain enqueue analyzer .50 saat .50 aktif
```

## File tersisa di folder ini
| File | Tugas |
|---|---|
| `viral_scorecard.py` | lapisan keputusan (lihat atas) |
| `scorecard-cron.sh` | wrapper cron (lock+guard disk+log) |
| `scorecard.config.json` | bobot grup + ambang kalibrasi skor |
| `viral_score_schema.sql` | skema `trend.viral_score` (idempoten) |
