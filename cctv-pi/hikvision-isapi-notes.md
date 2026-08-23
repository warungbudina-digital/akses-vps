# Catatan ISAPI Hikvision — DVR DS-7216HGHI-K1 (`192.168.60.240`)

> Dikumpulkan 2026-08-23 via audit+optimasi langsung dari Pi 4B (`ssh pi4b`, subnet sama krn `wlan0` di WiFi "ruang tamu" — lihat [[project_rpi4b_setup]]). Auth semua endpoint di bawah: **Digest**, `admin`/`qwerty1408` (⚠️ SAMA dgn password WiFi "ruang tamu" — reuse berisiko, rekomendasi ganti, lihat [[project_pi_cctv_audit]]). Base URL: `http://192.168.60.240` (port 80; port 8000 juga buka tapi tak dites, kemungkinan sama).

Firmware V4.71.411 (build 231207). Endpoint/kuirk di bawah SPESIFIK utk model+firmware ini — Hikvision beda model/firmware bisa beda perilaku, jangan asumsikan identik di device lain tanpa verifikasi ulang.

## Endpoint yang TERBUKTI (GET, aman baca)
| Endpoint | Isi |
|---|---|
| `/ISAPI/System/deviceInfo` | Model, serial, MAC, firmware |
| `/ISAPI/Security/users` | Daftar akun |
| `/ISAPI/System/Video/inputs/channels` | Daftar 16 channel + resolusi + status video (NO VIDEO kalau kosong) |
| `/ISAPI/Streaming/channels/<101,201,...>` | Config encoding per channel (101=ch1 main, 201=ch2 main, dst — pola `<channel>01`) |
| `/ISAPI/ContentMgmt/record/tracks/<id>` | Jadwal rekam LENGKAP (lihat bagian jadwal di bawah) |
| `/ISAPI/ContentMgmt/Storage` | Status HDD (capacity/freeSpace dlm MB) |
| `/ISAPI/Image/channels/<id>` | Brightness/contrast/saturation/hue/sharpness |
| `/ISAPI/System/Video/inputs/channels/<id>/motionDetection` | Config motion detection (region/sensitivity/targetType human,vehicle) |
| `/ISAPI/System/Network/interfaces/1/ipAddress` | IP/gateway/DNS |
| `/ISAPI/System/Network/EZVIZ` | Status Hik-Connect/EZVIZ cloud (nama internal ISAPI = "EZVIZ", BUKAN "HikConnect"/"Hiddns" — banyak nama endpoint tebakan umum di internet SALAH utk firmware ini, `System/Network/HiDdnsCfg` dkk semua 404) |
| `/ISAPI/System/Network/ddns`, `/ISAPI/System/Network/Ehome` | Fitur cloud/DDNS LAIN (beda dari EZVIZ, keduanya disabled di device ini, tak relevan utk Hik-Connect) |
| `<endpoint>/capabilities` | **SELALU cek ini dulu sebelum PUT** — kasih tahu `opt="val1,val2,..."` valid + `min`/`max` range. Contoh: `/ISAPI/ContentMgmt/record/tracks/101/capabilities`, `/ISAPI/Image/channels/1/capabilities`, `/ISAPI/System/Network/EZVIZ/capabilities` |

## Endpoint yang TERBUKTI bisa DITULIS (PUT), sudah dipakai live
- `PUT /ISAPI/Image/channels/<id>` — ubah sharpness/brightness/dst (flat XML, gampang, TAK PERNAH bermasalah).
- `PUT /ISAPI/Streaming/channels/<id>` — ubah bitrate/resolusi/fps encoding (flat XML, gampang).
- `PUT /ISAPI/ContentMgmt/record/tracks/<id>` — ubah jadwal rekam (XML BESAR+NESTED, lihat kuirk khusus di bawah — WAJIB baca sebelum coba).
- `PUT /ISAPI/ContentMgmt/Storage/hdd/<id>/format` — format HDD (body KOSONG, method PUT bukan GET — GET balik `403 methodNotAllowed` yg justru jadi petunjuk path benar tapi method salah). **DESTRUKTIF, konfirmasi user dulu.**

## ⚠️ KUIRK #1: PUT record/tracks — jangan "bersihkan" XML GET sebelum PUT balik
**Jebakan mahal (buang byk percobaan sebelum sadar):** respons GET utk `/ISAPI/ContentMgmt/record/tracks/<id>` itu XML BESAR (150+ baris, nested `TrackSchedule`>`ScheduleBlockList`>`ScheduleAction` ×7 hari + `CustomExtensionList`>`HolidaySchedule`). Insting pertama liat ini "kotor" (tiap elemen bawa `xmlns=` redundan, ada 1 elemen bocor `opt="..."` dari capabilities) dan coba dibersihkan (strip xmlns/opt) sebelum PUT balik — **JANGAN, ini yang bikin PUT gagal** dgn error `statusCode:6 "Invalid XML Content" / "Tag NNN is invalid (two root tags)"`.

**Cara benar (TERBUKTI, diverifikasi lewat isolasi bertahap):**
1. **PUT balik hasil GET 100% VERBATIM (tanpa ubah apa pun) DULU** sbg baseline test — kalau ini SUKSES (`statusCode:1 OK`), berarti format XML aslinya SUDAH BENAR, jangan disentuh strukturnya sama sekali.
2. Edit HANYA nilai teks yang mau diubah (`sed`/string-replace biasa), JANGAN reformat/strip atribut apa pun di elemen lain.
3. Kalau PUT masih gagal SETELAH langkah 1&2 (verbatim sukses, tapi versi ter-edit gagal) — masalahnya di NILAI yang dipilih, bukan format XML. Lanjut ke kuirk #2.

## ⚠️ KUIRK #2: enum yang "resmi valid" di capabilities belum tentu diterima runtime
Field `ActionRecordingMode`/`DefaultRecordingMode` py capabilities `opt="CMR,MOTION,ALARM,EDR,ALARMANDMOTION,AllEvent"`. **`MOTION` dan `AllEvent` KEDUANYA DITOLAK** (`illegalXXX`-style rejection dibungkus pesan generik "two root tags" yg MENYESATKAN — bukan literal soal XML). **`EDR` (Event Driven Recording) yang ternyata BENAR** — device ini butuh nama enum spesifik itu utk "rekam saat event/motion", bukan `MOTION` yg namanya kelihatan lebih intuitif. **Pelajaran: kalau 1 opsi enum "yg kelihatan paling masuk akal namanya" ditolak, JANGAN nyerah — coba SEMUA opsi lain di `opt=` list satu-per-satu**, nama tak selalu representatif thd implementasi firmware asli.

**Cara ganti continuous→event-triggered (reusable, teruji di 9 channel):**
```bash
curl --digest -u admin:PASSWORD "http://DVR_IP/ISAPI/ContentMgmt/record/tracks/<101|201|301|...>" -o track.xml
sed "s/CMR/EDR/g" track.xml > track-edr.xml
curl --digest -u admin:PASSWORD -X PUT -H "Content-Type: application/xml" \
  --data-binary @track-edr.xml "http://DVR_IP/ISAPI/ContentMgmt/record/tracks/<id>"
```
Channel ID pattern: `101`=ch1 main stream, `201`=ch2, ..., `1001`=ch10 (`(channel_number)*100 + 1`). Catatan: `DefaultRecordingMode` top-level TETAP balik `CMR` walau ikut di-sed jadi EDR — tampak field fallback yg dikunci device, TAK berpengaruh ke behavior asal 7 `ActionRecordingMode` (jadwal harian) sudah full EDR (cover 100% waktu).

## ⚠️ KUIRK #3: `verificationCode` EZVIZ WAJIB diisi kode fisik dari stiker device
`PUT /ISAPI/System/Network/EZVIZ` dgn `enabled=true` tapi `verificationCode` kosong → ditolak `illegalVerificationCode` (dibungkus pesan sama "two root tags" yg menyesatkan lagi — SELALU curiga pesan generik ini sbg validasi-value, BUKAN literal masalah XML, based on pattern kuirk #2 & #3 sama2 begini). Kode ini **TERCETAK FISIK di stiker DVR** (dekat QR code/serial number, biasa 6-12 karakter, format sesuai `min="6" max="12"` di capabilities) — **TAK BISA ditebak/dibuat sendiri**, harus baca fisik dari user. `verificationCodeModify:false` di capabilities = kode ini FIXED per-device, bukan bebas dipilih.

**Status per 2026-08-23: EZVIZ MASIH `enabled:false`, menunggu user kasih kode dari stiker fisik DVR sebelum bisa lanjut aktivasi.**

## Info tambahan berguna
- **DNS device ini `192.168.1.1` BUKAN sisa basi** — itu DNS server pusat (kemungkinan Pi-hole/AdGuard) yg dipakai LINTAS SEMUA WiFi di rumah ini (Pi sendiri dpt DNS sama dr DHCP "ruang tamu", terbukti resolve `google.com` sukses). **Jangan buru-buru curiga "stale config" cuma krn IP-nya beda subnet dari device** — verifikasi dulu apakah itu genuinely functioning resolver (`dig @<ip> <hostname>`) sebelum "memperbaiki" sesuatu yg sebenarnya sudah benar. (Pelajaran dari kesalahan diagnosa sesi ini sendiri — sempat coba "fix" DNS yg ternyata tak rusak.)
- Interface `addressingType:dynamic` (DHCP) → PUT ke `ipAddress`/DNS fields DITERIMA (`statusCode:1 OK`) tapi **DIAM-DIAM TAK PERSISTEN** (kalah oleh DHCP renewal berikutnya) — kalau memang perlu override static, harus ubah `addressingType` ke `static` dulu, PUT langsung ke field DNS saat mode dynamic itu percuma (tak error, tapi juga tak nempel).
