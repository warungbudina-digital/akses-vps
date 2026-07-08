package server

import (
	"encoding/json"
	"log/slog"
	"net/http"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/warungbudina/akses-vps/grpc-server/internal/auth"
	devicev1 "github.com/warungbudina/akses-vps/grpc-server/proto/gen"
)

// RadiusAccountingHandler exposes LinkSubscriberSession over plain
// HTTP/JSON at POST /v1/radius/accounting, for FreeRADIUS's rlm_rest module
// (Accounting-Start/Stop/Interim-Update) which speaks REST, not gRPC - see
// docs/13-accel-ppp-integration.md. Wraps the same DeviceService the gRPC
// server registers rather than duplicating the lookup/upsert logic.
//
// Request/response body fields match LinkSubscriberSessionRequest/Response
// exactly (radius_username, calling_station_id, framed_ip_address, pop,
// event_type / linked, device_id) - the generated proto structs already
// carry matching json struct tags, so they're decoded/encoded directly.
//
// Auth mirrors the gRPC interceptor's service-to-service path: an
// X-Internal-Api-Key header checked with the same constant-time comparison
// used by internal/middleware/auth.go's UnaryAuthInterceptor.
func RadiusAccountingHandler(svc DeviceService, internalAPIKey string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		if !auth.VerifyInternalAPIKey(r.Header.Get("X-Internal-Api-Key"), internalAPIKey) {
			http.Error(w, "invalid or missing internal api key", http.StatusUnauthorized)
			return
		}

		var req devicev1.LinkSubscriberSessionRequest
		dec := json.NewDecoder(r.Body)
		dec.DisallowUnknownFields()
		if err := dec.Decode(&req); err != nil {
			http.Error(w, "invalid json body: "+err.Error(), http.StatusBadRequest)
			return
		}

		resp, err := svc.LinkSubscriberSession(r.Context(), &req)
		if err != nil {
			writeLinkSubscriberSessionError(w, err)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			slog.Error("radius_accounting_response_encode_failed", "error", err)
		}
	}
}

// writeLinkSubscriberSessionError maps the gRPC status codes
// LinkSubscriberSession actually returns (see server.go) to HTTP statuses.
func writeLinkSubscriberSessionError(w http.ResponseWriter, err error) {
	st, ok := status.FromError(err)
	if !ok {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	httpStatus := http.StatusInternalServerError
	switch st.Code() {
	case codes.InvalidArgument:
		httpStatus = http.StatusBadRequest
	case codes.Unavailable:
		httpStatus = http.StatusServiceUnavailable
	}
	http.Error(w, st.Message(), httpStatus)
}
