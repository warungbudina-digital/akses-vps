# 16 — SOP Node Terjadwal (24/7 vs On-Demand)

## Kenapa dokumen ini ada

Infrastruktur ini punya dua kelas node dengan disiplin operasi yang berbeda.
Keputusan user (2026-08-07): **hanya sebagian kecil node yang hidup 24/7,
sisanya dinyalakan terjadwal/on-demand.** Dokumen ini adalah aturan main
supaya kelas "terjadwal" tidak diperlakukan seolah 24/7 — karena salah-perlakuan
menghasilkan alarm palsu, kehilangan data, dan kegagalan senyap.

Referensi terkait: `docs/12-wireguard-vpn.md` (topologi peer), `docs/15-alur-akses-wireguard.md`
(alur akses), `docs/10-backup-strategy.md` (backup stack utama).

## Klasifikasi node

| Node | IP WG | Kelas | Peran |
|---|---|---|---|
| **akses-vps** | 10.66.66.1 | **24/7** | Hub WireGuard + control-plane + pemicu semua kerja terjadwal |
| **Infinix X662** | 10.66.66.2 | **24/7** | HP otomasi (VN/Flow via Appium), encoder streaming |
| **Redmi Note 5** | 10.66.66.3 | **24/7** | (verifikasi status LCD sebelum diandalkan) |
| **DB-VPS** | 10.122.31.251 | **24/7** | PostgreSQL — semua state durable (antrean, hasil, backup) |
| **.50 warungbudina** | 10.66.66.50 | Terjadwal | Cloud Shell: viral_analyzer (analisa video) |
| **.60 balibruntattour** | 10.66.66.60 | Terjadwal | Cloud Shell: full-tool-browser (scraping + growth) |
| **Pi 4B pentest** | 10.66.66.4 | Terjadwal | Pi: pentest-agent, SpiderFoot, RAG vault — **rawan PANAS** |
| **Laptop SUARAHATI** | LAN 192.168.70.254 | Terjadwal | CDP Chrome (audit sesi login FB) |

**Alasan tiap node terjadwal:**
- **.50 / .60** = Google Cloud Shell **ephemeral** — VM di-recycle saat sesi
  browser ditutup; hidup hanya selama user membuka Cloud Shell.
- **Pi 4B** = hardware kadang **error akibat panas** → dijadwalkan OFF untuk
  mengurangi beban termal kumulatif.
- **Laptop** = mesin kerja user, tidak selalu menyala.

## Lima invarian (WAJIB dipatuhi untuk semua kerja terjadwal)

### 1. State durable hanya di tier 24/7
Node terjadwal = **compute sekali-pakai**. Apa pun yang perlu bertahan WAJIB
di DB-VPS (data) atau akses-vps (kunci, konfigurasi, pemicu). Jangan pernah
menjadikan node ephemeral sebagai satu-satunya tempat data penting.

- Contoh benar: antrean video di `media.video_ingest` (DB-VPS); hasil analisa
  di `media.video_analysis` (DB-VPS); backup DB browser di `db-vps:~/browser-db-backups/`.
- Jebakan: named Docker volume di Cloud Shell (`postgres-data` di .60) HILANG
  saat VM recycle — karena itu ada `browser-db-backup.sh`.

### 2. Pemicu datang dari akses-vps, bukan scheduler internal node
Scheduler di dalam node ephemeral (mis. node-cron/BullMQ `/schedules` di .60)
**hanya jalan selagi node hidup** → tidak andal. Semua penjadwalan berpindah
ke cron akses-vps yang **"menengok"** node dan bekerja saat node kebetulan hidup.

- Pola acuan: `viral-pipeline/run-drain.sh` (akses-vps menggerakkan .50).
- Pola acuan: `backup/bring-up-browser.sh` (akses-vps menggerakkan .60).

### 3. Cron akses-vps WAJIB no-op anggun saat target OFF
Node terjadwal OFF adalah **kondisi NORMAL**, bukan error. Skrip yang menyentuh
node terjadwal harus:
- **exit 0 + pesan "SKIP/normal"** saat target tak terjangkau.
- exit ≠ 0 **hanya** saat target HIDUP tapi ada masalah nyata.

Kalau tidak, log terisi alarm palsu tiap host OFF → melatih user mengabaikan
log → mematikan manfaat pemantauan.

### 4. Setiap node terjadwal punya health-report
No-op saat OFF; **berisik** saat ada masalah nyata saat ON. Bikin kegagalan
senyap jadi terlihat.

### 5. Bring-up terdefinisi per node
- **Cloud Shell (.50/.60)** = ephemeral, home ikut hilang → butuh skrip bring-up
  (clone + build + up) + paste bootstrap WG/SSH lebih dulu. **Tidak zero-touch.**
- **Pi 4B** = disk persisten + service systemd enabled → **bring-up ZERO-TOUCH
  saat power-on** (wg-quick/docker→pentest-agent/spiderfoot/ollama naik sendiri).
  Tidak perlu skrip deploy.

## Perkakas (di akses-vps)

| Skrip | Fungsi | Cron |
|---|---|---|
| `backup/browser-db-backup.sh` | pg_dump .60 → stream pipe → DB-VPS (validasi + rotasi 30) | `7 */2 * * *` (tiap 2 jam) |
| `backup/browser-health-report.sh` | deteksi gagal-senyap .60 (done+0 hasil), auth, backup basi, sesi/jadwal | `0 1 * * *` (09:00 WITA) |
| `backup/bring-up-browser.sh` | bring-up .60 dari akses-vps + sinkron API_KEY kanonik | manual (setelah user nyalakan .60) |
| `backup/pi-health-report.sh` | termal Pi (`get_throttled` decode) + service + disk | `5 1 * * *` (09:05 WITA) |
| `viral-pipeline/bring-up-analyzer.sh` | bring-up analyzer di .50 (dijalankan DI .50) | manual |
| `viral-pipeline/run-drain.sh` | kuras antrean video saat .50 aktif | manual/opsional cron |

Semua cron di atas berbagi prinsip #3 (no-op anggun). `date` akses-vps = **UTC**
→ konversi ke WITA (+8) saat baca jadwal.

## Kredensial & akses (semua di akses-vps, mode 600, TIDAK di repo)

| Target | Metode | Lokasi kunci/kredensial |
|---|---|---|
| .50 / .60 (Cloud Shell) | kunci admin bersama | `~/.ssh/akses-vps-cloudshell-admin` (opsi `from="10.66.66.1",restrict,pty`) |
| **Pi 4B** | **kunci SSH `ssh pi4b`** | `~/.ssh/pi4b-admin` (opsi `from="10.66.66.1",restrict,pty`); password sudah tak disimpan |
| Browser API (.60) | Bearer token | `~/.config/browser-api/credentials.env` (ditanam ke `.env` .60 oleh bring-up) |
| Laptop SUARAHATI | kunci SSH | `~/.ssh/laptop-suarahati-cdp` |
| DB-VPS | kunci SSH | `docs/.local-credentials/db-vps_ed25519` |

## Prosedur operasi

### Menyalakan node terjadwal
- **Cloud Shell (.50/.60):** user buka Cloud Shell akun bersangkutan → paste
  bootstrap (`~/key-testing-cloudshell/<akun>-bootstraps.sh`) → tunnel+SSH naik →
  jalankan bring-up (`bring-up-browser.sh` untuk .60 dari akses-vps; `bring-up-analyzer.sh`
  di .50). Host key Cloud Shell BERUBAH tiap VM baru → `ssh-keygen -R <ip>` + accept-new.
- **Pi 4B:** colok daya → boot → semua service naik zero-touch → `ssh pi4b` siap.
  Host key Pi PERSISTEN di SD (tetap lintas reboot, ganti hanya saat reflash).

### Mematikan Pi 4B (contoh, node rawan panas)
```
# sudo Pi butuh password admin (bukan NOPASSWD) — suapkan via stdin sekali pakai:
ssh pi4b "echo '<password-admin-Pi>' | sudo -S -p '' poweroff"
```
`poweroff` menghentikan OS (panas minimal) tapi papan Pi 4B **tidak memutus daya
dari colokan** — cabut adaptor kalau ingin nol panas/daya. Boot berikutnya
zero-touch. (Password admin Pi TIDAK disimpan di repo/skrip; ada di memori
operator / password manager.)

### Cek kesehatan saat node ON
Jalankan health-report terkait (`pi-health-report.sh` / `browser-health-report.sh`).
Untuk Pi: pastikan `throttled=0x0` & suhu rendah **sebelum** menjalankan beban
berat (RAG ingest ~75mnt, dir_scan penuh, wifi-capture).

## Konsekuensi yang diterima (sadar)

- Layanan pada node terjadwal (analyzer .50, browser .60, SpiderFoot/RAG Pi)
  hanya tersedia saat node ON. Kerja on-demand, bukan 24/7.
- Konsentrasi kepercayaan naik: **akses-vps** (kunci admin + kunci API) dan
  **DB-VPS** (semua data) jadi target bernilai tertinggi → prioritas hardening
  & backup (lihat `docs/08-security-hardening-checklist.md`, `docs/10-backup-strategy.md`).

## TODO / hardening opsional

- **Pi:** `PasswordAuthentication no` di sshd (kunci sudah jalan; Pi punya akses
  fisik sebagai jaring pengaman). Belum dilakukan — keputusan user.
- **Redmi Note 5:** verifikasi benar-benar bisa diandalkan sebagai node 24/7
  (riwayat: LCD+touch pernah mati total, proyek scrcpy tertunda).
- **Backup DB-VPS itu sendiri:** DB-VPS kini titik tunggal untuk seluruh histori
  growth + antrean → pertimbangkan backup off-site DB-VPS.
