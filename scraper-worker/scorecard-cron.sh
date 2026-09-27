#!/usr/bin/env bash
# Cron wrapper viral_scorecard.py (HUB akses-vps). Dijadwalkan SETELAH slot scrape .61.
# Baca trend.* -> skor tertimbang -> trend.viral_score. Untuk top-10:
#   - enqueue video ke analyzer .50 (asinkron: dim Hook/Pacing/Rewatch/Emosi diisi
#     run BERIKUTNYA setelah orchestrator drain, pola analyzer-pipeline-trigger).
#   - Gemini via ai_wiki_query -> RN7 (kalau RN7 mati, dim Relate/Universal = pending;
#     skor tetap keluar dari dim lain).
# Ringan di hub (aritmetika + baca DB + subprocess enqueue/gemini). Lock cegah overlap
# (run bisa lama kalau Gemini lambat: 10 video x ~timeout).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${LOG:-$HOME/scorecard.log}"
STATE="$HOME/.local/state/scorecard"; mkdir -p "$STATE"
ts(){ date -u +%FT%TZ; }

exec 9>"$STATE/lock"; flock -n 9 || { echo "[$(ts)] run lain masih jalan — lewati" >>"$LOG"; exit 0; }

# lindungi disk hub (pernah 93% penuh)
if [ "$(df --output=avail -m / | tail -1)" -lt 200 ]; then
  echo "[$(ts)] disk hub <200MB — lewati" >>"$LOG"; exit 0
fi

echo "[$(ts)] scorecard mulai" >>"$LOG"
python3 "$DIR/viral_scorecard.py" "$@" >>"$LOG" 2>&1
rc=$?
echo "[$(ts)] scorecard selesai (rc=$rc)" >>"$LOG"
exit "$rc"
