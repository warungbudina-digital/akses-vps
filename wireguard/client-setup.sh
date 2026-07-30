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
#      below). The PRIMARY key it authorizes is ADMIN_SSH_PUBKEY - a key whose
#      PRIVATE half already lives on the akses-vps admin box - appended to
#      /etc/ssh/keys/authorized_keys. This is deliberate: it means the VPS can
#      SSH in the moment the tunnel is up, with NO private key ever copied out
#      of this Cloud Shell (that copy-out step was the old chicken-and-egg). A
#      supplementary per-host key (~/.ssh/wg_access_key) is also generated but
#      is optional. NOTE: on Google Cloud Shell specifically, the real sshd is
#      started with an -o AuthorizedKeysFile override pointing at THAT path, not
#      the usual ~/.ssh/authorized_keys - confirmed live via `ps aux | grep
#      sshd`. If you're running this on a non-Cloud-Shell host, check your own
#      sshd's actual AuthorizedKeysFile first and adjust SSH_KEYS_FILE below to
#      match. The script now creates that dir (755, root:root) and file (644)
#      itself every run, so it no longer silently no-ops when the dir is absent.
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
# Public key whose PRIVATE half already lives on the akses-vps admin box.
# Authorizing THIS key (instead of one generated here) is what breaks the
# chicken-and-egg: the VPS connects in immediately with its own private key -
# nothing secret ever has to be copied OUT of this Cloud Shell. A public key is
# not a secret, so it is safe to keep hardcoded here. Leave empty to fall back
# to the old copy-the-private-key-out behaviour (not recommended).
#   private half on the VPS: ~/.ssh/akses-vps-cloudshell-admin
ADMIN_SSH_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBiEl3eJfIZLlDp20T7o9pF+v74c7X3rLns2qd9QNPRV akses-vps-cloudshell-admin"
# ------------------------------------------------

WG_IF="wg0"
WG_DIR="/etc/wireguard"
SERVER_PUBKEY="Jquw62SGYrgeUJhDcBrbmQ8FkBDj37+ccqi15f9RzyE="
SERVER_ENDPOINT="103.217.144.104:51820"
ALLOWED_IPS="10.66.66.1/32"   # split-tunnel: only reach the hub, not the whole mesh
SCRIPT_VERSION="2026-07-30.2" # bump on every change; printed at runtime so a stale Cloud Shell copy of this script is immediately obvious in the logs

log() { echo "[client-setup] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (Cloud Shell's .customize_environment already does; run manually with sudo otherwise)" >&2
  exit 1
fi

# ---- fail fast on unedited placeholders / a malformed tunnel IP ----
# Without this, an unedited CLIENT_TUNNEL_IP ("10.66.66.N/32") fails deep inside
# wg-quick with a cryptic "Bad address" and set -e aborts mid-run. Catch it here
# with a clear message BEFORE anything touches the system.
if [ "$PEER_LABEL" = "clientN (describe this deployment)" ]; then
  echo "[client-setup] ERROR: PEER_LABEL is still the placeholder - edit it near the top." >&2
  exit 1
fi
if [[ ! "$CLIENT_TUNNEL_IP" =~ ^10\.66\.66\.([0-9]{1,3})/32$ ]]; then
  echo "[client-setup] ERROR: CLIENT_TUNNEL_IP='$CLIENT_TUNNEL_IP' is not a real 10.66.66.X/32 address (still the 'N' placeholder?). Edit it near the top." >&2
  exit 1
fi
_octet="${BASH_REMATCH[1]}"
if [ "$_octet" -lt 2 ] || [ "$_octet" -gt 254 ]; then
  echo "[client-setup] ERROR: tunnel IP host octet $_octet out of range - use 2-254 (.1 is the hub itself)." >&2
  exit 1
fi

log "version $SCRIPT_VERSION | peer '$PEER_LABEL' | tunnel $CLIENT_TUNNEL_IP | ssh_access=$ENABLE_SSH_ACCESS"

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
  # Ensure the sshd AuthorizedKeysFile dir exists with the permissions sshd
  # actually needs, EVERY run. Two hard-won reasons this is unconditional now:
  #   1. The old code only appended if the dir already existed, else it just
  #      warned and skipped - so on a fresh VM (before Cloud Shell's onrun.sh
  #      recreated the dir) SSH access was silently never set up.
  #   2. A dir mode of 700 makes pubkey auth fail WITH NO LOG AT ALL (sshd
  #      checks the key as a non-root user and can't traverse a 700 dir).
  #      Force 755 dir / 644 file / root:root to avoid both traps.
  SSH_KEYS_DIR="$(dirname "$SSH_KEYS_FILE")"
  mkdir -p "$SSH_KEYS_DIR"
  touch "$SSH_KEYS_FILE"
  chmod 755 "$SSH_KEYS_DIR"
  chmod 644 "$SSH_KEYS_FILE"
  chown root:root "$SSH_KEYS_DIR" "$SSH_KEYS_FILE" 2>/dev/null || true

  # Race-safe single-append: two concurrent invocations (manual run + Cloud
  # Shell's own boot trigger firing .customize_environment) could each read
  # before either writes and clobber the other's append - lost a working key to
  # exactly this once, 2026-07-08. flock serialises it.
  authorize_key() {
    local pub="$1"
    [ -n "$pub" ] || return 0
    (
      flock -w 10 200 || { log "WARNING: could not lock $SSH_KEYS_FILE, skipping append this run"; exit 0; }
      if ! grep -qxF "$pub" "$SSH_KEYS_FILE" 2>/dev/null; then
        echo "$pub" >> "$SSH_KEYS_FILE"
        log "authorized key: ${pub##* }"
      fi
    ) 200>"${SSH_KEYS_FILE}.lock"
  }

  # PRIMARY - breaks the chicken-and-egg. Authorize a key whose PRIVATE half is
  # already on the akses-vps admin box, so the VPS logs in immediately with NO
  # key transfer out of here.
  if [ -n "${ADMIN_SSH_PUBKEY:-}" ]; then
    authorize_key "$ADMIN_SSH_PUBKEY"
  else
    log "WARNING: ADMIN_SSH_PUBKEY is empty - you will have to MANUALLY copy the"
    log "private half of the key generated below out to the admin box (the exact"
    log "chicken-and-egg this var exists to remove). Set it near the top."
  fi

  # SUPPLEMENTARY - a per-host key owned by THIS Cloud Shell. Optional and not
  # needed for VPS access when ADMIN_SSH_PUBKEY is set; kept for a Cloud-Shell-
  # owned identity if you ever want one.
  SSH_KEY_STORE="$REAL_HOME/.ssh"
  mkdir -p "$SSH_KEY_STORE"
  chmod 700 "$SSH_KEY_STORE"
  if [ ! -f "$SSH_KEY_STORE/wg_access_key" ]; then
    ssh-keygen -t ed25519 -f "$SSH_KEY_STORE/wg_access_key" -N "" -C "$PEER_LABEL" -q
    log "generated supplementary per-host SSH key: $SSH_KEY_STORE/wg_access_key"
  fi
  authorize_key "$(cat "$SSH_KEY_STORE/wg_access_key.pub" 2>/dev/null)"

  # basename "$REAL_HOME", not $(whoami) - this script runs as root, so whoami
  # would print "root" regardless of which account this actually is.
  TARGET_USER=$(basename "$REAL_HOME")

  # This script runs as root, so everything it just created under the real
  # account's ~/.ssh is root-owned - which locks that account out of its OWN
  # ~/.ssh (seen live: `ssh` on the Cloud Shell failed with "identity file ...
  # Permission denied" and could not write known_hosts). Hand ownership back.
  # (/etc/ssh/keys stays root:root on purpose - sshd requires that.)
  chown -R "$TARGET_USER":"$TARGET_USER" "$SSH_KEY_STORE" 2>/dev/null || true

  # Self-verify the admin key REALLY landed, matching on key material (field 2),
  # not the whole line, so a differing trailing comment can't cause a false
  # negative. This is the guard against "I followed the flow but SSH is still
  # denied" - a mismatch is shouted HERE, at setup time, not discovered later at
  # a failed ssh. (An old copy of this script, or an empty ADMIN_SSH_PUBKEY,
  # both surface as ssh_ready=false with the reason printed.)
  ssh_ready=false
  if [ -n "${ADMIN_SSH_PUBKEY:-}" ]; then
    _admin_material=$(printf '%s\n' "$ADMIN_SSH_PUBKEY" | awk '{print $2}')
    if [ -n "$_admin_material" ] && grep -qF "$_admin_material" "$SSH_KEYS_FILE" 2>/dev/null; then
      ssh_ready=true
    fi
  fi

  if [ "$ssh_ready" = true ]; then
    log "SSH ACCESS READY (admin key confirmed in $SSH_KEYS_FILE)."
    log "Connect FROM the akses-vps box (NOT from this Cloud Shell), directly over the tunnel:"
    log "  ssh -i ~/.ssh/akses-vps-cloudshell-admin -o IdentitiesOnly=yes -p 22 ${TARGET_USER}@${CLIENT_TUNNEL_IP%/*}"
  else
    log "!!! SSH ACCESS NOT READY - admin key is NOT in $SSH_KEYS_FILE. !!!"
    if [ -z "${ADMIN_SSH_PUBKEY:-}" ]; then
      log "  Reason: ADMIN_SSH_PUBKEY is empty. Set it near the top of THIS script"
      log "  (this may be an OLD copy - current version is $SCRIPT_VERSION) and re-run."
    else
      log "  Reason: the append did not stick (locked file / wrong path?). Current"
      log "  keys authorized right now:"; sed 's/^/    /' "$SSH_KEYS_FILE" 2>/dev/null
    fi
  fi
fi

# ---- overall result ----
# Exit 0 either way: an unregistered-peer "not yet connected" state on first
# run is an expected, recoverable condition for an unattended boot script,
# not a script failure - but it's reported distinctly so it's never silently
# mistaken for a real success.
_ssh_state="skipped (ENABLE_SSH_ACCESS=false)"
[ "$ENABLE_SSH_ACCESS" = true ] && { [ "${ssh_ready:-false}" = true ] && _ssh_state="READY" || _ssh_state="NOT READY (see warning above)"; }
if [ "$tunnel_ok" = true ]; then
  log "DONE (v$SCRIPT_VERSION) - tunnel: UP | SSH access: $_ssh_state. No cloudflared involved at any point."
else
  log "DONE (v$SCRIPT_VERSION) - tunnel: NOT confirmed yet (register the peer server-side, see above) | SSH access: $_ssh_state."
fi
