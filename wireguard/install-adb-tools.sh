#!/usr/bin/env bash
# install-adb-tools.sh
#
# Installs the Android Debug Bridge (adb) client on the akses-vps host
# itself. This was added to support auditing/controlling Android devices
# reached through the wg0 WireGuard hub (see register-client-peer.sh next
# to this file, and docs/12-wireguard-vpn.md) directly from the VPS,
# instead of always hopping through a laptop that happens to have
# platform-tools installed and LAN presence to the target device.
#
# Resource footprint check done before adding this (2026-07-20, 2 vCPU /
# 1.9GB RAM VPS): package is ~700KB on disk, adb server is idle (not
# started by this script or at boot) until a client command actually runs
# one, and even then it's a few MB RSS - negligible on this host.
#
# Deliberately NOT bundling the compiled adb binary itself in this repo -
# that would fight the existing .gitignore convention here (which already
# excludes other build/generated binaries). This script is the "bundle":
# rerunning it reproduces the same install anywhere, so it can be
# committed/pushed instead of a platform-specific binary blob.
#
# Usage:
#   sudo ./install-adb-tools.sh
#
# Security note: `adb` on its own does not open any port to the network -
# the client/server protocol binds to 127.0.0.1:5037 by default. Installing
# it here does not, by itself, expose adb to anything beyond this host.
set -euo pipefail

log() { echo "[install-adb-tools] $*"; }
die() { echo "[install-adb-tools] ERROR: $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "must run as root (sudo ./install-adb-tools.sh)"
fi

if command -v adb >/dev/null 2>&1; then
  log "adb already installed: $(adb version | head -1)"
  exit 0
fi

log "installing adb via apt..."
apt-get update -qq
apt-get install -y android-tools-adb

command -v adb >/dev/null 2>&1 || die "install finished but adb not found on PATH"
log "done: $(adb version | head -1)"
log "adb server is idle until first use (not started by this script, not enabled at boot)"
