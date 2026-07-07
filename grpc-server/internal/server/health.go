package server

import (
	"context"

	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

// HealthServer implementasi minimal grpc.health.v1 — dipakai oleh
// orchestrator (Docker healthcheck / RouterOS container healthcheck) dan
// load balancer untuk cek liveness/readiness.
type HealthServer struct {
	healthpb.UnimplementedHealthServer
	ready bool
}

func NewHealthServer() *HealthServer {
	return &HealthServer{ready: true}
}

func (h *HealthServer) SetReady(ready bool) {
	h.ready = ready
}

func (h *HealthServer) Check(ctx context.Context, req *healthpb.HealthCheckRequest) (*healthpb.HealthCheckResponse, error) {
	if !h.ready {
		return &healthpb.HealthCheckResponse{Status: healthpb.HealthCheckResponse_NOT_SERVING}, nil
	}
	return &healthpb.HealthCheckResponse{Status: healthpb.HealthCheckResponse_SERVING}, nil
}

func (h *HealthServer) Watch(req *healthpb.HealthCheckRequest, stream healthpb.Health_WatchServer) error {
	status := healthpb.HealthCheckResponse_SERVING
	if !h.ready {
		status = healthpb.HealthCheckResponse_NOT_SERVING
	}
	return stream.Send(&healthpb.HealthCheckResponse{Status: status})
}
