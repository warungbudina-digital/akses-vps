#!/usr/bin/env bash
# =====================================================================
# run-drain.sh — PEMICU ON-DEMAND orchestrator viral-pipeline.
# Jalan di akses-vps. Aman dipanggil berulang / dari cron poller:
# NO-OP murah kalau .50 mati ATAU antrean kosong (tak menyentuh .50 sia-sia).
#
# Alur:
#   1. lock (cegah dua drain bertumpuk)
#   2. hitung job 'pending' di DB-VPS  -> 0? keluar diam (exit 0)
#   3. pastikan ControlMaster ke .50   -> gagal? = .50 belum aktif, keluar (exit 0)
#   4. jalankan orchestrator (preflight-nya sendiri abort kalau analyzer .50 tak healthy)
#
# Pakai: bash ~/viral-pipeline/run-drain.sh   (manual, atau dari cron poller)
# Env  : MAX_JOBS=N (default 0=kuras semua) diteruskan ke orchestrator.
# =====================================================================
set -euo pipefail

PIPE_DIR="$HOME/viral-pipeline"
C50_SOCK="/tmp/c50.sock"
C50="warungbudina@10.66.66.50"
ADMIN_KEY="$HOME/.ssh/akses-vps-cloudshell-admin"
LOCK="/tmp/viral-drain.lock"
LOG="$HOME/viral-drain.log"

log(){ echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG" >&2; }

# cap log biar tak menggerus disk akses-vps
[ -f "$LOG" ] && [ "$(wc -l <"$LOG")" -gt 800 ] && tail -400 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"

# 1. lock non-blocking — kalau drain lain jalan, keluar diam
exec 9>"$LOCK"
if ! flock -n 9; then log "drain lain sedang jalan, lewati."; exit 0; fi

# 2. ada job pending? (DB-VPS selalu terjangkau dari akses-vps; query murah)
PENDING="$(ssh db-vps "sudo -n -u postgres psql -d scraper -tAq -c \"select count(*) from media.video_ingest where status='pending' and attempts < max_attempts;\"" 2>/dev/null | tr -dc 0-9)"
PENDING="${PENDING:-0}"
if [ "$PENDING" = 0 ]; then
  log "antrean kosong (0 pending), lewati."; exit 0
fi
log "ada $PENDING job pending."

# 3. pastikan ControlMaster ke .50 (kalau socket mati, bangun; kalau gagal = .50 belum aktif)
if ssh -o ControlPath="$C50_SOCK" -O check "$C50" 2>/dev/null; then
  log "master .50 sudah hidup."
else
  log "master .50 mati -> bangun..."
  if ssh -i "$ADMIN_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
         -o ControlMaster=auto -o ControlPath="$C50_SOCK" -o ControlPersist=6h \
         -MNf -o ConnectTimeout=12 -p 22 "$C50" 2>/dev/null; then
    log "master .50 UP."
  else
    log ".50 TAK terjangkau (aktifkan Cloud Shell .50 + paste bootstrap dulu). Lewati."
    exit 0
  fi
fi

# 4. kuras (orchestrator preflight sendiri: /healthz .50 + DB + tools; abort bersih kalau belum siap)
log "menjalankan orchestrator (MAX_JOBS=${MAX_JOBS:-0})..."
if MAX_JOBS="${MAX_JOBS:-0}" python3 "$PIPE_DIR/orchestrator.py" 2>&1 | tee -a "$LOG" >&2; then
  log "drain selesai."
else
  rc=${PIPESTATUS[0]}
  log "orchestrator exit $rc (mis. analyzer .50 belum healthy — jalankan bring-up-analyzer.sh)."
fi
