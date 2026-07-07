package server

import (
	"context"
	"log/slog"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	devicev1 "github.com/warungbudina/akses-vps/grpc-server/proto/gen"
)

// deviceServiceServer implementasi RPC yang didefinisikan di proto/device.proto.
// Detail integrasi ke GenieACS NBI / MQTT publisher disuntik lewat field,
// bukan hard-coded, supaya gampang di-mock saat unit test.
type deviceServiceServer struct {
	devicev1.UnimplementedDeviceServiceServer

	// genieACSClient, mqttPublisher, dst. — disuntik dari main.go
}

func NewDeviceServiceServer() devicev1.DeviceServiceServer {
	return &deviceServiceServer{}
}

func (s *deviceServiceServer) ListDevices(ctx context.Context, req *devicev1.ListDevicesRequest) (*devicev1.ListDevicesResponse, error) {
	// TODO: query genieacs-nbi (GET /devices) lalu mapping ke Device{}
	return &devicev1.ListDevicesResponse{}, nil
}

func (s *deviceServiceServer) GetDevice(ctx context.Context, req *devicev1.GetDeviceRequest) (*devicev1.Device, error) {
	if req.GetDeviceId() == "" {
		return nil, status.Error(codes.InvalidArgument, "device_id is required")
	}
	// TODO: query genieacs-nbi (GET /devices/{id})
	return nil, status.Error(codes.NotFound, "device not found")
}

func (s *deviceServiceServer) PublishCommand(ctx context.Context, req *devicev1.PublishCommandRequest) (*devicev1.PublishCommandResponse, error) {
	if req.GetDeviceId() == "" || req.GetTopic() == "" {
		return nil, status.Error(codes.InvalidArgument, "device_id and topic are required")
	}
	// TODO: publish ke mosquitto lewat MQTT client yang disuntik dari main.go
	slog.Info("publish_command", "device_id", req.GetDeviceId(), "topic", req.GetTopic())
	return &devicev1.PublishCommandResponse{Accepted: true}, nil
}

// NewGRPCServer merangkai gRPC server dengan seluruh interceptor (logging,
// metrics, auth), health service, dan reflection (untuk debugging via
// grpcurl — sebaiknya dimatikan di production murni lewat env flag).
// extraOpts dipakai untuk menyuntik grpc.Creds(...) (TLS) bila diaktifkan.
func NewGRPCServer(unaryInterceptors []grpc.UnaryServerInterceptor, extraOpts ...grpc.ServerOption) (*grpc.Server, *HealthServer) {
	opts := append([]grpc.ServerOption{
		grpc.ChainUnaryInterceptor(unaryInterceptors...),
	}, extraOpts...)
	s := grpc.NewServer(opts...)

	devicev1.RegisterDeviceServiceServer(s, NewDeviceServiceServer())

	health := NewHealthServer()
	healthpb.RegisterHealthServer(s, health)

	reflection.Register(s)

	return s, health
}
