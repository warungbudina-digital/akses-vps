#!/bin/sh
# Dijalankan certbot setelah renewal sukses (--deploy-hook).
# Reload nginx tanpa downtime (nginx -s reload cukup untuk pickup cert baru),
# dan sinkronkan cert terbaru ke direktori certs Mosquitto.
set -eu

echo "$(date -Iseconds) certbot renew-hook: reloading nginx"
docker exec nginx nginx -s reload || echo "warn: gagal reload nginx (cek apakah container bernama 'nginx')"

echo "$(date -Iseconds) certbot renew-hook: sinkronisasi cert ke mosquitto"
DOMAIN_PRIMARY="mqtt.domain.com"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN_PRIMARY}"
if [ -d "$CERT_DIR" ]; then
  cp "$CERT_DIR/fullchain.pem" /etc/letsencrypt/mosquitto-fullchain.pem
  cp "$CERT_DIR/privkey.pem"   /etc/letsencrypt/mosquitto-privkey.pem
  docker restart mosquitto || true
fi
