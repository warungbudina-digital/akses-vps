#!/usr/bin/env bash
# Laporan kesehatan stack `full-tool-browser` (.60) + deteksi GAGAL-SENYAP.
#
# MASALAH YANG DITANGANI: repo browser melaporkan job scraping sebagai
# status='done', error=NULL, TAPI result_count=0 ketika platform menyajikan
# CAPTCHA (TikTok) / login-wall (IG) ke IP datacenter. Tanpa pemeriksaan
# eksplisit, "strategi berbasis data" bisa berjalan berminggu-minggu di atas
# data KOSONG tanpa ada yang sadar. Skrip ini membuat kondisi itu BERISIK.
#
# Juga menandai: sesi cookie yang (hampir) kedaluwarsa, jadwal yang mandek,
# dan backup yang basi - tiga hal yang gagal DIAM-DIAM di sistem terjadwal.
#
# .60 hidup TERJADWAL -> .60 mati BUKAN error (exit 0, dilaporkan apa adanya).
#
# Exit: 0 sehat / .60 memang mati · 1 ADA MASALAH yang perlu tindakan.
set -uo pipefail

C60_HOST="${C60_HOST:-balibruntattour@10.66.66.60}"
C60_KEY="${C60_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
API="${BROWSER_API:-http://10.66.66.60:8080}"
DBVPS_HOST="${DBVPS_HOST:-db-vps}"
DEST_DIR="${DEST_DIR:-browser-db-backups}"
SILENT_WINDOW_H="${SILENT_WINDOW_H:-72}"   # jendela periksa job (jam)
BACKUP_STALE_H="${BACKUP_STALE_H:-192}"    # backup dianggap basi (jam, ~8 hari)

PROBLEMS=0
say()  { echo "$*"; }
warn() { echo "  !! $*"; PROBLEMS=$((PROBLEMS + 1)); }
ok()   { echo "  ok  $*"; }

ssh60() {
  ssh -o ControlPath=none -i "$C60_KEY" -o IdentitiesOnly=yes \
      -o ConnectTimeout=10 -o BatchMode=yes -p 22 "$C60_HOST" "$@"
}
sshdb() { ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null; }

# psql via STDIN (-f -): hindari neraka kutip bash->ssh->docker->psql.
q60() { printf '%s\n' "$1" | ssh60 'docker exec -i scraper-db psql -U scraper -d scraper -tAq -f -' 2>/dev/null | tr -d '\r'; }

say "=== Laporan kesehatan browser stack (.60) — $(date -u '+%Y-%m-%d %H:%M UTC') ==="

# ── A. Backup durabilitas (dicek DULUAN: berlaku walau .60 mati) ────────────
say "[A] Durabilitas backup (DB-VPS)"
LATEST=$(sshdb "ls -1t ~/${DEST_DIR}/scraper-*.sql.gz 2>/dev/null | head -1")
if [ -z "$LATEST" ]; then
  warn "BELUM ADA backup sama sekali di ${DBVPS_HOST}:~/${DEST_DIR}/ — data .60 tak terlindungi."
else
  AGE_S=$(sshdb "echo \$(( \$(date +%s) - \$(stat -c %Y '$LATEST') ))")
  AGE_H=$(( ${AGE_S:-0} / 3600 ))
  COUNT=$(sshdb "ls -1 ~/${DEST_DIR}/scraper-*.sql.gz 2>/dev/null | wc -l")
  if [ "$AGE_H" -gt "$BACKUP_STALE_H" ]; then
    warn "Backup terakhir ${AGE_H} jam lalu (> ${BACKUP_STALE_H}j) — jalankan browser-db-backup.sh saat .60 hidup."
  else
    ok "Backup terakhir ${AGE_H} jam lalu, total ${COUNT} arsip."
  fi
fi

# ── B. .60 hidup? (mati = normal untuk host terjadwal) ──────────────────────
say "[B] Ketersediaan .60"
if ! ssh60 true 2>/dev/null; then
  say "  -- .60 MATI (Cloud Shell tidak aktif). Normal untuk host terjadwal."
  say "     Pemeriksaan job/sesi/jadwal dilewati — akan dicek saat .60 hidup."
  say
  say "RINGKASAN: ${PROBLEMS} masalah."
  exit $(( PROBLEMS > 0 ? 1 : 0 ))
fi
ok ".60 hidup dan bisa di-SSH."

if ! ssh60 'docker ps --format "{{.Names}}" | grep -qx scraper-db' 2>/dev/null; then
  warn ".60 hidup TAPI container scraper-db belum jalan — perlu redeploy (docker compose up -d)."
  say
  say "RINGKASAN: ${PROBLEMS} masalah."
  exit 1
fi

# ── C. API + auth benar-benar aktif ────────────────────────────────────────
say "[C] API & auth"
HS=$(curl -m8 -s -o /dev/null -w '%{http_code}' "${API}/health" 2>/dev/null)
[ "$HS" = "200" ] && ok "/health = 200." || warn "/health = ${HS:-tak merespons}."
AS=$(curl -m8 -s -o /dev/null -w '%{http_code}' "${API}/sessions" 2>/dev/null)
if [ "$AS" = "401" ]; then
  ok "Auth AKTIF (endpoint sensitif menolak request tanpa kunci)."
else
  warn "Auth TIDAK aktif — /sessions balas ${AS}, bukan 401. API_KEY di .env .60 kosong/tak terpakai!"
fi

# ── D. GAGAL-SENYAP: job 'done' tapi hasilnya kosong ───────────────────────
say "[D] Gagal-senyap job scraping (${SILENT_WINDOW_H} jam terakhir)"
STATS=$(q60 "SELECT COUNT(*) FILTER (WHERE status='done' AND COALESCE(result_count,0)=0) || '|' ||
                    COUNT(*) FILTER (WHERE status='done' AND COALESCE(result_count,0)>0) || '|' ||
                    COUNT(*) FILTER (WHERE status='failed') || '|' ||
                    COUNT(*) FILTER (WHERE status IN ('pending','running') AND created_at < NOW() - INTERVAL '1 hour')
             FROM scraper_jobs WHERE created_at > NOW() - INTERVAL '${SILENT_WINDOW_H} hours';")
if [ -z "$STATS" ]; then
  warn "Tidak bisa query scraper_jobs di .60."
else
  IFS='|' read -r EMPTY GOOD FAILED STUCK <<< "$STATS"
  if [ "${EMPTY:-0}" -gt 0 ]; then
    warn "${EMPTY} job 'done' TAPI 0 hasil = GAGAL-SENYAP (CAPTCHA/login-wall). Jangan percaya status 'done' saja."
  fi
  [ "${FAILED:-0}" -gt 0 ] && warn "${FAILED} job FAILED."
  [ "${STUCK:-0}"  -gt 0 ] && warn "${STUCK} job tersangkut pending/running >1 jam (worker mati di tengah?)."
  [ "${EMPTY:-0}" -eq 0 ] && [ "${FAILED:-0}" -eq 0 ] && [ "${STUCK:-0}" -eq 0 ] \
    && ok "${GOOD:-0} job berhasil berisi, tidak ada gagal-senyap."
fi

# ── E. Sesi cookie: kedaluwarsa = scraping balik gagal-senyap ──────────────
say "[E] Sesi login tersimpan"
SESS=$(q60 "SELECT COUNT(*) || '|' ||
                   COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at < NOW()) || '|' ||
                   COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days')
            FROM scraper_sessions;")
IFS='|' read -r STOT SEXP SSOON <<< "${SESS:-0|0|0}"
if [ "${STOT:-0}" -eq 0 ]; then
  say "  -- Belum ada sesi tersimpan (scraping jalan sebagai visitor anonim = paling rawan captcha)."
else
  [ "${SEXP:-0}" -gt 0 ]  && warn "${SEXP} sesi SUDAH kedaluwarsa — impor ulang cookies.txt."
  [ "${SSOON:-0}" -gt 0 ] && warn "${SSOON} sesi kedaluwarsa <7 hari — siapkan cookies baru."
  [ "${SEXP:-0}" -eq 0 ] && [ "${SSOON:-0}" -eq 0 ] && ok "${STOT} sesi tersimpan, semua masih berlaku."
fi

# ── F. Jadwal aktif tapi tak pernah jalan ──────────────────────────────────
say "[F] Jadwal (cron internal .60)"
SCH=$(q60 "SELECT COUNT(*) FILTER (WHERE enabled) || '|' ||
                  COUNT(*) FILTER (WHERE enabled AND (last_run_at IS NULL OR last_run_at < NOW() - INTERVAL '48 hours'))
           FROM scraper_schedules;")
IFS='|' read -r SCEN SCSTALE <<< "${SCH:-0|0}"
if [ "${SCEN:-0}" -eq 0 ]; then
  say "  -- Belum ada jadwal aktif."
else
  [ "${SCSTALE:-0}" -gt 0 ] && warn "${SCSTALE} jadwal aktif TAPI tak jalan >48 jam (wajar kalau .60 jarang hidup — pertimbangkan pemicu dari akses-vps)."
  [ "${SCSTALE:-0}" -eq 0 ] && ok "${SCEN} jadwal aktif, semua jalan baru-baru ini."
fi

say
if [ "$PROBLEMS" -eq 0 ]; then
  say "RINGKASAN: SEHAT — tidak ada masalah terdeteksi."
else
  say "RINGKASAN: ${PROBLEMS} masalah perlu tindakan (lihat baris '!!' di atas)."
fi
exit $(( PROBLEMS > 0 ? 1 : 0 ))
