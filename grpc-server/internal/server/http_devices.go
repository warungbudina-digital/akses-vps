package server

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/warungbudina/akses-vps/grpc-server/internal/auth"
	devicev1 "github.com/warungbudina/akses-vps/grpc-server/proto/gen"
)

// RegisterDeviceRESTHandlers exposes ListDevices/GetDevice over plain
// HTTP/JSON at GET /v1/devices and GET /v1/devices/{id}, alongside the
// native gRPC endpoints. Wraps the same DeviceService the gRPC server
// registers rather than duplicating the GenieACS query logic.
//
// Why this exists: the public gateway (api.obc-crypto.com, via Cloudflare
// Tunnel) can't reliably deliver native gRPC's trailing HEADERS frame for
// responses that carry a body - Cloudflare's zone setting for this
// (long_lived_grpc) is off and not editable on the Free plan this zone is
// on, confirmed via Cloudflare's own zone settings API. Plain HTTP/JSON has
// no such requirement, so it works through the same path unmodified.
func RegisterDeviceRESTHandlers(mux *http.ServeMux, svc DeviceService, jwtManager *auth.JWTManager) {
	mux.HandleFunc("GET /v1/devices", listDevicesHandler(svc, jwtManager))
	mux.HandleFunc("GET /v1/devices/{id}", getDeviceHandler(svc, jwtManager))
}

func listDevicesHandler(svc DeviceService, jwtManager *auth.JWTManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !authenticateREST(w, r, jwtManager) {
			return
		}

		req := &devicev1.ListDevicesRequest{
			PageToken: r.URL.Query().Get("page_token"),
		}
		if v := r.URL.Query().Get("page_size"); v != "" {
			n, err := strconv.Atoi(v)
			if err != nil {
				http.Error(w, "invalid page_size", http.StatusBadRequest)
				return
			}
			req.PageSize = int32(n)
		}

		resp, err := svc.ListDevices(r.Context(), req)
		if err != nil {
			writeDeviceError(w, err)
			return
		}
		writeJSON(w, resp)
	}
}

func getDeviceHandler(svc DeviceService, jwtManager *auth.JWTManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !authenticateREST(w, r, jwtManager) {
			return
		}

		resp, err := svc.GetDevice(r.Context(), &devicev1.GetDeviceRequest{DeviceId: r.PathValue("id")})
		if err != nil {
			writeDeviceError(w, err)
			return
		}
		writeJSON(w, resp)
	}
}

// authenticateREST mirrors UnaryAuthInterceptor's Bearer JWT path (see
// internal/middleware/auth.go) - these handlers sit directly on the HTTP
// mux, outside the gRPC interceptor chain, so they need their own check.
// Same header, same JWTManager, same token clients already send for gRPC -
// switching a client from native gRPC to this REST path is just a
// transport/base_url change, not a new auth flow.
func authenticateREST(w http.ResponseWriter, r *http.Request, jwtManager *auth.JWTManager) bool {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		http.Error(w, "missing authorization header", http.StatusUnauthorized)
		return false
	}
	token := strings.TrimPrefix(authHeader, "Bearer ")
	if _, err := jwtManager.Verify(token); err != nil {
		http.Error(w, "invalid or expired token", http.StatusUnauthorized)
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// writeDeviceError maps the gRPC status codes ListDevices/GetDevice
// actually return (see server.go) to HTTP statuses.
func writeDeviceError(w http.ResponseWriter, err error) {
	st, ok := status.FromError(err)
	if !ok {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	httpStatus := http.StatusInternalServerError
	switch st.Code() {
	case codes.InvalidArgument:
		httpStatus = http.StatusBadRequest
	case codes.NotFound:
		httpStatus = http.StatusNotFound
	case codes.Unavailable:
		httpStatus = http.StatusServiceUnavailable
	}
	http.Error(w, st.Message(), httpStatus)
}
