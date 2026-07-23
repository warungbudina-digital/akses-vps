# 07 — Struktur Folder Project (Repo `akses-vps`)

```
akses-vps/
├── README.md
├── docker-compose.reference.yml
├── deploy.sh
├── .env.example
├── docs/
│   ├── 01-architecture.md
│   ├── 02-network-diagram.md
│   ├── 03-service-communication.md
│   ├── 04-tr069-request-flow.md
│   ├── 05-container-topology.md
│   ├── 06-component-explanation.md
│   ├── 07-project-structure.md
│   ├── 08-security-hardening-checklist.md
│   ├── 09-monitoring.md
│   ├── 10-backup-strategy.md
│   ├── 11-deployment-recommendations.md
│   ├── 12-wireguard-vpn.md
│   ├── 13-accel-ppp-integration.md
│   ├── 14-ssh-access-rotation.md
│   └── 15-alur-akses-wireguard.md
├── mikrotik/
│   └── routeros-chr.rsc
├── wireguard/
│   ├── client-setup.sh          # dijalankan di client (mis. Cloud Shell)
│   ├── register-client-peer.sh  # dijalankan di server, tambah peer baru
│   ├── deregister-client-peer.sh
│   └── install-adb-tools.sh     # opsional, ADB client di VPS untuk audit Android via wg0
├── nginx/
│   ├── nginx.conf
│   ├── conf.d/
│   │   ├── 00-bootstrap.conf
│   │   ├── 10-api-grpc.conf
│   │   ├── 20-acs.conf
│   │   ├── 21-cwmp.conf
│   │   └── 22-fs.conf
│   └── snippets/
│       ├── security-headers.conf
│       ├── proxy-params.conf
│       └── rate-limit.conf
├── mosquitto/
│   ├── README.md
│   ├── config/
│   │   ├── mosquitto.conf
│   │   ├── acl.conf
│   │   └── passwd           # gitignored, dibuat oleh deploy.sh
│   ├── data/                # persistent volume (gitignored)
│   └── log/                 # gitignored
├── mongodb/
│   ├── mongod.conf
│   └── init/
│       └── 01-create-users.js
├── freeradius/
│   ├── raddb/                # bind-mount ke /etc/freeradius - mayoritas file
│   │   │                      # default FreeRADIUS 3.2 (mods-available/,
│   │   │                      # mods-enabled/, sites-available/, policy.d/, dst.)
│   │   ├── clients.conf       # custom: entri per-PoP (lihat docs/13)
│   │   ├── radiusd.conf
│   │   ├── sites-enabled/
│   │   └── certs/            # gitignored - snakeoil TLS bawaan image, regenerate lokal
│   └── postgres-init/
│       └── 01-schema.sql
├── genieacs/
│   ├── Dockerfile
│   ├── genieacs.env.example
│   └── examples/
│       ├── preset-default-config.json
│       ├── provision-set-wifi.js
│       ├── virtual-parameter-mac-address.js
│       └── virtual-parameter-rssi.js
├── grpc-server/
│   ├── cmd/
│   │   └── server/
│   │       └── main.go
│   ├── internal/
│   │   ├── auth/
│   │   │   └── jwt.go
│   │   ├── config/
│   │   │   └── config.go
│   │   ├── genieacs/
│   │   │   └── client.go
│   │   ├── middleware/
│   │   │   ├── logging.go
│   │   │   ├── auth.go
│   │   │   └── metrics.go
│   │   ├── server/
│   │   │   ├── server.go
│   │   │   ├── health.go
│   │   │   ├── http_devices.go
│   │   │   └── http_radius_accounting.go
│   │   └── store/
│   │       └── mongo.go
│   ├── pkg/
│   │   └── logger/
│   │       └── logger.go
│   ├── proto/
│   │   ├── device.proto
│   │   └── gen/            # generated stubs (gitignored, generated via Makefile)
│   ├── configs/
│   │   └── config.yaml
│   ├── Dockerfile
│   ├── Makefile
│   ├── README.md
│   ├── go.mod
│   └── go.sum
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml
│   ├── loki/
│   │   └── loki-config.yml
│   ├── promtail/
│   │   └── promtail-config.yml
│   └── grafana/
│       └── provisioning/
│           ├── datasources/
│           │   └── datasources.yml
│           └── dashboards/
│               └── dashboards.yml
├── backup/
│   ├── backup.sh
│   ├── restore.sh
│   └── crontab.example
└── .gitignore
```

Tidak ada lagi folder `certbot/` — TLS publik sekarang ditangani Cloudflare
Tunnel (`cloudflared`, konfigurasi cukup lewat `CLOUDFLARE_TUNNEL_TOKEN` di
`.env`), bukan Let's Encrypt lokal. Diagram arsitektur umum di `docs/01` dan
`docs/05` tetap menyebut `certbot` sebagai bagian topologi referensi (opsi
kalau suatu saat deploy tanpa Cloudflare) - itu bukan klaim bahwa folder ini
ada di repo.

## Konvensi

- Semua file `*.example` **wajib** di-copy manual jadi non-`.example` (`.env`, `genieacs.env`) sebelum deploy — file asli berisi secret tidak boleh masuk git.
- `mosquitto/data`, `mosquitto/log`, `mosquitto/config/passwd`, `freeradius/raddb/certs`, `proto/gen`, dan seluruh `*.env` (tanpa `.example`) masuk `.gitignore`.
- `freeradius/raddb/` sebagian besar adalah file default paket FreeRADIUS 3.2 (dikutip utuh dari image resmi supaya bind-mount lengkap) — file yang benar-benar custom untuk `akses-vps` cuma `clients.conf` dan sedikit di `sites-enabled/`.
- Penomoran di `docs/` menandakan urutan baca yang disarankan, bukan urutan implementasi wajib.
