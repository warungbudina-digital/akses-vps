#!/usr/bin/env bash
# =====================================================================
# setup-gdrive-remotes.sh — hubungkan tiap profil browser ogis ke akun
# Gdrive-nya sendiri via rclone remote terpisah. Dijalankan DI akses-vps.
#
# Sumber kredensial: satu file OAuth-token JSON per profil di
#   ~/.config/ogis-gdrive/<nama-profil>.json
# (pola sama persis `~/.config/vn-gdrive/oauth-token-*.json` yg sudah
# dipakai utk remote `gfootage` — lihat project_viral_analyzer memory).
# BELUM ADA ISI sesi ini (folder disiapkan kosong) -> skrip ini SENGAJA
# no-op anggun (exit 0) kalau tak ada file .json ditemukan.
#
# Hasil: remote `gdrive-<nama-profil>` ditulis ke rclone config TERPISAH
# di ogis (~/browser/.rclone-ogis.conf) -- BUKAN rclone.conf hub, supaya
# 5 token akun beda ini tak campur dgn remote `gfootage` yg sudah ada.
#
# Pemakaian di ogis nanti: rclone --config ~/browser/.rclone-ogis.conf
#   copy <src> gdrive-<nama-profil>:<dest>
# =====================================================================
set -uo pipefail

OGIS_HOST="${OGIS_HOST:-maydualapan8@10.66.66.8}"
OGIS_KEY="${OGIS_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
CRED_DIR="${OGIS_GDRIVE_CRED_DIR:-$HOME/.config/ogis-gdrive}"
REMOTE_CONF="${REMOTE_CONF:-.rclone-ogis.conf}"   # relatif ~/browser di ogis

log(){ echo "[setup-gdrive-remotes $(date -u +%H:%M:%S)] $*"; }
sshogis(){ ssh -o ControlPath=none -i "$OGIS_KEY" -o IdentitiesOnly=yes \
           -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
           -o BatchMode=yes -p 22 "$OGIS_HOST" "$@"; }

if [ ! -d "$CRED_DIR" ]; then
  log "Folder kredensial $CRED_DIR belum ada -> no-op, exit 0."
  exit 0
fi

FILES=("$CRED_DIR"/*.json)
if [ ! -e "${FILES[0]}" ]; then
  log "Tak ada file .json di $CRED_DIR -> no-op, exit 0 (belum ada kredensial diisi)."
  exit 0
fi

CONF_TMP="$(mktemp)"
trap 'rm -f "$CONF_TMP"' EXIT

n=0
for f in "${FILES[@]}"; do
  name="$(basename "$f" .json)"
  remote="gdrive-${name}"
  token="$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))" "$f" 2>/dev/null)"
  if [ -z "$token" ]; then
    log "  [$name] GAGAL baca/parse $f -> skip."
    continue
  fi
  {
    echo "[$remote]"
    echo "type = drive"
    echo "scope = drive"
    echo "token = $token"
    echo
  } >> "$CONF_TMP"
  n=$((n + 1))
  log "  [$name] -> remote $remote disiapkan."
done

if [ "$n" -eq 0 ]; then
  log "Tak ada remote valid tersusun -> tak ada yg dikirim ke ogis."
  exit 0
fi

if sshogis "cat > ~/browser/$REMOTE_CONF" < "$CONF_TMP"; then
  sshogis "chmod 600 ~/browser/$REMOTE_CONF"
  log "OK: $n remote ditulis ke ogis:~/browser/$REMOTE_CONF"
else
  log "GAGAL: kirim config ke ogis."
  exit 1
fi
