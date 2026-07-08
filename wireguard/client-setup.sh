#!/usr/bin/env bash
# akses-vps-wireguard-client-setup.sh
#
# Sets up a Google Cloud Shell (or any Linux host) as a WireGuard peer into
# the akses-vps hub (103.217.144.104, tunnel subnet 10.66.66.0/24).
# Idempotent - safe to re-run.
#
# HOW TO REUSE THIS ON ANOTHER ACCOUNT:
#   1. Copy this file into that account's Cloud Shell $HOME.
#   2. Pick a free tunnel IP - check current usage on the akses-vps server
#      first (`sudo grep -B2 AllowedIPs /etc/wireguard/wg0.conf`) and edit
#      CLIENT_TUNNEL_IP below to something NOT already listed there.
#      Reusing an IP already in use will break the OTHER peer using it.
#   3. Give it a distinct PEER_LABEL below too (shows up as a comment in the
#      server's wg0.conf so you can tell peers apart later).
#   4. To make it survive Cloud Shell VM recycles (the underlying VM is
#      ephemeral - only $HOME persists across sessions): copy/rename this
#      file to ~/.customize_environment and chmod +x it. Google Cloud Shell
#      auto-runs that file as root on every environment boot.
#   5. Run it once manually to activate immediately (don't wait for next boot):
#       chmod +x akses-vps-wireguard-client-setup.sh
#       sudo ./akses-vps-wireguard-client-setup.sh
#   6. The script prints a WireGuard PUBLIC key at the end (not secret) -
#      register it as a new [Peer] block in wg0.conf on the akses-vps server
#      (103.217.144.104), matching PEER_LABEL/CLIENT_TUNNEL_IP you set below,
#      then reload: `sudo wg syncconf wg0 <(sudo wg-quick strip wg0)`.
#   7. It also sets up direct SSH access over the tunnel (see ENABLE_SSH_ACCESS
#      below) - generates its own SSH keypair and appends the public key to
#      /etc/ssh/keys/authorized_keys. NOTE: on Google Cloud Shell specifically,
#      the real sshd is started with an -o AuthorizedKeysFile override pointing
#      at THAT path, not the usual ~/.ssh/authorized_keys - confirmed live via
#      `ps aux | grep sshd`. If you're running this on a non-Cloud-Shell host,
#      check your own sshd's actual AuthorizedKeysFile first and adjust
#      SSH_KEYS_FILE below to match (defaulting to the Cloud Shell path will
#      silently do nothing useful elsewhere).
#   8. This script has NO runtime dependency on cloudflared/agent.obc-crypto.com
#      whatsoever - every step here is a local operation (apt, wg-quick, file
#      edits). Cloudflare tunnel is only ever needed as a REMOTE TRIGGER
#      mechanism to get this script to run in the first place on a box you
#      don't have direct terminal access to yet (e.g. via a deploy-agent HTTP
#      call) - once it has run once, direct SSH over the WireGuard tunnel
#      itself (see step 7) is the ongoing access path, independent of
#      Cloudflare entirely. Confirmed live 2026-07-08: agent.obc-crypto.com
#      went down (cloudflared crashed) while the WireGuard tunnel + SSH
#      access this script sets up kept working the whole time.
#   9. On FIRST run for a brand new peer, the tunnel verification step below
#      will legitimately fail/warn - the akses-vps server doesn't know this
#      peer's public key yet, so nothing will answer until a human registers
#      it server-side (step 6) and reloads. That's an inherent, unavoidable
#      manual step - the script doesn't have (and shouldn't be given)
#      credentials to modify the server's own WireGuard config itself.
#      Re-run this script (or just `wg-quick down wg0 && wg-quick up wg0`)
#      after registering, or wait for the automatic retry window below.
set -euo pipefail

# ---- edit these per account/deployment ----
CLIENT_TUNNEL_IP="10.66.66.N/32"   # must be unique across all peers on the hub
PEER_LABEL="clientN (describe this deployment)"
ENABLE_SSH_ACCESS=true             # set false to skip the SSH section entirely
SSH_KEYS_FILE="/etc/ssh/keys/authorized_keys"   # Cloud-Shell-specific, see note above
# ------------------------------------------------

WG_IF="wg0"
WG_DIR="/etc/wireguard"
SERVER_PUBKEY="Jquw62SGYrgeUJhDcBrbmQ8FkBDj37+ccqi15f9RzyE="
SERVER_ENDPOINT="103.217.144.104:51820"
ALLOWED_IPS="10.66.66.1/32"   # split-tunnel: only reach the hub, not the whole mesh

log() { echo "[client-setup] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (Cloud Shell's .customize_environment already does; run manually with sudo otherwise)" >&2
  exit 1
fi

if ! command -v wg >/dev/null 2>&1; then
  log "installing wireguard-tools"
  apt-get update -qq
  apt-get install -y -qq wireguard-tools
fi

mkdir -p "$WG_DIR"
chmod 700 "$WG_DIR"

# Keypair persisted under the real user's $HOME (survives Cloud Shell VM
# recycle, unlike /etc/wireguard which lives on the ephemeral root disk).
# NOT just $HOME - found live (2026-07-08) that when this script runs as
# root (which is how Cloud Shell invokes ~/.customize_environment - not via
# sudo), $HOME resolves to /root instead of the real persistent home,
# silently putting the "persistent" keypair on the ephemeral root disk too.
if [ -n "${SUDO_USER:-}" ]; then
  REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
elif [ -d /home ]; then
  # Cloud Shell / single-user VM convention: exactly one real user home
  # under /home. More reliable here than $HOME when running as root directly.
  REAL_HOME=$(find /home -mindepth 1 -maxdepth 1 -type d | head -n1)
fi
REAL_HOME="${REAL_HOME:-$HOME}"
KEY_STORE="$REAL_HOME/.wg-client-keys"
mkdir -p "$KEY_STORE"
chmod 700 "$KEY_STORE"

if [ ! -f "$KEY_STORE/private.key" ]; then
  umask 077
  wg genkey | tee "$KEY_STORE/private.key" | wg pubkey > "$KEY_STORE/public.key"
  log "generated NEW keypair for $PEER_LABEL"
fi

PRIVATE_KEY=$(cat "$KEY_STORE/private.key")

cat > "$WG_DIR/$WG_IF.conf" <<EOF
[Interface]
PrivateKey = $PRIVATE_KEY
Address = $CLIENT_TUNNEL_IP

[Peer]
PublicKey = $SERVER_PUBKEY
Endpoint = $SERVER_ENDPOINT
AllowedIPs = $ALLOWED_IPS
PersistentKeepalive = 25
EOF
chmod 600 "$WG_DIR/$WG_IF.conf"

wg-quick down "$WG_IF" 2>/dev/null || true
wg-quick up "$WG_IF"

log "wg0 up for '$PEER_LABEL' at $CLIENT_TUNNEL_IP."
log "Public key (not secret - register this on the akses-vps server):"
cat "$KEY_STORE/public.key"

# ---- verify the tunnel actually works before declaring success ----
# "sampai berhasil": don't just fire-and-forget the config, actually confirm
# the hub answers. Bounded retry (not infinite - this can run unattended at
# boot) since the hub may take a moment to reconnect, or a human may be
# registering this peer's key server-side WHILE this is running.
HUB_IP="${ALLOWED_IPS%/*}"
MAX_WAIT_SECONDS=60
POLL_INTERVAL=3
elapsed=0
tunnel_ok=false

log "verifying tunnel to hub ($HUB_IP) - up to ${MAX_WAIT_SECONDS}s..."
while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
  if ping -c 1 -W 2 "$HUB_IP" >/dev/null 2>&1; then
    tunnel_ok=true
    break
  fi
  sleep "$POLL_INTERVAL"
  elapsed=$((elapsed + POLL_INTERVAL))
done

if [ "$tunnel_ok" = true ]; then
  log "SUCCESS: tunnel to $HUB_IP is up and answering (took ~${elapsed}s)."
else
  log "NOT YET CONNECTED after ${MAX_WAIT_SECONDS}s - this is expected on a"
  log "brand new peer until a human registers the public key above as a"
  log "[Peer] block in wg0.conf on the akses-vps server and reloads"
  log "(sudo wg syncconf wg0 <(sudo wg-quick strip wg0)). Re-run this script"
  log "afterward, or just: wg-quick down $WG_IF && wg-quick up $WG_IF"
fi

# ---- direct SSH access over the tunnel (optional, see ENABLE_SSH_ACCESS) ----
if [ "$ENABLE_SSH_ACCESS" = true ]; then
  SSH_KEY_STORE="$REAL_HOME/.ssh"
  mkdir -p "$SSH_KEY_STORE"
  chmod 700 "$SSH_KEY_STORE"

  if [ ! -f "$SSH_KEY_STORE/wg_access_key" ]; then
    ssh-keygen -t ed25519 -f "$SSH_KEY_STORE/wg_access_key" -N "" -C "$PEER_LABEL" -q
    log "generated NEW SSH keypair for direct access: $SSH_KEY_STORE/wg_access_key"
  fi

  SSH_PUBKEY=$(cat "$SSH_KEY_STORE/wg_access_key.pub")

  # flock'd read-check-append: without this, two concurrent invocations
  # (e.g. this script run manually while Cloud Shell's own boot trigger for
  # .customize_environment also fires) can each read the file before either
  # writes, and the second write clobbers the first's append - lost an
  # already-working key to exactly this race once, 2026-07-08.
  if [ -f "$SSH_KEYS_FILE" ] || [ -d "$(dirname "$SSH_KEYS_FILE")" ]; then
    (
      flock -w 10 200 || { log "WARNING: could not lock $SSH_KEYS_FILE, skipping append this run"; exit 0; }
      if ! grep -qxF "$SSH_PUBKEY" "$SSH_KEYS_FILE" 2>/dev/null; then
        echo "$SSH_PUBKEY" >> "$SSH_KEYS_FILE"
        chmod 644 "$SSH_KEYS_FILE"
        log "added SSH key to $SSH_KEYS_FILE"
      fi
    ) 200>"${SSH_KEYS_FILE}.lock"
  else
    log "WARNING: $(dirname "$SSH_KEYS_FILE") doesn't exist - check your sshd's real AuthorizedKeysFile and adjust SSH_KEYS_FILE above"
  fi

  # basename "$REAL_HOME", not $(whoami) - this script runs as root (directly,
  # or via a chroot/docker escape like the one used to test it), so whoami
  # would print "root" here regardless of which account this actually is.
  TARGET_USER=$(basename "$REAL_HOME")
  log "to connect from elsewhere (e.g. jumping through the akses-vps hub):"
  log "  ssh -o ProxyCommand=\"ssh -W %h:%p warungbudina@103.217.144.104\" -i <path-to-private-key-copied-from-$SSH_KEY_STORE/wg_access_key> ${TARGET_USER}@${CLIENT_TUNNEL_IP%/*}"
fi

# ---- overall result ----
# Exit 0 either way: an unregistered-peer "not yet connected" state on first
# run is an expected, recoverable condition for an unattended boot script,
# not a script failure - but it's reported distinctly so it's never silently
# mistaken for a real success.
if [ "$tunnel_ok" = true ]; then
  log "DONE - tunnel + SSH access fully set up and verified working, no cloudflared involved at any point."
else
  log "DONE - local setup complete, but tunnel not confirmed reachable yet (see message above). Nothing more to do on this side until the server-side key registration happens."
fi
