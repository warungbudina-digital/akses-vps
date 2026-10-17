#!/usr/bin/env bash
# Backup "otak pengetahuan" Raspberry Pi 4B (vault wiki + index RAG + skrip
# rn5-ai-bridge) ke DB-VPS.
#
# KENAPA ADA: audit 2026-09-13 menemukan `~/wiki-docs` di Pi (seluruh basis
# pengetahuan: wireshark/spiderfoot/shodan/apk-cracking-analysis/online-
# resources + chatlog hasil panen RN5) **TIDAK PUNYA BACKUP SAMA SEKALI** -
# nol rclone, nol timer. Kalau storage Pi korup, semuanya hilang permanen.
# Ukurannya cuma ratusan KB, jadi tak ada alasan membiarkannya tanpa salinan.
#
# POLA: tar+gzip di Pi -> STREAM lewat pipe SSH -> mendarat di DB-VPS.
# Sengaja TIDAK mendarat di disk akses-vps (konvensi sama dgn
# browser-db-backup.sh: VPS ini control-plane ringan; lagipula cuma sisa
# ~4GB, sedangkan DB-VPS lega ~24GB).
#
# KENAPA ARSIP BERTANGGAL, BUKAN rsync MIRROR: mirror (`rsync --delete`) akan
# SETIA MENIRU kerusakan - kalau ada yg terhapus/korup di Pi, salinannya ikut
# hilang pd sinkron berikutnya. Arsip bertanggal memberi pemulihan
# titik-waktu (bisa ambil versi minggu lalu). Pelajaran yg sama sudah dicatat
# utk backup laptop: pakai pola aditif, jangan mirror destruktif.
#
# Pi = node 24/7. Jadi BEDA dari browser-db-backup.sh (.60 ephemeral):
# di sini Pi tak terjangkau = ANOMALI NYATA -> exit != 0 supaya kelihatan,
# bukan no-op diam.
#
# Jalankan manual, atau lewat cron di akses-vps.
set -uo pipefail

PI_HOST="${PI_HOST:-pi4b}"
DBVPS_HOST="${DBVPS_HOST:-db-vps}"
DEST_DIR="${DEST_DIR:-pi-vault-backups}"     # relatif ke $HOME di DB-VPS
RETENTION="${RETENTION:-30}"                 # simpan N arsip terbaru
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"           # UTC (akses-vps `date` = UTC)
NAME="pi-vault-${STAMP}.tar.gz"
MIN_BYTES="${MIN_BYTES:-20000}"              # arsip sehat pasti jauh > ini

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

sshpi()  { ssh -o ConnectTimeout=15 -o BatchMode=yes "$PI_HOST" "$@"; }

# db-vps mencetak banner login BESAR ke STDERR tiap koneksi -> selalu buang,
# kalau tidak log backup tenggelam (kejadian nyata di run pertama skrip ini).
# Konsekuensinya pesan error asli dr sisi db-vps ikut terbuang - itu SENGAJA
# diterima krn deteksi kegagalan di sini TIDAK bergantung pd stderr sama
# sekali, melainkan pd verifikasi HASIL (ukuran arsip + `tar tzf`), yg jauh
# lebih bisa dipercaya drpd menebak dari teks error.
sshdb()  { ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null; }

log "START backup vault Pi -> ${DBVPS_HOST}:~/${DEST_DIR}/${NAME}"

# --- 1. Pi harus hidup (node 24/7; kalau mati = masalah beneran) ---
if ! sshpi 'exit 0' 2>/dev/null; then
  log "FATAL: ${PI_HOST} tak terjangkau lewat SSH. Pi seharusnya 24/7 - periksa."
  exit 1
fi

# --- 2. siapkan folder tujuan ---
if ! sshdb "mkdir -p ~/${DEST_DIR}" 2>/dev/null; then
  log "FATAL: gagal menyiapkan ~/${DEST_DIR} di ${DBVPS_HOST}."
  exit 1
fi

# --- 3. stream tar dari Pi langsung ke DB-VPS ---
# index.db IKUT (8-9MB, kompres ~3MB): tanpa itu pemulihan wajib re-ingest
# seluruh domain lewat Ollama di Pi = lama + BIKIN PANAS (Pi node terjadwal,
# rawan panas - ini alasan yg sama kenapa ingest dibuat inkremental).
# Yg DIBUANG: cache python, file .pyc, dan semua *.log (regenerable/noise).
TAR_CMD='tar czf - -C "$HOME" \
  --exclude=__pycache__ --exclude="*.pyc" --exclude="*.log" \
  wiki-docs rn5-ai-bridge vault-search 2>/dev/null'

if ! sshpi "$TAR_CMD" | sshdb "cat > ~/${DEST_DIR}/${NAME}"; then
  log "FATAL: stream tar Pi -> DB-VPS gagal."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi

# --- 4. VERIFIKASI sebelum percaya (ukuran + arsip benar2 bisa dibaca) ---
SIZE="$(sshdb "stat -c %s ~/${DEST_DIR}/${NAME} 2>/dev/null" | tr -d '[:space:]')"
if [ -z "$SIZE" ] || [ "$SIZE" -lt "$MIN_BYTES" ]; then
  log "FATAL: arsip mencurigakan (${SIZE:-0} byte < ${MIN_BYTES}). Dibuang, backup lama TIDAK disentuh."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi

if ! sshdb "tar tzf ~/${DEST_DIR}/${NAME} >/dev/null 2>&1"; then
  log "FATAL: arsip korup (tar tzf gagal). Dibuang, backup lama TIDAK disentuh."
  sshdb "rm -f ~/${DEST_DIR}/${NAME}" 2>/dev/null
  exit 1
fi

NFILES="$(sshdb "tar tzf ~/${DEST_DIR}/${NAME} 2>/dev/null | wc -l" | tr -d '[:space:]')"
log "OK: ${NAME} (${SIZE} byte, ${NFILES} entri) terverifikasi."

# --- 5. prune HANYA setelah backup baru terbukti sehat ---
# (urutan ini disengaja: jangan pernah buang yg lama sebelum yg baru valid)
# Daftar-dulu-baru-hapus, dan hitung dari daftar itu - JANGAN hitung dari
# keluaran gabungan ssh (run pertama sempat lapor "13 dibuang" padahal NOL:
# yg terhitung ternyata baris banner login db-vps, bukan nama file).
OLD_LIST="$(sshdb "cd ~/${DEST_DIR} 2>/dev/null && ls -1t pi-vault-*.tar.gz 2>/dev/null | tail -n +$((RETENTION+1))")"
PRUNED=0
if [ -n "${OLD_LIST//[[:space:]]/}" ]; then
  PRUNED="$(printf '%s\n' "$OLD_LIST" | grep -c '^pi-vault-.*\.tar\.gz$')"
  printf '%s\n' "$OLD_LIST" | grep '^pi-vault-.*\.tar\.gz$' \
    | sshdb "cd ~/${DEST_DIR} && xargs -r rm -f"
fi
KEPT="$(sshdb "ls -1 ~/${DEST_DIR}/pi-vault-*.tar.gz 2>/dev/null | wc -l" | tr -d '[:space:]')"
log "DONE: ${KEPT} arsip tersimpan (retensi ${RETENTION}), ${PRUNED} lama dibuang."
exit 0
