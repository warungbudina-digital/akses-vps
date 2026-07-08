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

Sudah diverifikasi: handshake sukses, ping ke `10.66.66.1` (server) berhasil
dari beberapa client sekaligus (lihat daftar peer live di bawah).

### Peer aktif (per 2026-07-08)

| Label | IP tunnel | Perangkat | Status |
|---|---|---|---|
| client1 | `10.66.66.2` | Google Cloud Shell (`agent.obc-crypto.com` lab) | terhubung |
| client2 | `10.66.66.3` | Google Cloud Shell (akun test 2) | terhubung |
| client3 | `10.66.66.4` | Google Cloud Shell (akun test 3) | terhubung |
| pop1 | `10.66.66.10` | accel-ppp BNG PoP 1 (lihat `docs/13`) | belum terhubung, menunggu hardware PoP sungguhan |

`client4`/`client5` (`10.66.66.5`/`.6`) dicadangkan untuk testing berikutnya,
belum didaftarkan (belum ada public key nyata).

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

## Keamanan

- Private key server (`/etc/wireguard/server_private.key`) permission 600, root-only.
- Private key client **tidak disimpan di server** setelah dibagikan ke pemilik device.
- Port 51820/udp satu-satunya port VPN yang terbuka; tidak ada port WireGuard lain.
- **Hub-and-spoke, bukan mesh** (lihat bagian di atas) - blast radius satu client
  yang kompromis dibatasi ke hub saja, tidak menyebar ke client/PoP lain.
