# 10 — Strategi Backup

## Cakupan
1. **MongoDB** — `mongodump --archive --gzip` (logical dump, konsisten tanpa stop service).
2. **Konfigurasi GenieACS** — file env statis (preset/provision/virtual parameter sendiri hidup di Mongo, otomatis tercakup di dump #1).
3. **Konfigurasi WireGuard** — `/etc/wireguard` (server keys + `wg0.conf`, satu-satunya salinan state peer/registrasi VPN, tidak ada di git).
4. **Docker named volume lain** — `mongo-data` (raw file, sebagai lapisan kedua selain logical dump), `redis-data`, `mosquitto-data`, `mosquitto-log`, `radius-db-data`; `grafana-data`/`prometheus-data`/`loki-data` ikut *hanya jika* monitoring stack sedang aktif (di-skip otomatis kalau tidak).

Tidak ada backup sertifikat TLS — sejak migrasi ke Cloudflare Tunnel, TLS
publik ditangani Cloudflare edge, tidak ada lagi sertifikat lokal
(Let's Encrypt/certbot) yang perlu disimpan di sini.

## Jadwal
Harian jam 02:00 (low-traffic window) lewat cron di host — lihat `backup/crontab.example`. Skrip: `backup/backup.sh`.

## Retensi
- Lokal: 14 hari (auto-cleanup di akhir `backup.sh`).
- Offsite (opsional, sangat disarankan production): upload ke S3-compatible bucket (`S3_BUCKET` env var) — pertimbangkan retensi lebih panjang di sisi bucket (mis. lifecycle rule 90 hari) karena storage object jauh lebih murah.

## Restore
`backup/restore.sh <folder-backup>` — restore MongoDB otomatis, WireGuard
dipandu manual (butuh root, mencetak instruksi `tar xzf` + restart
`wg-quick@wg0`), volume lain juga dipandu manual (sengaja tidak
auto-overwrite semua volume by default untuk menghindari restore tidak
sengaja menimpa data production yang lebih baru).

## Uji Restore
Backup yang tidak pernah dites restore-nya = tidak ada backup. Jadwalkan **uji restore bulanan** ke environment staging terpisah (VPS kecil terpisah atau VM lokal), verifikasi:
- GenieACS UI bisa login dan menampilkan device list yang sesuai.
- Jumlah device di Mongo hasil restore cocok dengan sumber.
- Nginx bisa serve HTTPS dengan cert hasil restore (tidak expired).

## Sebelum Perubahan Besar
Selain jadwal harian, jalankan `backup.sh` manual sebelum: upgrade major version GenieACS/MongoDB, rotasi/pembersihan massal peer WireGuard, atau migrasi ke VPS lain.
