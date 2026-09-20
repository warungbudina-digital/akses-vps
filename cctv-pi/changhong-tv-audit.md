# Audit Smart TV Changhong `192.168.60.234` ("Living Room TV")

> Diaudit 2026-08-24 dari Pi 4B (`ssh pi4b`, `wlan0` di WiFi "ruang tamu" — lihat [[project_rpi4b_setup]]). Subnet sama dgn DVR Hikvision [[project_pi_cctv_audit]] & modem ZTE [[project_zte_modem_audit]].

> **Status per 2026-09-20:** TV sudah **OTA ke Android 14** (lihat seksi OTA di bawah). IP DHCP **bergeser** (`.234` ↔ `.220`) — script `tvctl.sh` cari otomatis lewat MAC. Identitas/versi di tabel bawah = kondisi saat audit awal (pra-OTA); nilai Android 11/patch 2025 sudah usang.

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

## Script kontrol `tvctl.sh` (operasional, di `pi4b:~/tvctl.sh`)

Wrapper ADB reusable, jalankan **di Pi 4B** (adb key Pi ter-otorisasi + satu LAN dgn TV). Aksi: `on | off | toggle | wol | voldown [N] | volup [N] | vol <0-100> | mute | status`. Wrapper hub `akses-vps:~/bin/tv` → `ssh pi4b ~/tvctl.sh $*`. Salinan di repo: [`tvctl.sh`](tvctl.sh).

**Poin desain penting:**
- IP TV **DHCP bergeser** (`.234` ↔ `.220`) → `find_ip()` cari otomatis lewat MAC `ac:ac:e2:52:1f:a7` (`ip neigh`), plus kandidat statis + WG `10.66.66.12`, HANYA terima yg ping-nya hidup.
- Volume ASLI dibaca dari `dumpsys audio` STREAM_MUSIC `streamVolume` (skala 0-100). **`settings get system volume_music` PALSU/statis (selalu 5)** di TV MediaTek ini — jangan dipakai. Terbukti 1 tekan keyevent = 1 unit skala.
- Wakefulness dibaca dari `dumpsys power` (`mWakefulness`). POWER = `keyevent 26`.
- **ADB hanya bisa membangunkan TV dari standby DANGKAL** (dimatikan via `off`/keyevent 26 → WiFi+adbd tetap hidup). Kalau TV dimatikan via **remote fisik** (standby-dalam → `offline`) atau mati-penuh (ping gagal) → **tak ada jalur wake via ADB**; fallback WoL disediakan (`wol`) tapi belum terbukti wake dari mati-penuh. **SOP: kalau mau bisa `on` dari jarak jauh, matikan pakai `tv off`, BUKAN remote.**

**Fix hardening (diaudit + diuji live 2026-09-20):**
1. **`on` tak lagi bisa MEMATIKAN TV yang Awake.** Dulu `[ wake = Awake ] || key 26` → kalau `dumpsys power` gagal-baca (string kosong) padahal TV nyala, POWER malah terkirim → TV mati (kebalikan `on`). Sekarang helper `wake_if_asleep()`: POWER **hanya** dikirim bila state eksplisit `Asleep/Dozing/Dreaming`; kosong/tak dikenal → tidak sentuh + log peringatan. Unit-test 5 kasus lolos (kosong→0 POWER, Asleep/Dozing→1, Awake/garbage→0).
2. **`find_ip()` anti salah-device saat DHCP geser.** Kandidat statis `.234/.220` kini wajib lolos `mac_ok()` (`ip neigh show <ip>` memetakan balik ke MAC TV) setelah ping — cegah `adb connect` ke perangkat lain yg kebetulan pegang IP itu & membalas ping. Entri by-MAC dari `ip neigh` (otoritatif) tetap dicoba duluan; WG `10.66.66.x` dikecualikan (beda L2). Terbukti live: TV `.234` diterima, router `.1` (MAC beda) DITOLAK.
3. **`vol`/`set` wajib argumen eksplisit** — dulu `vol` tanpa angka diam-diam set volume ke 3 (default step-count). Sekarang error + exit 1 sebelum connect.

Kode keluar: `0`=sukses/wake, `2`=gagal wake (remote-off/mati-penuh), `3`=unauthorized (approve popup di layar TV), `10`=TV tak di jaringan, `11`=ADB unauthorized, `13`=standby-dalam (offline).


## Standby & wake jarak jauh — Energy Mode (akar masalah + fix, 2026-09-20)

**Gejala:** `tvctl.sh off` (keyevent 26) membuat standby yg ADB-nya awalnya tetap hidup, TAPI setelah standby beberapa saat TV **lepas total dari jaringan** (ping mati, adb `offline`/hilang dari neigh) → `tvctl.sh on` gagal, WoL tak direspons → butuh remote fisik.

**Akar masalah (ditemukan via `dumpsys power`):**
- TV pakai **Ethernet `eth0`** (`wifi_on=0`; active default network = ETHERNET). Yg mati saat standby = NIC Ethernet, bukan WiFi.
- **Low Power Standby** aktif: `mIsEnabled=true`, `mStandbyTimeoutConfig=5000` (aktif **5 detik** setelah idle+layar mati). Energy Mode default TV = **"Low"** → `mIdentifier=low_energy_use`, `mAllowedFeatures=...NON_NETWORKED_STANDBY_FEATURES` → jaringan+adbd dimatikan ~5s setelah standby. `network_wol=1`/`network_wow=1` ada tapi sia-sia (NIC di-suspend total).

**Fix (TERUJI):** ubah **Energy Mode → "Optimized" (Networked Standby)** di `Settings → System → Power & Energy → Energy saver`, atau via ADB buka `com.android.tv.settings/.device.eco.EnergyModesActivity` lalu DPAD_DOWN→DPAD_CENTER (leanback: pakai DPAD, bukan tap). Policy berubah `low_energy_use` → **`moderate_energy_use`** dgn `NETWORKED_STANDBY_FEATURES` + `com.android.lowpowerstandby.WAKE_ON_LAN`.
- ⚠️ **WAJIB REBOOT TV** agar mode baru berlaku penuh. **Sebelum reboot** mode baru TIDAK efektif (network tetap mati di 35s). **Sesudah `adb reboot`**: uji `off`→tunggu 40s→**ping 5/5 hidup, `tvctl on`→Awake BERHASIL**. Setelan persisten lintas reboot.
- 3 mode tersedia: **Low/Standby** (`low_energy_use`, hemat, network mati di standby), **Optimized/Networked Standby** (`moderate_energy_use`, seimbang — REKOMENDASI), **Increased/Always connected** (paling boros, wake tercepat).

**SOP kontrol jarak jauh (pasca-fix):** matikan selalu via `~/bin/tv off` (BUKAN remote fisik) → standby yg network-nya tetap hidup → `~/bin/tv on` kapan pun berhasil. (Soak berjam-jam / Doze sangat dalam belum diuji, tapi sudah lewat titik aktivasi LPS 5s yg dulu jadi pembunuh.)


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
