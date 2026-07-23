#!/usr/bin/env bash
# adb-wireless-connect.sh
#
# Pairs + connects to an Android phone's "Wireless debugging" (Android 11+)
# from the akses-vps host, over the wg0 WireGuard tunnel, then runs a short
# read-only system audit. Written so the next time you just edit the three
# values at the top (IP, ports, code) and re-run - no need to remember the
# adb incantations or the LAN-vs-tunnel-IP gotcha each time.
#
# Companion to install-adb-tools.sh (installs the adb client this needs) and
# to the WireGuard onboarding scripts next to it. See docs/12-wireguard-vpn.md.
#
# ------------------------------------------------------------------------
# TWO THINGS THAT TRIP EVERYONE UP - READ ONCE:
#
# 1) The IP shown on the phone's Wireless-debugging screen (e.g. 192.168.1.7)
#    is the phone's *local Wi-Fi* IP. It is NOT reachable from this VPS.
#    Over the tunnel the phone is its wg0 address (e.g. 10.66.66.2). Always
#    put the *tunnel* IP in DEVICE_IP below, but keep the *same ports*.
#
# 2) Android wireless debugging uses TWO different ports:
#      - PAIR_PORT : shown in the "Pair device with pairing code" pop-up,
#                    together with the 6-digit code. Both are single-use and
#                    EXPIRE the moment you close that pop-up. Only needed the
#                    first time a given host pairs with the phone.
#      - CONNECT_PORT : shown on the MAIN "Wireless debugging" screen under
#                    "IP address & Port". This is what you actually connect
#                    to. On many ROMs it changes every time you toggle
#                    Wireless debugging off/on, so re-read it if connect fails.
#
#    Pairing is remembered (an adb key is stored on the phone), so on later
#    runs you can leave PAIR_CODE empty and only set CONNECT_PORT.
# ------------------------------------------------------------------------
#
# Usage:
#   ./adb-wireless-connect.sh                 # uses the values baked in below
#   DEVICE_IP=10.66.66.9 CONNECT_PORT=40001 ./adb-wireless-connect.sh   # override per run
#
# Security note: this connects OUT to the phone over the already-encrypted
# wg0 tunnel. It does not open any inbound port on this VPS - adb's own
# server still only listens on 127.0.0.1:5037.
set -euo pipefail

# ================= EDIT THESE PER PHONE / PER SESSION =================
DEVICE_IP="${DEVICE_IP:-10.66.66.N}"     # phone's wg0 TUNNEL ip (NOT its 192.168.x LAN ip)
PAIR_PORT="${PAIR_PORT:-XXXXX}"          # port from the "Pair device with pairing code" pop-up
PAIR_CODE="${PAIR_CODE:-XXXXXX}"         # 6-digit code from that same pop-up (leave "" if already paired)
CONNECT_PORT="${CONNECT_PORT:-XXXXX}"    # port from the MAIN Wireless-debugging screen (fill this in!)
# =====================================================================

log()  { echo "[adb-wireless] $*"; }
warn() { echo "[adb-wireless] WARN: $*" >&2; }
die()  { echo "[adb-wireless] ERROR: $*" >&2; exit 1; }

command -v adb >/dev/null 2>&1 || die "adb not found - run ./install-adb-tools.sh first"

# --- reachability check over the tunnel (fail fast with a clear message) ---
log "checking tunnel reachability to ${DEVICE_IP} ..."
if ! ping -c1 -W2 "${DEVICE_IP}" >/dev/null 2>&1; then
  die "cannot reach ${DEVICE_IP} over wg0. Is the phone's WireGuard tunnel up? (check: sudo wg show)"
fi
log "phone is reachable on the tunnel."

# --- step 1: pair (only if a code was provided) ---
if [ -n "${PAIR_CODE}" ]; then
  log "pairing with ${DEVICE_IP}:${PAIR_PORT} ..."
  # NOTE: `adb pair` exits 0 even when pairing FAILS, so we must judge success
  # from its stdout ("Successfully paired ...") rather than the exit code.
  pair_out="$(adb pair "${DEVICE_IP}:${PAIR_PORT}" "${PAIR_CODE}" 2>&1 || true)"
  echo "${pair_out}"
  if echo "${pair_out}" | grep -qi "Successfully paired"; then
    log "paired OK."
  else
    warn "pairing failed. Almost always this means the code/port EXPIRED."
    warn "On the phone: Wireless debugging -> 'Pair device with pairing code',"
    warn "then copy the FRESH port + code into PAIR_PORT / PAIR_CODE and re-run."
    die  "aborting - cannot continue without a successful pair."
  fi
else
  log "PAIR_CODE empty -> assuming this host already paired before, skipping pair step."
fi

# --- step 2: work out which port to connect on ---
if [ -z "${CONNECT_PORT}" ]; then
  warn "CONNECT_PORT is empty. Trying mDNS discovery (usually does NOT cross the wg tunnel)..."
  # Best-effort: mDNS is link-local multicast and typically will not traverse
  # WireGuard, so this often finds nothing - that's expected, not a bug.
  discovered="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect/ {print $NF}' | head -1 || true)"
  if [ -n "${discovered}" ]; then
    log "mDNS found a connect endpoint: ${discovered}"
    CONNECT_TARGET="${discovered}"
  else
    die "no CONNECT_PORT set and mDNS found nothing. Read the port under 'IP address & Port'
       on the phone's main Wireless-debugging screen and set CONNECT_PORT (it differs from PAIR_PORT)."
  fi
else
  CONNECT_TARGET="${DEVICE_IP}:${CONNECT_PORT}"
fi

# --- step 3: connect ---
log "connecting to ${CONNECT_TARGET} ..."
if ! adb connect "${CONNECT_TARGET}" | tee /dev/stderr | grep -qiE "connected|already"; then
  die "connect failed. On many ROMs the connect port changes every time you toggle
     Wireless debugging - re-read 'IP address & Port' on the phone and update CONNECT_PORT."
fi

# adb can report 'connected' then drop; confirm the device is really usable.
SERIAL="${CONNECT_TARGET}"
if ! adb -s "${SERIAL}" get-state 2>/dev/null | grep -q device; then
  die "device connected but not in 'device' state (may need an on-screen 'Allow' prompt on the phone)."
fi
log "device online: ${SERIAL}"

# --- step 4: short read-only system audit ---
echo
log "================= SYSTEM AUDIT ($(date '+%Y-%m-%d %H:%M:%S')) ================="
p() { adb -s "${SERIAL}" shell getprop "$1" 2>/dev/null | tr -d '\r'; }

printf '  %-22s %s\n' "Manufacturer:"    "$(p ro.product.manufacturer)"
printf '  %-22s %s\n' "Model:"           "$(p ro.product.model)"
printf '  %-22s %s\n' "Device:"          "$(p ro.product.device)"
printf '  %-22s %s\n' "Android version:" "$(p ro.build.version.release)"
printf '  %-22s %s\n' "SDK / API level:" "$(p ro.build.version.sdk)"
printf '  %-22s %s\n' "Security patch:"  "$(p ro.build.version.security_patch)"
printf '  %-22s %s\n' "Build ID:"        "$(p ro.build.display.id)"
printf '  %-22s %s\n' "Kernel:"          "$(adb -s "${SERIAL}" shell uname -a 2>/dev/null | tr -d '\r')"

# uptime + rough package counts - all read-only, nothing is changed on the phone.
printf '  %-22s %s\n' "Uptime:"          "$(adb -s "${SERIAL}" shell uptime 2>/dev/null | tr -d '\r')"
PKG_ALL="$(adb -s "${SERIAL}" shell pm list packages 2>/dev/null | wc -l | tr -d '[:space:]')"
PKG_3RD="$(adb -s "${SERIAL}" shell pm list packages -3 2>/dev/null | wc -l | tr -d '[:space:]')"
printf '  %-22s %s (of which %s user-installed)\n' "Installed packages:" "${PKG_ALL}" "${PKG_3RD}"

echo
log "audit done. The adb connection stays up; disconnect with:"
log "  adb disconnect ${SERIAL}"
