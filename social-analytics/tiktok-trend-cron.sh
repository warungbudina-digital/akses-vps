#!/usr/bin/env bash
# Entrypoint cron riset tren TikTok (hub akses-vps).
#
# Dijadwalkan di BEBERAPA slot per hari karena VM .60 cuma hidup saat laptop
# SUARAHATI menyala: slot yg menemukan .60 mati → collector SKIP (exit 0 tanpa
# data), slot berikutnya mencoba lagi. Sekali sukses di hari itu (WITA), slot
# sisa hari itu dilewati → maksimal 1 run data per hari (ramah anti-bot).
# Senin (WITA): setelah run sukses, kirim laporan mingguan ke Telegram (1x/minggu).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/tiktok-trend.log"
STATE="$HOME/.local/state/tiktok-trend"
mkdir -p "$STATE"
TODAY="$(TZ=Asia/Makassar date +%F)"
WEEK="$(TZ=Asia/Makassar date +%G-W%V)"

exec 9>"$STATE/lock"
flock -n 9 || { echo "[$(date -u +%FT%TZ)] run lain masih jalan — lewati" >>"$LOG"; exit 0; }

# Lindungi disk hub (pernah 93% penuh).
if [ "$(df --output=avail -m / | tail -1)" -lt 300 ]; then
  echo "[$(date -u +%FT%TZ)] disk hub <300MB — lewati" >>"$LOG"; exit 0
fi

if [ "$(cat "$STATE/last_ok_day" 2>/dev/null)" = "$TODAY" ]; then
  exit 0  # sudah ada data hari ini
fi

python3 "$DIR/tiktok_trend.py" >>"$LOG" 2>&1
rc=$?
# Bedakan "dilewati krn .60 mati" (exit 0 tanpa ringkasan) dari run sukses.
if [ $rc -eq 0 ] && tail -n 3 "$LOG" | grep -q "ringkasan:"; then
  echo "$TODAY" >"$STATE/last_ok_day"
  if [ "$(TZ=Asia/Makassar date +%u)" = "1" ] && [ "$(cat "$STATE/last_report_week" 2>/dev/null)" != "$WEEK" ]; then
    python3 "$DIR/tiktok_trend_report.py" --days 30 --telegram >>"$LOG" 2>&1 \
      && echo "$WEEK" >"$STATE/last_report_week"
  fi
fi
echo "[$(date -u +%FT%TZ)] cron selesai rc=$rc" >>"$LOG"

# Batasi ukuran log.
tail -n 2000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
