# 07 — Struktur Folder Project (Repo `akses-vps`)

```
akses-vps/
├── README.md
├── docker-compose.reference.yml
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
│   └── 11-deployment-recommendations.md
├── mikrotik/
│   └── routeros-chr.rsc
├── nginx/
│   ├── nginx.conf
│   ├── conf.d/
│   │   ├── acs.domain.com.conf
│   │   ├── api.domain.com.conf
│   │   ├── mqtt.domain.com.conf
│   │   ├── cwmp.domain.com.conf
│   │   ├── grafana.domain.com.conf
│   │   └── prometheus.domain.com.conf
│   └── snippets/
│       ├── security-headers.conf
│       ├── proxy-params.conf
│       └── rate-limit.conf
├── certbot/
│   ├── README.md
│   └── renew-hook.sh
├── mosquitto/
│   ├── config/
│   │   ├── mosquitto.conf
│   │   └── acl.conf
│   ├── data/            # persistent volume (gitignored)
│   └── log/             # gitignored
├── mongodb/
│   ├── mongod.conf
│   └── init/
│       └── 01-create-users.js
├── genieacs/
│   ├── genieacs.env.example
│   └── examples/
│       ├── preset-default-config.json
│       ├── provision-set-wifi.js
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
│   │   ├── middleware/
│   │   │   ├── logging.go
│   │   │   ├── auth.go
│   │   │   └── metrics.go
│   │   └── server/
│   │       ├── server.go
│   │       └── health.go
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

## Konvensi

- Semua file `*.example` **wajib** di-copy manual jadi non-`.example` (`.env`, `genieacs.env`) sebelum deploy — file asli berisi secret tidak boleh masuk git.
- `mosquitto/data`, `mosquitto/log`, `proto/gen`, dan seluruh `*.env` (tanpa `.example`) masuk `.gitignore`.
- Penomoran di `docs/` menandakan urutan baca yang disarankan, bukan urutan implementasi wajib.
