#!/usr/bin/env bash
# Backup database `ai_chatlog` (arsip percakapan AI dari RN7, lihat
# [[project_rn7_chat_harvest_db]]) dari DB-VPS -> Raspberry Pi 4B.
#
# KENAPA ARAHNYA KE PI, BUKAN KE DB-VPS SENDIRI: databasenya HIDUP di DB-VPS.
# Menyimpan salinannya di mesin yang sama tidak melindungi apa pun - satu
# mesin bermasalah, dua-duanya hilang. Pi = mesin lain, lokasi fisik lain
# (rumah vs VPS), dan 24/7. Ini juga SIMETRIS dgn pi-vault-backup.sh yang
# mengalir arah sebaliknya (Pi -> DB-VPS): keduanya saling menjaga.
#
# POLA: pg_dump+gzip di DB-VPS -> STREAM lewat pipe SSH -> mendarat di Pi.
# akses-vps cuma jadi orkestrator (punya SSH ke dua-duanya); datanya TIDAK
# singgah ke disk akses-vps - konsisten dgn browser-db-backup.sh, sekalian
# krn akses-vps memang sesak (~4GB sisa).
#
# Kedua ujung (DB-VPS & Pi) sama-sama node 24/7 -> kalau salah satu tak
# terjangkau itu ANOMALI NYATA, exit != 0 supaya kelihatan (BUKAN no-op
# anggun seperti skrip utk node ephemeral .60).
set -uo pipefail

DBVPS_HOST="${DBVPS_HOST:-db-vps}"
PI_HOST="${PI_HOST:-pi4b}"
DEST_DIR="${DEST_DIR:-backups/db-vps-ai_chatlog}"   # relatif ke $HOME di Pi
RETENTION="${RETENTION:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"                  # UTC (akses-vps date = UTC)
NAME="ai_chatlog-${STAMP}.sql.gz"
MIN_BYTES="${MIN_BYTES:-500}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# db-vps mencetak banner login besar ke STDERR tiap koneksi -> dibuang.
# Deteksi gagal TIDAK bergantung stderr, melainkan returncode + verifikasi
# hasil (ukuran, gzip -t, isi dump) - pola sama pi-vault-backup.sh.
sshdb() { ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null; }
sshpi() { ssh -o ConnectTimeout=15 -o BatchMode=yes "$PI_HOST" "$@"; }

log "START backup ai_chatlog: ${DBVPS_HOST} -> ${PI_HOST}:~/${DEST_DIR}/${NAME}"

if ! sshdb 'exit 0'; then
  log "FATAL: ${DBVPS_HOST} tak terjangkau (node 24/7 - periksa)."
  exit 1
fi
if ! sshpi 'exit 0' 2>/dev/null; then
  log "FATAL: ${PI_HOST} tak terjangkau (node 24/7 - periksa)."
  exit 1
fi
if ! sshpi "mkdir -p ~/${DEST_DIR}" 2>/dev/null; then
  log "FATAL: gagal menyiapkan ~/${DEST_DIR} di ${PI_HOST}."
  exit 1
fi

# pg_dump auth lewat ~/.pgpass milik user di db-vps (sudah dipasang saat
# database dibuat). --no-owner/--no-privileges biar dump gampang di-restore
# ke instance lain tanpa role ai_chatlog harus sudah ada duluan.
DUMP_CMD='pg_dump -h 127.0.0.1 -U ai_chatlog -d ai_chatlog --no-owner --no-privileges | gzip -9'

if ! sshdb "$DUMP_CMD" | sshpi "cat > ~/${DEST_DIR}/${NAME}"; then
  log "FATAL: stream pg_dump gagal."
  sshpi "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi

# --- VERIFIKASI berlapis sebelum dipercaya ---
SIZE="$(sshpi "stat -c %s ~/${DEST_DIR}/${NAME} 2>/dev/null" 2>/dev/null | tr -d '[:space:]')"
if [ -z "$SIZE" ] || [ "$SIZE" -lt "$MIN_BYTES" ]; then
  log "FATAL: dump mencurigakan (${SIZE:-0} byte < ${MIN_BYTES}). Dibuang, backup lama TIDAK disentuh."
  sshpi "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi
if ! sshpi "gzip -t ~/${DEST_DIR}/${NAME}" 2>/dev/null; then
  log "FATAL: gzip korup. Dibuang, backup lama TIDAK disentuh."
  sshpi "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi
# isi harus benar2 dump skema kita, bukan file gzip valid yg kebetulan kosong
if ! sshpi "gzip -dc ~/${DEST_DIR}/${NAME} | grep -q 'CREATE TABLE public.conversations'" 2>/dev/null; then
  log "FATAL: dump tak memuat tabel yg diharapkan. Dibuang, backup lama TIDAK disentuh."
  sshpi "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi

NROWS="$(sshpi "gzip -dc ~/${DEST_DIR}/${NAME} | grep -c '^COPY public'" 2>/dev/null | tr -d '[:space:]')"
log "OK: ${NAME} (${SIZE} byte, ${NROWS:-0} blok COPY) terverifikasi."

# --- prune HANYA setelah dump baru terbukti sehat ---
# daftar-dulu-baru-hapus lalu hitung dari daftar (jangan hitung dari keluaran
# gabungan ssh - bisa tercampur banner/noise; jebakan yg pernah kejadian).
OLD_LIST="$(sshpi "cd ~/${DEST_DIR} 2>/dev/null && ls -1t ai_chatlog-*.sql.gz 2>/dev/null | tail -n +$((RETENTION+1))" 2>/dev/null)"
PRUNED=0
if [ -n "${OLD_LIST//[[:space:]]/}" ]; then
  PRUNED="$(printf '%s\n' "$OLD_LIST" | grep -c '^ai_chatlog-.*\.sql\.gz$')"
  printf '%s\n' "$OLD_LIST" | grep '^ai_chatlog-.*\.sql\.gz$' \
    | sshpi "cd ~/${DEST_DIR} && xargs -r rm -f"
fi
KEPT="$(sshpi "ls -1 ~/${DEST_DIR}/ai_chatlog-*.sql.gz 2>/dev/null | wc -l" 2>/dev/null | tr -d '[:space:]')"
log "DONE: ${KEPT} dump tersimpan (retensi ${RETENTION}), ${PRUNED} lama dibuang."
exit 0
