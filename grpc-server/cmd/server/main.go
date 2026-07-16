// Command server adalah entrypoint grpc-server: gRPC di :50051 (h2, TLS
// opsional — biasanya TLS di-terminate di nginx dan link internal plain h2c),
// HTTP di :8443 untuk /healthz, /metrics (Prometheus), dan
// /v1/radius/accounting (webhook FreeRADIUS rlm_rest, lihat
// internal/server/http_radius_accounting.go).
package main

import (
	"context"
	"crypto/tls"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"

	"github.com/warungbudina/akses-vps/grpc-server/internal/auth"
	"github.com/warungbudina/akses-vps/grpc-server/internal/config"
	"github.com/warungbudina/akses-vps/grpc-server/internal/genieacs"
	"github.com/warungbudina/akses-vps/grpc-server/internal/middleware"
	"github.com/warungbudina/akses-vps/grpc-server/internal/server"
	"github.com/warungbudina/akses-vps/grpc-server/internal/store"
	"github.com/warungbudina/akses-vps/grpc-server/pkg/logger"
)

// mongoConnectRetryInitial/Max control the backoff for reconnecting to
// MongoDB in the background when it isn't reachable at startup — doubles
// each attempt up to the max. Kept short at the low end because the common
// case (see docs/13-accel-ppp-integration.md race) is mongo finishing its
// own init a few seconds after grpc-server starts on a full-stack restart.
const (
	mongoConnectRetryInitial = 2 * time.Second
	mongoConnectRetryMax     = 30 * time.Second
)

func main() {
	// Mode "-healthcheck": dipanggil oleh Docker/RouterOS container HEALTHCHECK.
	// Image runtime pakai distroless (tanpa shell/curl/wget), jadi self-check
	// paling sederhana adalah binary yang sama memanggil endpoint lokalnya sendiri.
	if len(os.Args) > 1 && os.Args[1] == "-healthcheck" {
		runHealthcheckProbe()
	}

	cfg := config.Load()
	log := logger.New(cfg.LogLevel, cfg.LogFormat)

	jwtManager := auth.NewJWTManager(cfg.JWTSecret, cfg.JWTIssuer, 24*time.Hour)
	genieACSClient := genieacs.NewClient(cfg.GenieACSNBIURL)

	// ctx is created here (rather than right before the serve loop, as
	// before) so the mongo background-retry goroutine below can share it
	// and exit cleanly on shutdown instead of retrying forever.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// mongoStoreRef is the live store, if any. Read by the shutdown path to
	// Close() whichever store ended up connected — the initial one, or one
	// obtained later by the retry goroutine.
	var mongoStoreRef atomic.Pointer[store.MongoStore]
	var mongoStore *store.MongoStore
	if cfg.MongoURI != "" {
		connectCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		ms, err := store.NewMongoStore(connectCtx, cfg.MongoURI)
		cancel()
		if err != nil {
			// Not fatal: this reproducibly happens on a full-stack restart,
			// since docker-compose's depends_on only waits for the mongodb
			// container to start, not for mongod to actually be accepting
			// connections yet. Serve everything else now and keep retrying
			// mongo in the background instead of leaving
			// LinkSubscriberSession permanently unavailable until someone
			// manually restarts this container.
			log.Warn("failed to connect to mongodb on startup, will retry in background; LinkSubscriberSession unavailable until then", "error", err)
		} else {
			mongoStore = ms
			mongoStoreRef.Store(ms)
			log.Info("connected to mongodb")
		}
	} else {
		log.Warn("MONGO_URI not set, LinkSubscriberSession will be unavailable")
	}

	unaryInterceptors := []grpc.UnaryServerInterceptor{
		middleware.UnaryLoggingInterceptor(),
		middleware.UnaryMetricsInterceptor(),
		middleware.UnaryAuthInterceptor(jwtManager, cfg.InternalAPIKey),
	}

	var serverOpts []grpc.ServerOption
	if cfg.TLSCertFile != "" && cfg.TLSKeyFile != "" {
		cert, err := tls.LoadX509KeyPair(cfg.TLSCertFile, cfg.TLSKeyFile)
		if err != nil {
			log.Error("failed to load TLS cert/key", "error", err)
			os.Exit(1)
		}
		creds := credentials.NewTLS(&tls.Config{
			Certificates: []tls.Certificate{cert},
			MinVersion:   tls.VersionTLS13,
		})
		serverOpts = append(serverOpts, grpc.Creds(creds))
		log.Info("grpc TLS enabled")
	} else {
		log.Info("grpc TLS disabled (expecting TLS termination upstream, e.g. nginx)")
	}

	grpcServer, health, deviceSvc := server.NewGRPCServer(mongoStore, genieACSClient, unaryInterceptors, serverOpts...)

	if mongoStore == nil && cfg.MongoURI != "" {
		go retryMongoConnect(ctx, cfg.MongoURI, &mongoStoreRef, deviceSvc, log)
	}

	lis, err := net.Listen("tcp", ":"+strconv.Itoa(cfg.GRPCPort))
	if err != nil {
		log.Error("failed to listen", "port", cfg.GRPCPort, "error", err)
		os.Exit(1)
	}

	// ---- HTTP server: healthz + metrics + radius accounting webhook ----
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.Handle("/metrics", promhttp.Handler())
	mux.Handle("/v1/radius/accounting", server.RadiusAccountingHandler(deviceSvc, cfg.InternalAPIKey))
	httpServer := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.HTTPPort),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Info("grpc server starting", "port", cfg.GRPCPort)
		if err := grpcServer.Serve(lis); err != nil {
			log.Error("grpc server stopped with error", "error", err)
		}
	}()

	go func() {
		log.Info("http server starting", "port", cfg.HTTPPort)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("http server stopped with error", "error", err)
		}
	}()

	<-ctx.Done()
	log.Info("shutdown signal received, draining connections")
	health.SetReady(false)

	shutdownCtx, cancel := context.WithTimeout(context.Background(), time.Duration(cfg.ShutdownTimeout)*time.Second)
	defer cancel()

	gracefulStopped := make(chan struct{})
	go func() {
		grpcServer.GracefulStop()
		close(gracefulStopped)
	}()

	select {
	case <-gracefulStopped:
		log.Info("grpc server gracefully stopped")
	case <-shutdownCtx.Done():
		log.Warn("graceful shutdown timeout exceeded, forcing stop")
		grpcServer.Stop()
	}

	_ = httpServer.Shutdown(shutdownCtx)

	if ms := mongoStoreRef.Load(); ms != nil {
		if err := ms.Close(shutdownCtx); err != nil {
			log.Warn("error closing mongodb connection", "error", err)
		}
	}

	log.Info("shutdown complete")
}

// retryMongoConnect keeps attempting to connect to MongoDB with exponential
// backoff until it succeeds or ctx is cancelled (shutdown). On success it
// injects the store into the running gRPC server via setter, so
// LinkSubscriberSession recovers without restarting the container — see the
// startup race this fixes in main()'s initial connect attempt above.
func retryMongoConnect(ctx context.Context, uri string, ref *atomic.Pointer[store.MongoStore], setter server.StoreSetter, log *slog.Logger) {
	backoff := mongoConnectRetryInitial
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}

		connectCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		ms, err := store.NewMongoStore(connectCtx, uri)
		cancel()
		if err != nil {
			log.Warn("mongodb reconnect attempt failed", "error", err, "next_retry_in", backoff)
			if backoff *= 2; backoff > mongoConnectRetryMax {
				backoff = mongoConnectRetryMax
			}
			continue
		}

		ref.Store(ms)
		setter.SetStore(ms)
		log.Info("connected to mongodb (recovered via background retry)")
		return
	}
}

func runHealthcheckProbe() {
	port := os.Getenv("HTTP_PORT")
	if port == "" {
		port = "8443"
	}
	client := http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://127.0.0.1:" + port + "/healthz")
	if err != nil || resp.StatusCode != http.StatusOK {
		os.Exit(1)
	}
	os.Exit(0)
}
