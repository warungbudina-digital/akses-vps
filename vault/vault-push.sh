#!/usr/bin/env bash
# vault-push — simpan sesi (cookies.txt [+ storageState json]) ke DB-VPS vault.session.
# Dijalankan DI akses-vps (hub); nulis DB-VPS via ssh db-vps (Cloud Shell tak bisa langsung).
# Payload di-base64 -> aman thd quote-chain bash->ssh->psql. Banner DB-VPS = STDERR (2>/dev/null).
#
# Pakai: vault-push.sh <code> <domain> <cookies_txt_file> [storage_state_json_file] \
#          [--node N] [--name NAME] [--platform P] [--email E]
set -euo pipefail
CODE=${1:?code}; DOMAIN=${2:?domain}; COOKF=${3:?cookies_txt_file}
SSF=""; NODE="hub"; NAME=""; PLAT=""; EMAIL=""
shift 3 || true
# arg ke-4 (opsional) = storage_state file jika bukan --flag
if [ "${1:-}" ] && [ "${1#--}" = "$1" ]; then SSF="$1"; shift; fi
while [ "${1:-}" ]; do case "$1" in
  --node) NODE="$2"; shift 2;; --name) NAME="$2"; shift 2;;
  --platform) PLAT="$2"; shift 2;; --email) EMAIL="$2"; shift 2;;
  *) echo "arg tak dikenal: $1" >&2; exit 2;; esac; done

[ -f "$COOKF" ] || { echo "cookies file tak ada: $COOKF" >&2; exit 1; }
B64C=$(base64 -w0 "$COOKF")
B64S=""; [ -n "$SSF" ] && [ -f "$SSF" ] && B64S=$(base64 -w0 "$SSF")

sqlstr(){ printf "%s" "$1" | sed "s/'/''/g"; }   # escape utk literal pendek (code/domain/meta)

SQL=$(cat <<SQL
SET ROLE scraper;
INSERT INTO vault.profile(code,display_name,platform,account_email)
VALUES ('$(sqlstr "$CODE")', NULLIF('$(sqlstr "$NAME")',''), NULLIF('$(sqlstr "$PLAT")',''), NULLIF('$(sqlstr "$EMAIL")',''))
ON CONFLICT (code) DO UPDATE SET
  display_name=COALESCE(EXCLUDED.display_name,vault.profile.display_name),
  platform=COALESCE(EXCLUDED.platform,vault.profile.platform),
  account_email=COALESCE(EXCLUDED.account_email,vault.profile.account_email),
  updated_at=now();
INSERT INTO vault.session(profile_code,domain,cookies_netscape,storage_state,source_node)
VALUES ('$(sqlstr "$CODE")','$(sqlstr "$DOMAIN")',
  convert_from(decode('$B64C','base64'),'UTF8'),
  $([ -n "$B64S" ] && echo "convert_from(decode('$B64S','base64'),'UTF8')::jsonb" || echo "NULL"),
  '$(sqlstr "$NODE")')
ON CONFLICT (profile_code,domain) DO UPDATE SET
  cookies_netscape=EXCLUDED.cookies_netscape,
  storage_state=COALESCE(EXCLUDED.storage_state,vault.session.storage_state),
  captured_at=now(), source_node=EXCLUDED.source_node;
INSERT INTO vault.audit(profile_code,domain,action,node) VALUES ('$(sqlstr "$CODE")','$(sqlstr "$DOMAIN")','push','$(sqlstr "$NODE")');
SQL
)
printf '%s' "$SQL" | ssh db-vps 'sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -f -' 2>/dev/null
echo "vault-push OK: $CODE / $DOMAIN (cookies $(wc -c <"$COOKF")B${SSF:+, +storageState})"
