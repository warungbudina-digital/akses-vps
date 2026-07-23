# 06 — Penjelasan Setiap Komponen

## 1. grpc-server (Golang)
API internal/eksternal berbasis gRPC (+ opsional gRPC-Gateway untuk REST/JSON). Tugas: menjembatani integrasi pihak ketiga ke GenieACS/MQTT tanpa mengekspos NBI GenieACS langsung ke publik, menerbitkan event device ke MQTT, cache di Redis untuk rate-limit & session. Lihat `grpc-server/README.md` untuk detail kode.

## 2. Mosquitto (MQTT Broker)
Broker pesan untuk event real-time (mis. status device, command dari backend ke agent lapangan). Autentikasi username/password wajib, TLS di port 8883, ACL per-topic per-user, listener WebSocket (9001) untuk klien browser lewat nginx.

## 3. Nginx Reverse Proxy
Satu-satunya pintu masuk publik. Melakukan TLS termination, HTTP/2, proxy WebSocket (upgrade header), gzip, rate-limiting (`limit_req_zone`), security headers (HSTS, CSP, X-Frame-Options, dst), proxy buffering yang di-tune, serta access/error log terstruktur (dikirim ke Loki via Promtail).

## 4. TLS Publik — Cloudflare Tunnel, bukan Certbot

Desain awal dokumen ini memakai Let's Encrypt/Certbot untuk TLS publik.
Deployment nyata sekarang memakai **Cloudflare Tunnel** sebagai gantinya
(lihat komponen 11 di bawah) — tidak ada Certbot, tidak ada volume
sertifikat lokal, tidak ada folder `certbot/` di repo ini. Alasan migrasi:
menghindari ketergantungan renewal cron + reload nginx yang bisa gagal
diam-diam, dan sekaligus menghilangkan kebutuhan publish port 443/80 ke
WAN sama sekali untuk domain UI/API.

## 5. GenieACS Slim (cwmp, ui, fs, nbi)
- **genieacs-cwmp** (`:7547`): endpoint yang menerima Inform dari CPE, implementasi protokol CWMP.
- **genieacs-nbi** (`:7557`): REST API Northbound — dipakai UI dan integrasi eksternal (termasuk grpc-server) untuk CRUD device, task, preset, provision.
- **genieacs-fs** (`:7567`): file server (firmware, config file) yang dirujuk task Download, backed oleh GridFS di MongoDB.
- **genieacs-ui** (`:3000`): dashboard admin berbasis web untuk operator.

## 6. MongoDB
Database utama GenieACS (koleksi `devices`, `tasks`, `presets`, `provisions`, `files`, `faults`, `virtualParameters`). Dijalankan dengan auth aktif (`--auth`), replica set opsional (untuk production sebaiknya minimal 1 primary + 1 secondary jika resource memungkinkan), `data-net` isolated.

## 7. Redis
Cache & ephemeral store: rate-limit counter untuk grpc-server, session token blacklist (JWT revocation), pub/sub ringan bila diperlukan tanpa membebani Mosquitto.

## 8. Monitoring (Prometheus, Grafana, Loki, Promtail)
- **Prometheus**: scrape metrics dari grpc-server (`/metrics`), nginx (via `nginx-prometheus-exporter`), mongodb (`mongodb_exporter`), node/container (`cadvisor`/`node_exporter`).
- **Grafana**: dashboard terpusat (CPU/RAM/Network per container, MQTT throughput, GenieACS inform rate, gRPC latency, Mongo ops).
- **Loki + Promtail**: centralized logging — semua container log ke stdout/stderr, Promtail men-tail Docker log driver dan push ke Loki, di-query lewat Grafana Explore.

## 9. UFW (Host Firewall)
Firewall native Linux di host VPS — default-deny, whitelist eksplisit
(`22/tcp`, `7547/tcp`, `51820/udp`). Menggantikan peran firewall/NAT edge
yang di desain awal direncanakan lewat MikroTik CHR — CHR tidak dipakai di
VPS ini karena hypervisor tidak meng-expose nested virtualization/KVM
(lihat `docs/01-architecture.md` dan `docs/12-wireguard-vpn.md`).
Dilengkapi `fail2ban` untuk brute-force SSH.

## 10. WireGuard (wg0)
VPN native kernel Linux (bukan container) untuk akses **admin/privat** —
terpisah total dari trafik produksi TR-069/GenieACS. Dipakai untuk reach
LAN pribadi di belakang perangkat MikroTik fisik milik client (`ltap-mini`),
akses langsung ke host VPS, dan kontrol smartphone via ADB. Detail
konfigurasi di `docs/12-wireguard-vpn.md`, contoh alur trafik lengkap di
`docs/15-alur-akses-wireguard.md`.

## 11. Cloudflare Tunnel (cloudflared)
Menangani TLS publik untuk domain UI/API (`acs`, `api`, `fs.obc-crypto.com`)
— menggantikan Let's Encrypt/certbot lokal. Koneksi outbound-only dari host
ke edge Cloudflare, tidak ada port inbound tambahan yang perlu dibuka di
UFW untuk domain-domain ini.
