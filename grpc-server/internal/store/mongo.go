// Package store membungkus akses MongoDB untuk grpc-server: mencari device
// GenieACS berdasarkan MAC address, dan menyimpan korelasi sesi pelanggan
// RADIUS <-> device (lihat docs/13-accel-ppp-integration.md).
package store

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type MongoStore struct {
	client   *mongo.Client
	devices  *mongo.Collection
	subLinks *mongo.Collection
}

func NewMongoStore(ctx context.Context, uri string) (*MongoStore, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		return nil, fmt.Errorf("mongo connect: %w", err)
	}
	if err := client.Ping(ctx, nil); err != nil {
		return nil, fmt.Errorf("mongo ping: %w", err)
	}

	db := client.Database("genieacs")
	return &MongoStore{
		client:   client,
		devices:  db.Collection("devices"),
		subLinks: db.Collection("subscriber_links"),
	}, nil
}

func (s *MongoStore) Close(ctx context.Context) error {
	return s.client.Disconnect(ctx)
}

// macFieldCandidates adalah daftar path parameter TR-069 yang bisa berisi MAC
// address, dicoba berurutan sampai ketemu. VirtualParameters.mac_address
// (lihat genieacs/examples/virtual-parameter-mac-address.js) dicek PERTAMA
// karena dinormalisasi seragam lintas vendor/data-model — sisanya best-effort
// untuk device yang belum mengaktifkan virtual parameter tsb.
var macFieldCandidates = []string{
	"VirtualParameters.mac_address._value",
	"InternetGatewayDevice.LANDevice.1.LANEthernetInterfaceConfig.1.MACAddress._value",
	"InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.MACAddress._value",
	"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANEthernetLinkConfig.MACAddress._value",
	"Device.Ethernet.Interface.1.MACAddress._value",
	"Device.WiFi.SSID.1.MACAddress._value",
}

// normalizeMACRegex membuat pattern regex case-insensitive yang cocok baik
// MAC ditulis dengan pemisah ':' atau '-' ataupun tanpa pemisah sama sekali,
// karena format ini berbeda-beda antar vendor CPE dan antar sistem RADIUS.
func normalizeMACRegex(mac string) (string, error) {
	hex := strings.ToUpper(strings.NewReplacer(":", "", "-", "", ".", "").Replace(mac))
	if matched, _ := regexp.MatchString(`^[0-9A-F]{12}$`, hex); !matched {
		return "", fmt.Errorf("invalid MAC address format: %q", mac)
	}
	pairs := make([]string, 6)
	for i := 0; i < 6; i++ {
		pairs[i] = regexp.QuoteMeta(hex[i*2 : i*2+2])
	}
	return "^" + strings.Join(pairs, "[:-]?") + "$", nil
}

// FindDeviceByMAC mencari _id device GenieACS yang punya MAC address tsb di
// salah satu parameter kandidat. Mengembalikan ("", false, nil) jika tidak
// ada yang cocok (bukan error — ini kondisi normal untuk device baru/belum
// dikenal GenieACS).
func (s *MongoStore) FindDeviceByMAC(ctx context.Context, mac string) (string, bool, error) {
	pattern, err := normalizeMACRegex(mac)
	if err != nil {
		return "", false, err
	}

	or := make(bson.A, 0, len(macFieldCandidates))
	for _, field := range macFieldCandidates {
		or = append(or, bson.M{field: bson.M{"$regex": pattern, "$options": "i"}})
	}

	var result struct {
		ID string `bson:"_id"`
	}
	err = s.devices.FindOne(ctx, bson.M{"$or": or}, options.FindOne().SetProjection(bson.M{"_id": 1})).Decode(&result)
	if err == mongo.ErrNoDocuments {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("find device by mac: %w", err)
	}
	return result.ID, true, nil
}

type SubscriberLink struct {
	RadiusUsername   string
	DeviceID         string
	CallingStationID string
	FramedIPAddress  string
	Pop              string
	Status           string // "active" | "disconnected"
}

// UpsertSubscriberLink menyimpan/memperbarui korelasi sesi pelanggan RADIUS
// ke device GenieACS. linked_at hanya diset saat dokumen pertama kali dibuat
// ($setOnInsert), updated_at selalu diperbarui.
func (s *MongoStore) UpsertSubscriberLink(ctx context.Context, link SubscriberLink) error {
	filter := bson.M{"_id": link.RadiusUsername}
	update := bson.M{
		"$set": bson.M{
			"device_id":          link.DeviceID,
			"calling_station_id": link.CallingStationID,
			"framed_ip_address":  link.FramedIPAddress,
			"pop":                link.Pop,
			"status":             link.Status,
			"updated_at":         time.Now().UTC(),
		},
		"$setOnInsert": bson.M{
			"linked_at": time.Now().UTC(),
		},
	}
	_, err := s.subLinks.UpdateOne(ctx, filter, update, options.Update().SetUpsert(true))
	if err != nil {
		return fmt.Errorf("upsert subscriber_links: %w", err)
	}
	return nil
}
