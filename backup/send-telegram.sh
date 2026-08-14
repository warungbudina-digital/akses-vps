#!/usr/bin/env bash
# Helper kirim pesan Telegram. Dipakai skrip alert (mis. rn7-health-report.sh).
#
# Kredensial: ~/.config/telegram-alert/credentials.env (chmod 600) berisi
#   TELEGRAM_BOT_TOKEN=...   (dari @BotFather)
#   TELEGRAM_CHAT_ID=...     (dari getUpdates)
# Bisa juga via env langsung. Kalau kredensial kosong → NO-OP anggun (exit 0),
# supaya cron alert tak error saat belum dikonfigurasi.
#
# Pakai: send-telegram.sh "teks pesan"   (atau pipe: echo "..." | send-telegram.sh)
# Exit: 0 terkirim / no-op · 1 gagal kirim (API error / jaringan).
set -uo pipefail

CRED="${TELEGRAM_CRED_FILE:-$HOME/.config/telegram-alert/credentials.env}"
[ -f "$CRED" ] && { set -a; . "$CRED"; set +a; }

TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT="${TELEGRAM_CHAT_ID:-}"

MSG="${1:-}"
[ -z "$MSG" ] && MSG="$(cat)"   # dukung pipe

if [ -z "$TOKEN" ] || [ -z "$CHAT" ]; then
  echo "send-telegram: kredensial belum diisi ($CRED) — NO-OP." >&2
  exit 0
fi
if [ -z "$MSG" ]; then
  echo "send-telegram: pesan kosong." >&2
  exit 1
fi

RESP=$(curl -sS --max-time 15 \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=${MSG}" \
  -d "disable_web_page_preview=true" 2>&1)

if echo "$RESP" | grep -q '"ok":true'; then
  exit 0
else
  echo "send-telegram: GAGAL — ${RESP}" >&2
  exit 1
fi
