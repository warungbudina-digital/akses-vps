// Package config memuat konfigurasi grpc-server. Sesuai requirement,
// konfigurasi utama diambil dari Environment Variable (12-factor), file
// configs/config.yaml hanya dipakai sebagai fallback/default saat development.
package config

import (
	"os"
	"strconv"
)

type Config struct {
	GRPCPort        int
	HTTPPort        int
	TLSCertFile     string
	TLSKeyFile      string
	ShutdownTimeout int

	JWTSecret      string
	JWTIssuer      string
	InternalAPIKey string

	RedisAddr     string
	RedisPassword string
	RedisDB       int

	MongoURI string

	MQTTBrokerURL string
	MQTTUsername  string
	MQTTPassword  string
	MQTTClientID  string

	LogLevel  string
	LogFormat string

	OTelExporterEndpoint string
	ServiceName          string
}

func Load() *Config {
	return &Config{
		GRPCPort:        envInt("GRPC_PORT", 50051),
		HTTPPort:        envInt("HTTP_PORT", 8443),
		TLSCertFile:     envStr("TLS_CERT_FILE", ""),
		TLSKeyFile:      envStr("TLS_KEY_FILE", ""),
		ShutdownTimeout: envInt("SHUTDOWN_TIMEOUT_SECONDS", 15),

		JWTSecret:      mustEnv("JWT_SECRET"),
		JWTIssuer:      envStr("JWT_ISSUER", "akses-vps"),
		InternalAPIKey: mustEnv("INTERNAL_API_KEY"),

		RedisAddr:     envStr("REDIS_ADDR", "redis:6379"),
		RedisPassword: envStr("REDIS_PASSWORD", ""),
		RedisDB:       envInt("REDIS_DB", 0),

		MongoURI: envStr("MONGO_URI", ""),

		MQTTBrokerURL: envStr("MQTT_BROKER_URL", "tcp://mosquitto:1883"),
		MQTTUsername:  envStr("MQTT_USERNAME", "grpc-service"),
		MQTTPassword:  envStr("MQTT_PASSWORD", ""),
		MQTTClientID:  envStr("MQTT_CLIENT_ID", "grpc-server"),

		LogLevel:  envStr("LOG_LEVEL", "info"),
		LogFormat: envStr("LOG_FORMAT", "json"),

		OTelExporterEndpoint: envStr("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
		ServiceName:          envStr("OTEL_SERVICE_NAME", "grpc-server"),
	}
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return def
}

// mustEnv dipakai untuk secret wajib — sengaja panic saat boot (bukan saat
// runtime) kalau operator lupa set, daripada silently jalan dengan default
// yang tidak aman.
func mustEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic("missing required environment variable: " + key)
	}
	return v
}
