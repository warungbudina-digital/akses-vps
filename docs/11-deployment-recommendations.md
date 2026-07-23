# 11 — Rekomendasi Deployment Production

## Topologi yang Dipakai: Docker Engine Langsung di Host VPS

Desain awal dokumen ini mempertimbangkan MikroTik CHR (RouterOS Cloud Hosted
Router) sebagai edge router/firewall, dengan dua varian: CHR menjalankan
seluruh container (RouterOS Container feature), atau CHR sekadar router di
depan host Docker. **Keduanya butuh CHR jalan sebagai guest VM, yang artinya
butuh nested virtualization (KVM/VT-x) di-expose oleh hypervisor VPS.**

Pada instance nyata (AKSES-VPS), hypervisor **tidak** meng-expose
VT-x/AMD-V ke guest (`grep vmx/svm /proc/cpuinfo` kosong, `/dev/kvm` tidak
ada) — CHR tidak bisa dijalankan dengan wajar (hanya lewat emulasi software
QEMU/TCG yang sangat lambat, tidak layak untuk router). Detail lengkap
temuan ini ada di `docs/12-wireguard-vpn.md`.

**Topologi yang benar-benar dipakai:**

```
Internet -> VPS public IP -> UFW (host Linux, default-deny, whitelist
                              22/tcp, 7547/tcp, 51820/udp)
                                   |
                                   v
                              Docker Engine (host VPS Linux)
                              docker-compose.reference.yml dijalankan
                              LANGSUNG (bukan cuma referensi), lengkap
                              healthcheck + restart policy
```

Firewall/NAT edge yang di desain awal direncanakan lewat RouterOS sekarang
ditangani dua hal:
- **UFW** (host) — default-deny, whitelist port eksplisit, plus `fail2ban`
  untuk brute-force SSH.
- **Cloudflare Tunnel** (`cloudflared`) — TLS publik + proteksi edge untuk
  domain UI/API (`acs`, `api`, `fs.obc-crypto.com`), menggantikan peran
  certbot/Let's Encrypt lokal. Koneksi keluar saja ke edge Cloudflare,
  tidak ada port tambahan yang perlu di-publish untuk domain-domain ini.
- **WireGuard** (`wg0`, native kernel Linux) — bukan pengganti firewall
  edge, tapi jalur terpisah untuk akses admin/privat (lihat
  `docs/12-wireguard-vpn.md` dan `docs/15-alur-akses-wireguard.md`).

Kalau di masa depan migrasi ke VPS provider yang **memang** meng-expose
nested virtualization, CHR sebagai edge router tetap bisa dipertimbangkan
lagi sebagai opsi arsitektur — tapi itu keputusan baru untuk lingkungan
baru, bukan sesuatu yang dipertahankan sebagai kode/config siap pakai di
repo ini.

## Sizing VPS Awal
| Skala (jumlah CPE aktif) | vCPU | RAM | Disk | Catatan |
|---|---|---|---|---|
| < 500 | 4 | 8 GB | 80 GB SSD | Sesuai sizing di `docs/05-container-topology.md` |
| 500 – 5.000 | 8 | 16 GB | 160 GB SSD | Pisahkan MongoDB ke VM/volume terpisah, pertimbangkan replica set |
| > 5.000 | 16+ | 32 GB+ | 320 GB+ NVMe | genieacs-cwmp perlu > 1 instance di belakang load balancer L4 (mis. HAProxy/nginx `stream` module ke beberapa backend cwmp) |

## Performa Tinggi, Resource Rendah
1. **genieacs-cwmp** adalah bottleneck utama saat mass-inform — beri CPU limit lebih tinggi dibanding service lain, dan pertimbangkan multiple replica di belakang nginx `upstream` dengan `least_conn` bila CPE > 2.000.
2. **MongoDB** — pastikan index (`mongodb/init/01-create-users.js`) terpasang; index yang hilang adalah penyebab #1 GenieACS lambat saat device banyak.
3. **Redis** dipakai untuk cache ringan (rate-limit, session) — bukan primary store, jadi `maxmemory-policy allkeys-lru` aman diset agar tidak OOM.
4. **Nginx** `worker_processes auto` + `sendfile`/`tcp_nopush` sudah di-tune di `nginx/nginx.conf`; jangan aktifkan modul yang tidak dipakai (mis. modul image processing) untuk kurangi footprint.
5. **UFW/conntrack di host** — untuk trafik established/related bervolume tinggi, pastikan `nf_conntrack_max` cukup besar (`sysctl net.netfilter.nf_conntrack_max`) supaya tidak jadi bottleneck saat mass-inform CPE; ini pengganti peran FastTrack RouterOS di desain awal.

## Kemudahan Maintenance
- Semua image di-pin ke tag spesifik (bukan `:latest`) sebelum go-live — `latest` di file referensi ini sengaja dipakai untuk kejelasan dokumentasi, ganti ke versi terkunci (mis. `mongo:7.0.12`) saat deploy sungguhan.
- CI/CD minimal: build `grpc-server` image → push ke registry privat → `docker compose pull && docker compose up -d --no-deps grpc-server` (zero-downtime untuk service stateless).
- Staging environment terpisah (VPS kecil) untuk uji upgrade GenieACS/MongoDB sebelum ke production.
- Dokumentasikan setiap perubahan UFW/WireGuard yang signifikan (bukan cuma di-`iptables`/`wg` langsung tanpa jejak) — lihat `docs/12-wireguard-vpn.md` untuk konvensi registrasi peer via script, bukan edit manual.

## Skalabilitas Jangka Panjang
- Kalau CPE terus bertambah, pisahkan **data plane** (mongodb, redis) ke VM/managed service terpisah dari **control plane** (genieacs-*, grpc-server, nginx) agar bisa di-scale independen.
- Pertimbangkan MongoDB replica set (1 primary + 2 secondary) begitu jumlah device membuat downtime maintenance Mongo terasa mahal.
- `grpc-server` stateless — gampang di-scale horizontal di belakang nginx `upstream` begitu traffic API meningkat.
