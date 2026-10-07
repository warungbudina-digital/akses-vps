#!/usr/bin/env bash
# =====================================================================
# publish-browser-gui-dns.sh — buat CNAME browser-gui.obc-crypto.com ->
# tunnel Cloudflare (proxied), idempoten. Dijalankan DI akses-vps.
#
# Pakai pola sama dgn rn7.obc-crypto.com (tunnel 348c9322-...). Ingress
# tunnel TIDAK diubah di sini — token Cloudflare di .env tak punya akses
# baca akun; pastikan ingress tunnel meneruskan Host browser-gui ke nginx.
#
# Pemakaian: ./publish-browser-gui-dns.sh
# =====================================================================
set -uo pipefail

ENV_FILE="${ENV_FILE:-$HOME/akses-vps/.env}"
TUNNEL_TARGET="348c9322-2bbb-456e-8ebc-1eb77117776f.cfargotunnel.com"
NAME="browser-gui.obc-crypto.com"
ZONE_NAME="obc-crypto.com"
API="https://api.cloudflare.com/client/v4"

T="$(grep '^CLOUDFLARE_API_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
[ -n "$T" ] || { echo "GAGAL: CLOUDFLARE_API_TOKEN kosong di $ENV_FILE"; exit 1; }
cf(){ curl -s -m20 -H "Authorization: Bearer $T" -H 'Content-Type: application/json' "$@"; }

Z="$(cf "$API/zones?name=$ZONE_NAME" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["result"][0]["id"])')" \
  || { echo "GAGAL: zone $ZONE_NAME tak ditemukan"; exit 1; }

EXIST="$(cf "$API/zones/$Z/dns_records?name=$NAME" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["result"]))')"
if [ "$EXIST" != "0" ]; then
  echo "SUDAH ADA: $NAME — tak diubah."
  exit 0
fi

RES="$(cf -X POST "$API/zones/$Z/dns_records" \
  --data "{\"type\":\"CNAME\",\"name\":\"$NAME\",\"content\":\"$TUNNEL_TARGET\",\"proxied\":true,\"ttl\":1}")"
echo "$RES" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("OK" if d.get("success") else d)'
