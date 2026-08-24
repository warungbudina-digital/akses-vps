# Audit Smart TV Changhong `192.168.60.234` ("Living Room TV")

> Diaudit 2026-08-24 dari Pi 4B (`ssh pi4b`, `wlan0` di WiFi "ruang tamu" — lihat [[project_rpi4b_setup]]). Subnet sama dgn DVR Hikvision [[project_pi_cctv_audit]] & modem ZTE [[project_zte_modem_audit]].

## Identitas device
| | |
|---|---|
| Model (internal) | `AI_PONT` (product `DVB92`, device `redwood`) |
| Manufacturer | Changhong (Hongkong) Trading Limited |
| Nama di jaringan | "Living Room TV" |
| Chipset | MediaTek **MT5867** (platform reference "redwood") |
| MAC | `AC:AC:E2:52:1F:A7` |
| Koneksi | Ethernet kabel (`ethernet_connected:true`), IP `192.168.60.234` |
| Android | **11 (R)**, build `RTMA.250416.071`, tanggal build 2025-06-11 |
| Security patch | 2025-06-01 (~14 bulan stale per tgl audit) |
| Cast stack | Chromecast built-in, `cast_build_revision 3.72.446070` |

## Port terbuka (full scan 1-65535)
| Port | Servis | Keterangan |
|---|---|---|
| 8008 | HTTP (DIAL) | `/ssdp/device-desc.xml` + `/setup/eureka_info` bocor info device TANPA AUTH (nama, cast revision, uptime, public key RSA) — risiko rendah, cuma fingerprinting |
| 8009 | TLS (CastV2) | Protokol Google Cast — casting media jalan out-of-box tanpa pairing (memang desain Chromecast built-in) |
| 6466 | TLS | Android TV Remote channel (data) |
| 6467 | TLS | Android TV Remote pairing — **handshake protokol sukses penuh (pairing_request_ack → options → configuration_ack) TAPI TV tidak pernah menampilkan popup PIN di layar** — kesimpulan: skin Android TV Changhong ini tidak mewire UI dialog utk servis resmi Google ini (daemon jaringan jalan, UI-nya tidak diimplementasi). **Jalur ini MENTOK, jangan diulang** — pakai ADB (lihat di bawah) sbg gantinya. |
| 9000, 8443 | TLS | Widevine DRM provisioning (cert asli `O=Google Inc, OU=Widevine`, issuer `Changhong TV redwood Mediatek t56 Cast ICA`) — bukan attack surface, murni DRM |
| 35841, 40933 | tcpwrapped | Tak merespons probe HTTP/TLS — protokol biner internal, tak diinvestigasi lanjut (ROI rendah) |
| 56789, 56790 | HTTP | Server jetty-style, semua path balas 404 generik — API lokal companion-app, endpoint aktif belum ditemukan |
| 5555 | ADB | **TERTUTUP secara default** — baru terbuka setelah USB debugging diaktifkan manual di menu TV (lihat di bawah). Tak ada toggle "Network debugging" terpisah di build ini — perilaku Android TV standar: toggle "USB debugging" ITU SENDIRI yang membuka ADB daemon di TCP 5555 (karena TV tak punya port USB-ke-PC konvensional). |

**Tak ada** port 22/23/80 (admin web) terbuka secara default — postur jaringan default cukup bersih.

## ✅ Kontrol remote — SUKSES via ADB (bukan Android TV Remote Service)

**Jalur yang GAGAL:** Android TV Remote Service resmi Google (port 6466/6467, dipakai app "Android TV Remote Control"/Google Home "your remote"). Protokol level network 100% sukses tapi TV tak pernah tampilkan PIN di layar — **batasan firmware/skin Changhong**, bukan soal jaringan. Sudah dicoba berkali-kali (TV mati→nyala, request diulang) tetap tak muncul.

**Jalur yang BERHASIL — ADB via jaringan:**
1. User aktifkan **Developer Options** di TV (Settings → Device Preferences → About → tekan "Build" 7x).
2. User aktifkan toggle **"USB debugging"** di menu Developer Options (build ini TIDAK punya toggle "Network debugging" terpisah — cuma USB debugging, tapi itu SUDAH cukup buka port 5555 di jaringan).
3. Dari Pi: `adb connect 192.168.60.234:5555` → awalnya `unauthorized` (butuh approve popup RSA fingerprint di layar TV — popup INI berhasil muncul, beda dgn Android TV Remote Service yg gagal tampil).
4. User approve popup di TV → `adb devices` balik status `device` (fully authorized).
5. **TERBUKTI LIVE**: kirim `input keyevent KEYCODE_VOLUME_UP/DOWN` → user konfirmasi lihat indikator volume naik-turun beneran di TV.
6. **TERBUKTI LIVE lanjutan**: `am start -a android.settings.SYSTEM_UPDATE_SETTINGS` → berhasil buka halaman System Update di TV (screenshot diambil via `adb shell screencap`).

**Kapabilitas ADB yang didapat:** full `input keyevent`/`input tap` (setara D-pad + sentuh), `am start` (buka activity apa pun termasuk Settings pages), `screencap`/`screenrecord`, `pm list packages` (126 paket terpasang), install/uninstall APK (`adb install`/`adb uninstall` — sideload app dimungkinkan). **TIDAK ada root** (`adb root` → "adbd cannot run as root in production builds", `su` tak ditemukan) — postur produksi standar, akses tetap dibatasi shell biasa (`shell` user, bukan `root`).

**Catatan reusable:** SETELAH toggle "USB debugging" TV kembali OFF (atau TV reboot), port 5555 akan tertutup lagi — perlu aktifkan ulang toggle-nya di TV kalau mau akses ADB lagi nanti. Sertifikat otorisasi ADB Pi (`~/.android/adbkey`) kemungkinan tetap tersimpan di TV kalau user pilih "Always allow" saat approve, jadi popup approve mungkin tak muncul lagi di percobaan berikutnya (perlu diverifikasi ulang sesi depan).

## 🎉 Temuan besar: OTA System Upgrade tersedia — Android 11 → 14

Field `has_update:false` di DIAL `/setup/eureka_info` **MENYESATKAN** — itu cuma status firmware Cast/Chromecast, BUKAN status OS Android penuh. Saat halaman System Update dibuka via ADB, ternyata ada **upgrade OS besar tersedia**:

- **Dari Android R (11) ke Android U (14)** — lompatan 3 versi major.
- Ukuran: **1.02 GB**.
- Handler: `com.google.android.gms.update.SystemUpdatePanoActivity` (OTA lewat mekanisme Google Play services, bukan updater custom Changhong).
- Status awal: "Waiting to download" dgn tombol "Download".
- **✅ 2026-08-24: Download DIPICU via ADB** (`input tap` pada tombol Download, koordinat diverifikasi presisi dari screenshot 1280x720 asli — resolusi PNG = resolusi fisik, tak ada scaling) → status berubah jadi **"Downloading"**, tombol jadi "Pause" — proses terkonfirmasi berjalan (screenshot before/after tersimpan).
- **PENTING**: TV harus tetap menyala + tersambung listrik sampai proses selesai (download → instal → reboot otomatis). JANGAN dimatikan di tengah proses (peringatan eksplisit di layar: "may not restart" kalau listrik terputus).
- **Progres terpantau (2026-08-24)**: Download 1.02GB → **selesai 100% dlm hitungan menit** (kemungkinan cache lokal ISP/CDN cepat) → "Verifying" → "Installing... Step 1 of 2" → TV **reboot total** (unreachable ping beberapa menit) → **✅ BERHASIL SEMPURNA**, TV online kembali dgn Android 14. **Catatan teknis**: `adb shell screencap` sempat HANG/timeout beberapa kali persis saat proses download/verify berat — TV kemungkinan throttle I/O buat proses lain saat OTA jalan, bukan tanda ADB terputus (`adb devices`/`shell echo` tetap responsif normal di saat sama). Kalau perlu screenshot progress OTA sesi depan, kasih timeout lebih longgar (15-20 detik) drpd curiga koneksi putus.

### ✅ HASIL AKHIR UPGRADE (dikonfirmasi pasca-reboot)
| | Sebelum | Sesudah |
|---|---|---|
| Android | 11 (R) | **14 (U)** |
| Security patch | 2025-06-01 (~14 bulan stale) | **2026-06-01** (~2.5 bulan) |
| Build | `RTMA.250416.071` (2025-06-11) | `UKNV.260514.001` (2026-05-14) |

**ADB reconnect pasca-reboot: LANGSUNG status `device` tanpa perlu approve popup ulang** — konfirmasi kuat sertifikat otorisasi ADB ("Always allow from this computer") **persisten melewati reboot + OTA major version** (tersimpan di partition yg tak ikut ter-wipe). Ini berarti akses ADB dari Pi ke TV ini sekarang genuinely permanen selama toggle USB debugging tak dimatikan manual dan cert tak dihapus manual dari sisi TV.

## Kesimpulan audit
- ✅ Postur jaringan default bersih (tak ada admin-web/telnet/ADB terbuka tanpa campur tangan user).
- 🟡 Info device bocor tanpa auth via DIAL (`:8008/setup/eureka_info`) — risiko rendah, sekadar fingerprinting.
- ⚠️ Android TV Remote Service resmi (PIN pairing) **tak berfungsi** di firmware ini — batasan skin OEM, bukan bisa difix dari sisi jaringan.
- ✅ **Kontrol remote penuh via ADB BERHASIL** setelah user aktifkan USB debugging manual sekali — reusable ke depan (asal toggle tetap ON / TV tak direset).
- 🎉 **Upgrade OS besar (Android 11→14) ditemukan & dipicu** — pertama kali ketahuan kalau melihat lewat DIAL API saja (yg bilang sudah "up to date").
- Security patch sebelum upgrade sudah 14 bulan stale — upgrade ke Android 14 akan membawa patch jauh lebih baru + fitur baru.
