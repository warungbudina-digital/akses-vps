#!/usr/bin/env bash
# Restore dari satu folder backup hasil backup.sh.
# Usage: ./restore.sh /opt/backups/akses-vps/2026-07-07_020000
set -euo pipefail

SRC="${1:?Usage: restore.sh <backup-folder>}"

echo "Restore MongoDB..."
MONGO_ARCHIVE=$(ls "${SRC}"/mongo-*.archive)
docker cp "${MONGO_ARCHIVE}" "mongodb:/tmp/restore.archive"
docker exec mongodb mongorestore \
  --username "${MONGO_ROOT_USER}" --password "${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase admin \
  --archive="/tmp/restore.archive" --gzip --drop

echo "Restore Let's Encrypt certs..."
LE_ARCHIVE=$(ls "${SRC}"/letsencrypt-*.tar.gz)
docker run --rm -v letsencrypt-certs:/data -v "${SRC}:/backup" alpine \
  sh -c "cd /data && tar xzf /backup/$(basename "${LE_ARCHIVE}")"

echo "Restore Docker volumes lain (pilih manual sesuai kebutuhan):"
ls "${SRC}"/volume-*.tar.gz
echo "Contoh: docker run --rm -v <volume-name>:/data -v ${SRC}:/backup alpine sh -c 'cd /data && tar xzf /backup/volume-<name>-*.tar.gz'"

echo "Restore MikroTik config: import manual via /import file=mikrotik-*.rsc di RouterOS terminal."

echo "Restore selesai. Restart service yang relevan: docker compose restart mongodb genieacs-cwmp genieacs-nbi genieacs-ui nginx"
