# 03 — Diagram Komunikasi Antar Service

```mermaid
sequenceDiagram
    participant CPE as CPE (TR-069 Device)
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

    CPE->>NG: HTTPS Inform (cwmp.domain.com:443)
    NG->>CWMP: proxy_pass genieacs-cwmp:7547
    CWMP->>DB: read/write device data
    CWMP-->>NBI: emit task queue event (via DB)
    AD->>NG: HTTPS acs.domain.com
    NG->>UI: proxy_pass genieacs-ui:3000
    UI->>NBI: REST calls genieacs-nbi:7557
    NBI->>DB: query/update devices, presets, provisions
    CPE->>NG: HTTP download firmware (fs.domain.com)
    NG->>FS: proxy_pass genieacs-fs:7567
    FS->>DB: read file metadata (GridFS)

    GR->>DB: (optional) read device summary for API
    GR->>RD: cache session/rate-limit counters
    GR->>MQ: publish device events
    MQ-->>GR: subscribe command topics
    AD->>NG: HTTPS api.domain.com (gRPC-Web/REST gateway)
    NG->>GR: proxy_pass grpc-server:50051 (h2c/HTTP2)
```

## Matriks Komunikasi (siapa boleh bicara ke siapa)

| From \ To | nginx | genieacs-cwmp | genieacs-nbi | genieacs-fs | genieacs-ui | mongodb | redis | mosquitto | grpc-server | prometheus |
|---|---|---|---|---|---|---|---|---|---|---|
| Internet | ✅ (443,80,7547) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| nginx | - | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ (WS) | ✅ | ✅ (opsional, dashboard internal) |
| genieacs-cwmp/nbi/fs/ui | ❌ | - | - | - | - | ✅ | ❌ | ❌ | ❌ | - |
| grpc-server | ❌ | ❌ | ✅ (opsional, integrasi) | ❌ | ❌ | ✅ (opsional) | ✅ | ✅ | - | - |
| prometheus | ❌ | scrape :9100/metrics | scrape | scrape | scrape | exporter | exporter | exporter | scrape /metrics | - |
| promtail | membaca log lokal semua container (docker socket/log driver) → forward ke loki | | | | | | | | | |

Prinsip **zero trust antar container**: hubungan di atas tidak otomatis "boleh" hanya karena satu Docker network — tetap ditegakkan lewat:
- Docker network internal terpisah (`db-net` untuk mongodb/redis, `edge-net` untuk nginx↔service, tidak semua container ikut semua network).
- Autentikasi wajib di setiap service (Mongo auth, Redis `requirepass`, Mosquitto user/ACL, gRPC JWT + internal API key, GenieACS NBI dibatasi hanya diakses dari `genieacs-ui`/`grpc-server` via network policy, bukan lewat publik).
