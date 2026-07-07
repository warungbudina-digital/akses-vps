# 08 — Security Hardening Checklist

## Network / Edge
- [ ] MikroTik firewall filter: default `DROP` di `input` dan `forward`, whitelist eksplisit saja (`mikrotik/routeros-chr.rsc`).
- [ ] RAW firewall buang paket invalid sebelum conntrack (SYN+FIN, FIN tanpa ACK, dst).
- [ ] `admin-allowed` address-list dibatasi ke IP kantor/VPN, bukan `0.0.0.0/0`.
- [ ] SSH & Winbox RouterOS hanya dari `admin-allowed`, port default diganti bila perlu.
- [ ] FastTrack **tidak** diaktifkan untuk trafik yang butuh inspeksi L7 penuh.
- [ ] IPv6 firewall dikonfigurasi paralel dengan IPv4 (jangan sampai IPv6 "lupa" di-filter).
- [ ] Hanya `nginx` yang dst-nat dari WAN; tidak ada service lain yang di-port-forward langsung.

## TLS
- [ ] `ssl_protocols TLSv1.2 TLSv1.3;` — TLS 1.0/1.1 dimatikan.
- [ ] Cipher suite modern (ECDHE + AEAD saja), `ssl_prefer_server_ciphers on`.
- [ ] HSTS aktif dengan `includeSubDomains` dan `preload` (submit ke hstspreload.org setelah stabil).
- [ ] Sertifikat auto-renew tervalidasi jalan (`certbot renew --dry-run` rutin).
- [ ] MQTT TLS (8883) pakai `tls_version tlsv1.3`.

## Authentication & Authorization
- [ ] MongoDB `authorization: enabled`, user least-privilege terpisah per konsumen (`genieacs` readWrite, `grpc_readonly` read-only) — **bukan** root user dipakai aplikasi.
- [ ] Redis `requirepass` diset, tidak pernah bind ke 0.0.0.0 tanpa password.
- [ ] Mosquitto `allow_anonymous false`, ACL per-topic per-user, credential per konsumen (bukan shared password).
- [ ] gRPC: JWT wajib untuk klien eksternal, API key internal untuk service-to-service, keduanya ditegakkan lewat interceptor (bukan opsional per-handler).
- [ ] GenieACS UI: ganti default admin credential segera setelah instalasi, aktifkan strong password policy.
- [ ] Grafana/Prometheus dashboard dibatasi IP admin di level nginx **selain** login aplikasi (defense in depth).

## Container Hardening
- [ ] Semua container custom (`grpc-server`) jalan sebagai **non-root** (`user: 65532:65532` / distroless `nonroot`).
- [ ] `read_only: true` + `tmpfs` untuk direktori yang memang butuh tulis sementara.
- [ ] `security_opt: ["no-new-privileges:true"]` di semua service.
- [ ] Tidak ada container yang mount `docker.sock` kecuali benar-benar perlu (Promtail perlu untuk discovery — batasi read-only, pertimbangkan alternatif seperti Docker logging driver `loki` langsung jika ingin menghindari mount socket).
- [ ] Image base minimal (`alpine`, `distroless`) — kurangi attack surface & ukuran image.
- [ ] Resource limit (CPU/memory) di-set untuk semua container agar satu service bermasalah tidak menghabiskan seluruh resource VPS.

## Secrets
- [ ] Tidak ada secret hard-code di Dockerfile/compose/config yang di-commit — semua lewat `.env` (gitignored) atau secret manager.
- [ ] `.env.example` / `*.env.example` di-commit sebagai template, **bukan** file asli.
- [ ] Rotasi berkala: JWT secret, internal API key, password Mongo/Redis/Mosquitto, minimal setiap 90 hari atau segera setelah dicurigai bocor.
- [ ] Pertimbangkan secret manager eksternal (Vault, SOPS+age, atau minimal Docker secrets) untuk production skala besar, bukan `.env` polos.

## Rate Limiting & Abuse Prevention
- [ ] `limit_req_zone` terpisah untuk trafik UI, API, dan CWMP (rate CWMP lebih longgar karena legitimate burst saat mass-reconnect).
- [ ] `limit_conn` per-IP untuk mencegah satu klien menghabiskan worker connection.
- [ ] Fail2ban (atau address-list RouterOS ala fail2ban di `routeros-chr.rsc`) untuk brute-force SSH/HTTP auth.

## Observability sebagai Kontrol Keamanan
- [ ] Log akses nginx & auth failure masuk Loki, buat alert untuk lonjakan 401/403/429.
- [ ] Alert untuk sertifikat TLS mendekati expired.
- [ ] Alert untuk service down (`up == 0`) — indikasi dini serangan DoS atau crash.

## Operasional
- [ ] Backup harian teruji restore-nya (lihat `docs/10-backup-strategy.md`).
- [ ] Dependency (image Docker, go.mod, npm) di-scan berkala (`trivy`, `govulncheck`, `npm audit`) — jadwalkan di CI.
- [ ] Dokumentasi runbook incident response minimal: siapa dihubungi, cara isolasi container yang dicurigai compromised, cara rotate semua secret sekaligus.
