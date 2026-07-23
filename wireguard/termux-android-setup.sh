#!/data/data/com.termux/files/usr/bin/sh
# termux-android-setup.sh
#
# Generates a WireGuard keypair and a ready-to-import client config for an
# Android phone running Termux, to join it as a peer into the akses-vps hub
# (103.217.144.104, tunnel subnet 10.66.66.0/24). Distilled from the actual
# scripts used to onboard the "Redmi-Note-5" peer (see docs/12-wireguard-vpn.md)
# - generalized here so the next phone doesn't repeat that ad hoc process.
#
# Requires the `wireguard-tools` Termux package (`pkg install wireguard-tools`)
# and the official "WireGuard" Android app (to import the generated .conf).
#
# HOW TO REUSE THIS FOR A NEW PHONE:
#   1. Copy this file into Termux on the phone ($HOME).
#   2. Pick a free tunnel IP - check current usage on the akses-vps server
#      first (`sudo grep -B2 AllowedIPs /etc/wireguard/wg0.conf`) and edit
#      CLIENT_TUNNEL_IP below to something NOT already listed there.
#      Reusing an IP already in use will break the OTHER peer using it.
#   3. Give it a distinct OUTPUT_LABEL below too (becomes the .conf filename
#      and shows up as a comment in the server's wg0.conf).
#   4. Run it: `sh termux-android-setup.sh`
#   5. It prints a WireGuard PUBLIC key at the end (not secret) - register it
#      as a new peer on the akses-vps server:
#        sudo ./wireguard/register-client-peer.sh <label> <public-key> [tunnel-ip]
#      (see docs/12-wireguard-vpn.md for the full registration flow).
#   6. Import the generated `/sdcard/<OUTPUT_LABEL>.conf` into the WireGuard
#      Android app (Import from file/QR) and activate the tunnel.
set -eu

# ---- edit these per phone ----
CLIENT_TUNNEL_IP="10.66.66.N/32"   # must be unique across all peers on the hub
OUTPUT_LABEL="clientN-phonemodel"  # becomes /sdcard/<OUTPUT_LABEL>.conf and the wg0.conf comment
SERVER_PUBLIC_KEY="Jquw62SGYrgeUJhDcBrbmQ8FkBDj37+ccqi15f9RzyE="   # akses-vps wg0 public key, doesn't change per phone
SERVER_ENDPOINT="103.217.144.104:51820"
# -------------------------------

KEY_DIR="$HOME"
PRIV_KEY_FILE="${KEY_DIR}/wg-private.key"
PUB_KEY_FILE="${KEY_DIR}/wg-public.key"
OUT_CONF="/sdcard/${OUTPUT_LABEL}.conf"

wg genkey > "${PRIV_KEY_FILE}"
wg pubkey < "${PRIV_KEY_FILE}" > "${PUB_KEY_FILE}"
chmod 600 "${PRIV_KEY_FILE}"

PRIV="$(cat "${PRIV_KEY_FILE}")"
{
  echo "[Interface]"
  echo "PrivateKey = ${PRIV}"
  echo "Address = ${CLIENT_TUNNEL_IP}"
  echo "DNS = 1.1.1.1"
  echo ""
  echo "[Peer]"
  echo "PublicKey = ${SERVER_PUBLIC_KEY}"
  echo "Endpoint = ${SERVER_ENDPOINT}"
  echo "AllowedIPs = 10.66.66.1/32"
  echo "PersistentKeepalive = 25"
} > "${OUT_CONF}"

echo "Config ditulis ke ${OUT_CONF}"
echo "Public key (daftarkan ini di server, BUKAN private key):"
cat "${PUB_KEY_FILE}"
