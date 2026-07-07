// Command server adalah entrypoint grpc-server: gRPC di :50051 (h2, TLS
// opsional — biasanya TLS di-terminate di nginx dan link internal plain h2c),
// HTTP di :8443 untuk /healthz dan /metrics (Prometheus).
package main

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"

	"github.com/warungbudina/akses-vps/grpc-server/internal/auth"
	"github.com/warungbudina/akses-vps/grpc-server/internal/config"
	"github.com/warungbudina/akses-vps/grpc-server/internal/middleware"
	"github.com/warungbudina/akses-vps/grpc-server/internal/server"
	"github.com/warungbudina/akses-vps/grpc-server/pkg/logger"
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

	grpcServer, health := server.NewGRPCServer(unaryInterceptors, serverOpts...)

	lis, err := net.Listen("tcp", ":"+strconv.Itoa(cfg.GRPCPort))
	if err != nil {
		log.Error("failed to listen", "port", cfg.GRPCPort, "error", err)
		os.Exit(1)
	}

	// ---- HTTP server: healthz + metrics ----
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.Handle("/metrics", promhttp.Handler())
	httpServer := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.HTTPPort),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

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
	log.Info("shutdown complete")
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
