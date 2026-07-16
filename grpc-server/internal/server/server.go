package server

import (
	"context"
	"errors"
	"log/slog"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	"github.com/warungbudina/akses-vps/grpc-server/internal/genieacs"
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

// defaultListPageSize/maxListPageSize bound ListDevices' page_size: unset
// falls back to default, oversized requests are clamped rather than
// rejected outright since a caller asking for too much is a much more
// common mistake than one being malicious about it.
const (
	defaultListPageSize = 50
	maxListPageSize     = 500
)

// deviceOnlineThreshold: a CPE that's informed within this window of "now"
// is considered online. TR-069 periodic inform defaults to 300-600s across
// the vendors provisioned here (see genieacs/examples/preset-default-config.json);
// this leaves a couple of missed cycles of slack before flipping to offline.
const deviceOnlineThreshold = 15 * time.Minute

// deviceServiceServer implementasi RPC yang didefinisikan di proto/device.proto.
// Detail integrasi ke GenieACS NBI / MQTT publisher disuntik lewat field,
// bukan hard-coded, supaya gampang di-mock saat unit test.
type deviceServiceServer struct {
	devicev1.UnimplementedDeviceServiceServer

	// atomic.Pointer so LinkSubscriberSession (read from grpc request
	// goroutines) and SetStore (written from the mongo retry goroutine)
	// can race safely without a mutex.
	store atomic.Pointer[store.MongoStore]

	// genieACSClient talks to genieacs-nbi over plain HTTP within the
	// docker network — no auth, since NBI isn't published outside it (see
	// docker-compose.reference.yml). Never nil in practice (main.go always
	// constructs one), but ListDevices/GetDevice check anyway so a future
	// caller that skips the constructor fails loudly instead of panicking.
	genieACSClient *genieacs.Client
	// mqttPublisher — disuntik dari main.go (belum diimplementasikan, lihat PublishCommand)
}

func NewDeviceServiceServer(mongoStore *store.MongoStore, genieACSClient *genieacs.Client) *deviceServiceServer {
	d := &deviceServiceServer{genieACSClient: genieACSClient}
	if mongoStore != nil {
		d.store.Store(mongoStore)
	}
	return d
}

func (s *deviceServiceServer) SetStore(mongoStore *store.MongoStore) {
	s.store.Store(mongoStore)
}

func (s *deviceServiceServer) ListDevices(ctx context.Context, req *devicev1.ListDevicesRequest) (*devicev1.ListDevicesResponse, error) {
	if s.genieACSClient == nil {
		return nil, status.Error(codes.Unavailable, "genieacs client not configured")
	}

	pageSize := int(req.GetPageSize())
	switch {
	case pageSize <= 0:
		pageSize = defaultListPageSize
	case pageSize > maxListPageSize:
		pageSize = maxListPageSize
	}

	skip := 0
	if tok := req.GetPageToken(); tok != "" {
		parsed, err := strconv.Atoi(tok)
		if err != nil || parsed < 0 {
			return nil, status.Error(codes.InvalidArgument, "invalid page_token")
		}
		skip = parsed
	}

	devices, total, err := s.genieACSClient.ListDevices(ctx, pageSize, skip)
	if err != nil {
		slog.Error("list_devices_failed", "error", err)
		return nil, status.Error(codes.Internal, "failed to query genieacs")
	}

	resp := &devicev1.ListDevicesResponse{
		Devices: make([]*devicev1.Device, len(devices)),
	}
	for i, d := range devices {
		resp.Devices[i] = toProtoDevice(d)
	}
	if next := skip + len(devices); next < total {
		resp.NextPageToken = strconv.Itoa(next)
	}
	return resp, nil
}

func (s *deviceServiceServer) GetDevice(ctx context.Context, req *devicev1.GetDeviceRequest) (*devicev1.Device, error) {
	if req.GetDeviceId() == "" {
		return nil, status.Error(codes.InvalidArgument, "device_id is required")
	}
	if s.genieACSClient == nil {
		return nil, status.Error(codes.Unavailable, "genieacs client not configured")
	}

	device, err := s.genieACSClient.GetDevice(ctx, req.GetDeviceId())
	if errors.Is(err, genieacs.ErrNotFound) {
		return nil, status.Error(codes.NotFound, "device not found")
	}
	if err != nil {
		slog.Error("get_device_failed", "device_id", req.GetDeviceId(), "error", err)
		return nil, status.Error(codes.Internal, "failed to query genieacs")
	}
	return toProtoDevice(*device), nil
}

func toProtoDevice(d genieacs.Device) *devicev1.Device {
	deviceStatus := "offline"
	var lastInformUnix int64
	if !d.LastInform.IsZero() {
		lastInformUnix = d.LastInform.Unix()
		if time.Since(d.LastInform) < deviceOnlineThreshold {
			deviceStatus = "online"
		}
	}
	return &devicev1.Device{
		DeviceId:       d.ID,
		SerialNumber:   d.SerialNumber,
		Manufacturer:   d.Manufacturer,
		ProductClass:   d.ProductClass,
		LastInformUnix: lastInformUnix,
		Status:         deviceStatus,
	}
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
func NewGRPCServer(mongoStore *store.MongoStore, genieACSClient *genieacs.Client, unaryInterceptors []grpc.UnaryServerInterceptor, extraOpts ...grpc.ServerOption) (*grpc.Server, *HealthServer, DeviceService) {
	opts := append([]grpc.ServerOption{
		grpc.ChainUnaryInterceptor(unaryInterceptors...),
	}, extraOpts...)
	s := grpc.NewServer(opts...)

	deviceSvc := NewDeviceServiceServer(mongoStore, genieACSClient)
	devicev1.RegisterDeviceServiceServer(s, deviceSvc)

	health := NewHealthServer()
	healthpb.RegisterHealthServer(s, health)

	reflection.Register(s)

	return s, health, deviceSvc
}
