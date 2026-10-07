#!/usr/bin/env bash
# =====================================================================
# bring-up-gui-61.sh — siapkan stasiun login GUI (gui-chromium + di-relay)
# di .61 (Cloud Shell gogobuda65, EPHEMERAL). Dijalankan DI akses-vps.
#
# Idempoten: sudah live -> verifikasi lalu exit 0.
# Kredensial: GUI_PASSWORD dibuat sekali di hub
#   (~/.config/gui-61/credentials.env, 600) lalu di-sync ke .61.
# DI_PROXY dibaca dari ~/.config/dataimpulse/proxy.env (durable di hub).
#
# Pemakaian: ./bring-up-gui-61.sh
# Exit: 0 live · 1 gagal / .61 belum dinyalakan user.
# =====================================================================
set -uo pipefail

G_HOST="${G_HOST:-gogobuda65@10.66.66.61}"
G_KEY="${G_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
G_CRED="${G_CRED:-$HOME/.config/gui-61/credentials.env}"
DI_CRED="${DI_CRED:-$HOME/.config/dataimpulse/proxy.env}"
GUI_URL="${GUI_URL:-http://10.66.66.61:3000}"
HERE="$(cd "$(dirname "$0")" && pwd)"

log(){ echo "[bring-up-gui-61 $(date -u +%H:%M:%S)] $*"; }
g61(){ ssh -o ControlPath=none -i "$G_KEY" -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
        -o BatchMode=yes "$G_HOST" "$@"; }

# ── 1. Kredensial hub (dibuat sekali) ───────────────────────────────────────
mkdir -p "$(dirname "$G_CRED")"
if [ ! -f "$G_CRED" ]; then
  log "credentials.env absen -> buat GUI_USER + GUI_PASSWORD acak."
  { printf 'GUI_USER=gogobud\n'; printf 'GUI_PASSWORD=%s\n' "$(openssl rand -base64 24 | tr -d '/+=\n' | cut -c1-24)"; } > "$G_CRED"
  chmod 600 "$G_CRED"
fi
set -a; . "$G_CRED"; set +a
if [ -f "$DI_CRED" ]; then set -a; . "$DI_CRED"; set +a; fi
[ -n "${DI_PROXY:-}" ] || { log "GAGAL: DI_PROXY kosong (cek $DI_CRED)."; exit 1; }

# ── 2. Fast path: sudah live? ───────────────────────────────────────────────
if [ "$(curl -m8 -s -o /dev/null -w '%{http_code}' "$GUI_URL/")" = "401" ]; then
  log "SUDAH live (GUI auth aktif, 401 tanpa login). Tak ada yang perlu dilakukan."
  exit 0
fi

# ── 3. .61 bisa di-SSH? ─────────────────────────────────────────────────────
if ! g61 true 2>/dev/null; then
  log "GAGAL: .61 tak bisa di-SSH. Nyalakan Cloud Shell gogobuda65 + paste bootstrap, lalu ulangi."
  exit 1
fi

# ── 4. Sync compose + cdp script; tulis .env (chmod 600) ────────────────────
g61 'mkdir -p ~/gui-61/config'
scp -q -i "$G_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$HERE/docker-compose.yml" "$HERE/cdp_cookies.py" "$G_HOST:~/gui-61/"
g61 "umask 077; cat > ~/gui-61/.env" <<ENV
GUI_USER=${GUI_USER}
GUI_PASSWORD=${GUI_PASSWORD}
DI_PROXY=${DI_PROXY}
ENV

# ── 5. Nyalakan (build tak perlu; image pull) ───────────────────────────────
log "docker compose up -d di .61 ..."
g61 'cd ~/gui-61 && docker compose up -d 2>&1 | tail -5'

# ── 6. Verifikasi: 401 tanpa login = auth menggigit ─────────────────────────
sleep 8
code="$(curl -m8 -s -o /dev/null -w '%{http_code}' "$GUI_URL/")"
proxy="$(g61 'curl -s -m30 --socks5-hostname 127.0.0.1:1080 https://ifconfig.co/ip' 2>/dev/null)"
log "GUI http=$code  egress via relay=${proxy:-<tak terukur>}"
[ "$code" = "401" ] && [ -n "$proxy" ] && { log "OK: GUI live, egress residensial aktif."; exit 0; }
log "!!! Verifikasi GAGAL. Cek: ssh .61 'cd ~/gui-61 && docker compose logs --tail 40'"
exit 1
