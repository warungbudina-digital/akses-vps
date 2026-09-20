# Checklist Optimasi CCTV — DVR Hikvision DS-7216HGHI-K1

> DVR `192.168.60.240` (WiFi "ruang tamu"), 16-ch Turbo-HD, FW V4.71.411, 9 kamera aktif (ch1-5,7-10), 1 HDD ~466GB. Diakses via ISAPI dari Pi 4B (`admin`/`qwerty1408`, Digest). Status per 2026-09-20.

## ✅ Sudah dikerjakan
- [x] **Mode rekam EDR (event-driven)** semua channel — retensi jauh lebih panjang dari continuous 24/7 (dulu ~5.5 hari). `ActionRecordingMode=EDR`.
- [x] **Motion detection human+vehicle** aktif (sensitivitas 80) — dasar EDR.
- [x] **Sharpness 5** semua channel; bitrate channel WD1 (ch3,5) diturunkan sesuai resolusi.
- [x] **Label OSD channel** diisi sesuai lokasi (lihat `hikvision-isapi-notes.md`).
- [x] **NTP aktif** (2026-09-20) — `timeMode` manual→NTP (`time1.google.com`), jam terkoreksi ~33 mnt & auto-sync. Timestamp akurat untuk barang bukti.
- [x] **Substream** terkonfigurasi (~200kbps/15fps) untuk remote/HP hemat bandwidth.
- [x] **UPnP OFF** — device tak auto-forward port ke internet.

## ⏳ Storage & retensi (bottleneck: 1 HDD penuh, freeSpace 0)
- [ ] Ganti HDD ke surveillance-grade lebih besar (WD Purple / Seagate SkyHawk 4-8TB) — model K1 cuma 1 bay, tak bisa tambah HDD internal.
- [ ] Turunkan fps/bitrate mainstream channel non-kritis (mis. 25→15fps) bila retensi masih kurang.
- [ ] Rapikan **region motion** ke area penting saja → kurangi false-trigger EDR yang boros storage.
- [ ] Pantau `freeSpace` beberapa hari untuk ukur retensi nyata mode EDR.

## ⏳ Kualitas malam / IR
- [ ] **Kamera 08 (Arah Kantor): perbaiki daya** — malam `NO VIDEO` = brown-out saat IR nyala. Ganti adaptor/kabel 12V, atau ganti unit bila IR board rusak. (lihat health-check di `hikvision-isapi-notes.md`)
- [ ] Tambah IR illuminator eksternal untuk area luas gelap; jaga lensa/kaca IR bersih; hindari pantulan IR dari dinding/kaca di depan kamera.
- [ ] Catatan: day/night+IR kamera analog dikontrol KAMERA sendiri, bukan DVR (tak ada endpoint ISAPI-nya).

## ⏳ Keandalan
- [ ] **Pasang UPS** untuk DVR + kamera — cegah brown-out (relevan ke kamera 08) & korupsi HDD saat listrik kedip.
- [ ] Monitor **S.M.A.R.T HDD** berkala via ISAPI (`/ISAPI/ContentMgmt/Storage/hdd/1`) — deteksi dini HDD aus.

## ⏳ Keamanan
- [ ] **Ganti password `qwerty1408`** — saat ini SAMA dengan password WiFi "ruang tamu"; pakai password unik & kuat (rekaman CCTV = high-value).
- [ ] Jangan port-forward DVR ke internet — untuk remote pakai Hik-Connect P2P / VPN.
- [ ] Cek firmware lebih baru dari V4.71.411 (Des 2023) di situs Hikvision.
- [ ] Verifikasi anti-bruteforce/illegal-login-lock aktif.

## Endpoint ISAPI yang berguna
- Waktu: `GET/PUT /ISAPI/System/time` (+ `/time/ntpServers`)
- Storage: `GET /ISAPI/ContentMgmt/Storage/hdd/1`
- Rekam: `GET/PUT /ISAPI/ContentMgmt/record/tracks/<ch>01`
- Encoding: `GET/PUT /ISAPI/Streaming/channels/<ch>01` (main) / `<ch>02` (sub)
- Snapshot cek: `GET /ISAPI/Streaming/channels/<ch>01/picture`
- Motion: `GET/PUT /ISAPI/System/Video/inputs/channels/<ch>/motionDetection`
