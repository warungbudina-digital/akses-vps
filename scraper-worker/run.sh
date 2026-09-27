#!/usr/bin/env bash
# Orkestrator scraper-worker (HUB akses-vps).
# Scrape jalan di CS .61 (requests-only, ringan); DB ditulis di hub (ingest.py).
# Alur: rsync kode -> .61 -> ssh jalankan run_worker.py -> JSONL balik ke hub -> ingest.py -> DB-VPS.
#
# Beban HUB minimal: hanya ssh + parse JSONL + suap psql (bukan scraping/browser).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CS_ADMIN_KEY="${CS_ADMIN_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
WORKER_HOST="${WORKER_HOST:-gogobuda65@10.66.66.61}"   # CS .61 (gogobuda)
WORKER_DIR="${WORKER_DIR:-scraper-worker}"             # relatif ke $HOME .61
WATCHLIST="${WATCHLIST:-$DIR/../social-analytics/tiktok_watchlist.json}"
LOG="${LOG:-$HOME/scraper-worker.log}"
STATE="$HOME/.local/state/scraper-worker"; mkdir -p "$STATE"
ts(){ date -u +%FT%TZ; }
TODAY="$(TZ=Asia/Makassar date +%F)"

# Cloud Shell EPHEMERAL -> host-key ganti tiap wake. Pola lib-cs-deploy.sh:
# StrictHostKeyChecking=no + UserKnownHostsFile=/dev/null (WG mesh = trust boundary,
# IP hanya reachable via tunnel privat; `accept-new` TETAP menolak kalau ada entri basi).
SSH_CMD="ssh -i $CS_ADMIN_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o BatchMode=yes"

exec 9>"$STATE/lock"; flock -n 9 || { echo "[$(ts)] run lain jalan — lewati" >>"$LOG"; exit 0; }
[ "$(cat "$STATE/last_ok_day" 2>/dev/null)" = "$TODAY" ] && { echo "[$(ts)] sudah sukses hari ini" >>"$LOG"; exit 0; }

# 1) .61 hidup? (Cloud Shell laptop-gated — kalau mati, SKIP spt pola tiktok_trend.py)
if ! $SSH_CMD "$WORKER_HOST" 'true' 2>>"$LOG"; then
  echo "[$(ts)] .61 tak reachable — SKIP (bukan error)" >>"$LOG"; exit 0
fi

# 2) deploy kode ke .61 (idempoten; requests sudah ada di CS)
$SSH_CMD "$WORKER_HOST" "mkdir -p $WORKER_DIR" 2>>"$LOG"
rsync -az -e "$SSH_CMD" \
  "$DIR/tiktok_scraper.py" "$DIR/run_worker.py" "$WORKER_HOST:$WORKER_DIR/" 2>>"$LOG" || {
  echo "[$(ts)] rsync gagal" >>"$LOG"; exit 1; }
scp -q -i "$CS_ADMIN_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null -o BatchMode=yes \
  "$WATCHLIST" "$WORKER_HOST:$WORKER_DIR/watchlist.json" 2>>"$LOG"

# 3) jalankan di .61, stream JSONL balik -> ingest di hub
#    (jeda antar-request DARI watchlist: delay_min_s/max_s 25-45 — WAJIB, IP CS kena 503 kalau terlalu cepat)
echo "[$(ts)] mulai scrape di $WORKER_HOST" >>"$LOG"
if $SSH_CMD "$WORKER_HOST" \
     "cd $WORKER_DIR && python3 run_worker.py --watchlist watchlist.json" 2>>"$LOG" \
   | python3 "$DIR/ingest.py" 2>>"$LOG"; then
  echo "$TODAY" >"$STATE/last_ok_day"
  echo "[$(ts)] SELESAI + ingested" >>"$LOG"
else
  echo "[$(ts)] scrape/ingest gagal (lihat log)" >>"$LOG"; exit 1
fi
