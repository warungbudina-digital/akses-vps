#!/usr/bin/env bash
# =====================================================================
# setup-browser-profiles.sh — bikin profil browser di full-tool-browser
# ogis (idempoten). Dijalankan DI akses-vps, panggil API ogis lewat WG.
#
# Nama profil = nama domain RAG (`ogis-vault/wiki/scrape-<nama>/`) = nama
# remote rclone (`setup-gdrive-remotes.sh`) — SATU identifier konsisten.
#
# Isi PROFILES di bawah dgn 5 nama nyata begitu sudah ditentukan (lihat
# docs/20-ogis-cloudshell-onboarding.md §4 "Terbuka"). Sengaja default
# array KOSONG supaya skrip ini aman dijalankan (no-op) sebelum itu.
#
# Pemakaian: PROFILES="a b c" ./setup-browser-profiles.sh   (override cepat)
#            atau edit PROFILES default di bawah.
# =====================================================================
set -uo pipefail

API="${OGIS_BROWSER_API:-http://10.66.66.8:8080}"
CRED="${BROWSER_API_CRED:-$HOME/.config/browser-api/credentials.env}"
# shellcheck disable=SC2206
PROFILES=(${PROFILES:-})   # kosong = no-op, isi nanti (5 nama profil nyata)

log(){ echo "[setup-browser-profiles $(date -u +%H:%M:%S)] $*"; }

[ -f "$CRED" ] && { set -a; . "$CRED"; set +a; }
KEY="${BROWSER_API_KEY:-}"
if [ -z "$KEY" ]; then
  log "GAGAL: BROWSER_API_KEY kosong — set env atau isi ${CRED}."
  exit 1
fi

if [ "${#PROFILES[@]}" -eq 0 ]; then
  log "PROFILES kosong (belum ditentukan) -> no-op, exit 0."
  exit 0
fi

EXISTING="$(curl -m8 -s -H "Authorization: Bearer $KEY" "$API/browser/profiles" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(p['name'] for p in d.get('profiles',[])))" 2>/dev/null)"
log "Profil yg sudah ada: ${EXISTING:-(tak terbaca / API belum jalan)}"

for name in "${PROFILES[@]}"; do
  if echo " $EXISTING " | grep -q " $name "; then
    log "  [$name] sudah ada -> skip."
    continue
  fi
  BODY=$(python3 -c "
import json, sys
name = sys.argv[1]
print(json.dumps({
  'action': 'create',
  'profile': {'name': name, 'driver': 'managed', 'profileDir': name, 'stealth': True}
}))
" "$name")
  RESP="$(curl -m15 -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "$BODY" "$API/browser/profiles")"
  if echo "$RESP" | grep -q '"ok":true'; then
    log "  [$name] DIBUAT."
  else
    log "  [$name] GAGAL: $RESP"
  fi
done
