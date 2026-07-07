# grpc-server

Golang gRPC service yang menjembatani sistem eksternal ke GenieACS NBI dan
Mosquitto, tanpa perlu meng-expose keduanya langsung ke publik.

## Fitur
- gRPC + reflection (`grpcurl` friendly saat dev, matikan reflection di
  production murni dengan menghapus `reflection.Register` bila perlu).
- gRPC Health Checking Protocol (`grpc.health.v1.Health`).
- Middleware: logging terstruktur (slog JSON), Prometheus metrics, JWT/API-key auth.
- Graceful shutdown (SIGINT/SIGTERM → drain → `GracefulStop` dengan timeout).
- Konfigurasi 100% via environment variable (lihat `internal/config/config.go`
  dan `configs/config.yaml` sebagai referensi nilai).
- TLS opsional langsung di gRPC listener (`TLS_CERT_FILE`/`TLS_KEY_FILE`) —
  default-nya TLS di-terminate di nginx dan link internal plain h2c.
- OpenTelemetry-ready: `OTEL_EXPORTER_OTLP_ENDPOINT` disediakan di config;
  wiring tracer provider tinggal ditambahkan di `main.go` begitu exporter
  (Tempo/Jaeger/OTel Collector) tersedia — dibiarkan no-op agar tidak
  menambah overhead saat belum dipakai.

## Menjalankan

```bash
make proto   # generate stub dari proto/device.proto (butuh protoc + plugin go/go-grpc)
make run     # jalankan lokal
make docker-build && make docker-run
```

## Environment Variables Wajib
| Var | Keterangan |
|---|---|
| `JWT_SECRET` | Secret HMAC untuk verifikasi token JWT klien API |
| `INTERNAL_API_KEY` | Key untuk komunikasi service-to-service (mis. dari script GenieACS) |

Lihat `internal/config/config.go` untuk daftar lengkap + default value.
