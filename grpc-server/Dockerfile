# ---- Stage 1: build ----
FROM golang:1.22-alpine AS builder

RUN apk add --no-cache git ca-certificates

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" -o /out/grpc-server ./cmd/server

# ---- Stage 2: runtime (distroless, non-root, minimal attack surface) ----
FROM gcr.io/distroless/static-debian12:nonroot AS runtime

WORKDIR /app
COPY --from=builder /out/grpc-server /app/grpc-server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

USER nonroot:nonroot

EXPOSE 50051 8443

# Health check dilakukan lewat HTTP /healthz (grpc_health_probe bisa dipakai
# juga jika image punya binary tsb; distroless tidak punya shell/curl).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/app/grpc-server", "-healthcheck"]

ENTRYPOINT ["/app/grpc-server"]
