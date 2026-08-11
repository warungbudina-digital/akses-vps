#!/usr/bin/env bash
# repro_rn7.sh — entry-point orkestrasi reproduksi VN di RN7 (rantai penuh 4 tahap).
# Rantai: footage-plan -> DELIVER klip -> IMPOR ke proyek VN (terurut) ->
#         KONVERSI segments->plan -> REPRO edit (repro-drive.sh DEVICE=rn7).
#
# Pakai:  repro_rn7.sh <base> [--run] [--splits "t1,t2"]
#   butuh: <base>.footage-plan.json (footage_audit.py) + <base>.segments.json (ir_to_vn.py)
#   --run  = sekalian jalankan tahap REPRO edit (default: berhenti stlh impor+plan siap)
# Env: RN7_IP (default 10.66.66.6), RN7_PORT (kalau kosong -> auto-scan nmap),
#      CONTAINER (default tool-appium-appium-1), TOOL_APPIUM (default ~/tool-appium)
#
# Impor multi-klip diotomasi via tests/import-clips.js (filter album VN-src, tap
# check_view TERBALIK krn grid date-desc -> seleksi = urutan fase). Delivery --clean
# jaga album = tepat N klip ini.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="${1:?usage: repro_rn7.sh <base> [--run] [--splits t1,t2]}"; shift || true
RUN=0; SPLITS=""
while [ $# -gt 0 ]; do case "$1" in
  --run) RUN=1;; --splits) SPLITS="${2:-}"; shift;; *) echo "arg tak dikenal: $1" >&2;;
esac; shift; done

RN7_IP="${RN7_IP:-10.66.66.6}"
CONTAINER="${CONTAINER:-tool-appium-appium-1}"
TOOL_APPIUM="${TOOL_APPIUM:-$HOME/tool-appium}"
FPLAN="${BASE}.footage-plan.json"; SEG="${BASE}.segments.json"
[ -f "$FPLAN" ] || { echo "!! tak ada $FPLAN" >&2; exit 2; }
[ -f "$SEG" ]   || { echo "!! tak ada $SEG" >&2; exit 2; }

# --- resolve UDID RN7 (reuse koneksi / auto-scan port wireless-debug) ---
UDID=""
if [ -n "${RN7_PORT:-}" ]; then UDID="${RN7_IP}:${RN7_PORT}"; fi
if [ -z "$UDID" ]; then
  UDID=$(docker exec "$CONTAINER" adb devices 2>/dev/null | awk -v ip="$RN7_IP" '$1 ~ ip {print $1; exit}')
fi
if [ -z "$UDID" ]; then
  echo ">> scan port adb RN7 ($RN7_IP) ..." >&2
  P=$(timeout 60 sudo nmap -Pn -p30000-45000 --open "$RN7_IP" 2>/dev/null | grep -oE '^[0-9]+' | head -1)
  [ -n "$P" ] || { echo "!! port adb RN7 tak ketemu (HP online? Wireless debugging aktif?)" >&2; exit 3; }
  UDID="${RN7_IP}:${P}"
  docker exec "$CONTAINER" adb connect "$UDID" >&2
fi
echo ">> RN7 UDID=$UDID"

# --- 1) DELIVER footage (folder dibersihkan -> album VN-src = tepat N klip ini) ---
echo ">> [1/4] deliver footage -> RN7"
python3 "$DIR/deliver_footage.py" "$FPLAN" --udid "$UDID" --container "$CONTAINER" --clean || exit 4

# --- 2) IMPOR multi-klip ke proyek VN baru (TERURUT fase) ---
echo ">> [2/4] impor klip ke VN (import-clips.js)"
docker exec "$CONTAINER" adb -s "$UDID" shell am force-stop com.frontrow.vlog >/dev/null 2>&1
docker exec "$CONTAINER" adb -s "$UDID" shell "monkey -p com.frontrow.vlog -c android.intent.category.LAUNCHER 1" >/dev/null 2>&1
sleep 11   # tunggu splash -> MainActivity
IMP_OUT=$( cd "$TOOL_APPIUM" && timeout 220 docker compose exec -T -e ANDROID_UDID="$UDID" \
  -e APP_PACKAGE=com.frontrow.vlog -e FORCE_APP_LAUNCH=false -e DEVICE=rn7 -e ALBUM=VN-src \
  appium npx wdio run ./wdio.conf.js --spec tests/import-clips.js 2>&1 )
echo "$IMP_OUT" | grep -E "\[import\]" || true
echo "$IMP_OUT" | grep -qE "[0-9]+ passing" || { echo "!! impor GAGAL"; echo "$IMP_OUT" | tail -5; exit 6; }

# --- 3) KONVERSI segments -> plan repro ---
echo ">> [3/4] konversi segments -> repro-plan"
RPLAN="${BASE}.repro-plan.json"
python3 "$DIR/segments_to_repro.py" "$SEG" --out "$RPLAN" || exit 5

# --- 4) REPRO (edit) via repro-drive.sh DEVICE=rn7 (footage sudah di timeline) ---
CMD=(env DEVICE=rn7 ANDROID_UDID="$UDID" "$TOOL_APPIUM/repro-drive.sh" "$RPLAN")
[ -n "$SPLITS" ] && CMD+=("$SPLITS")
echo ">> [4/4] repro (edit VN):"
echo "   ${CMD[*]}"
if [ "$RUN" -eq 1 ]; then
  echo "   (menjalankan repro — footage sudah diimpor ke proyek VN)"
  "${CMD[@]}"
else
  echo "   (dry: klip terkirim+terurut+DIIMPOR ke editor & plan siap."
  echo "    Tambah --run untuk sekalian jalankan edit repro.)"
fi
