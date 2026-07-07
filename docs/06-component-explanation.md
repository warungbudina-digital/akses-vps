# 06 — Penjelasan Setiap Komponen

## 1. grpc-server (Golang)
API internal/eksternal berbasis gRPC (+ opsional gRPC-Gateway untuk REST/JSON). Tugas: menjembatani integrasi pihak ketiga ke GenieACS/MQTT tanpa mengekspos NBI GenieACS langsung ke publik, menerbitkan event device ke MQTT, cache di Redis untuk rate-limit & session. Lihat `grpc-server/README.md` untuk detail kode.

## 2. Mosquitto (MQTT Broker)
Broker pesan untuk event real-time (mis. status device, command dari backend ke agent lapangan). Autentikasi username/password wajib, TLS di port 8883, ACL per-topic per-user, listener WebSocket (9001) untuk klien browser lewat nginx.

## 3. Nginx Reverse Proxy
Satu-satunya pintu masuk publik. Melakukan TLS termination, HTTP/2, proxy WebSocket (upgrade header), gzip, rate-limiting (`limit_req_zone`), security headers (HSTS, CSP, X-Frame-Options, dst), proxy buffering yang di-tune, serta access/error log terstruktur (dikirim ke Loki via Promtail).

## 4. Let's Encrypt (Certbot)
Menerbitkan & memperbarui sertifikat otomatis untuk semua subdomain (`acs`, `cwmp`, `mqtt`, `api`, `grafana`, `prometheus`). Mode **webroot** atau **standalone dengan pre/post hook** untuk reload nginx setelah renewal. Sertifikat disimpan di volume bersama yang di-mount read-only ke nginx.

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

## 9. MikroTik CHR
Edge router/firewall: terminasi WAN, NAT, firewall filter+raw, FastTrack untuk trafik established/related, DNS caching, dan (tergantung topologi yang dipilih — lihat `docs/01-architecture.md`) tempat container berjalan atau sekadar router di depan host Docker.
