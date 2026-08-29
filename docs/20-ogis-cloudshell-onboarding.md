# 20 — Onboarding profil ke-4 wake-orchestrator: "ogis"

## 1. Apa & kenapa

Profil Cloud Shell ke-4 ditambahkan ke pola 3-profil yang sudah ada
(lihat `docs/17-sop-laptop-cloudshell-wake-cycle.md`), khusus untuk jadi
**instance scraper terpisah** (data medsos/konten untuk `viral_analyzer`).
Rencana besar: hasil scrape → wiki dokumen baru + indeks ke RAG vault
Pi4B (vector+semantic metadata per-profil "pengetahuan" berbeda) — itu
**Fase 2, belum dikerjakan** (Pi4B belum reachable saat Fase 1 ini
dikerjakan). Dokumen ini murni catatan **Fase 1: onboarding infra**.

| | |
|---|---|
| Akun Google | `maydualapan8@gmail.com` |
| Profil Chrome laptop | Profile 11, nama tampilan **"Ogis-Chain"** |
| WireGuard tunnel IP | `10.66.66.8` (auto-pick dari `new-cloudshell-peer.sh`) |
| Project yang dideploy | `full-tool-browser` — **instance KEDUA**, terpisah dari yang sudah jalan di `.60`/balibruntattour |
| Urutan wake-orchestrator | balibruntattour → gogobuda → yuni → **ogis** (terakhir) |

**Catatan penting:** `maydualapan8@gmail.com` BUKAN akun baru di
infrastruktur ini — akun ini sudah dipakai sebagai remote Gdrive
`gfootage` (`RAW-VIDEO/`, `VN-exports/`) untuk pipeline `viral_analyzer`
yang sama persis, lihat `project_viral_analyzer` memory. Jadi kombinasi
compute (Cloud Shell) + storage (Gdrive) sekarang di satu akun yang
sama untuk pipeline yang sama.

## 2. Yang diubah (2026-08-29)

### Laptop (`SUARAHATI`)
- `D:\scloudshell\ogis-bootstraps.sh` — bootstrap WG+SSH+watchdog, dari
  `new-cloudshell-peer.sh ogis` di hub (key TETAP, sejajar 3 bootstrap
  lain di folder yang sama).
- `Desktop\Cloud Shell - ogis.lnk` — shortcut Chrome, args disalin dari
  pola shortcut `balibruntattour` (`--remote-debugging-port=9222
  --remote-debugging-address=127.0.0.1 --profile-directory="Profile 11"
  "https://shell.cloud.google.com/?ephemeral=true"`).
- `C:\chrome-cdp\open-and-bootstrap-cs.py` — entri baru di list
  `PROFILES` (name `ogis`, shortcut+bootstrap path di atas). Backup:
  `open-and-bootstrap-cs.py.bak-20260829-add-ogis`.
- `C:\chrome-cdp\open-cs.ps1` — `[ValidateSet(...)]` ditambah `'ogis'`.
  Backup: `open-cs.ps1.bak-20260829-add-ogis`.
- Scheduled Task **`open-cs-ogis`** — kloning persis `open-cs-yuni`
  (InteractiveToken, TANPA auto-trigger, `Task To Run` =
  `open-cs.ps1 -Profile ogis`, Stop-if-runs 15 menit). Dibuat via XML
  export/import dari `open-cs-yuni` supaya setelan identik.

### Hub (`akses-vps`)
- `wireguard/wg0.conf` — peer `ogis` terdaftar (`new-cloudshell-peer.sh`).
- `backup/lib-cs-deploy.sh` — fungsi baru `deploy_ogis()`/
  `_deploy_ogis_impl()`. **TIDAK ada script baru** — reuse
  `bring-up-browser.sh` apa adanya lewat env override
  `C60_HOST=maydualapan8@10.66.66.8` + `BROWSER_API=http://10.66.66.8:8080`
  (skrip itu sudah baca env ini dgn default ke `.60`; `C60_KEY` tetap
  admin key bersama, tak perlu diubah).
- `backup/wake-orchestrator.sh` — blok ke-4 `process_profile_with_retry
  "ogis" ...` ditambah di akhir urutan (setelah yuni), `STATUS_OGIS`
  masuk ke ringkasan `finish()`.
- `backup/cs-auto-deploy.sh` — `run_and_log deploy_ogis` ditambah
  (jaring pengaman 5-menitan).
- `docs/17-sop-laptop-cloudshell-wake-cycle.md` — tabel profil, hitungan
  "3→4 profil", inventaris file/task, semuanya disinkronkan.

## 3. Verifikasi yang sudah/perlu dilakukan
- [x] `wg show` di hub menampilkan peer `ogis` di `10.66.66.8/32`.
- [x] Shortcut+wiring+Scheduled Task laptop dibuat & diverifikasi via
  `Get-Content`/`schtasks /query`.
- [x] `bash -n` bersih untuk `wake-orchestrator.sh`, `lib-cs-deploy.sh`,
  `cs-auto-deploy.sh`.
- [x] Trigger manual pertama (2026-08-29 19:43 WITA): tab Cloud Shell
  `maydualapan8@cloudshell` **benar-benar terbuka & login BENAR** (akun
  cocok, profil Chrome 11 terkonfirmasi). Bootstrap ke-upload+ke-paste
  (`upload rc=0`, `tutup popup transfer rc=0`, `bootstrap run rc=0` —
  welcome banner Cloud Shell muncul), TAPI command pertama
  (`chmod +x ogis-bootstr...`) ke-scrape TERPOTONG → status lokal
  "TAK PASTI". Cross-check ground-truth (`wg show`/`reachable_cs`):
  **handshake WG = 0, belum reachable** — bootstrap BELUM benar-benar
  jalan sampai `wg-quick up`.
- [ ] Retry manual kedua (19:48 WITA) dipicu tanpa jeda cukup →
  **race 2-tab**: tab pertama dapat notice Cloud Shell "Your session
  was transferred to another browser tab", tab kedua sempat balik ke
  layar "Membangun koneksi..." lalu settle jadi terminal KOSONG (belum
  ada prompt/log lanjutan). Masih **belum reachable** setelah total
  ~10 menit menunggu (2× polling 240s+180s dari hub).
- [x] **✅ 2026-08-29 22:31 WITA: bootstrap `ogis` SUKSES PENUH.** Retry
  manual ke-3 (jeda ~2.5 jam dari percobaan ke-2, menghindari race
  sebelumnya) → `reachable_cs` sukses dlm <4 menit, WG handshake up.
  `deploy_ogis`/`bring-up-browser.sh` langsung dijalankan menyusul:
  clone repo baru, build+up Docker (~3mnt14dtk), **`health=200`,
  `/sessions` tanpa-kunci=401, dengan-kunci=200 (auth aktif & kunci
  cocok)**. Disk `.8`: 53G free/57% used (jauh lebih lega dari `.60`).
  **Pelajaran dikonfirmasi:** akar masalah 2 percobaan pertama memang
  race dari retrigger manual beruntun tanpa jeda (bukan masalah
  wiring) — begitu dikasih jeda wajar, jalan mulus di percobaan
  berikutnya persis pola 3 profil lain.
- [x] ~~BELUM ada bootstrap `ogis` yang sukses penuh sampai WG up.~~
  Wiring infra (shortcut/task/script/lib-cs-deploy/wake-orchestrator)
  **terverifikasi benar** — masalahnya murni di eksekusi live pertama
  kali (kombinasi: kemungkinan besar ini sesi Cloud Shell PERTAMA akun
  ini — provisioning awal beda/lebih lambat dari 3 akun lain yg sudah
  lama dipakai — DITAMBAH race akibat 2x manual trigger beruntun tanpa
  jeda dari saya). **Pelajaran: JANGAN retrigger `open-cs-ogis` manual
  beruntun tanpa jeda ≥5 menit** — biarkan `cs-auto-deploy.sh` (tiap
  5mnt) atau retry bawaan `wake-orchestrator.sh` (jeda 10mnt) yang
  coba ulang ke tab yang SUDAH terbuka, itu pola yang terbukti jalan
  utk 3 profil lain (lihat §3 `docs/17-...md`).
- [ ] Cek lanjutan yang masih perlu dilakukan sesi berikutnya: apakah
  tab ogis yang sudah terbuka (kosong, belum crash) akhirnya siap
  sendiri, ATAU perlu 1x cek visual manual di layar laptop (mungkin
  ada dialog first-time Cloud Shell/ToS akun baru yang belum pernah
  dipakai, yang tak ke-handle otomasi existing).
- [ ] `curl -m8 http://10.66.66.8:8080/health` → `{"ok":true}` dari hub,
  `/sessions` tanpa key → 401.
- [ ] Satu siklus penuh `wake-orchestrator.sh` (jadwal otomatis atau
  manual) → baris `RINGKASAN AKHIR` memuat `ogis=OK`.

## 4. Fase 2 — REVISI: vault MANDIRI di ogis (bukan proxy ke Pi4B), + 5 profil + 5 Gdrive

**⚠️ Arsitektur di bawah ini MENGGANTIKAN rencana awal Fase 2** (yang
sempat menyiapkan konvensi domain di Pi4B `~/wiki-docs/`). User merevisi:
ogis harus **mandiri** — Chromium sendiri (SUDAH ADA, §1-3), Ollama+index
vektor sendiri (BUKAN cuma kirim data ke Pi4B), 5 profil browser, tiap
profil terhubung ke akun Gdrive-nya sendiri. Detail arsitektur lengkap +
alasan tiap keputusan: **`akses-vps/ogis-vault/README.md`** — baca itu
sbg sumber kebenaran, ringkas di sini:

- **`akses-vps/ogis-vault/`** (dir baru, git-tracked): `docker-compose.yml`
  (service `ollama`, TERPISAH dari `~/browser` yg dipakai bersama `.60`),
  `ingest.py`/`ingest-append.py`/`search.py` (adaptasi 1:1 dari Pi4B
  `~/vault-search`, index & wiki kini LOKAL di ogis bukan di Pi), `wiki/
  _meta/` (konvensi frontmatter+tag, sama pola Pi4B), `wiki/scrape-example/`
  (template), `bring-up-ogis-vault.sh` (idempoten, **auto-restore index.db
  dari backup DB-VPS** kalau lokal absen pasca-recycle), `setup-browser-
  profiles.sh` (bikin N profil via `POST /browser/profiles`), `setup-
  gdrive-remotes.sh` (link tiap profil ke remote rclone `gdrive-<profil>`).
- **`akses-vps/backup/ogis-vault-backup.sh`** (hub, cron `17 */2 * * *`) —
  stream `index.db` ogis → DB-VPS `~/ogis-vault-backups/` (pola persis
  `browser-db-backup.sh`). Ini yang bikin index vektor TAK hilang
  permanen meski Cloud Shell ephemeral.
- **`lib-cs-deploy.sh` `deploy_ogis`** kini juga panggil `bring-up-ogis-
  vault.sh` + `setup-browser-profiles.sh` + `setup-gdrive-remotes.sh`
  setelah `bring-up-browser.sh` — SENGAJA independen (gagal di sini TAK
  menjatuhkan status "browser OK" profil `ogis` di wake-orchestrator).

**Konvensi penamaan — 1 identifier, 3 peran:** `<nama-profil>` = nama
profil browser = nama domain vault (`scrape-<nama-profil>`) = nama remote
rclone (`gdrive-<nama-profil>`).

**Yang MASIH belum ditentukan (keputusan user, belum dikerjakan):**
- **5 nama profil browser konkret** — `PROFILES=()` di `setup-browser-
  profiles.sh` masih kosong (no-op aman), isi begitu ditentukan.
- **5 kredensial akun Gdrive** — folder `~/.config/ogis-gdrive/` di hub
  disiapkan, mekanismenya jalan (no-op anggun kalau kosong), tapi belum
  ada file `.json` diisi.
- Siapa/apa yang menulis catatan `.md` dari hasil scrape mentah (manual
  atau skrip otomatis mirip `ir_to_vn.py`) — belum dibangun.
- Rencana lama (Pi4B `~/wiki-docs/_meta/scrape-domain-convention.md` dkk)
  **DIBIARKAN ADA** di Pi4B (tak dihapus, tak rusak) tapi TIDAK dipakai
  utk alur ogis ini lagi — kalau ke depan ternyata mau MENGGABUNG dua
  vault (Pi4B + ogis-vault) jadi satu, itu keputusan terpisah yang belum
  diambil.
