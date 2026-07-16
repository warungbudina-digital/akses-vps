// Package genieacs implements a minimal client for the GenieACS NBI (North
// Bound Interface) HTTP API — just enough of it to back
// DeviceService.ListDevices/GetDevice (see proto/device.proto).
package genieacs

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// ErrNotFound is returned by GetDevice when no device matches the given ID.
var ErrNotFound = errors.New("genieacs: device not found")

type Client struct {
	baseURL    string
	httpClient *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// Device is the subset of a GenieACS device document that DeviceService
// exposes over gRPC.
type Device struct {
	ID           string
	Manufacturer string
	OUI          string
	ProductClass string
	SerialNumber string
	LastInform   time.Time
}

// rawDevice mirrors the fields projected out of a GenieACS device document
// (see deviceProjection below). _deviceId's nested keys are
// underscore-prefixed exactly as genieacs-cwmp stores them from the TR-069
// Inform RPC's DeviceId struct — confirmed against the installed
// genieacs-nbi 1.2.16 bundle directly (grep for "_deviceId" in
// bin/genieacs-nbi), since the public NBI docs don't document the raw
// device document schema, only the query/projection param syntax.
type rawDevice struct {
	ID       string `json:"_id"`
	DeviceID struct {
		Manufacturer string `json:"_Manufacturer"`
		OUI          string `json:"_OUI"`
		ProductClass string `json:"_ProductClass"`
		SerialNumber string `json:"_SerialNumber"`
	} `json:"_deviceId"`
	LastInform flexibleTime `json:"_lastInform"`
}

func (d rawDevice) toDevice() Device {
	return Device{
		ID:           d.ID,
		Manufacturer: d.DeviceID.Manufacturer,
		OUI:          d.DeviceID.OUI,
		ProductClass: d.DeviceID.ProductClass,
		SerialNumber: d.DeviceID.SerialNumber,
		LastInform:   time.Time(d.LastInform),
	}
}

// flexibleTime accepts the handful of shapes NBI's date fields could
// plausibly arrive in across genieacs versions: a quoted RFC3339 string, a
// bare epoch-millis number, or a MongoDB extended-JSON {"$date": ...}
// wrapper (string or number inside) — the live server currently has zero
// devices to sample a real response from, so this stays permissive instead
// of committing to one shape and breaking silently on the others.
// Unrecognized input decodes to the zero time rather than failing the
// whole device.
type flexibleTime time.Time

func (t *flexibleTime) UnmarshalJSON(b []byte) error {
	b = bytes.TrimSpace(b)
	if len(b) == 0 || string(b) == "null" {
		return nil
	}

	if b[0] == '{' {
		var wrapped struct {
			Date json.RawMessage `json:"$date"`
		}
		if err := json.Unmarshal(b, &wrapped); err != nil || len(wrapped.Date) == 0 {
			return nil
		}
		return t.UnmarshalJSON(wrapped.Date)
	}

	if b[0] == '"' {
		var s string
		if err := json.Unmarshal(b, &s); err == nil {
			if parsed, err := time.Parse(time.RFC3339, s); err == nil {
				*t = flexibleTime(parsed)
			}
		}
		return nil
	}

	if ms, err := strconv.ParseInt(string(b), 10, 64); err == nil {
		*t = flexibleTime(time.UnixMilli(ms))
	}
	return nil
}

const deviceProjection = "_id,_deviceId,_lastInform"

// ListDevices returns up to limit devices starting at the given offset
// (GenieACS NBI paginates via skip/limit, not opaque cursors), plus the
// total number of devices in the collection.
func (c *Client) ListDevices(ctx context.Context, limit, skip int) ([]Device, int, error) {
	q := url.Values{}
	q.Set("projection", deviceProjection)
	q.Set("sort", `{"_id":1}`)
	q.Set("limit", strconv.Itoa(limit))
	q.Set("skip", strconv.Itoa(skip))

	raws, total, err := c.getDevices(ctx, q)
	if err != nil {
		return nil, 0, err
	}
	devices := make([]Device, len(raws))
	for i, r := range raws {
		devices[i] = r.toDevice()
	}
	return devices, total, nil
}

// GetDevice looks up a single device by its GenieACS _id. GenieACS NBI has
// no GET /devices/{id} route — verified directly against the live server,
// it 405s — so this filters the list endpoint down to one document instead,
// the way the NBI API reference documents doing single-device lookups.
func (c *Client) GetDevice(ctx context.Context, id string) (*Device, error) {
	query, err := json.Marshal(map[string]string{"_id": id})
	if err != nil {
		return nil, fmt.Errorf("genieacs: encode query: %w", err)
	}

	q := url.Values{}
	q.Set("projection", deviceProjection)
	q.Set("query", string(query))
	q.Set("limit", "1")

	raws, _, err := c.getDevices(ctx, q)
	if err != nil {
		return nil, err
	}
	if len(raws) == 0 {
		return nil, ErrNotFound
	}
	dev := raws[0].toDevice()
	return &dev, nil
}

func (c *Client) getDevices(ctx context.Context, q url.Values) ([]rawDevice, int, error) {
	reqURL := c.baseURL + "/devices/?" + q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, 0, fmt.Errorf("genieacs: build request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("genieacs: request devices: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, fmt.Errorf("genieacs: read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, 0, fmt.Errorf("genieacs: unexpected status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var raws []rawDevice
	if err := json.Unmarshal(body, &raws); err != nil {
		return nil, 0, fmt.Errorf("genieacs: decode response: %w", err)
	}

	total := len(raws)
	if t, err := strconv.Atoi(resp.Header.Get("Total")); err == nil {
		total = t
	}

	return raws, total, nil
}
