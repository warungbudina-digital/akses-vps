# 08 — Security Hardening Checklist

## Network / Edge

Tidak ada MikroTik CHR/RouterOS di VPS ini (hypervisor tidak expose nested
virtualization — lihat `docs/01-architecture.md`); firewall edge ditangani
UFW di host Linux + WireGuard untuk jalur admin/privat. Item di bawah
sudah diverifikasi live, bukan cuma target:

- [x] UFW default `deny (incoming)`, whitelist eksplisit saja: `22/tcp` (SSH), `7547/tcp` (CWMP), `51820/udp` (WireGuard) — tidak ada `0.0.0.0/0` untuk service lain.
- [x] IPv6 di-whitelist paralel dengan IPv4 untuk ketiga port yang sama (`ufw status` menunjukkan entri `(v6)` untuk masing-masing, jangan sampai IPv6 "lupa" di-filter).
- [x] Hanya `nginx` yang publish port ke host (`7547`); semua service lain (mongodb, redis, genieacs-*, freeradius, radius-db) **tidak** ada published port sama sekali — cek berkala dengan `docker ps` (kolom PORTS harus kosong untuk service ini).
- [x] SSH hanya key-based auth (ed25519), tidak ada password auth aktif — kehilangan satu-satunya private key = lockout total kecuali ada akses console provider (lihat `docs/14-ssh-access-rotation.md`).
- [ ] `fail2ban` saat ini cuma jail `sshd` — pertimbangkan tambahan jail untuk brute-force HTTP auth (nginx `limit_req` sudah membantu, tapi bukan pengganti fail2ban).
- [x] WireGuard hub-and-spoke: tiap peer `AllowedIPs` dibatasi `/32` (kecuali gateway LAN seperti `ltap-mini`), peer tidak bisa saling reach satu sama lain — lihat `docs/12-wireguard-vpn.md`.
- [ ] Untuk trafik volume tinggi (mass-inform CPE), pastikan `nf_conntrack_max` di host cukup besar — tidak ada FastTrack RouterOS di sini, conntrack Linux biasa yang menangani established/related.

## TLS

`nginx` di deployment ini **tidak** terminate TLS sama sekali (tidak ada
`listen ... ssl` di `nginx/conf.d/*.conf`, semua plain `listen 80`/`7547`)
— TLS publik untuk domain UI/API ditangani **Cloudflare Tunnel** di edge,
bukan certbot/Let's Encrypt lokal seperti desain awal. Item TLS jadi dua
kelompok:

- [ ] **Sisi Cloudflare (dashboard Zero Trust/SSL-TLS)**: mode enkripsi minimal "Full" (idealnya "Full (strict)" kalau origin sudah punya cert), TLS 1.2/1.3 minimum, HSTS `includeSubDomains` diaktifkan di edge.
- [x] `nginx/nginx.conf` sudah dibersihkan dari baris `ssl_protocols`/`ssl_ciphers`/`ssl_stapling`/`resolver` yang inert (tidak ada server block yang pakai `listen ssl`) — dihapus, sudah di-reload live tanpa downtime, `nginx -t` valid.
- [ ] CWMP jalur langsung port `7547` (untuk CPE tanpa SNI/TLS modern) **plain HTTP, tanpa TLS sama sekali** — risiko yang diterima sadar untuk kompatibilitas CPE lawas, bukan oversight; pastikan payload yang lewat jalur ini tidak berisi data sensitif di luar protokol TR-069 itu sendiri.
- [ ] MQTT TLS (8883) **saat ini dinonaktifkan** di `mosquitto/config/mosquitto.conf` (cert domain asli belum ada) — kalau diaktifkan lagi, `tls_version tlsv1.3` dan sumber sertifikat perlu direncanakan ulang (bukan lagi dari certbot, folder itu sudah tidak ada).

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
