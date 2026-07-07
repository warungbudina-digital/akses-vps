# akses-vps — TR-069/GenieACS Production Architecture

Arsitektur production-ready untuk sistem TR-069/GenieACS yang berjalan sebagai
container di dalam MikroTik CHR (dengan alternatif topologi CHR-sebagai-edge +
Docker di host VPS — lihat `docs/11-deployment-recommendations.md`).

## Mulai Dari Sini

1. Baca `docs/01-architecture.md` s/d `docs/06-component-explanation.md` untuk memahami desain.
2. `docs/07-project-structure.md` — peta seluruh repo ini.
3. `docs/08-security-hardening-checklist.md` — **wajib** dicentang sebelum go-live.
4. `docs/11-deployment-recommendations.md` — pilih topologi A (full RouterOS Container) atau B (CHR edge + Docker host, direkomendasikan).

## Struktur Singkat

| Folder | Isi |
|---|---|
| `docs/` | Dokumentasi arsitektur, diagram, checklist, strategi |
| `mikrotik/` | Konfigurasi RouterOS CLI (firewall, NAT, container) |
| `nginx/` | Reverse proxy: TLS, rate-limit, security header, per-subdomain |
| `mosquitto/` | MQTT broker: auth, ACL, TLS |
| `mongodb/` | Config + init script (user least-privilege, index) |
| `genieacs/` | Env config + contoh preset/provision/virtual parameter |
| `grpc-server/` | Golang gRPC service (source lengkap, Dockerfile, Makefile) |
| `monitoring/` | Prometheus, Loki, Promtail, Grafana provisioning |
| `backup/` | Script backup harian + restore |
| `certbot/` | Setup & renewal Let's Encrypt |
| `docker-compose.reference.yml` | Referensi dependency graph seluruh service |

## Quick Start (development lokal, topologi Docker Compose)

```bash
cp .env.example .env
cp genieacs/genieacs.env.example genieacs/genieacs.env
# isi semua CHANGE_ME di kedua file di atas

docker compose -f docker-compose.reference.yml up -d
```

Untuk deployment sungguhan ke MikroTik CHR, ikuti `mikrotik/routeros-chr.rsc`
dan `docs/11-deployment-recommendations.md`.

## Keamanan

Jangan commit file `*.env` (non-`.example`), `mosquitto/config/passwd`, atau
sertifikat privat. Sudah diatur di `.gitignore`. Ganti seluruh nilai
`CHANGE_ME` / `domain.com` sebelum deploy ke production.
