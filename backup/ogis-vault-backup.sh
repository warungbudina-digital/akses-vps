#!/usr/bin/env bash
# Backup index vektor `ogis-vault` (Cloud Shell ogis, 10.66.66.8) ke DB-VPS.
#
# KENAPA ADA: ogis = Google Cloud Shell EPHEMERAL, index.db (SQLite) cuma
# file biasa di home VM -> VM recycle = index vektor (pengetahuan hasil
# scrape) HILANG TOTAL. Skrip ini bikin itu TIDAK terjadi in-practice:
# `ogis-vault/bring-up-ogis-vault.sh` otomatis restore dari backup terbaru
# di sini kalau index.db lokal absen pasca-recycle.
#
# POLA: cat index.db -> gzip -> STREAM lewat pipe SSH -> mendarat di DB-VPS.
# Sengaja TIDAK mendarat di disk akses-vps (VPS ini control-plane ringan).
# Pola PERSIS `browser-db-backup.sh` — baca itu kalau perlu banding struktur.
#
# ogis HANYA HIDUP TERJADWAL (bukan 24/7). Karena itu skrip ini:
#   - no-op ANGGUN (exit 0) kalau ogis mati / index.db belum ada.
#   - exit != 0 HANYA kalau ogis hidup TAPI backup benar-benar gagal.
set -uo pipefail

OGIS_HOST="${OGIS_HOST:-maydualapan8@10.66.66.8}"
OGIS_KEY="${OGIS_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
DBVPS_HOST="${DBVPS_HOST:-db-vps}"
DEST_DIR="${DEST_DIR:-ogis-vault-backups}"   # relatif ke $HOME di DB-VPS
RETENTION="${RETENTION:-30}"                 # simpan N dump terbaru
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"           # UTC
NAME="index-${STAMP}.db.gz"
MIN_BYTES="${MIN_BYTES:-100}"                # SQLite kosong pun > ini; jaga dr file 0-byte

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

sshogis() {
  ssh -o ControlPath=none -i "$OGIS_KEY" -o IdentitiesOnly=yes \
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=10 -o BatchMode=yes -p 22 "$OGIS_HOST" "$@"
}

# db-vps mencetak banner login BESAR ke STDERR -> selalu buang (JANGAN
# `sed 1,Nd`, itu memotong ISI, bukan banner).
sshdb() {
  ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null
}

# ── 1. Preflight: ogis hidup + index.db ada? (mati/absen = normal) ─────────
if ! sshogis true 2>/dev/null; then
  log "SKIP: ogis tidak bisa di-SSH (Cloud Shell mati / bootstrap belum jalan). Ini normal."
  exit 0
fi

if ! sshogis '[ -f ~/ogis-vault/index.db ]' 2>/dev/null; then
  log "SKIP: ~/ogis-vault/index.db belum ada di ogis (belum pernah di-ingest). Ini normal."
  exit 0
fi

# ── 2. Siapkan direktori tujuan di DB-VPS ───────────────────────────────────
if ! sshdb "mkdir -p ~/${DEST_DIR}"; then
  log "GAGAL: DB-VPS tak terjangkau - tidak ada tujuan backup."
  exit 1
fi

# ── 3. Stream index.db .60 -> DB-VPS (tak mendarat di disk akses-vps) ──────
log "Backup index.db di ogis -> ${DBVPS_HOST}:~/${DEST_DIR}/${NAME}"
if ! sshogis 'cat ~/ogis-vault/index.db | gzip -9' 2>/dev/null \
     | sshdb "cat > ~/${DEST_DIR}/${NAME}.part"; then
  log "GAGAL: pipe index.db -> DB-VPS terputus."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}.part"
  exit 1
fi

# ── 4. Validasi sebelum commit nama final ───────────────────────────────────
SIZE=$(sshdb "stat -c %s ~/${DEST_DIR}/${NAME}.part 2>/dev/null || echo 0")
if [ "${SIZE:-0}" -lt "$MIN_BYTES" ]; then
  log "GAGAL: backup cuma ${SIZE}B (< ${MIN_BYTES}B) - dianggap rusak, dibuang."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}.part"
  exit 1
fi

if ! sshdb "gzip -t ~/${DEST_DIR}/${NAME}.part"; then
  log "GAGAL: arsip gzip korup (gzip -t), dibuang."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}.part"
  exit 1
fi

sshdb "mv ~/${DEST_DIR}/${NAME}.part ~/${DEST_DIR}/${NAME} && chmod 600 ~/${DEST_DIR}/${NAME}"
log "OK: ${NAME} (${SIZE}B) tersimpan di ${DBVPS_HOST}:~/${DEST_DIR}/"

# ── 5. Rotasi: sisakan N terbaru ────────────────────────────────────────────
sshdb "
  cd ~/${DEST_DIR} || exit 0
  ls -1t index-*.db.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | while read -r f; do
    rm -f -- \"\$f\" && echo \"rotasi: buang \$f\"
  done
"

# ── 6. Ringkas isi backup (jumlah chunk, bukti backup BERISI) ───────────────
CHUNKS=$(sshogis "sqlite3 ~/ogis-vault/index.db 'SELECT COUNT(*) FROM chunks;' 2>/dev/null" \
  || sshogis "python3 -c \"import sqlite3; print(sqlite3.connect('$HOME/ogis-vault/index.db').execute('SELECT COUNT(*) FROM chunks').fetchone()[0])\"" 2>/dev/null)
log "Isi index saat backup: ${CHUNKS:-tak terbaca} chunk"
exit 0
