#!/usr/bin/env bash
# footage-index-refresh.sh — snapshot isi RN7 /sdcard/Movies/Seal (gabungan unduhan
# Seal + stok Pexels/Pixabay hasil push_raw_footage.py) jadi JSON statis buat
# dashboard editor (nginx/dashboards/editor/footage-index.json) -- supaya user
# bisa PILIH footage nyata alih-alih menebak nama file, tanpa dashboard butuh
# backend live (tetap statis, cuma dibaca via fetch()).
#
# (2026-10-31, revisi permintaan user) Sumber PINDAH dari Gdrive gfootage:RAW-VIDEO/
# (dipensiunkan) ke RN7 lokal (adb via container tool-appium, pola sama
# vn_export_gdrive.sh -- adb host langsung TERBUKTI tak jalan, lihat audit 31/10).
# BEDA penting dari versi Gdrive: RN7 node 24/7 tapi SERING tidur (Doze/tak dicas,
# lihat memori project_redmi_vn_node) -- offline sesaat itu NORMAL, bukan kegagalan
# nyata. Makanya kalau adb gagal, output LAMA dipertahankan apa adanya (TAK ditimpa
# 0 file) -- beda dari versi Gdrive dulu yg menimpa dgn files:[] tiap gagal (akar
# risiko "nol vs gagal mengukur", lihat memori feedback_kegagalan_menyamar_sukses).
#
# Pakai: cron tiap 30 menit. Read-only (adb shell `stat`, nol tulis ke RN7).
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/../nginx/dashboards/editor/footage-index.json"
TMP="$(mktemp)"

RN7_IP="${RN7_IP:-10.66.66.6}"
CONTAINER="${CONTAINER:-tool-appium-appium-1}"
REMOTE_DIR="/sdcard/Movies/Seal"

docker exec "$CONTAINER" adb connect "${RN7_IP}:5555" >/dev/null 2>&1
UDID=$(docker exec "$CONTAINER" adb devices 2>/dev/null | awk -v ip="$RN7_IP" '$1~ip && $2=="device"{print $1; exit}')

if [ -z "$UDID" ]; then
  echo "RN7 tak terjangkau adb -- footage-index.json LAMA dipertahankan (bukan ditimpa 0 file). $(date -u +%FT%TZ)"
  exit 0
fi

RAW=$(docker exec "$CONTAINER" adb -s "$UDID" shell "cd $REMOTE_DIR && for f in *; do [ -f \"\$f\" ] && stat -c '%s|%Y|%n' \"\$f\"; done 2>/dev/null" 2>/dev/null | tr -d '\r')

python3 - "$RAW" "$REMOTE_DIR" > "$TMP" <<'PYEOF'
import json, sys, datetime
raw, remote_dir = sys.argv[1], sys.argv[2]
files = []
for line in raw.splitlines():
    line = line.strip()
    if not line or "|" not in line:
        continue
    try:
        size, mtime, name = line.split("|", 2)
        files.append({
            "path": f"rn7:{remote_dir}/{name}",
            "name": name,
            "size_bytes": int(size),
            "modified": datetime.datetime.fromtimestamp(int(mtime), datetime.timezone.utc).isoformat(),
        })
    except Exception:
        continue
out = {
    "remote": f"rn7:{remote_dir}",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "ok": True,
    "files": files,
}
print(json.dumps(out, indent=2, ensure_ascii=False))
PYEOF

chmod 644 "$TMP"   # mktemp default 600 -> nginx worker (user "nginx", beda dari owner
                    # file) gagal baca -> 403 senyap. Sama akar bug spt .htpasswd-editor.
mv "$TMP" "$OUT"
echo "footage-index.json ditulis ($(python3 -c "import json;print(len(json.load(open('$OUT'))['files']))") file) — $(date -u +%FT%TZ)"
