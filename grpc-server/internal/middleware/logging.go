package middleware

import (
	"context"
	"log/slog"
	"time"

	"google.golang.org/grpc"
)

// UnaryLoggingInterceptor mencatat setiap RPC: method, durasi, status.
// Log terstruktur (via slog default JSON handler) dikonsumsi Promtail->Loki.
func UnaryLoggingInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		start := time.Now()
		resp, err := handler(ctx, req)
		duration := time.Since(start)

		attrs := []any{
			slog.String("method", info.FullMethod),
			slog.Duration("duration", duration),
		}
		if err != nil {
			attrs = append(attrs, slog.String("error", err.Error()))
			slog.Error("grpc_request_failed", attrs...)
		} else {
			slog.Info("grpc_request", attrs...)
		}
		return resp, err
	}
}
