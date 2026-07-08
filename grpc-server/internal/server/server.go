package server

import (
	"context"
	"log/slog"
	"strings"
	"sync/atomic"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	"github.com/warungbudina/akses-vps/grpc-server/internal/store"
	devicev1 "github.com/warungbudina/akses-vps/grpc-server/proto/gen"
)

// StoreSetter lets main.go inject a MongoStore that was connected after
// server startup (see main.go's mongo retry loop) — the server may start
// serving before mongo is reachable, then gain store access once a
// background reconnect succeeds.
type StoreSetter interface {
	SetStore(mongoStore *store.MongoStore)
}

// DeviceService is what main.go holds onto after NewGRPCServer: the gRPC
// server registers it directly, but main.go also needs to call
// LinkSubscriberSession itself, from the REST /v1/radius/accounting handler
// (see http_radius_accounting.go) - FreeRADIUS's rlm_rest module speaks
// HTTP, not gRPC, so that endpoint is a thin wrapper reusing this same
// implementation rather than a second one.
type DeviceService interface {
	devicev1.DeviceServiceServer
	StoreSetter
}

// deviceServiceServer implementasi RPC yang didefinisikan di proto/device.proto.
// Detail integrasi ke GenieACS NBI / MQTT publisher disuntik lewat field,
// bukan hard-coded, supaya gampang di-mock saat unit test.
type deviceServiceServer struct {
	devicev1.UnimplementedDeviceServiceServer

	// atomic.Pointer so LinkSubscriberSession (read from grpc request
	// goroutines) and SetStore (written from the mongo retry goroutine)
	// can race safely without a mutex.
	store atomic.Pointer[store.MongoStore]
	// genieACSClient, mqttPublisher, dst. — disuntik dari main.go
}

func NewDeviceServiceServer(mongoStore *store.MongoStore) *deviceServiceServer {
	d := &deviceServiceServer{}
	if mongoStore != nil {
		d.store.Store(mongoStore)
	}
	return d
}

func (s *deviceServiceServer) SetStore(mongoStore *store.MongoStore) {
	s.store.Store(mongoStore)
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

// LinkSubscriberSession dipanggil FreeRADIUS (rlm_rest) saat Accounting-Start/
// Stop/Interim-Update dari accel-ppp di PoP. Mencocokkan calling_station_id
// (MAC CPE) ke device GenieACS lalu upsert ke koleksi subscriber_links.
// Lihat docs/13-accel-ppp-integration.md untuk alur lengkap.
func (s *deviceServiceServer) LinkSubscriberSession(ctx context.Context, req *devicev1.LinkSubscriberSessionRequest) (*devicev1.LinkSubscriberSessionResponse, error) {
	if req.GetRadiusUsername() == "" || req.GetCallingStationId() == "" {
		return nil, status.Error(codes.InvalidArgument, "radius_username and calling_station_id are required")
	}
	st := s.store.Load()
	if st == nil {
		return nil, status.Error(codes.Unavailable, "mongo store not configured")
	}

	deviceID, found, err := st.FindDeviceByMAC(ctx, req.GetCallingStationId())
	if err != nil {
		slog.Error("link_subscriber_session_lookup_failed", "mac", req.GetCallingStationId(), "error", err)
		return nil, status.Error(codes.Internal, "failed to look up device by MAC")
	}

	// EqualFold, not ==: FreeRADIUS's %{Acct-Status-Type} xlat (the source
	// for this field once rlm_rest is wired up, see docs/13) expands to the
	// dictionary VALUE name verbatim - "Stop", not "stop" - so an exact
	// match here would silently never fire and every session would stay
	// marked "active" forever, including real disconnects.
	statusVal := "active"
	if strings.EqualFold(req.GetEventType(), "stop") {
		statusVal = "disconnected"
	}

	if err := st.UpsertSubscriberLink(ctx, store.SubscriberLink{
		RadiusUsername:   req.GetRadiusUsername(),
		DeviceID:         deviceID,
		CallingStationID: req.GetCallingStationId(),
		FramedIPAddress:  req.GetFramedIpAddress(),
		Pop:              req.GetPop(),
		Status:           statusVal,
	}); err != nil {
		slog.Error("link_subscriber_session_upsert_failed", "username", req.GetRadiusUsername(), "error", err)
		return nil, status.Error(codes.Internal, "failed to persist subscriber link")
	}

	slog.Info("link_subscriber_session",
		"username", req.GetRadiusUsername(),
		"mac", req.GetCallingStationId(),
		"pop", req.GetPop(),
		"event", req.GetEventType(),
		"device_found", found,
		"device_id", deviceID,
	)
	return &devicev1.LinkSubscriberSessionResponse{Linked: found, DeviceId: deviceID}, nil
}

// NewGRPCServer merangkai gRPC server dengan seluruh interceptor (logging,
// metrics, auth), health service, dan reflection (untuk debugging via
// grpcurl — sebaiknya dimatikan di production murni lewat env flag).
// extraOpts dipakai untuk menyuntik grpc.Creds(...) (TLS) bila diaktifkan.
func NewGRPCServer(mongoStore *store.MongoStore, unaryInterceptors []grpc.UnaryServerInterceptor, extraOpts ...grpc.ServerOption) (*grpc.Server, *HealthServer, DeviceService) {
	opts := append([]grpc.ServerOption{
		grpc.ChainUnaryInterceptor(unaryInterceptors...),
	}, extraOpts...)
	s := grpc.NewServer(opts...)

	deviceSvc := NewDeviceServiceServer(mongoStore)
	devicev1.RegisterDeviceServiceServer(s, deviceSvc)

	health := NewHealthServer()
	healthpb.RegisterHealthServer(s, health)

	reflection.Register(s)

	return s, health, deviceSvc
}
