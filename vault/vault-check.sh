#!/usr/bin/env bash
# vault-check — pantau masa berlaku sesi di vault.session (DB-VPS).
# Dijalankan DI akses-vps lewat cron harian. Tidak me-refresh sesi (login ulang
# butuh manusia); hanya mencatat peringatan ke vault.audit dan ke log.
#
# Pakai: vault-check.sh [HARI_PERINGATAN=7]
# Exit: 0 tak ada sesi kedaluwarsa · 1 ada sesi sudah kedaluwarsa · 2 gagal baca DB
# Audit: action 'expiring' / 'expired', maks SATU baris per (profil,domain,action) per 24 jam
#        supaya jejak audit tak banjir tiap hari.
set -uo pipefail
WARN_DAYS="${1:-7}"
q(){ ssh -n db-vps "sudo -n -u postgres psql -d scraper -tAF '|' -c \"$1\"" 2>/dev/null; }

ROWS=$(q "SELECT profile_code, domain, to_char(expires_at AT TIME ZONE 'Asia/Makassar','YYYY-MM-DD HH24:MI'),
  CASE WHEN expires_at <= now() THEN 'expired' WHEN expires_at <= now() + interval '${WARN_DAYS} days' THEN 'expiring' ELSE 'ok' END
  FROM vault.session WHERE expires_at IS NOT NULL ORDER BY expires_at;") || { echo "vault-check: gagal baca DB" >&2; exit 2; }

EXPIRED=0
while IFS='|' read -r code domain until status; do
  [ -n "$code" ] || continue
  echo "$(date '+%F %T') $code $domain berlaku s/d $until WITA -> $status"
  [ "$status" = ok ] && continue
  [ "$status" = expired ] && EXPIRED=1
  # dedupe 24 jam: hanya catat bila belum ada baris action ini dalam 24 jam terakhir
  SEEN=$(q "SELECT count(*) FROM vault.audit WHERE profile_code='$code' AND domain='$domain' AND action='$status' AND at > now() - interval '24 hours';")
  if [ "${SEEN:-1}" = "0" ]; then
    ssh -n db-vps "sudo -n -u postgres psql -d scraper -c \"SET ROLE scraper; INSERT INTO vault.audit(profile_code,domain,action,node) VALUES ('$code','$domain','$status','hub');\"" >/dev/null 2>&1 || true
  fi
done <<< "$ROWS"

exit $EXPIRED
