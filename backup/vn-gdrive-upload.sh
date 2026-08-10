#!/usr/bin/env bash
# vn-gdrive-upload.sh — tarik export VN dari RN7 (WG tunnel) -> upload ke Gdrive (rclone).
# Pola SOP node-terjadwal: state 24/7 (akses-vps), no-op anggun saat RN7 OFF.
# Prasyarat: rclone remote 'gdrive' terkonfig (OAuth) + tool-appium container (adb).
# Cron contoh: 17 */3 * * * ~/akses-vps/backup/vn-gdrive-upload.sh
set -uo pipefail
REMOTE="gdrive:VN-Node-Outputs"          # folder tujuan di Gdrive
RN7_IP="10.66.66.6"
VN_DIRS=(/sdcard/DCIM/VN /sdcard/Movies/VN /sdcard/DCIM/Camera)  # kandidat folder export VN
DONE_DIR="/sdcard/DCIM/VN/_uploaded"     # arsip di HP pasca-upload (anti dobel)
TMP="$(mktemp -d /tmp/vn-upload.XXXXXX)"
LOG=~/vn-gdrive-upload.log
trap 'rm -rf "$TMP"' EXIT
log(){ echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
adb(){ docker exec tool-appium-appium-1 adb "$@"; }

command -v rclone >/dev/null || { log "rclone tak ada"; exit 0; }
rclone listremotes 2>/dev/null | grep -q '^gdrive:' || { log "remote 'gdrive' belum dikonfig (OAuth) — SKIP"; exit 0; }

# RN7 online? (no-op anggun)
ping -c1 -W2 "$RN7_IP" >/dev/null 2>&1 || { log "RN7 OFF — no-op"; exit 0; }
PORT=$(sudo -n nmap -Pn -p30000-45000 --open -T4 "$RN7_IP" 2>/dev/null | grep -oE '^[0-9]+' | head -1)
[ -n "$PORT" ] || { log "port adb RN7 tak ketemu (wireless-debug off?) — no-op"; exit 0; }
S="$RN7_IP:$PORT"; adb connect "$S" >/dev/null 2>&1

# kumpulkan file export video (mp4/mov) yg BELUM di-arsip
mapfile -t FILES < <(for d in "${VN_DIRS[@]}"; do adb -s "$S" shell "ls $d/*.mp4 $d/*.mov 2>/dev/null" 2>/dev/null; done | tr -d '\r' | grep -vE "_uploaded/" | sort -u)
[ "${#FILES[@]}" -eq 0 ] && { log "tak ada export baru — no-op"; exit 0; }

adb -s "$S" shell "mkdir -p $DONE_DIR" >/dev/null 2>&1
OK=0
for f in "${FILES[@]}"; do
  [ -z "$f" ] && continue
  bn=$(basename "$f")
  log "pull $f"
  if adb -s "$S" pull "$f" "$TMP/$bn" >/dev/null 2>&1 && [ -s "$TMP/$bn" ]; then
    if rclone copy "$TMP/$bn" "$REMOTE" --no-traverse 2>>"$LOG"; then
      # verifikasi ada di remote lalu arsip di HP (bukan hapus permanen)
      if rclone lsf "$REMOTE/$bn" >/dev/null 2>&1; then
        adb -s "$S" shell "mv '$f' '$DONE_DIR/'" >/dev/null 2>&1
        log "UPLOADED + arsip: $bn"; OK=$((OK+1))
      else log "verify GAGAL di remote: $bn (biar di HP)"; fi
    else log "rclone upload GAGAL: $bn"; fi
    rm -f "$TMP/$bn"
  else log "pull GAGAL/kosong: $bn"; fi
done
log "SELESAI: $OK/${#FILES[@]} ter-upload"
# cap log 800 baris
tail -800 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
