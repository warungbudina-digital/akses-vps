#!/usr/bin/env bash
# vault-pull — ambil sesi dari DB-VPS vault.session → file lokal (+opsi import ke .60).
# Dijalankan DI akses-vps. Output base64-decode (aman). Banner = STDERR (2>/dev/null).
#
# Pakai: vault-pull.sh <code> <domain> [--out-cookies FILE] [--out-ss FILE] [--to60]
#   --to60 : langsung POST /sessions/<code>/import ke .60 (cookiesTxt)
set -euo pipefail
CODE=${1:?code}; DOMAIN=${2:?domain}; shift 2 || true
OUTC="/tmp/vault-${CODE}-cookies.txt"; OUTS=""; TO60=0
while [ "${1:-}" ]; do case "$1" in
  --out-cookies) OUTC="$2"; shift 2;; --out-ss) OUTS="$2"; shift 2;;
  --to60) TO60=1; shift;; *) echo "arg tak dikenal: $1" >&2; exit 2;; esac; done

esc(){ printf "%s" "$1" | sed "s/'/''/g"; }
q(){ ssh db-vps "sudo -n -u postgres psql -d scraper -tAc \"$1\"" 2>/dev/null; }

B64C=$(q "SELECT encode(convert_to(coalesce(cookies_netscape,''),'UTF8'),'base64') FROM vault.session WHERE profile_code='$(esc "$CODE")' AND domain='$(esc "$DOMAIN")';" | tr -d '\n')
if [ -z "$B64C" ]; then echo "vault-pull: TAK ADA sesi utk $CODE/$DOMAIN" >&2; exit 1; fi
printf '%s' "$B64C" | base64 -d > "$OUTC"
echo "vault-pull OK: $CODE/$DOMAIN → $OUTC ($(wc -c <"$OUTC")B)"

if [ -n "$OUTS" ]; then
  B64S=$(q "SELECT encode(convert_to(coalesce(storage_state::text,''),'UTF8'),'base64') FROM vault.session WHERE profile_code='$(esc "$CODE")' AND domain='$(esc "$DOMAIN")';" | tr -d '\n')
  [ -n "$B64S" ] && printf '%s' "$B64S" | base64 -d > "$OUTS" && echo "  storageState → $OUTS"
fi
ssh db-vps "sudo -n -u postgres psql -d scraper -c \"INSERT INTO vault.audit(profile_code,domain,action,node) VALUES ('$(esc "$CODE")','$(esc "$DOMAIN")','pull','hub');\"" 2>/dev/null >/dev/null || true

if [ "$TO60" = 1 ]; then
  KEY=$(grep -oE '[A-Za-z0-9]{40,}' ~/.config/browser-api/credentials.env | head -1)
  CT=$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$OUTC")
  code=$(curl -s -m20 -o /tmp/vault-import.out -w '%{http_code}' -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
    -X POST "http://10.66.66.60:8080/sessions/${CODE}/import" -d "{\"platform\":\"${DOMAIN}\",\"cookiesTxt\":${CT}}")
  echo "  import→.60 HTTP $code: $(head -c 200 /tmp/vault-import.out)"
fi
