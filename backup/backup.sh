#!/usr/bin/env bash
# Backup harian: MongoDB, konfigurasi WireGuard, ADB keypair, credential
# lokal non-git, konfigurasi GenieACS, dan seluruh Docker named volume
# yang relevan.
#
# Tidak lagi backup sertifikat TLS - sejak migrasi ke Cloudflare Tunnel,
# TLS publik ditangani Cloudflare edge, tidak ada lagi sertifikat lokal
# (Let's Encrypt/certbot) yang perlu di-backup di sini.
#
# Tidak ada lagi export MikroTik CHR: CHR tidak di-deploy di VPS ini
# (nested virtualization/KVM tidak tersedia - lihat docs/11 & docs/12,
# dipakai WireGuard native di kernel Linux sebagai gantinya).
#
# Jadwalkan lewat cron (lihat backup/crontab.example).
set -euo pipefail

# --- Lokasi & environment ---------------------------------------------------
# Resolusi path absolut dari lokasi script ini supaya aman dijalankan dari cwd
# manapun (cron jalan dengan cwd=/, bukan repo root). REPO_ROOT = parent dari
# folder backup/ tempat script ini berada.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Kredensial Mongo (MONGO_ROOT_USER / MONGO_ROOT_PASSWORD) datang dari .env.
# Source di sini supaya script standalone (tidak bergantung env cron).
if [ -f "${REPO_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${REPO_ROOT}/.env"
  set +a
fi

BACKUP_ROOT="${BACKUP_ROOT:-/opt/backups/akses-vps}"
DATE="$(date +%Y-%m-%d_%H%M%S)"
DEST="${BACKUP_ROOT}/${DATE}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"   # opsional, kosongkan jika tidak pakai offsite backup

# Docker Compose tidak set container_name, jadi nama mengikuti pola
# <project>-<service>-1 dan volume <project>_<volume>. Project name default =
# nama direktori (akses-vps); override lewat COMPOSE_PROJECT bila di-deploy di
# path/nama lain saat migrasi.
COMPOSE_PROJECT="${COMPOSE_PROJECT:-akses-vps}"

mkdir -p "${DEST}"

echo "[$(date -Iseconds)] Backup dimulai -> ${DEST}"

# 1. MongoDB (dump logikal, konsisten walau service tetap jalan)
echo "-> MongoDB dump"
MONGO_CONTAINER="$(docker ps --filter "name=${COMPOSE_PROJECT}-mongodb" --format '{{.Names}}' | head -n1)"
if [ -z "${MONGO_CONTAINER}" ]; then
  echo "ERROR: container mongodb tidak ditemukan (project=${COMPOSE_PROJECT}) - apakah stack jalan?" >&2
  exit 1
fi
docker exec "${MONGO_CONTAINER}" mongodump \
  --username "${MONGO_ROOT_USER}" --password "${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase admin \
  --archive="/tmp/mongo-${DATE}.archive" --gzip
docker cp "${MONGO_CONTAINER}:/tmp/mongo-${DATE}.archive" "${DEST}/mongo-${DATE}.archive"
docker exec "${MONGO_CONTAINER}" rm -f "/tmp/mongo-${DATE}.archive"

# 2. Konfigurasi WireGuard (wg0.conf + server keys) - satu-satunya salinan
#    state peer/registrasi VPN, TIDAK ada di git (repo cuma punya script
#    otomasinya). File root-only 600, jadi step ini butuh dijalankan sebagai
#    root (sama seperti crontab.example). Di-tar dengan permission dijaga.
echo "-> WireGuard config"
if [ -r /etc/wireguard/wg0.conf ]; then
  tar czf "${DEST}/wireguard-${DATE}.tar.gz" -C /etc wireguard
  chmod 600 "${DEST}/wireguard-${DATE}.tar.gz"
else
  echo "warn: /etc/wireguard/wg0.conf tidak terbaca (butuh root?) - WireGuard TIDAK ter-backup" >&2
fi

# 3. ADB keypair host ini (~/.android/adbkey{,.pub}) - identitas yang dipakai
#    `adb connect <tunnel-ip>:5555` ke smartphone lewat wg0 (lihat
#    docs/15-alur-akses-wireguard.md). TIDAK ada di git (private key).
#    Tanpa file ini, host baru dapat key baru dan SETIAP HP yang sudah
#    di-approve harus di-approve ulang manual (tap "Allow" di layar HP).
#    ADB_KEY_DIR override-able untuk deployment di username lain.
echo "-> ADB keypair"
ADB_KEY_DIR="${ADB_KEY_DIR:-/home/warungbudina/.android}"
if [ -r "${ADB_KEY_DIR}/adbkey" ]; then
  tar czf "${DEST}/adbkey-${DATE}.tar.gz" -C "$(dirname "${ADB_KEY_DIR}")" "$(basename "${ADB_KEY_DIR}")/adbkey" "$(basename "${ADB_KEY_DIR}")/adbkey.pub"
  chmod 600 "${DEST}/adbkey-${DATE}.tar.gz"
else
  echo "warn: ${ADB_KEY_DIR}/adbkey tidak terbaca - ADB keypair TIDAK ter-backup" >&2
fi

# 4. Credential lokal non-git (docs/.local-credentials/) - kredensial yang
#    sengaja TIDAK di-commit (gitignored) tapi harus selamat saat migrasi,
#    mis. SSH credential ke host lain seperti DB-VPS. File di-tar dengan
#    permission dijaga (arsip 600). Di-skip kalau folder belum ada.
echo "-> Local credentials"
if [ -d "${REPO_ROOT}/docs/.local-credentials" ]; then
  tar czf "${DEST}/local-credentials-${DATE}.tar.gz" -C "${REPO_ROOT}/docs" .local-credentials
  chmod 600 "${DEST}/local-credentials-${DATE}.tar.gz"
else
  echo "   skip: docs/.local-credentials/ tidak ada"
fi

# 5. Konfigurasi GenieACS (preset/provision/vparam disimpan di Mongo — sudah
#    tercakup di dump di atas — bagian ini backup file env/config statis)
echo "-> GenieACS config"
tar czf "${DEST}/genieacs-config-${DATE}.tar.gz" genieacs/genieacs.env genieacs/examples 2>/dev/null || true

# 6. Docker named volume. Nama sudah di-prefix project. Volume yang belum ada
#    (mis. monitoring stack belum di-start) di-SKIP eksplisit - jangan biarkan
#    `docker run -v` membuat volume kosong lalu men-tar-nya (backup kosong
#    diam-diam). radius-db-data & mosquitto-log ikut, sebelumnya terlewat.
echo "-> Docker named volumes"
for SHORT in mongo-data redis-data mosquitto-data mosquitto-log radius-db-data \
             grafana-data prometheus-data loki-data; do
  VOL="${COMPOSE_PROJECT}_${SHORT}"
  if ! docker volume inspect "${VOL}" >/dev/null 2>&1; then
    echo "   skip: volume ${VOL} tidak ada (service belum berjalan?)"
    continue
  fi
  docker run --rm -v "${VOL}:/data:ro" -v "${DEST}:/backup" alpine \
    tar czf "/backup/volume-${SHORT}-${DATE}.tar.gz" -C /data . \
    && echo "   ok: ${VOL}" \
    || echo "warn: gagal backup volume ${VOL}" >&2
done

# 7. Upload offsite (opsional)
if [ -n "${S3_BUCKET}" ]; then
  echo "-> Upload ke S3: ${S3_BUCKET}"
  aws s3 cp "${DEST}" "s3://${S3_BUCKET}/akses-vps/${DATE}/" --recursive
fi

# 8. Retensi lokal
echo "-> Bersihkan backup lokal > ${RETENTION_DAYS} hari"
find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} \;

echo "[$(date -Iseconds)] Backup selesai."
