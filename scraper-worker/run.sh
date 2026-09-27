#!/usr/bin/env bash
# Orkestrator scraper-worker (HUB akses-vps).
# Scrape jalan di CS .61 (requests-only, ringan); DB ditulis di hub (ingest.py).
# Alur: rsync kode -> .61 -> ssh jalankan run_worker.py -> JSONL balik ke hub -> ingest.py -> DB-VPS.
#
# Beban HUB minimal: hanya ssh + parse JSONL + suap psql (bukan scraping/browser).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WORKER_SSH="${WORKER_SSH:-cs61}"          # TODO: set alias ssh .61 (ControlMaster spt c50/c60)
WORKER_DIR="${WORKER_DIR:-~/scraper-worker}"
WATCHLIST="${WATCHLIST:-$DIR/../social-analytics/tiktok_watchlist.json}"
LOG="${LOG:-$HOME/scraper-worker.log}"
STATE="$HOME/.local/state/scraper-worker"; mkdir -p "$STATE"
ts(){ date -u +%FT%TZ; }
TODAY="$(TZ=Asia/Makassar date +%F)"

exec 9>"$STATE/lock"; flock -n 9 || { echo "[$(ts)] run lain jalan — lewati" >>"$LOG"; exit 0; }

# maks 1 run sukses/hari (idempoten lintas-rebuild VM: penanda di hub, bukan di .61)
[ "$(cat "$STATE/last_ok_day" 2>/dev/null)" = "$TODAY" ] && { echo "[$(ts)] sudah sukses hari ini" >>"$LOG"; exit 0; }

# 1) .61 hidup? (Cloud Shell laptop-gated — kalau mati, SKIP spt pola tiktok_trend.py)
#    PRASYARAT tercatat: (a) MTU route 10.66.66.61/32 mtu 1380 di hub (bug laten spt .60),
#    (b) host-key .61 berubah -> ssh pakai accept-new / bersihkan known_hosts dulu.
if ! ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        "$WORKER_SSH" 'true' 2>>"$LOG"; then
  echo "[$(ts)] .61 tak reachable — SKIP (bukan error)" >>"$LOG"; exit 0
fi

# 2) deploy kode ke .61 (idempoten; cs-auto-deploy juga bisa yang urus)
rsync -az --delete -e 'ssh -o BatchMode=yes' \
  "$DIR/tiktok_scraper.py" "$DIR/run_worker.py" "$WORKER_SSH:$WORKER_DIR/" 2>>"$LOG" || {
  echo "[$(ts)] rsync gagal" >>"$LOG"; exit 1; }
scp -q "$WATCHLIST" "$WORKER_SSH:$WORKER_DIR/watchlist.json" 2>>"$LOG"

# 3) jalankan di .61, stream JSONL balik -> ingest di hub
echo "[$(ts)] mulai scrape di $WORKER_SSH" >>"$LOG"
if ssh -o BatchMode=yes "$WORKER_SSH" \
     "cd $WORKER_DIR && python3 run_worker.py --watchlist watchlist.json" 2>>"$LOG" \
   | python3 "$DIR/ingest.py" 2>>"$LOG"; then
  echo "$TODAY" >"$STATE/last_ok_day"
  echo "[$(ts)] SELESAI + ingested" >>"$LOG"
else
  echo "[$(ts)] scrape/ingest gagal (lihat log)" >>"$LOG"; exit 1
fi
