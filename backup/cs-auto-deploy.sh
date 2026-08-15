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
#   yuni (.50)             -> bring-up-analyzer.sh v2 (ML: whisper+CLIP, clone+build+deploy
#                              penuh, idempoten; auto docker-rm kalau container lama ternyata
#                              V1, krn bring-up-analyzer.sh sendiri tak deteksi varian)
#   balibruntattour (.60)  -> bring-up-browser.sh      (clone+build+deploy penuh, idempoten)
#   gogobuda (.61)         -> n8n-uploader (repo mcp-video-editor, direstruktur
#                              2026-08-15): full bring-up, state di Postgres DB-VPS
#                              (role/db `n8n_uploader`, pg_hba SEMPIT cuma
#                              10.66.66.61/32) + N8N_ENCRYPTION_KEY durable +
#                              basic-auth — kredensial di-inject dari
#                              ~/.config/n8n-uploader/credentials.env (hub, 600).
#                              WireGuard-only (5678), TANPA Cloudflare Tunnel.
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

# --- yuni (.50) -> viral_analyzer V2 (full bring-up) ---
if ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 true 2>/dev/null; then
  log ".50 (yuni) reachable -> pastikan analyzer V2 (ML) jalan"
  IS_V2="$(ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 'bash -s' <<'CHECKEOF' 2>/dev/null
H=$(curl -sf http://127.0.0.1:9021/healthz 2>/dev/null)
if echo "$H" | grep -q '"asr": *true' && echo "$H" | grep -q '"semantic": *true'; then
  echo 1
else
  echo 0
fi
CHECKEOF
)"
  [ -z "$IS_V2" ] && IS_V2=0
  if [ "$IS_V2" = "1" ]; then
    log ".50 analyzer V2 SUDAH jalan sehat, skip rebuild."
  else
    # container lama (kalau ada) BUKAN V2 (mis. masih V1 dari sebelumnya) -> bring-up-analyzer.sh
    # sendiri tak deteksi varian (cuma cek /healthz ada-tidaknya), jadi hapus dulu biar ke-rebuild V2.
    ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 'docker rm -f viral_analyzer 2>/dev/null || true' >>"$LOG" 2>&1
    if ssh "${SSHOPTS[@]}" warungbudina@10.66.66.50 'bash -s -- v2' < "$HOME/viral-pipeline/bring-up-analyzer.sh" >>"$LOG" 2>&1; then
      log ".50 analyzer V2 bring-up OK."
    else
      log ".50 analyzer V2 bring-up GAGAL (lihat baris di atas)."
    fi
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

# --- gogobuda (.61) -> n8n-uploader (full bring-up, Postgres DB-VPS + WG-only) ---
N8N_CRED="$HOME/.config/n8n-uploader/credentials.env"
N8N_OAUTH="$HOME/.config/n8n-uploader/oauth-client.env"
N8N_TOKEN_SRC="$HOME/.config/n8n-uploader/token.json"
if ssh "${SSHOPTS[@]}" gogobuda65@10.66.66.61 true 2>/dev/null; then
  if [ ! -f "$N8N_CRED" ] || [ ! -f "$N8N_OAUTH" ]; then
    log ".61 (gogobuda) reachable TAPI kredensial belum lengkap ($N8N_CRED / $N8N_OAUTH) - skip deploy."
  else
    log ".61 (gogobuda) reachable -> bring-up n8n-uploader"
    # shellcheck disable=SC1090
    set -a; . "$N8N_CRED"; . "$N8N_OAUTH"; set +a
    # sinkron token.json Gdrive dari hub kalau ada salinan durable (opsional -
    # kalau belum ada, deploy.sh sendiri berhenti jelas di configure_rclone).
    if [ -f "$N8N_TOKEN_SRC" ]; then
      ssh "${SSHOPTS[@]}" gogobuda65@10.66.66.61 'mkdir -p ~/mcp-video-editor && cat > ~/mcp-video-editor/token.json' < "$N8N_TOKEN_SRC" 2>>"$LOG"
    fi
    if ssh "${SSHOPTS[@]}" gogobuda65@10.66.66.61 bash -s >>"$LOG" 2>&1 <<REMOTE_EOF
set -euo pipefail
cd ~
if [ -d mcp-video-editor/.git ]; then
  cd mcp-video-editor && git pull --ff-only
else
  git clone https://github.com/warungbudina-digital/mcp-video-editor.git
  cd mcp-video-editor
fi
export DB_POSTGRESDB_HOST='$DB_POSTGRESDB_HOST'
export DB_POSTGRESDB_PORT='$DB_POSTGRESDB_PORT'
export DB_POSTGRESDB_DATABASE='$DB_POSTGRESDB_DATABASE'
export DB_POSTGRESDB_USER='$DB_POSTGRESDB_USER'
export DB_POSTGRESDB_PASSWORD='$DB_POSTGRESDB_PASSWORD'
export RCLONE_CLIENT_ID='$RCLONE_CLIENT_ID'
export RCLONE_CLIENT_SECRET='$RCLONE_CLIENT_SECRET'
export N8N_ENCRYPTION_KEY='$N8N_ENCRYPTION_KEY'
export N8N_BASIC_AUTH_USER='$N8N_BASIC_AUTH_USER'
export N8N_BASIC_AUTH_PASSWORD='$N8N_BASIC_AUTH_PASSWORD'
bash n8n-script.sh
REMOTE_EOF
    then
      log ".61 n8n-uploader bring-up OK."
    else
      log ".61 n8n-uploader bring-up GAGAL atau BELUM LENGKAP (lihat baris di atas — kandidat penyebab: token.json Gdrive belum diisi asli)."
    fi
  fi
else
  log ".61 (gogobuda) belum reachable - skip."
fi

log "cs-auto-deploy selesai."
