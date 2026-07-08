#!/usr/bin/env bash
# register-client-peer.sh
#
# Run ON THE akses-vps SERVER (as root) once you've received a public key
# from a client that ran akses-vps-wireguard-client-setup*.sh on a Google
# Cloud Shell (or anywhere else). Adds it as a new [Peer], reloads wg0
# without downtime, and verifies connectivity - the same sequence done
# manually for client1/client2/client3, now automated with the safety
# checks that sequence actually needed in practice.
#
# Usage:
#   sudo ./register-client-peer.sh <label> <public-key> [tunnel-ip]
#
# Examples:
#   sudo ./register-client-peer.sh client4 bH3OPgDxCUa0Ew95GTcjEzgEIo7Gc0j4z0DtFpt8qiA=
#   sudo ./register-client-peer.sh client4 bH3OPgDxCUa0Ew95GTcjEzgEIo7Gc0j4z0DtFpt8qiA= 10.66.66.5
#
# If tunnel-ip is omitted, the next free 10.66.66.N address is picked
# automatically (skipping anything already in wg0.conf).
set -euo pipefail

WG_CONF="/etc/wireguard/wg0.conf"
WG_IF="wg0"
SUBNET_PREFIX="10.66.66"
MAX_WAIT_SECONDS=30
POLL_INTERVAL=3

log() { echo "[register-peer] $*"; }
die() { echo "[register-peer] ERROR: $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "must run as root (sudo ./register-client-peer.sh ...)"
fi

command -v wg >/dev/null 2>&1 || die "wg not found - is wireguard-tools installed?"
command -v wg-quick >/dev/null 2>&1 || die "wg-quick not found - is wireguard-tools installed?"
[ -f "$WG_CONF" ] || die "$WG_CONF not found"

LABEL="${1:-}"
PUBKEY="${2:-}"
TUNNEL_IP="${3:-}"

if [ -z "$LABEL" ] || [ -z "$PUBKEY" ]; then
  echo "usage: $0 <label> <public-key> [tunnel-ip]" >&2
  exit 1
fi

# ---- validate public key format (44 base64 chars, decodes to 32 bytes) ----
if ! [[ "$PUBKEY" =~ ^[A-Za-z0-9+/]{43}=$ ]]; then
  die "'$PUBKEY' doesn't look like a WireGuard public key (expected 44 base64 chars ending in '=')"
fi
DECODED_LEN=$(echo "$PUBKEY" | base64 -d 2>/dev/null | wc -c) || die "'$PUBKEY' is not valid base64"
[ "$DECODED_LEN" -eq 32 ] || die "'$PUBKEY' decodes to $DECODED_LEN bytes, expected 32 - not a real WireGuard key"

# ---- catch the single most common mistake seen in practice: pasting the
#      SERVER's own public key instead of a client-generated one ----
SERVER_PUBKEY=$(wg show "$WG_IF" public-key 2>/dev/null || true)
if [ -n "$SERVER_PUBKEY" ] && [ "$PUBKEY" = "$SERVER_PUBKEY" ]; then
  die "that IS this server's own public key, not a client key. On the CLIENT, use 'sudo cat ~/.wg-client-keys/public.key' or the 'interface: wg0 / public key:' line (not the 'peer:' line) from 'wg show' run there."
fi

# ---- reject if this exact public key is already registered ----
if grep -qF "PublicKey = $PUBKEY" "$WG_CONF"; then
  die "this public key is already registered in $WG_CONF - nothing to do. Check 'sudo wg show' for its current status."
fi

# ---- resolve the tunnel IP ----
if [ -z "$TUNNEL_IP" ]; then
  for i in $(seq 2 254); do
    CANDIDATE="$SUBNET_PREFIX.$i"
    if ! grep -qF "AllowedIPs = $CANDIDATE/32" "$WG_CONF"; then
      TUNNEL_IP="$CANDIDATE"
      break
    fi
  done
  [ -n "$TUNNEL_IP" ] || die "could not find a free address in $SUBNET_PREFIX.0/24"
  log "no IP given, auto-picked free address: $TUNNEL_IP"
else
  TUNNEL_IP="${TUNNEL_IP%/32}"
fi

if grep -qF "AllowedIPs = $TUNNEL_IP/32" "$WG_CONF"; then
  die "$TUNNEL_IP/32 is already assigned to another peer in $WG_CONF - pick a different IP or omit it to auto-pick"
fi

# ---- back up before touching the live config ----
BACKUP="$WG_CONF.bak-$(date +%Y%m%d%H%M%S)"
cp "$WG_CONF" "$BACKUP"
log "backed up current config to $BACKUP"

# ---- append the new peer ----
cat >> "$WG_CONF" <<EOF

[Peer]
# $LABEL (registered $(date -u +%Y-%m-%dT%H:%M:%SZ) via register-client-peer.sh)
PublicKey = $PUBKEY
AllowedIPs = $TUNNEL_IP/32
EOF
log "appended [Peer] block for '$LABEL' at $TUNNEL_IP/32"

# ---- reload without downtime ----
if ! wg syncconf "$WG_IF" <(wg-quick strip "$WG_IF"); then
  log "reload FAILED - restoring backup"
  cp "$BACKUP" "$WG_CONF"
  die "wg syncconf failed, $WG_CONF restored from backup - nothing was left half-applied"
fi
log "reloaded $WG_IF (existing peers untouched)"

# ---- verify: wait for a real ping response, bounded retry ----
log "verifying connectivity to $TUNNEL_IP (up to ${MAX_WAIT_SECONDS}s)..."
elapsed=0
ok=false
while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
  if ping -c 1 -W 2 "$TUNNEL_IP" >/dev/null 2>&1; then
    ok=true
    break
  fi
  sleep "$POLL_INTERVAL"
  elapsed=$((elapsed + POLL_INTERVAL))
done

if [ "$ok" = true ]; then
  log "SUCCESS: '$LABEL' ($TUNNEL_IP) registered and answering ping (took ~${elapsed}s)."
else
  log "REGISTERED, but not answering ping yet after ${MAX_WAIT_SECONDS}s."
  log "Normal if the client hasn't run its setup script yet, or its own tunnel"
  log "isn't up right now. Check again later: ping $TUNNEL_IP"
fi

echo
log "current peer list:"
wg show "$WG_IF"
