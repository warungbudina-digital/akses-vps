#!/usr/bin/env bash
# Backup database scraper `full-tool-browser` (Cloud Shell .60) ke DB-VPS.
#
# KENAPA ADA: .60 = Google Cloud Shell EPHEMERAL dan datanya ada di named
# Docker volume `postgres-data`, BUKAN bind-mount ke $HOME. Begitu VM recycle,
# SELURUH histori growth (scraped_profiles/scraped_posts/sessions/schedules)
# HILANG. Tanpa skrip ini, tracking pertumbuhan akun jangka panjang mustahil.
#
# POLA: pg_dump di .60 -> STREAM lewat pipe SSH -> mendarat di DB-VPS.
# Sengaja TIDAK mendarat di disk akses-vps (VPS ini control-plane ringan).
#
# .60 HANYA HIDUP TERJADWAL (bukan 24/7). Karena itu skrip ini:
#   - no-op ANGGUN (exit 0) kalau .60 mati / tunnel down / container belum naik.
#     Ini KONDISI NORMAL, bukan error - jangan bikin cron spam alert.
#   - exit != 0 HANYA kalau .60 hidup TAPI backup benar-benar gagal.
#
# Jalankan manual, atau lewat cron di akses-vps (lihat crontab.example).
set -uo pipefail

C60_HOST="${C60_HOST:-balibruntattour@10.66.66.60}"
C60_KEY="${C60_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
DBVPS_HOST="${DBVPS_HOST:-db-vps}"
DEST_DIR="${DEST_DIR:-browser-db-backups}"   # relatif ke $HOME di DB-VPS
RETENTION="${RETENTION:-30}"                 # simpan N dump terbaru
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"           # UTC (akses-vps `date` = UTC)
NAME="scraper-${STAMP}.sql.gz"
MIN_BYTES="${MIN_BYTES:-1000}"               # dump valid pasti > ini

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

ssh60() {
  ssh -o ControlPath=none -i "$C60_KEY" -o IdentitiesOnly=yes \
      -o ConnectTimeout=10 -o BatchMode=yes -p 22 "$C60_HOST" "$@"
}

# db-vps mencetak banner login BESAR ke STDERR tiap koneksi -> selalu buang,
# kalau tidak log backup tenggelam. (JANGAN buang pakai `sed 1,Nd`: itu
# memotong baris ISI, bukan banner - jebakan yang pernah menyesatkan.)
sshdb() {
  ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null
}

# ── 1. Preflight: .60 hidup? (mati = normal, keluar diam-diam) ───────────────
if ! ssh60 true 2>/dev/null; then
  log "SKIP: .60 tidak bisa di-SSH (Cloud Shell mati / bootstrap belum jalan). Ini normal."
  exit 0
fi

if ! ssh60 'docker ps --format "{{.Names}}" | grep -qx scraper-db' 2>/dev/null; then
  log "SKIP: container scraper-db tidak jalan di .60 (belum redeploy pasca-recycle). Ini normal."
  exit 0
fi

# ── 2. Siapkan direktori tujuan di DB-VPS ───────────────────────────────────
if ! sshdb "mkdir -p ~/${DEST_DIR}"; then
  log "GAGAL: DB-VPS tak terjangkau - tidak ada tujuan backup."
  exit 1
fi

# ── 3. Stream pg_dump .60 -> DB-VPS (tak mendarat di disk akses-vps) ────────
# pg_dump dijalankan DI DALAM container (kredensial ada di env container),
# hasil di-gzip di sisi .60 supaya yang lewat WireGuard sudah terkompresi.
log "Dump scraper-db di .60 -> ${DBVPS_HOST}:~/${DEST_DIR}/${NAME}"
if ! ssh60 'docker exec scraper-db pg_dump -U scraper -d scraper --no-owner --no-privileges | gzip -9' 2>/dev/null \
     | sshdb "cat > ~/${DEST_DIR}/${NAME}.part"; then
  log "GAGAL: pipe pg_dump -> DB-VPS terputus."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}.part"
  exit 1
fi

# ── 4. Validasi sebelum commit nama final (cegah dump kosong/rusak) ─────────
SIZE=$(sshdb "stat -c %s ~/${DEST_DIR}/${NAME}.part 2>/dev/null || echo 0")
if [ "${SIZE:-0}" -lt "$MIN_BYTES" ]; then
  log "GAGAL: dump cuma ${SIZE}B (< ${MIN_BYTES}B) - dianggap rusak, dibuang."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}.part"
  exit 1
fi

# gzip -t = verifikasi integritas arsip sebelum dipakai sebagai backup sah
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
  ls -1t scraper-*.sql.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | while read -r f; do
    rm -f -- \"\$f\" && echo \"rotasi: buang \$f\"
  done
"

# ── 6. Ringkas isi backup (bukti backup BERISI, bukan cuma ada) ─────────────
# SQL dikirim lewat STDIN (psql -f -), BUKAN dirangkai sebagai argumen -c:
# rantai kutip bash->ssh->docker exec->psql terlalu rapuh (sudah terbukti pecah).
ROWS=$(printf '%s\n' \
  "SELECT (SELECT COUNT(*) FROM scraped_posts) || ' post / ' || (SELECT COUNT(*) FROM scraped_profiles) || ' profil / ' || (SELECT COUNT(*) FROM scraper_sessions) || ' sesi';" \
  | ssh60 'docker exec -i scraper-db psql -U scraper -d scraper -tAq -f -' 2>/dev/null | tr -d '\r')
log "Isi DB saat backup: ${ROWS:-tak terbaca}"
exit 0
