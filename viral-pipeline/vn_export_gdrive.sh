#!/usr/bin/env bash
# vn_export_gdrive.sh — export proyek VN aktif -> (opsional tambah musik) -> Gdrive.
#
# Rantai: render VN (tests/export-video.js) -> deteksi MP4 baru di /sdcard/DCIM/VN ->
# pull ke akses-vps -> [--music: mux audio klip + musik via ffmpeg di container .50] ->
# rclone upload ke Gdrive. Menutup "hasil bisa ditonton dgn suara".
#
# ⚠️ Library musik VN MOD MATI (cloud gated) -> musik DITAMBAH via ffmpeg (bukan di VN).
# Klip Pexels sendiri sudah punya track audio; --music menambah bed musik di atasnya.
#
# Pakai: vn_export_gdrive.sh [--music FILE.mp3] [--name out.mp4] [--remote gfootage:VN-exports/]
# Env: RN7_IP(10.66.66.6) RN7_PORT(auto) CONTAINER(tool-appium-appium-1) TOOL_APPIUM(~/tool-appium)
#      C50_SOCK(/tmp/c50.sock) C50_HOST(warungbudina@10.66.66.50)
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
MUSIC="" ; NAME="vn-export-$(date -u +%Y%m%d-%H%M%S).mp4" ; REMOTE="gfootage:VN-exports/"
MVOL=0.7 ; CVOL=0.8
while [ $# -gt 0 ]; do case "$1" in
  --music) MUSIC="${2:-}"; shift;; --name) NAME="${2:-}"; shift;;
  --remote) REMOTE="${2:-}"; shift;; --music-vol) MVOL="${2:-}"; shift;;
  --clip-vol) CVOL="${2:-}"; shift;; *) echo "arg tak dikenal: $1" >&2;;
esac; shift; done

RN7_IP="${RN7_IP:-10.66.66.6}" ; CONTAINER="${CONTAINER:-tool-appium-appium-1}"
TOOL_APPIUM="${TOOL_APPIUM:-$HOME/tool-appium}"
C50_SOCK="${C50_SOCK:-/tmp/c50.sock}" ; C50_HOST="${C50_HOST:-warungbudina@10.66.66.50}"
VNDIR="/sdcard/DCIM/VN"
adb() { docker exec "$CONTAINER" adb -s "$UDID" "$@"; }
c50() { ssh -o ControlPath="$C50_SOCK" -p22 "$C50_HOST" "$@"; }

# resolve UDID RN7
UDID="${RN7_PORT:+$RN7_IP:$RN7_PORT}"
[ -z "$UDID" ] && UDID=$(docker exec "$CONTAINER" adb devices 2>/dev/null | awk -v ip="$RN7_IP" '$1~ip{print $1;exit}')
[ -z "$UDID" ] && { echo "!! RN7 adb tak connect" >&2; exit 3; }
echo ">> RN7 UDID=$UDID"

# 1) snapshot file VN sebelum + jalankan export
BEFORE=$(adb shell "ls $VNDIR/*.mp4 2>/dev/null" | tr -d '\r' | sort)
echo ">> [1/4] render VN (export-video.js)"
OUT=$( cd "$TOOL_APPIUM" && timeout 260 docker compose exec -T -e ANDROID_UDID="$UDID" \
  -e APP_PACKAGE=com.frontrow.vlog -e FORCE_APP_LAUNCH=false -e DEVICE=rn7 \
  appium npx wdio run ./wdio.conf.js --spec tests/export-video.js 2>&1 )
echo "$OUT" | grep -E "\[export\]" || true
echo "$OUT" | grep -qE "[0-9]+ passing" || { echo "!! export GAGAL"; echo "$OUT" | tail -6; exit 4; }

# 2) deteksi MP4 baru
sleep 2
AFTER=$(adb shell "ls -t $VNDIR/*.mp4 2>/dev/null" | tr -d '\r')
NEWF=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER" | sort) | tail -1)
[ -z "$NEWF" ] && NEWF=$(echo "$AFTER" | head -1)   # fallback: terbaru
[ -z "$NEWF" ] && { echo "!! tak ada MP4 baru di $VNDIR" >&2; exit 5; }
echo ">> [2/4] file render: $NEWF"

# pull binary-safe (exec-out)
LOCAL="/tmp/$(basename "$NAME" .mp4)-raw.mp4"
adb exec-out cat "$NEWF" > "$LOCAL"
echo "   pulled $(wc -c < "$LOCAL") byte -> $LOCAL"

FINAL="/tmp/$NAME"
if [ -n "$MUSIC" ] && [ -f "$MUSIC" ]; then
  echo ">> [3/4] tambah musik ($MUSIC) via ffmpeg di .50"
  cat "$LOCAL" | c50 "cat > ~/_vx.mp4"
  cat "$MUSIC" | c50 "cat > ~/_vm.aud"
  c50 'docker cp ~/_vx.mp4 viral_analyzer:/tmp/vx.mp4 >/dev/null 2>&1; docker cp ~/_vm.aud viral_analyzer:/tmp/vm.aud >/dev/null 2>&1'
  c50 "docker exec viral_analyzer sh -c \"ffmpeg -y -i /tmp/vx.mp4 -i /tmp/vm.aud -filter_complex '[0:a]volume=$CVOL[a0];[1:a]volume=$MVOL[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0,aformat=sample_rates=44100:channel_layouts=stereo[a]' -map 0:v -map '[a]' -c:v copy -c:a aac -b:a 128k /tmp/vfinal.mp4\" >/dev/null 2>&1 && docker cp viral_analyzer:/tmp/vfinal.mp4 ~/_vfinal.mp4 >/dev/null 2>&1"
  c50 "cat ~/_vfinal.mp4" > "$FINAL"
  c50 'rm -f ~/_vx.mp4 ~/_vm.aud ~/_vfinal.mp4; docker exec viral_analyzer rm -f /tmp/vx.mp4 /tmp/vm.aud /tmp/vfinal.mp4' 2>/dev/null
  [ -s "$FINAL" ] || { echo "!! mux musik gagal, pakai video asli"; cp "$LOCAL" "$FINAL"; }
else
  echo ">> [3/4] tanpa --music: pakai audio klip apa adanya"
  cp "$LOCAL" "$FINAL"
fi
echo "   final: $(wc -c < "$FINAL") byte -> $FINAL"

# 4) upload Gdrive
echo ">> [4/4] upload ke $REMOTE"
timeout 120 rclone copy "$FINAL" "$REMOTE" --timeout 60s --retries 3 2>&1 | grep -iE "Copied|error|quota" || true
echo ">> SELESAI: $REMOTE$(basename "$FINAL")"
rm -f "$LOCAL"
