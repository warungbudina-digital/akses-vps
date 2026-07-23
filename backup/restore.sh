#!/usr/bin/env bash
# Restore dari satu folder backup hasil backup.sh.
# Usage: ./restore.sh /opt/backups/akses-vps/2026-07-07_020000
set -euo pipefail

SRC="${1:?Usage: restore.sh <backup-folder>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [ -f "${REPO_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${REPO_ROOT}/.env"
  set +a
fi

COMPOSE_PROJECT="${COMPOSE_PROJECT:-akses-vps}"

echo "Restore MongoDB..."
MONGO_CONTAINER="$(docker ps --filter "name=${COMPOSE_PROJECT}-mongodb" --format '{{.Names}}' | head -n1)"
if [ -z "${MONGO_CONTAINER}" ]; then
  echo "ERROR: container mongodb tidak ditemukan (project=${COMPOSE_PROJECT})" >&2
  exit 1
fi
MONGO_ARCHIVE=$(ls "${SRC}"/mongo-*.archive)
docker cp "${MONGO_ARCHIVE}" "${MONGO_CONTAINER}:/tmp/restore.archive"
docker exec "${MONGO_CONTAINER}" mongorestore \
  --username "${MONGO_ROOT_USER}" --password "${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase admin \
  --archive="/tmp/restore.archive" --gzip --drop

echo
echo "Restore WireGuard (manual - butuh root, hati-hati menimpa peer aktif):"
echo "  Backup arsip: ${SRC}/wireguard-*.tar.gz"
echo "  sudo tar xzf ${SRC}/wireguard-*.tar.gz -C /etc   # pulihkan /etc/wireguard"
echo "  sudo systemctl restart wg-quick@wg0"

echo
echo "Restore ADB keypair (manual - tanpa ini, host baru harus di-approve"
echo "ulang manual di tiap HP yang sudah pernah di-approve):"
echo "  Backup arsip: ${SRC}/adbkey-*.tar.gz"
echo "  tar xzf ${SRC}/adbkey-*.tar.gz -C \$(dirname \${ADB_KEY_DIR:-/home/warungbudina/.android})"
echo "  chmod 600 \${ADB_KEY_DIR:-/home/warungbudina/.android}/adbkey"
echo "  adb kill-server && adb start-server   # supaya adb server pakai key yang di-restore"

echo
echo "Restore credential lokal non-git (docs/.local-credentials/, mis. SSH"
echo "credential DB-VPS) - manual, pulihkan ke dalam repo:"
echo "  Backup arsip: ${SRC}/local-credentials-*.tar.gz"
echo "  tar xzf ${SRC}/local-credentials-*.tar.gz -C ${REPO_ROOT}/docs"
echo "  chmod -R 600 ${REPO_ROOT}/docs/.local-credentials/*"

echo
echo "Restore Docker volumes lain (pilih manual sesuai kebutuhan):"
ls "${SRC}"/volume-*.tar.gz 2>/dev/null || echo "  (tidak ada arsip volume)"
echo "Contoh (nama volume harus di-prefix project, mis. ${COMPOSE_PROJECT}_redis-data):"
echo "  docker run --rm -v ${COMPOSE_PROJECT}_<name>:/data -v ${SRC}:/backup alpine \\"
echo "    sh -c 'cd /data && tar xzf /backup/volume-<name>-*.tar.gz'"

echo
echo "Restore selesai. Restart service yang relevan:"
echo "  docker compose restart mongodb genieacs-cwmp genieacs-nbi genieacs-ui nginx"
