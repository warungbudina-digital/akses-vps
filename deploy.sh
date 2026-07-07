#!/usr/bin/env bash
# Deploy akses-vps stack. Auto-generate secret yang masih kosong/CHANGE_ME
# di .env (JWT_SECRET, INTERNAL_API_KEY, MQTT_PASSWORD) setiap dijalankan,
# supaya operator tidak perlu isi manual nilai kriptografis acak ini.
#
# Usage:
#   ./deploy.sh              -> deploy core services (tanpa monitoring stack)
#   ./deploy.sh --monitoring -> deploy termasuk Prometheus/Grafana/Loki/Promtail
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=.env
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE tidak ditemukan. Copy dari .env.example dan isi dulu." >&2
  exit 1
fi

gen_secret() { openssl rand -hex 32; }

set_env_if_placeholder() {
  local key="$1"
  local current
  current=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)
  if [ -z "$current" ] || [[ "$current" == CHANGE_ME* ]]; then
    local value
    value=$(gen_secret)
    if grep -qE "^${key}=" "$ENV_FILE"; then
      sed -i "s#^${key}=.*#${key}=${value}#" "$ENV_FILE"
    else
      echo "${key}=${value}" >> "$ENV_FILE"
    fi
    echo "[deploy] Generated baru untuk ${key}"
  else
    echo "[deploy] ${key} sudah terisi, dilewati"
  fi
}

echo "[deploy] Menyiapkan secret otomatis..."
set_env_if_placeholder JWT_SECRET
set_env_if_placeholder INTERNAL_API_KEY
set_env_if_placeholder MQTT_PASSWORD

# shellcheck disable=SC1090
source "$ENV_FILE"

echo "[deploy] Menyiapkan genieacs/genieacs.env dari template (kalau belum ada)..."
if [ ! -f genieacs/genieacs.env ]; then
  cp genieacs/genieacs.env.example genieacs/genieacs.env
  sed -i "s#^GENIEACS_MONGODB_CONNECTION_URL=.*#GENIEACS_MONGODB_CONNECTION_URL=mongodb://${GENIEACS_MONGO_USER}:${GENIEACS_MONGO_PASSWORD}@mongodb:27017/genieacs?authSource=genieacs#" genieacs/genieacs.env
  sed -i "s#^GENIEACS_UI_JWT_SECRET=.*#GENIEACS_UI_JWT_SECRET=$(gen_secret)#" genieacs/genieacs.env
  echo "[deploy] genieacs.env dibuat dari template"
else
  echo "[deploy] genieacs.env sudah ada, dilewati"
fi

echo "[deploy] Menyiapkan Mosquitto password file (kalau belum ada)..."
mkdir -p mosquitto/config
if [ ! -f mosquitto/config/passwd ]; then
  docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
    mosquitto_passwd -b -c /mosquitto/config/passwd grpc-service "${MQTT_PASSWORD}" >/dev/null
  docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
    mosquitto_passwd -b /mosquitto/config/passwd monitor "$(gen_secret)" >/dev/null
  chmod 644 mosquitto/config/passwd
  echo "[deploy] mosquitto passwd file dibuat"
else
  echo "[deploy] mosquitto passwd sudah ada, dilewati"
fi

CORE_SERVICES="nginx grpc-server mosquitto genieacs-cwmp genieacs-nbi genieacs-fs genieacs-ui mongodb redis"

if [ "${1:-}" == "--monitoring" ]; then
  echo "[deploy] Deploy core + monitoring stack..."
  docker compose -f docker-compose.reference.yml --env-file .env --profile monitoring up -d --build $CORE_SERVICES prometheus grafana loki promtail
else
  echo "[deploy] Deploy core services saja (skip monitoring, hemat RAM)..."
  docker compose -f docker-compose.reference.yml --env-file .env up -d --build $CORE_SERVICES
fi

echo "[deploy] Selesai. Status:"
docker compose -f docker-compose.reference.yml ps
