#!/usr/bin/env bash
# =====================================================================
# check-wake-pipeline.sh — cek status pipeline wake-otomatis laptop
# SUARAHATI (NodeWake-0845 -> ensure-chrome-cdp -> open-cs 3-profil ->
# cs-auto-deploy.sh hub) lalu kirim ringkasan ke Telegram. Dipakai utk
# pengecekan SATU KALI (cron day-specific) atau manual kapan saja.
#
# Pemakaian: ./check-wake-pipeline.sh
# =====================================================================
set -uo pipefail

TG="$HOME/akses-vps/backup/send-telegram.sh"
OUT="$HOME/check-wake-pipeline.$(date -u +%Y%m%d).log"

log(){ echo "$*" | tee -a "$OUT"; }

log "=== check-wake-pipeline $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# --- 1) Laptop: Chrome hidup + orkestrator open-cs sudah selesai? ---
LAPTOP_OK=0
LAPTOP_SUMMARY="?"
CHROME_LOG="$(ssh -o ConnectTimeout=10 ltap-mini \
  "powershell -NoProfile -Command \"(Get-Process chrome -ErrorAction SilentlyContinue).Count; Get-Content C:\\chrome-cdp\\open-cs.log -Tail 60 -ErrorAction SilentlyContinue\"" 2>&1 | sed '/^#< CLIXML/d')"
log "--- laptop open-cs.log (tail) ---"
log "$CHROME_LOG"

if echo "$CHROME_LOG" | grep -q "open-and-bootstrap-cs: selesai"; then
  LAPTOP_OK=1
  LAPTOP_SUMMARY="orkestrator SELESAI"
elif [ -z "$CHROME_LOG" ]; then
  LAPTOP_SUMMARY="TAK BISA SSH ke laptop (mungkin belum wake / masih hibernasi)"
else
  LAPTOP_SUMMARY="orkestrator BELUM ketemu marker selesai (mungkin masih proses / macet - cek log di atas)"
fi
log ">>> LAPTOP: $LAPTOP_SUMMARY"

# --- 2) Hub: status cs-auto-deploy per profil ---
DEPLOY_LOG="$HOME/cs-auto-deploy.log"
log "--- cs-auto-deploy.log (baris ringkas terakhir) ---"
RECENT="$(grep '^\[cs-auto-deploy' "$DEPLOY_LOG" 2>/dev/null | tail -25)"
log "$RECENT"

status_of(){
  # $1 = pola pencarian OK, $2 = label
  if echo "$RECENT" | grep -q "$1"; then
    echo "OK"
  elif echo "$RECENT" | grep -qi "GAGAL"; then
    echo "GAGAL"
  elif echo "$RECENT" | grep -q "belum reachable"; then
    echo "belum reachable"
  else
    echo "?"
  fi
}

YUNI_STATUS="$(status_of "analyzer V2 bring-up OK\|analyzer V2 SUDAH jalan sehat")"
BALI_STATUS="$(status_of "browser bring-up OK")"
GOGO_STATUS="$(status_of "n8n clone-check selesai")"

log ">>> yuni(.50)=$YUNI_STATUS | balibruntattour(.60)=$BALI_STATUS | gogobuda(.61)=$GOGO_STATUS"

# --- 3) Kalau ada GAGAL, gali detail (baris seputar kegagalan, bukan cuma ringkasan) ---
DIAG=""
if echo "$RECENT" | grep -qi "GAGAL"; then
  DIAG="$(grep -n -i "GAGAL" "$DEPLOY_LOG" | tail -3 | while IFS=: read -r ln _; do
    sed -n "$((ln>30?ln-30:1)),${ln}p" "$DEPLOY_LOG"
  done)"
  log "--- DIAGNOSA (konteks sebelum baris GAGAL) ---"
  log "$DIAG"
fi

# --- 4) Susun pesan Telegram ---
ALL_OK=0
if [ "$LAPTOP_OK" = "1" ] && [ "$YUNI_STATUS" = "OK" ] && [ "$BALI_STATUS" = "OK" ] && [ "$GOGO_STATUS" = "OK" ]; then
  ALL_OK=1
fi

if [ "$ALL_OK" = "1" ]; then
  MSG="✅ Cek pipeline wake pagi ini SUKSES semua.
- Laptop: $LAPTOP_SUMMARY
- yuni(.50) analyzer V2: OK
- balibruntattour(.60) browser: OK
- gogobuda(.61) clone n8n: OK"
else
  MSG="⚠️ Cek pipeline wake pagi ini ADA YANG PERLU DIPERIKSA.
- Laptop: $LAPTOP_SUMMARY
- yuni(.50): $YUNI_STATUS
- balibruntattour(.60): $BALI_STATUS
- gogobuda(.61): $GOGO_STATUS
Detail lengkap: $OUT (di akses-vps)"
fi

log "--- pesan Telegram ---"
log "$MSG"
"$TG" "$MSG" || log "WARN: kirim Telegram gagal (lihat stderr)."

log "=== selesai ==="
