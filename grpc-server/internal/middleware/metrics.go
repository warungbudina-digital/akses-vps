package middleware

import (
	"context"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"google.golang.org/grpc"
)

var (
	RequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "grpc_server_requests_total",
			Help: "Total gRPC requests processed, by method and status code.",
		},
		[]string{"method", "code"},
	)

	RequestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "grpc_server_request_duration_seconds",
			Help:    "gRPC request latency distribution.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"method"},
	)
)

func init() {
	prometheus.MustRegister(RequestsTotal, RequestDuration)
}

// UnaryMetricsInterceptor mengekspos counter+histogram per method ke
// Prometheus (di-scrape dari endpoint HTTP /metrics, lihat internal/server).
func UnaryMetricsInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		start := time.Now()
		resp, err := handler(ctx, req)

		code := "OK"
		if err != nil {
			code = "ERROR"
		}
		RequestsTotal.WithLabelValues(info.FullMethod, code).Inc()
		RequestDuration.WithLabelValues(info.FullMethod).Observe(time.Since(start).Seconds())

		return resp, err
	}
}
