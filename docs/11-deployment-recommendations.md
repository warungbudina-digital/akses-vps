# 11 — Rekomendasi Deployment Production

## Dua Topologi yang Didukung

### A. Full RouterOS Container (CHR menjalankan semua container)
**Pilih ini jika**: CHR memang harus jadi satu-satunya VM (lisensi/biaya VPS terbatas ke 1 instance), atau tim sudah sangat familiar RouterOS dan ingin semua kontrol (network+compute) dalam satu tempat.

Kelebihan: satu titik manajemen, isolasi network native RouterOS.
Kekurangan: RouterOS Container belum punya orchestrator setara Compose/K8s — scaling, rolling update, dan dependency ordering harus diatur manual lewat script/scheduler RouterOS; ekosistem monitoring/tooling container kurang matang dibanding Docker Engine murni.

### B. CHR sebagai Edge Router + Host VPS menjalankan Docker (REKOMENDASI untuk production serius)
**Pilih ini jika**: prioritas adalah kemudahan maintenance, observability matang, dan skalabilitas jangka panjang.

Topologi:
```
Internet -> VPS public IP -> MikroTik CHR (VM, firewall/NAT/QoS)
                                   |
                                   v (forward ke bridge/NIC kedua atau
                                      hairpin NAT ke host)
                              VPS Host (Docker Engine + docker-compose.reference.yml
                              dijalankan langsung, bukan hanya referensi)
```
CHR tetap menjalankan **seluruh** firewall filter/raw/NAT/FastTrack seperti didokumentasikan, tapi trafik yang lolos di-forward ke Docker Engine yang berjalan di host VPS (via bridge interface CHR-host, bukan lagi veth per-container). Semua container di `docker-compose.reference.yml` benar-benar dipakai (bukan cuma referensi), lengkap dengan Compose healthcheck, restart policy, dan resource limit.

Kelebihan: full Docker ecosystem (Compose/Swarm/K8s kalau perlu scale lebih jauh), tooling monitoring lebih lengkap, image dari registry publik langsung kompatibel, CI/CD lebih mudah (build & push image, `docker compose pull && up -d`).
Kekurangan: satu layer virtualisasi ekstra (CHR tetap jalan sebagai VM) dibanding native RouterOS hardware.

> **Rekomendasi tim**: mulai dengan **Topologi B** untuk kecepatan development dan maintenance, terutama karena `grpc-server` custom butuh iterasi cepat (build-test-deploy). Topologi A tetap didukung penuh (`mikrotik/routeros-chr.rsc`) untuk kasus di mana constraint infrastruktur mengharuskan semuanya dalam satu CHR.

## Sizing VPS Awal
| Skala (jumlah CPE aktif) | vCPU | RAM | Disk | Catatan |
|---|---|---|---|---|
| < 500 | 4 | 8 GB | 80 GB SSD | Sesuai sizing di `docs/05-container-topology.md` |
| 500 – 5.000 | 8 | 16 GB | 160 GB SSD | Pisahkan MongoDB ke VM/volume terpisah, pertimbangkan replica set |
| > 5.000 | 16+ | 32 GB+ | 320 GB+ NVMe | genieacs-cwmp perlu > 1 instance di belakang load balancer L4 (MikroTik dapat load-balance TCP ke beberapa backend cwmp) |

## Performa Tinggi, Resource Rendah
1. **genieacs-cwmp** adalah bottleneck utama saat mass-inform — beri CPU limit lebih tinggi dibanding service lain, dan pertimbangkan multiple replica di belakang nginx `upstream` dengan `least_conn` bila CPE > 2.000.
2. **MongoDB** — pastikan index (`mongodb/init/01-create-users.js`) terpasang; index yang hilang adalah penyebab #1 GenieACS lambat saat device banyak.
3. **Redis** dipakai untuk cache ringan (rate-limit, session) — bukan primary store, jadi `maxmemory-policy allkeys-lru` aman diset agar tidak OOM.
4. **Nginx** `worker_processes auto` + `sendfile`/`tcp_nopush` sudah di-tune di `nginx/nginx.conf`; jangan aktifkan modul yang tidak dipakai (mis. modul image processing) untuk kurangi footprint.
5. **FastTrack** di MikroTik signifikan menghemat CPU untuk trafik established/related — pastikan tetap aktif di production, hanya nonaktifkan sementara saat debugging paket-level.

## Kemudahan Maintenance
- Semua image di-pin ke tag spesifik (bukan `:latest`) sebelum go-live — `latest` di file referensi ini sengaja dipakai untuk kejelasan dokumentasi, ganti ke versi terkunci (mis. `mongo:7.0.12`) saat deploy sungguhan.
- CI/CD minimal: build `grpc-server` image → push ke registry privat → `docker compose pull && docker compose up -d --no-deps grpc-server` (zero-downtime untuk service stateless).
- Staging environment terpisah (VPS kecil) untuk uji upgrade GenieACS/MongoDB sebelum ke production.
- Dokumentasikan setiap perubahan RouterOS lewat `/export` yang di-commit ke git (`mikrotik/routeros-chr.rsc` sebagai source of truth, bukan hanya hasil klik-klik Winbox).

## Skalabilitas Jangka Panjang
- Kalau CPE terus bertambah, pisahkan **data plane** (mongodb, redis) ke VM/managed service terpisah dari **control plane** (genieacs-*, grpc-server, nginx) agar bisa di-scale independen.
- Pertimbangkan MongoDB replica set (1 primary + 2 secondary) begitu jumlah device membuat downtime maintenance Mongo terasa mahal.
- `grpc-server` stateless — gampang di-scale horizontal di belakang nginx `upstream` begitu traffic API meningkat.
