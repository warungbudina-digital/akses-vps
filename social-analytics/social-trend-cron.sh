#!/usr/bin/env bash
# Entrypoint cron riset tren konten (hub akses-vps): Instagram + YouTube.
#
# ⛔ TikTok DIHAPUS 2026-10-16 (keputusan user, lihat social_trend_report.py
# docstring untuk alasan lengkap): dulu skrip ini juga menjalankan
# tiktok_trend.py (butuh VM .60, sering CAPTCHA) — baris itu dibuang, bukan
# cuma dinonaktifkan, supaya tak membingungkan sesi berikutnya.
#
# social_trend.py (IG Graph API + YouTube publik) TAK butuh .60/laptop sama
# sekali — jalan murni dari hub, jadi tak ada lagi gerbang "VM mati = skip".
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/social-trend.log"
STATE="$HOME/.local/state/social-trend"
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

# 1x sukses data/hari sudah cukup (akun tak berubah drastis dalam sejam).
if [ "$(cat "$STATE/last_ok_day" 2>/dev/null)" != "$TODAY" ]; then
  if python3 "$DIR/social_trend.py" >>"$LOG" 2>&1; then
    echo "$TODAY" >"$STATE/last_ok_day"
  fi
fi

# Laporan mingguan (Senin), 1x/minggu.
if [ "$(TZ=Asia/Makassar date +%u)" = "1" ] && [ "$(cat "$STATE/last_report_week" 2>/dev/null)" != "$WEEK" ]; then
  python3 "$DIR/social_trend_report.py" --days 30 --telegram >>"$LOG" 2>&1 \
    && echo "$WEEK" >"$STATE/last_report_week"
fi
echo "[$(ts)] cron selesai" >>"$LOG"

# Batasi ukuran log.
tail -n 3000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
