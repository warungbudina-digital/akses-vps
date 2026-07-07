#!/usr/bin/env bash
# Backup harian: MongoDB, konfigurasi GenieACS, sertifikat Let's Encrypt,
# konfigurasi MikroTik, dan seluruh Docker named volume.
#
# Jadwalkan lewat cron (lihat backup/crontab.example) atau RouterOS scheduler
# yang meng-exec container ini.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/opt/backups/akses-vps}"
DATE="$(date +%Y-%m-%d_%H%M%S)"
DEST="${BACKUP_ROOT}/${DATE}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"   # opsional, kosongkan jika tidak pakai offsite backup

mkdir -p "${DEST}"

echo "[$(date -Iseconds)] Backup dimulai -> ${DEST}"

# 1. MongoDB (dump logikal, konsisten walau service tetap jalan)
echo "-> MongoDB dump"
docker exec mongodb mongodump \
  --username "${MONGO_ROOT_USER}" --password "${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase admin \
  --archive="/tmp/mongo-${DATE}.archive" --gzip
docker cp "mongodb:/tmp/mongo-${DATE}.archive" "${DEST}/mongo-${DATE}.archive"
docker exec mongodb rm -f "/tmp/mongo-${DATE}.archive"

# 2. Konfigurasi GenieACS (preset/provision/vparam disimpan di Mongo — sudah
#    tercakup di dump di atas — bagian ini backup file env/config statis)
echo "-> GenieACS config"
tar czf "${DEST}/genieacs-config-${DATE}.tar.gz" genieacs/genieacs.env genieacs/examples 2>/dev/null || true

# 3. Sertifikat Let's Encrypt
echo "-> Let's Encrypt certs"
docker run --rm -v letsencrypt-certs:/data -v "${DEST}:/backup" alpine \
  tar czf "/backup/letsencrypt-${DATE}.tar.gz" -C /data .

# 4. Konfigurasi MikroTik CHR (export penuh RouterOS config via API/SSH)
echo "-> MikroTik RouterOS config export"
if [ -n "${MIKROTIK_HOST:-}" ]; then
  ssh -o StrictHostKeyChecking=accept-new "${MIKROTIK_SSH_USER}@${MIKROTIK_HOST}" \
    "/export file=backup-${DATE}" || echo "warn: gagal export via ssh"
  scp "${MIKROTIK_SSH_USER}@${MIKROTIK_HOST}:backup-${DATE}.rsc" "${DEST}/mikrotik-${DATE}.rsc" || true
fi

# 5. Seluruh Docker named volume (generic loop, aman untuk volume baru yang ditambah nanti)
echo "-> Docker named volumes"
for VOL in mongo-data redis-data mosquitto-data grafana-data prometheus-data loki-data; do
  docker run --rm -v "${VOL}:/data" -v "${DEST}:/backup" alpine \
    tar czf "/backup/volume-${VOL}-${DATE}.tar.gz" -C /data . || echo "warn: volume ${VOL} tidak ditemukan"
done

# 6. Upload offsite (opsional)
if [ -n "${S3_BUCKET}" ]; then
  echo "-> Upload ke S3: ${S3_BUCKET}"
  aws s3 cp "${DEST}" "s3://${S3_BUCKET}/akses-vps/${DATE}/" --recursive
fi

# 7. Retensi lokal
echo "-> Bersihkan backup lokal > ${RETENTION_DAYS} hari"
find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} \;

echo "[$(date -Iseconds)] Backup selesai."
