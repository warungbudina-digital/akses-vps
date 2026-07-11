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

### Peer aktif (per 2026-07-11)

| Label | IP tunnel | Perangkat | Status |
|---|---|---|---|
| ltap-mini | `10.66.66.5` | MikroTik RB912R-2nD (RouterOS 7.7) — **client LAN pribadi**, bukan subscriber-facing: `ether1` + switch tambahan ke laptop, IP camera, media streaming saja, `wlan2` tetap disabled. Lihat catatan RouterOS di bawah. | **terhubung** — handshake aktif, ping dua arah OK |
| client20 | `10.66.66.21` | Google Cloud Shell (sesi aktif saat ini) | **terhubung** — handshake aktif |
| client16 | `10.66.66.17` | belum terdokumentasi | terdaftar, idle — handshake terakhir ~6 jam lalu, tidak sedang aktif |
| client1 | `10.66.66.2` | Google Cloud Shell (`agent.obc-crypto.com` lab) | terdaftar, tidak ada handshake tercatat (sesi Cloud Shell kemungkinan tidak sedang jalan — VM Cloud Shell reset ~20 menit setelah sesi berakhir) |
| client2 | `10.66.66.3` | Google Cloud Shell (akun test 2) | terdaftar, tidak ada handshake tercatat (idem client1) |
| client3 | `10.66.66.4` | Google Cloud Shell (akun test 3) | terdaftar, tidak ada handshake tercatat (idem client1) |
| client7 | `10.66.66.8` | belum terdokumentasi | terdaftar, tidak ada handshake tercatat |
| client12 | `10.66.66.13` | belum terdokumentasi | terdaftar, tidak ada handshake tercatat |
| client13 | `10.66.66.14` | belum terdokumentasi | terdaftar, tidak ada handshake tercatat |

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

## Keamanan

- Private key server (`/etc/wireguard/server_private.key`) permission 600, root-only.
- Private key client **tidak disimpan di server** setelah dibagikan ke pemilik device.
- Port 51820/udp satu-satunya port VPN yang terbuka; tidak ada port WireGuard lain.
- **Hub-and-spoke, bukan mesh** (lihat bagian di atas) - blast radius satu client
  yang kompromis dibatasi ke hub saja, tidak menyebar ke client/PoP lain — catatan:
  saat ini ini kontrol client-side saja, lihat catatan di bagian topologi di atas.
