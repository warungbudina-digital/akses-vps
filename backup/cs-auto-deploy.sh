#!/usr/bin/env bash
# =====================================================================
# cs-auto-deploy.sh — cron poller (HUB akses-vps): begitu tunnel Cloud
# Shell profil laptop (yuni/.50, balibruntattour/.60, gogobuda/.61)
# terdeteksi hidup pasca-bootstrap laptop (laptop sisi CDP cuma naikkan
# WG+SSH via open-and-bootstrap-cs.py, TIDAK git-clone/deploy — lihat
# project_medsos_agent.md), skrip inilah yang jalankan git-clone+deploy
# yang sudah di-SOP-kan. No-op anggun kalau profil belum/tak reachable
# (NORMAL — laptop node terjadwal, tak selalu hidup).
#
#   yuni (.50)             -> bring-up-analyzer.sh v1 (clone+build+deploy penuh, idempoten)
#   balibruntattour (.60)  -> bring-up-browser.sh      (clone+build+deploy penuh, idempoten)
#   gogobuda (.61)         -> HANYA git clone n8n-io/n8n (TANPA deploy/setup — user audit dulu)
#
# flock cegah tumpang-tindih antar-tick cron (build/clone bisa makan menit).
# =====================================================================
set -uo pipefail

LOCK="$HOME/.cs-auto-deploy.lock"
LOG="$HOME/cs-auto-deploy.log"

exec 200>"$LOCK"
flock -n 200 || { echo "[cs-auto-deploy $(date -u +%H:%M:%S)Z] sudah berjalan (lock) - skip." >> "$LOG"; exit 0; }

ADMIN_KEY="$HOME/.ssh/akses-vps-cloudshell-admin"
SSHOPTS=(-i "$ADMIN_KEY" -o IdentitiesOnly=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new -o BatchMode=yes)

log(){ echo "[cs-auto-deploy $(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }

# cap log (laptop-style, jaga ringan)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 800 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# --- yuni (.50) -> viral_analyzer (full bring-up) ---
if ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 true 2>/dev/null; then
  log ".50 (yuni) reachable -> bring-up analyzer v1"
  if ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 'bash -s -- v1' < "$HOME/viral-pipeline/bring-up-analyzer.sh" >>"$LOG" 2>&1; then
    log ".50 analyzer bring-up OK."
  else
    log ".50 analyzer bring-up GAGAL (lihat baris di atas)."
  fi
else
  log ".50 (yuni) belum reachable - skip (normal kalau laptop/bootstrap belum jalan)."
fi

# --- balibruntattour (.60) -> full-tool-browser (full bring-up) ---
if ssh "${SSHOPTS[@]}" balibruntattour@10.66.66.60 true 2>/dev/null; then
  log ".60 (balibruntattour) reachable -> bring-up browser"
  if bash "$HOME/akses-vps/backup/bring-up-browser.sh" >>"$LOG" 2>&1; then
    log ".60 browser bring-up OK."
  else
    log ".60 browser bring-up GAGAL (lihat baris di atas)."
  fi
else
  log ".60 (balibruntattour) belum reachable - skip."
fi

# --- gogobuda (.61) -> HANYA git clone n8n, TANPA deploy (user audit manual dulu) ---
if ssh "${SSHOPTS[@]}" gogobuda65@10.66.66.61 true 2>/dev/null; then
  log ".61 (gogobuda) reachable -> pastikan clone n8n-io/n8n (TANPA deploy)"
  if ssh "${SSHOPTS[@]}" gogobuda65@10.66.66.61 \
      'if [ -d "$HOME/n8n/.git" ]; then echo "n8n sudah ter-clone, skip."; else git clone --depth 1 https://github.com/n8n-io/n8n.git "$HOME/n8n" && echo "n8n clone OK (shallow, TANPA setup/deploy)."; fi' >>"$LOG" 2>&1; then
    log ".61 n8n clone-check selesai."
  else
    log ".61 n8n clone GAGAL (lihat baris di atas)."
  fi
else
  log ".61 (gogobuda) belum reachable - skip."
fi

log "cs-auto-deploy selesai."
