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

## Akses yang didapat client VPN

Peer default (`client1`) diberi `AllowedIPs = 10.66.66.2/32` di sisi server.
Di sisi client, `AllowedIPs` diset ke `10.66.66.0/24, 10.122.31.0/24` — artinya
**split-tunnel**: hanya trafik ke subnet VPN dan jaringan privat 4 VPS
(`10.122.31.0/24`) yang lewat tunnel, trafik internet biasa tetap lewat jalur
normal client. Untuk full-tunnel (semua trafik lewat VPS), ganti AllowedIPs
client jadi `0.0.0.0/0, ::/0`.

Sudah diverifikasi: handshake sukses, ping ke `10.66.66.1` (server) dan
`10.122.31.252` (VPS CLAUDE, lewat NAT/forward) berhasil.

## Menambah client baru

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
