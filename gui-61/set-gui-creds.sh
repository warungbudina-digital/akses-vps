#!/usr/bin/env bash
# =====================================================================
# set-gui-creds.sh — terapkan kredensial GUI dari hub ke .61 lalu recreate
# gui-chromium. Sumber kredensial: ~/.config/gui-61/credentials.env (hub).
# Dijalankan DI akses-vps. Tidak mencetak nilai secret.
# =====================================================================
set -euo pipefail

G_HOST="${G_HOST:-gogobuda65@10.66.66.61}"
G_KEY="${G_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
CRED="$HOME/.config/gui-61/credentials.env"
DI_CRED="$HOME/.config/dataimpulse/proxy.env"

set -a; . "$CRED"; . "$DI_CRED"; set +a
SSH=(ssh -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -o ConnectTimeout=10 -i "$G_KEY" "$G_HOST")

"${SSH[@]}" "umask 077; cat > ~/gui-61/.env" <<ENV
GUI_USER=${GUI_USER}
GUI_PASSWORD=${GUI_PASSWORD}
DI_PROXY=${DI_PROXY}
ENV

"${SSH[@]}" 'cd ~/gui-61 && docker compose up -d && docker compose ps --format "{{.Name}} {{.Status}}"'

sleep 8
echo "GUI http=$(curl -s -m8 -o /dev/null -w '%{http_code}' http://10.66.66.61:3000/) (401 = auth aktif)"
echo "user GUI: ${GUI_USER}"
