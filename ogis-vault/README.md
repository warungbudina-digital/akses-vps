# ogis-vault — Ollama+RAG mandiri di Cloud Shell `ogis`

Vault semantic-search LOKAL di `ogis` (10.66.66.8, akun `maydualapan8`),
terpisah dari `~/vault-search` di Pi4B. Dibangun 2026-08-29 — arsitektur
& kode ingest/search ADAPTASI 1:1 dari Pi4B (sudah teruji di sana, tidak
didesain ulang), cuma path/vault-label diganti + jadi containerized
(Ollama via Docker, bukan native systemd seperti Pi4B).

## Kenapa terpisah dari Pi4B, dan kenapa terpisah dari `~/browser`
- **Terpisah dari Pi4B:** `ogis` dan Pi4B adalah node berbeda; user minta
  ogis MANDIRI (compute+index sendiri), bukan cuma kirim data ke Pi4B.
- **Terpisah dari `~/browser`:** repo `warungbudina-digital/browser`
  dipakai BERSAMA `.60` (balibruntattour) — kalau Ollama ditambah ke
  compose stack itu, `.60` yang tak butuh RAG ikut menanggungnya.

## Komponen
- **Ollama** (Docker, `docker-compose.yml`) — `nomic-embed-text` (768-dim),
  port `127.0.0.1:11434` (internal, tak publik).
- `ingest.py` — rebuild index penuh dari `wiki/<domain>/*.md` ber-`corpus:true`.
- `ingest-append.py <domain>` — tambah/update SATU domain tanpa ganggu yg lain.
- `search.py` — cari (`--domain <nama>` utk scope 1 profil, kosongkan utk lintas).
- `wiki/_meta/` — aturan frontmatter+tag (identik pola Pi4B, `frontmatter-
  schema.md`+`tag-taxonomy.md`).
- `wiki/scrape-example/` — TEMPLATE domain (semua `corpus:false`, bukan
  pengetahuan nyata) siap `cp -r` saat domain nyata dibuat.
- `bring-up-ogis-vault.sh` — idempoten, jalan DI HUB (menggerakkan ogis via
  SSH+WG): push source, `docker compose up`, pull model, **restore index.db
  dari backup DB-VPS otomatis kalau lokal absen** (VM fresh pasca-recycle).
- `setup-browser-profiles.sh` — bikin N profil browser di `full-tool-browser`
  ogis (`driver:managed`), idempoten. Isi array `PROFILES` dgn nama nyata.
- `setup-gdrive-remotes.sh` — hubungkan tiap profil ke akun Gdrive-nya
  (baca `~/.config/ogis-gdrive/<profil>.json` di HUB, tulis rclone remote
  `gdrive-<profil>` ke `~/browser/.rclone-ogis.conf` di ogis). No-op anggun
  kalau folder kredensial kosong.

## Konvensi penamaan — SATU identifier, tiga peran
```
<nama-profil>
```
dipakai konsisten sbg: (1) nama profil browser (`POST /browser/profiles`),
(2) nama domain vault (`wiki/scrape-<nama-profil>/`), (3) nama remote
rclone (`gdrive-<nama-profil>`). Supaya jejak data 1-ke-1 tertelusur dari
scrape mentah -> pengetahuan tercari -> tersimpan di Gdrive akun yg benar.

## Backup & ketahanan (Cloud Shell EPHEMERAL — index bisa hilang tiap recycle)
`akses-vps/backup/ogis-vault-backup.sh` (jalan di HUB, cron) stream
`index.db` -> DB-VPS `~/ogis-vault-backups/` (gzip, validasi, rotasi —
pola persis `browser-db-backup.sh`). `bring-up-ogis-vault.sh` OTOMATIS
restore dari backup terbaru kalau index.db lokal absen -> pasca-recycle,
pengetahuan TIDAK hilang (asal backup sempat jalan sebelumnya).

## Alur kerja penuh (begitu nama profil + kredensial Gdrive sudah ada)
1. Isi `PROFILES=(nama1 nama2 ...)` di `setup-browser-profiles.sh`, isi
   `~/.config/ogis-gdrive/<nama>.json` per akun di HUB.
2. `deploy_ogis` (wake-orchestrator/cs-auto-deploy) otomatis jalankan:
   `bring-up-browser.sh` -> `bring-up-ogis-vault.sh` -> `setup-browser-
   profiles.sh` -> `setup-gdrive-remotes.sh`.
3. Scraping tiap profil (mekanisme scrape->markdown BELUM dibangun,
   di luar cakupan direktori ini) -> tulis ke `wiki/scrape-<nama>/*.md`
   di ogis -> `python3 ingest-append.py scrape-<nama>`.
4. `python3 search.py --domain scrape-<nama> "query"` utk cari 1 profil,
   atau tanpa `--domain` utk lintas-profil.
5. Upload hasil mentah ke Gdrive profil itu: `rclone --config
   ~/browser/.rclone-ogis.conf copy <src> gdrive-<nama>:<dest>`.
