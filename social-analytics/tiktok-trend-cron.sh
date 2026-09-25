#!/usr/bin/env bash
# Entrypoint cron riset tren konten (hub akses-vps): TikTok + Instagram + YouTube.
#
# Dijadwalkan di beberapa slot per hari (lihat crontab). Tiap sumber punya penanda
# "sudah sukses hari ini" sendiri → maks 1 run data per sumber per hari:
#   - social_trend.py (IG Graph API + YouTube publik): tak butuh .60, biasanya
#     sukses di slot pertama.
#   - tiktok_trend.py: butuh VM .60 (hidup hanya saat laptop SUARAHATI menyala);
#     slot yg menemukan .60 mati → SKIP, slot berikutnya mencoba lagi.
# Senin (WITA): laporan mingguan ke Telegram, 1x/minggu — dikirim setelah TikTok
# sukses, ATAU di slot terakhir hari itu walau TikTok gagal (IG/YT tetap terlapor).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/tiktok-trend.log"
STATE="$HOME/.local/state/tiktok-trend"
LAST_SLOT_UTC_HOUR=9   # slot terakhir di crontab (10 3,6,9 * * *)
mkdir -p "$STATE"
TODAY="$(TZ=Asia/Makassar date +%F)"
WEEK="$(TZ=Asia/Makassar date +%G-W%V)"
ts() { date -u +%FT%TZ; }

exec 9>"$STATE/lock"
flock -n 9 || { echo "[$(ts)] run lain masih jalan — lewati" >>"$LOG"; exit 0; }

# Lindungi disk hub (pernah 93% penuh).
if [ "$(df --output=avail -m / | tail -1)" -lt 300 ]; then
  echo "[$(ts)] disk hub <300MB — lewati" >>"$LOG"; exit 0
fi

# 1) Instagram + YouTube
if [ "$(cat "$STATE/social_last_ok_day" 2>/dev/null)" != "$TODAY" ]; then
  if python3 "$DIR/social_trend.py" >>"$LOG" 2>&1; then
    echo "$TODAY" >"$STATE/social_last_ok_day"
  fi
fi

# 2) TikTok. Bedakan "dilewati krn .60 mati" (exit 0 tanpa ringkasan) dari sukses.
tiktok_ok=0
if [ "$(cat "$STATE/last_ok_day" 2>/dev/null)" = "$TODAY" ]; then
  tiktok_ok=1
else
  python3 "$DIR/tiktok_trend.py" >>"$LOG" 2>&1
  rc=$?
  if [ $rc -eq 0 ] && tail -n 3 "$LOG" | grep -q "ringkasan:"; then
    echo "$TODAY" >"$STATE/last_ok_day"; tiktok_ok=1
  fi
fi

# 3) Laporan mingguan (Senin).
if [ "$(TZ=Asia/Makassar date +%u)" = "1" ] && [ "$(cat "$STATE/last_report_week" 2>/dev/null)" != "$WEEK" ]; then
  if [ $tiktok_ok -eq 1 ] || [ "$(date -u +%-H)" -ge $LAST_SLOT_UTC_HOUR ]; then
    python3 "$DIR/tiktok_trend_report.py" --days 30 --telegram >>"$LOG" 2>&1 \
      && echo "$WEEK" >"$STATE/last_report_week"
  fi
fi
echo "[$(ts)] cron selesai (tiktok_ok=$tiktok_ok)" >>"$LOG"

# Batasi ukuran log.
tail -n 3000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
