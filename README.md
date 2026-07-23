# akses-vps — TR-069/GenieACS Production Architecture

Arsitektur production-ready untuk sistem TR-069/GenieACS yang berjalan
sebagai Docker Compose langsung di host VPS Linux — firewall/NAT edge
ditangani UFW (host) + Cloudflare Tunnel (TLS publik), akses admin/privat
lewat WireGuard native. Tidak memakai MikroTik CHR/RouterOS di jalur
manapun (lihat `docs/01-architecture.md` dan `docs/11-deployment-recommendations.md`
untuk alasannya — hypervisor VPS tidak expose nested virtualization/KVM).

## Mulai Dari Sini

1. Baca `docs/01-architecture.md` s/d `docs/06-component-explanation.md` untuk memahami desain.
2. `docs/07-project-structure.md` — peta seluruh repo ini.
3. `docs/08-security-hardening-checklist.md` — **wajib** dicentang sebelum go-live.
4. `docs/11-deployment-recommendations.md` — sizing VPS & rekomendasi operasional.
5. `docs/12-wireguard-vpn.md` + `docs/15-alur-akses-wireguard.md` — akses admin/privat via WireGuard.

## Struktur Singkat

| Folder | Isi |
|---|---|
| `docs/` | Dokumentasi arsitektur, diagram, checklist, strategi |
| `nginx/` | Reverse proxy: TLS, rate-limit, security header, per-subdomain |
| `mosquitto/` | MQTT broker: auth, ACL, TLS |
| `mongodb/` | Config + init script (user least-privilege, index) |
| `genieacs/` | Env config + contoh preset/provision/virtual parameter |
| `freeradius/` | RADIUS AAA server: `clients.conf` per-PoP, schema Postgres |
| `grpc-server/` | Golang gRPC service (source lengkap, Dockerfile, Makefile) |
| `monitoring/` | Prometheus, Loki, Promtail, Grafana provisioning |
| `backup/` | Script backup harian + restore |
| `wireguard/` | Script registrasi/deregistrasi client VPN, setup client |
| `docker-compose.reference.yml` | Referensi dependency graph seluruh service |

## Quick Start (development lokal maupun production — sama, Docker Compose)

```bash
cp .env.example .env
cp genieacs/genieacs.env.example genieacs/genieacs.env
# isi semua CHANGE_ME di kedua file di atas

docker compose -f docker-compose.reference.yml up -d
# atau ./deploy.sh (auto-generate secret yang masih CHANGE_ME)
```

Untuk sizing VPS dan rekomendasi operasional production, lihat
`docs/11-deployment-recommendations.md`.

## Keamanan

Jangan commit file `*.env` (non-`.example`), `mosquitto/config/passwd`, atau
sertifikat privat. Sudah diatur di `.gitignore`. Ganti seluruh nilai
`CHANGE_ME` / `domain.com` sebelum deploy ke production.
