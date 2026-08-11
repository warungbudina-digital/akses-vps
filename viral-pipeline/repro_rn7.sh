#!/usr/bin/env bash
# repro_rn7.sh — entry-point orkestrasi reproduksi VN di RN7 (menyambung pipeline).
# Rantai: footage-plan -> DELIVER klip ke RN7 -> segments -> KONVERSI plan repro ->
#         perintah repro-drive.sh (DEVICE=rn7) siap jalan.
#
# Pakai:  repro_rn7.sh <base> [--run] [--splits "t1,t2"]
#   butuh: <base>.footage-plan.json (footage_audit.py) + <base>.segments.json (ir_to_vn.py)
# Env: RN7_IP (default 10.66.66.6), RN7_PORT (kalau kosong -> auto-scan nmap),
#      CONTAINER (default tool-appium-appium-1), TOOL_APPIUM (default ~/tool-appium)
#
# CATATAN: repro-drive.sh mengedit footage yg SUDAH di timeline VN. Di antara DELIVER
# dan REPRO ada langkah IMPOR klip ke proyek VN (VideoEditorMatisseActivity, vn-map
# §26/§26a) — belum diotomasi di sini; klip sudah TERURUT di picker (01_,02_,...).
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

# --- 1) DELIVER footage ---
echo ">> [1/3] deliver footage -> RN7"
python3 "$DIR/deliver_footage.py" "$FPLAN" --udid "$UDID" --container "$CONTAINER" || exit 4

# --- 2) KONVERSI segments -> plan repro ---
echo ">> [2/3] konversi segments -> repro-plan"
RPLAN="${BASE}.repro-plan.json"
python3 "$DIR/segments_to_repro.py" "$SEG" --out "$RPLAN" || exit 5

# --- 3) REPRO (edit) via repro-drive.sh DEVICE=rn7 ---
CMD=(env DEVICE=rn7 ANDROID_UDID="$UDID" "$TOOL_APPIUM/repro-drive.sh" "$RPLAN")
[ -n "$SPLITS" ] && CMD+=("$SPLITS")
echo ">> [3/3] repro (edit VN):"
echo "   ${CMD[*]}"
if [ "$RUN" -eq 1 ]; then
  echo "   (menjalankan — pastikan klip SUDAH diimpor ke proyek VN)"
  "${CMD[@]}"
else
  echo "   (dry: klip terkirim+terurut & plan siap. Impor klip ke VN lalu tambah --run,"
  echo "    atau jalankan perintah di atas manual.)"
fi
