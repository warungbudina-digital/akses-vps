# 12 — WireGuard VPN (AKSES-VPS)

## Kenapa bukan MikroTik CHR

Desain awal (`docs/01-architecture.md`) menyebut opsi CHR sebagai edge router.
Saat implementasi nyata di AKSES-VPS (103.217.144.104), dicek dan
**nested virtualization tidak tersedia**:

```
grep -oE "vmx|svm" /proc/cpuinfo   # kosong
ls /dev/kvm                        # No such file or directory
```

Hypervisor IDCloudHost tidak meng-expose VT-x/AMD-V ke guest, sehingga CHR
(yang butuh KVM) tidak bisa dijalankan dengan wajar di VPS ini (hanya bisa
lewat emulasi software QEMU/TCG yang sangat lambat, tidak layak untuk router).
Karena tujuan sebenarnya adalah **akses VPN**, dipilih **WireGuard native di
kernel Linux** (modul `wireguard` sudah built-in di kernel `6.8.0-134-generic`),
jauh lebih ringan dan sesuai kondisi VPS 2 vCPU/1.9GB ini.

## Konfigurasi

- Interface: `wg0`, subnet VPN: `10.66.66.0/24`
- Server: `10.66.66.1`, listen port `51820/udp`
- Server public key: `Jquw62SGYrgeUJhDcBrbmQ8FkBDj37+ccqi15f9RzyE=`
- IP forwarding aktif (`/etc/sysctl.d/99-wireguard.conf`)
- NAT/MASQUERADE keluar lewat `ens3` (PostUp/PostDown di `/etc/wireguard/wg0.conf`)
- UFW: `51820/udp` dibuka
- Service: `wg-quick@wg0` (systemd, enabled on boot)

## Akses yang didapat client VPN — hub-and-spoke, bukan mesh (update 2026-07-08)

**Topologi saat ini: hub-and-spoke, bukan full mesh.** Setiap client di-*set* dengan
`AllowedIPs = 10.66.66.1/32` di sisi client-nya sendiri (bukan
`10.66.66.0/24, 10.122.31.0/24` seperti versi awal dokumen ini) — artinya
**setiap client cuma bisa reach hub (`10.66.66.1`), tidak bisa reach client
lain**. Ini keputusan sadar, bukan keterbatasan teknis: dipertimbangkan lewat
inversion thinking saat testing client2/client3 — kalau semua peer saling
reachable, satu akun test Google Cloud Shell yang murah/disposable yang
kompromis bisa langsung punya jalur network ke `pop1` begitu PoP sungguhan
tersambung, yang bertentangan langsung dengan prinsip "kompromi satu PoP
tidak membuka semua" di `docs/13`. Kalau suatu saat perlu peer-to-peer,
jadikan itu **exception spesifik** (pasangan peer tertentu), bukan perubahan
blanket ke seluruh mesh, dan PoP tetap harus dikecualikan.

Di sisi server, tiap peer tetap `AllowedIPs = 10.66.66.N/32` masing-masing
(tidak berubah - ini yang menentukan peer mana yang boleh mengklaim source IP
mana, dan sekaligus jadi routing table server untuk tahu paket ke IP mana
diteruskan ke peer mana).

> Catatan: kontrol hub-and-spoke ini saat ini hidup sepenuhnya di *routing
> table masing-masing client* (`AllowedIPs` client cuma `10.66.66.1/32`).
> Server sendiri (`iptables FORWARD -i wg0 -j ACCEPT` / `-o wg0 -j ACCEPT`
> tanpa pembatasan pasangan interface) tidak menolak forwarding wg0↔wg0 —
> jadi ini bukan proteksi kriptografis, tergantung client tidak menambah
> route sendiri ke `10.66.66.0/24`. Belum ada exception peer-to-peer yang
> terdaftar per tanggal dokumen ini.

### Peer aktif (per 2026-07-23)

| Label | IP tunnel | Perangkat | Status |
|---|---|---|---|
| ltap-mini | `10.66.66.5`, `192.168.70.0/24` | MikroTik RB912R-2nD (RouterOS 7.7) — **client LAN pribadi**, bukan subscriber-facing: `ether1` + switch tambahan ke laptop, IP camera, media streaming saja, `wlan2` tetap disabled. Lihat catatan RouterOS di bawah. | **terhubung** — handshake ~1 menit lalu, ping dua arah OK |
| Redmi-Note-5 | `10.66.66.3` | Smartphone Android (Redmi Note 5) — didaftarkan 2026-07-16 (sebelumnya berlabel `redmi-note5-picoclaw`), di-rename ke label bersih 2026-07-23 | **terhubung** — handshake ~1 menit lalu |
| Infinix-Hot-11 | `10.66.66.2` | Smartphone Android (Infinix Hot 11) — didaftarkan 2026-07-20 (sebelumnya berlabel `infinix-smartphone`), di-rename ke label bersih 2026-07-23 | **terhubung** — handshake ~2 menit lalu |
| client50 | `10.66.66.51` | belum terdokumentasi | terdaftar 2026-07-16, idle — handshake terakhir ~5 hari 21 jam lalu |
| client51 | `10.66.66.52` | belum terdokumentasi | terdaftar 2026-07-18, idle — handshake terakhir ~4 hari 16 jam lalu |
| client60 | `10.66.66.61` | belum terdokumentasi | terdaftar 2026-07-19, idle — handshake terakhir ~3 hari 14 jam lalu |
| client61 | `10.66.66.62` | belum terdokumentasi | terdaftar 2026-07-19, idle — handshake terakhir ~2 hari 16 jam lalu |
| client71 | `10.66.66.72` | belum terdokumentasi | terdaftar 2026-07-21, idle — handshake terakhir ~1 hari 13 jam lalu |
| client81 | `10.66.66.82` | belum terdokumentasi | terdaftar 2026-07-21, idle — handshake terakhir ~15 jam lalu |

**Catatan drift 2026-07-11 → 2026-07-23:** peer lama di tabel sebelumnya
(`client20`/`.21`, `client16`/`.17`, `client1`/`.2` lama, `client2`/`.3` lama,
`client3`/`.4`, `client7`/`.8`, `client12`/`.13`, `client13`/`.14`) sudah tidak
ada lagi di `/etc/wireguard/wg0.conf` saat ini — di-deregister di suatu titik
antara kedua tanggal ini tanpa commit dokumentasi yang menyertainya (`wg0.conf`
sendiri tidak pernah masuk git — lihat catatan keamanan di bawah). Slot IP
`10.66.66.2` dan `10.66.66.3` sejak itu didaftarkan ulang untuk device baru
(sekarang `Infinix-Hot-11` dan `Redmi-Note-5`) — kebetulan sama seperti slot
`client1`/`client2` versi lama, tapi itu re-registrasi baru, bukan peer yang
sama. Tabel di atas mencerminkan isi live `wg0.conf` per 2026-07-23, dicek
langsung lewat `wg show wg0` + `wg0.conf`, bukan disalin dari versi sebelumnya.

**`pop1` (`10.66.66.10`) sengaja tidak terdaftar saat ini** — slot lama (didaftarkan
2026-07-08) key-nya hilang saat manual-edit dan sudah di-deregister
(2026-07-11, `deregister-client-peer.sh pop1`) karena tidak bisa dipulihkan dan
tidak ada yang terhubung dengannya. Sempat dipertimbangkan memakai `ltap-mini`
sebagai `pop1` (BNG PPPoE via fitur native RouterOS, pengganti `accel-ppp` yang
memang tidak bisa jalan di RouterOS — lihat `docs/13`), tapi dibatalkan: jaringan
di belakang `ltap-mini` terkonfirmasi cuma perangkat pribadi (laptop/kamera/
streaming), bukan CPE pelanggan, jadi PPPoE-server tidak akan pernah dipakai.
`pop1` didaftarkan ulang nanti (key baru, `register-client-peer.sh pop1
<public-key> 10.66.66.10`) begitu ada hardware PoP sungguhan yang benar-benar
menghadap subscriber — RADIUS client `pop1` di `freeradius/raddb/clients.conf`
(IP `10.66.66.10`, secret) sudah siap dan tidak perlu diubah saat itu terjadi.

**`client4` (`10.66.66.5`, didaftarkan 2026-07-09) hilang/mati** — public key-nya
ke-blank saat proses manual-edit dan tidak ada backup `wg0.conf` yang menyimpan
key aslinya, jadi tidak bisa dipulihkan. IP `10.66.66.5` yang tadinya dicadangkan
untuknya sekarang dipakai ulang oleh `ltap-mini`. Kalau `client4` perlu diaktifkan
lagi, daftarkan sebagai peer baru dengan key baru dan IP lain yang masih kosong.

"Belum terdokumentasi" di atas berarti label ada di `wg0.conf` (via
`register-client-peer.sh`) tapi tidak ada catatan perangkat/tujuannya di mana
pun — untuk registrasi berikutnya, sertakan deskripsi perangkat di komentar
`[Peer]` atau update tabel ini di saat yang sama, supaya tidak menumpuk lagi.

## Menambah client baru

Dua script di `wireguard/` di repo ini mengotomasi proses yang dulu manual:

- **`wireguard/client-setup.sh`** — dijalankan **di client** (mis. Google Cloud
  Shell). Install `wireguard-tools`, generate keypair (persisten, aman dari
  VM recycle Cloud Shell), bawa `wg0` up, verifikasi konektivitas (retry
  sampai berhasil, bukan fire-and-forget), dan opsional setup akses SSH
  langsung lewat tunnel juga. Edit `CLIENT_TUNNEL_IP`/`PEER_LABEL` di bagian
  atas file sebelum dipakai — nilainya sengaja diisi placeholder (`N`) di
  repo ini, harus diisi IP yang benar-benar unik per deployment (cek daftar
  peer di atas dulu). Detail lengkap + alasan tiap keputusan desain ada di
  komentar dalam file itu sendiri (termasuk dua bug nyata yang pernah
  ketemu: resolusi `$HOME`/`whoami` yang salah saat script jalan sebagai
  root, dan race condition saat menulis `authorized_keys` bersamaan).

- **`wireguard/register-client-peer.sh`** — dijalankan **di server** (akses-vps)
  setelah menerima public key dari client. Otomasi proses yang dulu manual
  (append `[Peer]` block, `wg syncconf`, verifikasi ping) plus validasi yang
  ternyata perlu di praktik: menolak kalau public key yang diberikan
  ternyata public key **server sendiri** (kesalahan yang beberapa kali
  kejadian nyata saat testing - orang salah baca output `wg show`), menolak
  duplikat, auto-pilih IP kosong berikutnya kalau tidak diisi manual, dan
  backup `wg0.conf` sebelum diubah.

  ```bash
  sudo ./wireguard/register-client-peer.sh <label> <public-key> [tunnel-ip]
  # contoh:
  sudo ./wireguard/register-client-peer.sh client4 bH3OPgDxCUa0Ew95GTcjEzgEIo7Gc0j4z0DtFpt8qiA=
  ```

Cara manual lama (masih valid, dipakai `register-client-peer.sh` di baliknya):

```bash
wg genkey | tee clientN_private.key | wg pubkey > clientN_public.key
# tambahkan blok [Peer] baru di /etc/wireguard/wg0.conf dengan
# PublicKey = <clientN_public> dan AllowedIPs = 10.66.66.N/32 (IP unik)
sudo wg syncconf wg0 <(wg-quick strip wg0)   # reload tanpa downtime
```

**Peringatan operasional:** beberapa peer di atas sempat rusak (key ke-blank,
seluruh blok `[Peer]` terhapus, key satu peer ke-paste ke blok peer lain)
akibat edit manual langsung ke `wg0.conf` di luar `register-client-peer.sh`/
`deregister-client-peer.sh` (lihat komentar historis di file itu sendiri,
tanggal 2026-07-09). **Selalu pakai kedua script ini**, jangan edit
`wg0.conf` dengan tangan — script sudah menangani backup, validasi, dan
reload atomik yang justru ada untuk mencegah insiden itu.

### Catatan khusus: client RouterOS/MikroTik (mis. `ltap-mini`)

Peer `ltap-mini` (MikroTik RB912R-2nD, RouterOS 7.7) sempat handshake sukses
tapi ping ke `10.66.66.1` selalu timeout dari terminal RouterOS-nya (insiden
2026-07-11). Root cause: **RouterOS tidak otomatis menambahkan route dari
`allowed-address` di `/interface wireguard peers`**, berbeda dengan
`wg-quick` di Linux yang otomatis `ip route add` untuk setiap `AllowedIPs`.
Akibatnya handshake + `persistent-keepalive` tetap jalan normal (paket
keepalive dibuat langsung oleh driver WireGuard, tidak lewat routing table),
tapi trafik IP asli (ping, dst) tidak punya jalur keluar/masuk lewat
interface tunnel sama sekali.

Fix-nya, route harus ditambahkan manual di RouterOS:

```
/ip route add dst-address=10.66.66.1/32 gateway=wg-akses-vps comment="route ke AKSES-VPS hub via WireGuard"
```

(`/32` ke hub saja, bukan `10.66.66.0/24`, supaya tetap konsisten dengan
desain hub-and-spoke di atas.) **Setiap client RouterOS/MikroTik baru
(termasuk hardware PoP sungguhan nanti saat `pop1` didaftarkan ulang) perlu
route manual ini** — checklist setup client MikroTik jadi: buat interface
`wireguard`, tambah peer dengan `allowed-address=10.66.66.1/32`, **plus**
`/ip route add` di atas, baru verifikasi dengan `/ping 10.66.66.1`.

### Audit keamanan & hardening `ltap-mini` (2026-07-11)

Setelah tunnel-nya jalan, dilakukan audit live via SSH langsung ke device
(`10.66.66.5:2222`, lewat tunnel dari akses-vps — WAN `wlan1` sengaja tidak
membuka SSH/Winbox dari internet sama sekali, jadi ini satu-satunya jalur
remote ke device ini). Board terkonfirmasi `LtAP mini` asli (MIPS 24Kc,
64MB RAM, 16MB storage — sangat terbatas, perhatikan kalau mau nambah
konfigurasi/logging di device ini).

**Sudah baik dari awal (dikonfirmasi live, sempat dikira belum di-hardening
dari baca `.rsc` statis saja):**
- `telnet`/`ftp`/`www`/`api`/`api-ssl` semua sudah `disabled` di `/ip service`
  — cuma `ssh` (dipindah ke port `2222`, bukan default `22`) dan `winbox`
  (`8291`) yang aktif.
- `wlan2` terkonfirmasi `disabled` di level interface (bukan cuma ganti SSID).
- Hanya satu user (`full` privilege) — wajar untuk single-operator device,
  tidak perlu dipecah kecuali ada operator lain nanti.

**Diterapkan saat audit (live, terverifikasi tidak memutus akses):**
```
/ip firewall filter set [find comment="allow dari tunnel AKSES-VPS" and chain=input] src-address=10.66.66.1
/ip firewall filter set [find comment="dari tunnel AKSES-VPS" and chain=forward] src-address=10.66.66.1
/ip firewall filter set [find comment="drop invalid" and chain=forward] disabled=no
```
Sebelumnya rule input/forward untuk `in-interface=wg-akses-vps` menerima dari
siapa pun yang bisa reach lewat tunnel, bukan cuma hub — sekarang dibatasi
`src-address=10.66.66.1` (defense-in-depth terhadap gap iptables FORWARD
`wg0`↔`wg0` di server yang belum diperbaiki, lihat catatan di bagian topologi
hub-and-spoke di atas). Rule `drop invalid` di `chain=forward` yang tadinya
`disabled=yes` juga diaktifkan, konsisten dengan `chain=input`.

**Diketahui, sengaja TIDAK diubah (keputusan operator, bukan terlewat):**
- Profil WiFi `wifi-kantor` (dipakai `wlan1` sebagai WAN) masih mengizinkan
  WPA1 (`wpa-psk`) + cipher TKIP yang deprecated, bukan WPA2/AES-only —
  berisiko downgrade attack dari rogue/evil-twin AP. PSK-nya sendiri juga
  lemah (pola kata umum + angka pendek). Tidak diubah karena AP "Kantor"
  di luar kendali langsung, dan device ini cuma bisa diakses remote lewat
  jalur yang bergantung pada `wlan1` — kalau AP asli ternyata butuh WPA1/TKIP,
  memperketat ke WPA2-only bisa memutus WAN dan menghilangkan satu-satunya
  jalur remote ke device ini sampai ada yang datang fisik ke lokasi.
- Firewall `chain=input`/`forward` untuk `in-interface=ether1` (LAN) masih
  accept-all, belum dibatasi ke address-list admin — risiko relatif kecil
  karena cuma `ssh`/`winbox` yang listening sama sekali di seluruh sistem
  (lihat poin "sudah baik" di atas), tapi kalau nanti ada operator lain atau
  device tambahan di LAN yang tidak sepenuhnya dipercaya, ini kandidat
  hardening berikutnya.

**Persistensi:** config RouterOS (termasuk keypair WireGuard di
`wg-akses-vps`) tersimpan permanen di flash device, bukan di RAM — beda
dengan client Google Cloud Shell yang harus di-`.customize_environment`-kan
supaya persistent. Restart/mati listrik **tidak** menghapus config; tunnel
akan reconnect sendiri (`persistent-keepalive`) begitu `wlan1` dapat WAN lagi.
Yang menghapus config: factory reset atau ganti unit hardware (key terikat
ke instance interface, bukan ke device secara umum).

## Keamanan

- Private key server (`/etc/wireguard/server_private.key`) permission 600, root-only.
- Private key client **tidak disimpan di server** setelah dibagikan ke pemilik device.
- Port 51820/udp satu-satunya port VPN yang terbuka; tidak ada port WireGuard lain.
- **Hub-and-spoke, bukan mesh** (lihat bagian di atas) - blast radius satu client
  yang kompromis dibatasi ke hub saja, tidak menyebar ke client/PoP lain — catatan:
  saat ini ini kontrol client-side saja, lihat catatan di bagian topologi di atas.

### Routing ke jaringan DVR eksternal untuk kamera Net1 TBS 2603SE (2026-07-13)
Encoder TBS 2603SE (`192.168.70.217`, LAN `ltap-mini`) perlu diarahkan ke
sebuah DVR/NVR bergaya Hikvision di jaringan kantor lain yang **tidak**
langsung terhubung ke `ltap-mini`. Topologi yang ditemukan saat audit:

```
akses-vps (VPS) --WireGuard--> ltap-mini (10.66.66.5, LAN 192.168.70.0/24)
                                   |
                                   +--wlan1 (WiFi client, wifi-kantor)--> 192.168.1.0/24
                                                                              |
                                                                              +-- 192.168.1.1 (gateway internet kantor, TIDAK
                                                                              |    punya rute balik ke 192.168.60.0/24)
                                                                              +-- 192.168.1.20 (router lokal terpisah, WAN di
                                                                                   192.168.1.0/24, LAN bridge-all di
                                                                                   192.168.60.0/24 - DVR ada di sini)
```

`192.168.1.1` (gateway kantor) tidak tahu cara route ke `192.168.60.0/24`
milik router lokal `192.168.1.20` — dua jaringan itu tidak saling
terhubung di level routing meskipun satu fisik lokasi. Karena `192.168.1.1`
di luar kendali (bukan device kita), fix-nya dilakukan sepenuhnya di
`ltap-mini` pakai static route + NAT (bukan minta perubahan di router
kantor):
```
/ip route add dst-address=192.168.60.0/24 gateway=192.168.1.20 comment=to-DVR-net
/ip firewall nat add chain=srcnat dst-address=192.168.60.0/24 out-interface=wlan1 action=masquerade comment=nat-to-DVR-net
```
Dengan masquerade, trafik ke `192.168.60.0/24` terlihat oleh
`192.168.1.20` datang dari `192.168.1.40` (IP `wlan1` milik
`ltap-mini` sendiri di jaringan kantor) — `192.168.1.20` tidak perlu rute
balik khusus karena itu memang alamat yang langsung terhubung di
`ether1`-nya, dan dia sudah otomatis tahu cara ke `192.168.60.0/24`
(LAN-nya sendiri di `bridge-all`). Setelah rule ini, `ping` dari
`ltap-mini` ke DVR (`192.168.60.240`) berhasil (sebelumnya 100% loss).

**Channel Net1 di TBS diupdate** (via `POST /RPC` JSON-RPC 2.0 milik encoder,
method `enc.update`, bukan lewat RouterOS) — `enable=true`,
`net.decodeV=true`, `net.decodeA=true`, dan `net.path` diarahkan ke
stream channel 1 DVR (URL RTSP lengkap dengan kredensial ada di
`docs/.local-credentials/net1-dvr-camera.env`, **tidak** di-commit —
lihat entri baru di `.gitignore`).

**Belum selesai / known issue:** setelah routing jalan dan channel
diaktifkan, encoder aktif mencoba connect ke DVR (terkonfirmasi lewat
`/ip firewall connection print` di `ltap-mini` — ada exchange TCP
~250-300 byte tiap beberapa detik) tapi belum menghasilkan gambar. Pola yang
diamati (percobaan koneksi manual dari luar makin cepat ditolak DVR seiring
banyaknya percobaan berturut-turut) mengarah ke proteksi
rate-limit/lockout koneksi di sisi DVR, kemungkinan dipicu kombinasi retry
otomatis encoder + percobaan manual saat troubleshooting — bukan masalah
kredensial RTSP yang pasti salah. Sedang menunggu cooldown lalu cek ulang;
kalau masih gagal setelah itu, langkah berikutnya adalah cek pengaturan
lockout IP dan kredensial RTSP terpisah (kalau ada) langsung di web UI DVR.

### Update: pendekatan DVR dibatalkan, konfigurasi di-revert (2026-07-13)
Setelah routing ke DVR berhasil (lihat bagian di atas) tapi gambar Net1
tetap tidak muncul — encoder terus mencoba connect (~250-300 byte exchange
tiap beberapa detik, terkonfirmasi lewat `/ip firewall connection print`)
namun tidak pernah berhasil establish stream, bahkan setelah cooldown 10
menit dengan pola byte exchange yang identik persis (jadi bukan soal
rate-limit sementara, kemungkinan besar kredensial RTSP terpisah dari
kredensial web login, atau path RTSP tidak sesuai standar Hikvision asli
di firmware OEM/clone ini) — diputuskan untuk **tidak jadi memakai DVR
Hikvision ini sebagai sumber Net1/Net2**. Kamera IP akan dipasang langsung
nanti, terhubung ke switch Ruijie, alih-alih lewat DVR di jaringan kantor
lain yang terpisah.

**Semua perubahan terkait di-revert ke kondisi semula:**
- Channel Net1 di TBS: `enable=false`, `net.path` kembali ke placeholder
  pabrik (`rtsp://admin:admin@192.168.1.23/cam/realmonitor?channel=1&subtype=0`,
  sama seperti Net2 yang memang tidak pernah dipakai), `decodeV`/`decodeA`
  kembali `false`.
- Static route (`dst-address=192.168.60.0/24 gateway=192.168.1.20`) dan NAT
  masquerade (`nat-to-DVR-net`) di `ltap-mini` dihapus — tidak ada lagi
  rute ke jaringan DVR dari `ltap-mini`.
- `/ip socks` di `ltap-mini` (sempat diaktifkan sementara untuk diagnostik
  RTSP langsung) dikembalikan ke `disabled`.
- File kredensial `docs/.local-credentials/net1-dvr-camera.env` dihapus,
  sudah tidak relevan.

**Catatan teknis penting untuk kerja berikutnya lewat jalur yang sama:**
saat verifikasi, ditemukan bahwa `/tool fetch ... output=user` RouterOS
kadang **merender ulang string panjang tanpa spasi (URL) dengan menyisipkan
spasi di titik word-wrap** — tidak konsisten/tidak selalu terjadi, dan
tidak terkait lebar terminal (sudah dicoba PTY 30000 kolom, tetap muncul).
Ini murni bug tampilan konsol, bukan korupsi data asli di device — tapi
kalau hasil `output=user` dipakai lagi untuk membangun payload
`enc.update` berikutnya tanpa validasi, field seperti `net.path` bisa
ke-submit dengan korupsi tanpa sadar. Sempat kejadian sekali pada field
`Net2.net.path` (untung tidak dipakai/tidak signifikan) sebelum ketahuan
dan diperbaiki. **Wajib validasi ulang tiap field URL/path (grep untuk
spasi mencurigakan) sebelum submit `enc.update`** kalau proses
serupa diulang nanti. `/tool fetch ... dst-path=` (simpan ke file lokal)
sendiri terbukti reliable/byte-exact; masalah cuma muncul saat memakai
`output=user` untuk preview di konsol. Upaya pakai `src-path=` untuk POST
upload (coba ambil isi file balik lewat HTTP) juga gagal — RouterOS 7.7
selalu mengirim `Content-Length: 0` untuk mode ini, jadi body tidak
pernah benar-benar terkirim (kemungkinan bug/keterbatasan firmware, bukan
masalah di sisi penerima).

### Switch Ruijie terdeteksi di LAN `ltap-mini` (2026-07-13)
Terkait rencana pasang kamera IP langsung (lihat bagian di atas), switch
Ruijie yang akan jadi tempat colok kamera sudah terdeteksi di LAN
`ltap-mini` (`192.168.70.0/24`, interface `ether1` — LAN yang sama dengan
TBS 2603SE) lewat DHCP lease:
- IP: `192.168.70.253`
- Hostname: `RG-ES205GC-C79F47` (seri Ruijie RG-ES205GC)
- MAC: `EC:B9:70:C7:9F:47`

Dicek lewat `/ip dhcp-server lease print detail` di `ltap-mini`, status
`bound`, aktif. Belum ada kamera yang tersambung ke switch ini per catatan
tanggal di atas — begitu kamera terpasang dan dapat IP, channel Net1/Net2
TBS bisa dikonfigurasi mengarah ke situ (ganti pendekatan DVR yang sudah
di-revert).

Catatan tambahan: ada satu device lain di lease yang sama
(`192.168.70.254`, hostname `SuaraHati`, MAC `10:C3:7B:B5:ED:72`,
terdeteksi juga lewat LLDP dengan system-caps repeater/wlan-ap/router) —
kemungkinan AP/router pribadi, bukan bagian dari topologi kamera, belum
diselidiki lebih lanjut.

### Audit laptop `SuaraHati` di LAN `ltap-mini` (2026-07-13)
Device kedua yang terdeteksi di lease `ltap-mini` (`192.168.70.254`,
lihat catatan switch Ruijie di atas) diaudit langsung lewat SSH
(`warungbudina@192.168.70.254`, Win32-OpenSSH — shell default `cmd.exe`,
dipakai `powershell`/`wmic` untuk detail). Akses dari luar LAN-nya lewat
SOCKS4 sementara di `ltap-mini` (`/ip socks`, sama seperti diagnostik RTSP
sebelumnya — dimatikan lagi setelah selesai).

**Hardware:** ASUS X450EA (laptop budget ~2014), AMD E1-2500 APU 2-core/
2-thread @1.4GHz, RAM ~9.4GB (kemungkinan upgrade dari stok, kapasitas
ganjil menandakan kombinasi keping tidak seragam), storage SSD 240GB
(BULLDOZER-240GB, merek generik/OEM) dengan ±153GB free dari 223GB
usable, BIOS AMI `X450EA.303` (2014-02-28).

**OS & software:** Windows 8.1 Pro 64-bit (build 9600, tanggal install
tercatat 2023-12-10 — kemungkinan besar reimage, bukan install asli).
User lokal: `Administrator`, `Guest`, `warungbudina`. Windows Defender
aktif, Windows Firewall ON di ketiga profile (Domain/Private/Public).
Software terpasang yang relevan: Chrome, Edge, VS Code, Google Cloud SDK,
VLC, WinRAR, **RealVNC Viewer**, **Advanced IP Scanner 2.5.1** (network
scanner), AMD Catalyst Control Center, driver Realtek Ethernet +
Qualcomm/Intel Android USB (kemungkinan buat tethering/dev HP). Ada satu
entry tidak jelas: **web control version 3.0.7.7** — nama generik,
fungsinya belum diketahui, perlu ditelusuri kalau sempat.

**Network:** device ini **dual-homed** — WiFi `Wi-Fi-Utama` ke
`192.168.1.30` (jaringan kantor yang sama dipakai WAN `ltap-mini`) **dan**
Ethernet ke `192.168.70.254` (LAN kamera/encoder ini) sekaligus.
`IP Routing Enabled: No` di Windows-nya, jadi tidak aktif nge-bridge dua
jaringan itu, tapi tetap punya presence langsung di keduanya. Port yang
listening: `22` (sshd, jalur akses audit ini), `135/445/139` (RPC/SMB/
NetBIOS standar Windows), `554` (RTSP — dicek ternyata `wmpnetwk.exe`,
built-in Windows Media Player Network Sharing, bukan terkait kamera),
`1025-1030`/`2869`/`5357`/`10243` (RPC dinamis & SSDP/device discovery
standar).

**Temuan yang perlu perhatian:**
1. Windows 8.1 sudah **end-of-life** (extended support berakhir Januari
   2023) — tidak lagi dapat security patch dari Microsoft, terlepas dari
   panjangnya daftar update yang sudah terpasang.
2. Password SSH yang dipakai untuk audit ini (`123`) **sangat lemah** —
   gampang di-brute-force, dan sshd-nya reachable dari seluruh LAN ini.
3. Karena dual-homed, kalau device ini kompromis, dampaknya bisa nyebar
   ke jaringan kantor (`192.168.1.0/24`) sekaligus LAN kamera/encoder ini.
4. Kombinasi RealVNC Viewer + network scanner mengindikasikan device ini
   mungkin dipakai juga sebagai alat admin/akses jaringan — perlu
   dikonfirmasi itu memang disengaja, bukan sisa instalasi lama yang
   terlupakan.

Belum ada tindakan perbaikan yang diterapkan pada audit ini (murni
observasi) — password SSH dan status EOL OS jadi kandidat utama kalau mau
di-follow-up.

### Update audit `SuaraHati`: password SSH diganti, cek port HDMI (2026-07-13)
Follow-up dari audit di atas:

**Password SSH diganti.** Password lama (`123`) diganti dengan password
random kuat (20 karakter, campuran huruf besar/kecil/angka/simbol) lewat
`net user warungbudina` (akun `warungbudina` di laptop ini member grup
Administrators lokal, jadi bisa langsung set tanpa perlu password lama).
Terverifikasi: login dengan password baru berhasil, password lama sudah
ditolak. Password baru disimpan di luar git (lihat `.gitignore`), tidak
dicatat di sini.

**Cek hardware port HDMI.** Diminta audit apakah port HDMI di laptop ini
berfungsi. **Tidak bisa dites fisik dari remote** (butuh display benar-benar
tercolok saat ini) — hasil yang bisa dikumpulkan lewat WMI/registry:
- Driver GPU (AMD Radeon HD 8240): status `OK`, tidak ada error.
- Display yang aktif SEKARANG cuma layar built-in laptop (1366x768,
  EDID `CMN1491`) — dikonfirmasi `VideoOutputTechnology` = internal, bukan
  eksternal.
- Device Manager: tidak ada error terkait GPU/display sama sekali (cuma
  satu error tidak terkait, sisa driver PS/2 mouse yang stale).
- **Riwayat EDID di registry menunjukkan DUA monitor eksternal berbeda**
  (`GSM5B01`, `LKP2C02` — ID panel beda dari layar built-in) pernah
  terdeteksi di masa lalu — bukti kuat salah satu port video eksternal
  laptop ini (HDMI dan/atau VGA, X450EA punya keduanya) **pernah berfungsi**.

**Kesimpulan:** tidak ada indikasi masalah di level driver/OS, dan ada
bukti historis port eksternal pernah jalan — tapi status HDMI secara
spesifik (vs VGA) dan apakah masih berfungsi HARI INI **belum bisa
dipastikan tanpa tes fisik** (colok display asli ke port HDMI-nya
langsung). Perlu verifikasi manual di lokasi kalau mau kepastian penuh.

### Tes HDMI langsung: laptop `SuaraHati` -> TBS 2603SE (2026-07-13)
HDMI laptop `SuaraHati` disambungkan langsung ke input HDMI TBS 2603SE
untuk tes nyata (menyusul catatan "perlu verifikasi manual" di atas).
Dicek dari kedua sisi secara bersamaan:

- **Sisi TBS:** `enc.getInputState` via RPC tetap menunjukkan
  `"avalible": false` untuk channel HDMI — tidak ada sinyal terdeteksi.
- **Sisi laptop:** Windows tetap cuma mendeteksi satu display (layar
  built-in, 1366x768) — tidak ada display kedua yang muncul.
- Dipaksa lewat `DisplaySwitch.exe /extend` supaya Windows coba aktifkan
  output kedua secara paksa — **tidak ada perubahan**, tetap cuma satu
  display terdeteksi.
- Windows Event Log (`System`) dicek untuk event hotplug/PnP di sekitar
  waktu pengetesan — tidak ada event terkait HDMI/display sama sekali,
  cuma driver audio/kernel filter generik dari boot sebelumnya.

**Kesimpulan:** sudah ruled out kemungkinan software/driver di sisi laptop
(driver GPU sehat, forced-extend tidak membantu, tidak ada hotplug event
sama sekali baik dari OS maupun dari status TBS) — mengarah ke **masalah
hardware/kabel**, bukan konfigurasi. Kandidat: kabel tidak terpasang
sempurna/kabel rusak, port HDMI laptop yang fisiknya bermasalah (sejalan
dengan catatan audit sebelumnya — cuma ada bukti HISTORIS port eksternal
pernah jalan, tidak ada bukti aktif saat ini), atau port input HDMI TBS
yang bermasalah.

**Langkah lanjut yang disarankan:** tes port HDMI laptop langsung ke
monitor/TV yang diketahui berfungsi (tanpa lewat TBS) untuk isolasi apakah
masalahnya di laptop atau di TBS — belum dilakukan, perlu di lokasi.
