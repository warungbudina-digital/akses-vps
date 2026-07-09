#!/usr/bin/env bash
# deregister-client-peer.sh
#
# Companion to register-client-peer.sh. Run ON THE akses-vps SERVER (as root)
# to remove a peer's [Peer] block from wg0.conf - e.g. when a client's key
# changed (re-registering the same label with a new key must go through this
# first, otherwise you end up with two [Peer] blocks for one client) or the
# client is being decommissioned. Backs up first, removes exactly one
# [Peer] block, reloads wg0 without downtime, rolls back automatically if
# the reload fails.
#
# Usage:
#   sudo ./deregister-client-peer.sh <label|public-key|tunnel-ip> [-y]
#
# Examples:
#   sudo ./deregister-client-peer.sh client7
#   sudo ./deregister-client-peer.sh 10.66.66.8
#   sudo ./deregister-client-peer.sh iXu7Zv4ZrOcKYXqRH/n19PFYtF/LQ7HTwS9RHmLpZ2c=
#   sudo ./deregister-client-peer.sh client7 -y      # skip the confirmation prompt
#
# The identifier is auto-detected: a 44-char base64 string is treated as a
# public key, something IP-shaped is treated as a tunnel IP (bare "8" is
# shorthand for 10.66.66.8), anything else is matched against the label in
# each [Peer] block's leading "# label ..." comment (whole-label match, so
# "client1" never matches "client10").
set -euo pipefail

WG_CONF="/etc/wireguard/wg0.conf"
WG_IF="wg0"
SUBNET_PREFIX="10.66.66"

log() { echo "[deregister-peer] $*"; }
die() { echo "[deregister-peer] ERROR: $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "must run as root (sudo ./deregister-client-peer.sh ...)"
fi

command -v wg >/dev/null 2>&1 || die "wg not found - is wireguard-tools installed?"
command -v wg-quick >/dev/null 2>&1 || die "wg-quick not found - is wireguard-tools installed?"
[ -f "$WG_CONF" ] || die "$WG_CONF not found"

IDENTIFIER="${1:-}"
ASSUME_YES=false
for arg in "$@"; do
  [ "$arg" = "-y" ] || [ "$arg" = "--yes" ] && ASSUME_YES=true
done

if [ -z "$IDENTIFIER" ]; then
  echo "usage: $0 <label|public-key|tunnel-ip> [-y]" >&2
  exit 1
fi

# ---- figure out which [Peer] block this identifies, and pull its PublicKey
#      (the unique key used to actually locate/remove the block) ----
TARGET_PUBKEY=""
MATCH_DESC=""

if [[ "$IDENTIFIER" =~ ^[A-Za-z0-9+/]{43}=$ ]]; then
  # looks like a public key
  TARGET_PUBKEY="$IDENTIFIER"
  grep -qF "PublicKey = $TARGET_PUBKEY" "$WG_CONF" || die "no peer with public key '$TARGET_PUBKEY' found in $WG_CONF"
  MATCH_DESC="public key $TARGET_PUBKEY"

elif [[ "$IDENTIFIER" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/32)?$ ]] || [[ "$IDENTIFIER" =~ ^[0-9]{1,3}$ ]]; then
  # looks like a full tunnel IP, or a bare last-octet shorthand
  if [[ "$IDENTIFIER" =~ ^[0-9]{1,3}$ ]]; then
    TARGET_IP="$SUBNET_PREFIX.$IDENTIFIER"
  else
    TARGET_IP="${IDENTIFIER%/32}"
  fi
  TARGET_PUBKEY=$(awk -v RS="" -v ip="AllowedIPs = $TARGET_IP/32" '
    index($0, ip) { for (i=1;i<=NF;i++) if ($i=="PublicKey") print $(i+2) }
  ' "$WG_CONF")
  [ -n "$TARGET_PUBKEY" ] || die "no peer with tunnel IP $TARGET_IP/32 found in $WG_CONF"
  MATCH_DESC="tunnel IP $TARGET_IP/32"

else
  # treat as a label - match the whole label on a "# label ..." comment line,
  # so "client1" doesn't also match "client10"
  MATCHES=$(awk -v RS="" -v label="$IDENTIFIER" '
    {
      n = split($0, lines, "\n")
      for (i=1;i<=n;i++) {
        if (lines[i] ~ ("^# " label "([ (]|$)")) {
          for (j=1;j<=n;j++) {
            if (lines[j] ~ /^PublicKey = /) { sub(/^PublicKey = /, "", lines[j]); print lines[j]; break }
          }
        }
      }
    }
  ' "$WG_CONF")
  MATCH_COUNT=$(printf '%s\n' "$MATCHES" | grep -c . || true)
  if [ "$MATCH_COUNT" -eq 0 ]; then
    die "no peer labeled '$IDENTIFIER' found in $WG_CONF (check 'sudo wg show' or grep the comments in $WG_CONF)"
  elif [ "$MATCH_COUNT" -gt 1 ]; then
    die "label '$IDENTIFIER' matches more than one [Peer] block - re-run with the exact public key instead"
  fi
  TARGET_PUBKEY="$MATCHES"
  MATCH_DESC="label '$IDENTIFIER'"
fi

[ -n "$TARGET_PUBKEY" ] || die "could not resolve '$IDENTIFIER' to a peer"

# ---- refuse to remove the server's own key (shouldn't be possible via the
#      lookups above, but guard it explicitly since this is destructive) ----
SERVER_PUBKEY=$(wg show "$WG_IF" public-key 2>/dev/null || true)
[ -n "$SERVER_PUBKEY" ] && [ "$TARGET_PUBKEY" = "$SERVER_PUBKEY" ] && die "refusing to remove this server's own key"

TARGET_BLOCK=$(awk -v RS="" -v ORS="\n\n" -v key="PublicKey = $TARGET_PUBKEY" 'index($0, key)' "$WG_CONF")
log "matched via $MATCH_DESC - block to remove:"
echo "$TARGET_BLOCK" | sed 's/^/    /'

if [ "$ASSUME_YES" != true ]; then
  read -r -p "[deregister-peer] Remove this peer and reload $WG_IF now? [y/N] " REPLY
  [[ "$REPLY" =~ ^[Yy]$ ]] || die "aborted, nothing changed"
fi

# ---- back up before touching the live config ----
BACKUP="$WG_CONF.bak-$(date +%Y%m%d%H%M%S)"
cp "$WG_CONF" "$BACKUP"
log "backed up current config to $BACKUP"

# ---- remove exactly that one [Peer] paragraph, keep everything else
#      (including [Interface], byte-for-byte) untouched ----
awk -v RS="" -v ORS="\n\n" -v key="PublicKey = $TARGET_PUBKEY" '
  !index($0, key) { print }
' "$WG_CONF" | sed -e '$ { /^$/d }' > "$WG_CONF.new"

mv "$WG_CONF.new" "$WG_CONF"
chmod 600 "$WG_CONF"
chown root:root "$WG_CONF"
log "removed [Peer] block for $MATCH_DESC"

# ---- reload without downtime, rollback on failure ----
if ! wg syncconf "$WG_IF" <(wg-quick strip "$WG_IF"); then
  log "reload FAILED - restoring backup"
  cp "$BACKUP" "$WG_CONF"
  die "wg syncconf failed, $WG_CONF restored from backup - nothing was left half-applied"
fi
log "reloaded $WG_IF (remaining peers untouched)"

# ---- verify the peer is actually gone from the live interface ----
if wg show "$WG_IF" | grep -qF "$TARGET_PUBKEY"; then
  die "peer still shows up in 'wg show $WG_IF' after reload - investigate before trusting this removal"
fi
log "SUCCESS: peer removed and confirmed absent from 'wg show $WG_IF'"

echo
log "current peer list:"
wg show "$WG_IF"
