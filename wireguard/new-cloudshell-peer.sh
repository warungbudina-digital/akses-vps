#!/usr/bin/env bash
# new-cloudshell-peer.sh
#
# Run ON THE akses-vps SERVER (as root). One command per Google account you want
# to add as a SEPARATE ephemeral Cloud Shell peer (Option B):
#
#   sudo ./new-cloudshell-peer.sh <label> [tunnel-ip]
#
# For each account it:
#   1. generates a FRESH WireGuard keypair (unique per peer),
#   2. picks a free 10.66.66.X tunnel IP (or uses the one you pass),
#   3. registers the pubkey on this server via register-client-peer.sh (persistent),
#   4. writes a ready-to-paste ephemeral bootstrap file with that peer's fixed key
#      baked in, at ./bootstraps/<label>-ephemeral-bootstrap.sh
#
# Then, on that account's Cloud Shell (ephemeral), paste the generated bootstrap
# and `sudo bash` it each session. The WG key is fixed, so the server
# registration stays valid forever - you never re-register that peer.
#
# ⚠️ Each generated bootstrap contains a WG PRIVATE KEY = a credential into this
#    hub. Store them in a password manager; do not commit to a public repo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WG_CONF="/etc/wireguard/wg0.conf"
SUBNET_PREFIX="10.66.66"
REGISTER="$HERE/register-client-peer.sh"
OUTDIR="$HERE/bootstraps"

# ---- shared hub constants (same in every bootstrap) ----
SERVER_PUBKEY="Jquw62SGYrgeUJhDcBrbmQ8FkBDj37+ccqi15f9RzyE="
SERVER_ENDPOINT="103.217.144.104:51820"
ALLOWED_IPS="10.66.66.1/32"
ADMIN_SSH_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBiEl3eJfIZLlDp20T7o9pF+v74c7X3rLns2qd9QNPRV akses-vps-cloudshell-admin"
ADMIN_KEY_OPTIONS='from="10.66.66.1",restrict,pty'

log() { echo "[new-peer] $*"; }
die() { echo "[new-peer] ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (sudo ./new-cloudshell-peer.sh <label> [ip])"
command -v wg >/dev/null 2>&1 || die "wg not found - wireguard-tools missing on the server?"
[ -f "$WG_CONF" ] || die "$WG_CONF not found"
[ -x "$REGISTER" ] || die "$REGISTER not found/executable next to this script"

LABEL="${1:-}"
TUNNEL_IP="${2:-}"
[ -n "$LABEL" ] || { echo "usage: $0 <label> [tunnel-ip]" >&2; exit 1; }

# ---- pick a free tunnel IP if none given (so we know it for the bootstrap) ----
if [ -z "$TUNNEL_IP" ]; then
  for i in $(seq 2 254); do
    if ! grep -qF "AllowedIPs = $SUBNET_PREFIX.$i/32" "$WG_CONF"; then
      TUNNEL_IP="$SUBNET_PREFIX.$i"; break
    fi
  done
  [ -n "$TUNNEL_IP" ] || die "no free address in $SUBNET_PREFIX.0/24"
  log "auto-picked free tunnel IP: $TUNNEL_IP"
else
  TUNNEL_IP="${TUNNEL_IP%/32}"
  grep -qF "AllowedIPs = $TUNNEL_IP/32" "$WG_CONF" && die "$TUNNEL_IP/32 already assigned - pick another or omit to auto-pick"
fi

# ---- generate a fresh unique keypair for this peer ----
PRIV="$(wg genkey)"
PUB="$(printf '%s' "$PRIV" | wg pubkey)"
log "generated keypair for '$LABEL' - pubkey $PUB"

# ---- register the pubkey on the server (persistent, reload without downtime) ----
log "registering peer on server..."
"$REGISTER" "$LABEL" "$PUB" "$TUNNEL_IP" >/dev/null || die "registration failed - see register-client-peer.sh output"
log "registered '$LABEL' at $TUNNEL_IP/32 (persistent in $WG_CONF)"

# ---- emit the per-account ephemeral bootstrap ----
mkdir -p "$OUTDIR"; chmod 700 "$OUTDIR"
OUT="$OUTDIR/${LABEL}-ephemeral-bootstrap.sh"
umask 077
cat > "$OUT" <<BOOTSTRAP
#!/usr/bin/env bash
# ${LABEL}-ephemeral-bootstrap.sh  (Opsi B - Cloud Shell EPHEMERAL, peer '${LABEL}')
# Paste on this account's Cloud Shell each session:  sudo bash ${LABEL}-ephemeral-bootstrap.sh
# WG key is FIXED so the server registration stays valid - never re-register.
# ⚠️ Contains a WG private key = hub credential. Keep it in a password manager.
set -euo pipefail
WG_PRIVATE_KEY="${PRIV}"
CLIENT_TUNNEL_IP="${TUNNEL_IP}/32"
SERVER_PUBKEY="${SERVER_PUBKEY}"
SERVER_ENDPOINT="${SERVER_ENDPOINT}"
ALLOWED_IPS="${ALLOWED_IPS}"
ADMIN_SSH_PUBKEY="${ADMIN_SSH_PUBKEY}"
ADMIN_KEY_OPTIONS='${ADMIN_KEY_OPTIONS}'
SSH_KEYS_FILE="/etc/ssh/keys/authorized_keys"
WG_IF="wg0"
log(){ echo "[${LABEL}-boot] \$*"; }
[ "\$(id -u)" -eq 0 ] || { echo "harus root: sudo bash \$0" >&2; exit 1; }
# File ini memuat WG private key (kredensial hub) - segera batasi ke pemilik saja
# supaya tidak world-readable (default 664/775 saat dibuat via editor). No-op kalau
# di-pipe via stdin (\$0 bukan file).
[ -f "\$0" ] && chmod 600 "\$0" 2>/dev/null || true
command -v wg >/dev/null 2>&1 || { log "install wireguard-tools"; apt-get update -qq && apt-get install -y -qq wireguard-tools; }
mkdir -p /etc/wireguard; chmod 700 /etc/wireguard
cat > /etc/wireguard/\$WG_IF.conf <<EOF
[Interface]
PrivateKey = \$WG_PRIVATE_KEY
Address = \$CLIENT_TUNNEL_IP

[Peer]
PublicKey = \$SERVER_PUBKEY
Endpoint = \$SERVER_ENDPOINT
AllowedIPs = \$ALLOWED_IPS
PersistentKeepalive = 25
EOF
chmod 600 /etc/wireguard/\$WG_IF.conf
wg-quick down \$WG_IF 2>/dev/null || true
wg-quick up \$WG_IF
log "wg0 up sbg \$(wg show \$WG_IF public-key) di \$CLIENT_TUNNEL_IP"
if ping -c1 -W2 "\${ALLOWED_IPS%/*}" >/dev/null 2>&1; then log "tunnel ke hub OK."; else log "tunnel BELUM jawab - cek handshake."; fi
SSH_KEYS_DIR="\$(dirname "\$SSH_KEYS_FILE")"
mkdir -p "\$SSH_KEYS_DIR"; touch "\$SSH_KEYS_FILE"
chmod 755 "\$SSH_KEYS_DIR"; chmod 644 "\$SSH_KEYS_FILE"; chown root:root "\$SSH_KEYS_DIR" "\$SSH_KEYS_FILE" 2>/dev/null || true
LINE="\${ADMIN_KEY_OPTIONS:+\$ADMIN_KEY_OPTIONS }\$ADMIN_SSH_PUBKEY"
MATERIAL="\$(printf '%s\n' "\$LINE" | grep -oE 'AAAA[0-9A-Za-z+/]+=*' | head -n1)"
(
  flock -w 10 200 || { log "lock gagal, skip"; exit 0; }
  grep -qF "\$MATERIAL" "\$SSH_KEYS_FILE" 2>/dev/null && { grep -vF "\$MATERIAL" "\$SSH_KEYS_FILE" > "\$SSH_KEYS_FILE.tmp" || :; cat "\$SSH_KEYS_FILE.tmp" > "\$SSH_KEYS_FILE"; rm -f "\$SSH_KEYS_FILE.tmp"; }
  echo "\$LINE" >> "\$SSH_KEYS_FILE"
) 200>"\$SSH_KEYS_FILE.lock"
grep -qF "\$MATERIAL" "\$SSH_KEYS_FILE" && log "SSH ACCESS READY - dari VPS: ssh -i ~/.ssh/akses-vps-cloudshell-admin -o IdentitiesOnly=yes -p 22 \$(basename \$(getent passwd 1000 | cut -d: -f6))@\${CLIENT_TUNNEL_IP%/*}" || log "!!! SSH NOT READY"
log "DONE (peer '${LABEL}', ephemeral, key TETAP)."
BOOTSTRAP
chmod 600 "$OUT"

log "DONE. Bootstrap for '$LABEL' -> $OUT"
log "  Peer:   $LABEL @ $TUNNEL_IP/32  (pubkey $PUB)"
log "  Next:   paste $OUT on that account's Cloud Shell, then: sudo bash <file>"
log "  Store this file securely (it holds a WG private key)."
