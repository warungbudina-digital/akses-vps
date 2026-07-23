# 03 — Diagram Komunikasi Antar Service

Tidak ada port `443` yang di-publish di deployment ini — TLS publik untuk
domain UI/API/CWMP ditangani **Cloudflare Tunnel** (`cloudflared`, outbound-only,
nginx cukup plain HTTP `:80` di baliknya), kecuali CWMP yang juga punya jalur
kedua langsung ke port `7547` (untuk CPE lawas tanpa SNI/TLS modern). Lihat
`docs/02-network-diagram.md` untuk port map lengkap.

```mermaid
sequenceDiagram
    participant CPE as CPE (TR-069 Device)
    participant CFD as cloudflared (Cloudflare Tunnel)
    participant NG as nginx
    participant CWMP as genieacs-cwmp
    participant NBI as genieacs-nbi
    participant FS as genieacs-fs
    participant UI as genieacs-ui
    participant DB as mongodb
    participant RD as redis
    participant MQ as mosquitto
    participant GR as grpc-server
    participant AD as Admin (browser)

    Note over CPE,NG: CWMP: dua jalur. (1) via tunnel, TLS di edge Cloudflare.<br/>(2) langsung port 7547, plain HTTP, untuk CPE tanpa SNI/TLS modern.
    CPE->>CFD: HTTPS Inform (cwmp.obc-crypto.com)
    CFD->>NG: plain HTTP :80 (tunnel internal)
    CPE->>NG: HTTP Inform langsung :7547 (bypass tunnel)
    NG->>CWMP: proxy_pass genieacs-cwmp:7547
    CWMP->>DB: read/write device data
    CWMP-->>NBI: emit task queue event (via DB)
    AD->>CFD: HTTPS acs.obc-crypto.com
    CFD->>NG: plain HTTP :80
    NG->>UI: proxy_pass genieacs-ui:3000
    UI->>NBI: REST calls genieacs-nbi:7557
    NBI->>DB: query/update devices, presets, provisions
    CPE->>CFD: HTTPS download firmware (fs.obc-crypto.com)
    CFD->>NG: plain HTTP :80
    NG->>FS: proxy_pass genieacs-fs:7567
    FS->>DB: read file metadata (GridFS)

    GR->>DB: (optional) read device summary for API
    GR->>RD: cache session/rate-limit counters
    GR->>MQ: publish device events
    MQ-->>GR: subscribe command topics
    AD->>CFD: HTTPS api.obc-crypto.com (gRPC-Web/REST gateway)
    CFD->>NG: plain HTTP :80
    NG->>GR: proxy_pass grpc-server:50051 (h2c/HTTP2)
```

## Matriks Komunikasi (siapa boleh bicara ke siapa)

| From \ To | nginx | genieacs-cwmp | genieacs-nbi | genieacs-fs | genieacs-ui | mongodb | redis | mosquitto | grpc-server | prometheus |
|---|---|---|---|---|---|---|---|---|---|---|
| Internet | ✅ via `cloudflared` (outbound-only tunnel, `:80` internal) + `:7547` langsung (UFW allow) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| nginx | - | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ (WS) | ✅ | ✅ (opsional, dashboard internal) |
| genieacs-cwmp/nbi/fs/ui | ❌ | - | - | - | - | ✅ | ❌ | ❌ | ❌ | - |
| grpc-server | ❌ | ❌ | ✅ (opsional, integrasi) | ❌ | ❌ | ✅ (opsional) | ✅ | ✅ | - | - |
| prometheus | ❌ | scrape :9100/metrics | scrape | scrape | scrape | exporter | exporter | exporter | scrape /metrics | - |
| promtail | membaca log lokal semua container (docker socket/log driver) → forward ke loki | | | | | | | | | |

> Baris `prometheus`/`promtail` menggambarkan desain **kalau** profile
> `monitoring` diaktifkan (off by default di VPS ini, lihat
> `docs/09-monitoring.md`) — exporter yang disebut (nginx-exporter,
> mongodb-exporter, dst.) belum ada di `docker-compose.reference.yml` saat ini.

Prinsip **zero trust antar container**: hubungan di atas tidak otomatis "boleh" hanya karena satu Docker network — tetap ditegakkan lewat:
- Docker network internal terpisah (`data-net` untuk mongodb/redis, `edge-net` untuk nginx↔service publik, `app-net` untuk service aplikasi, `radius-net` untuk freeradius/radius-db — tidak semua container ikut semua network, lihat `docs/05-container-topology.md`).
- Autentikasi wajib di setiap service (Mongo auth, Redis `requirepass`, Mosquitto user/ACL, gRPC JWT + internal API key, GenieACS NBI dibatasi hanya diakses dari `genieacs-ui`/`grpc-server` via network policy, bukan lewat publik).
