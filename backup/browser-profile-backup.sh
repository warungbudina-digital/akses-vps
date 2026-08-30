#!/usr/bin/env bash
# Backup sesi login (~/browser/data/artifacts/<profil>/sessions/*.json di
# balibruntattour, .60) -- cookies per-akun disimpan lewat mekanisme BAWAAN
# `sessionSave`/`sessionLoad` (POST /browser/request {action:"session-save",
# name:"<akun>"}) -- ke Gdrive maydualapan8, folder
# `Project-Tutorial/browser-profile/` (remote rclone `project-tutorial:`).
#
# KENAPA sessions/*.json, BUKAN seluruh data/profiles/: profil remote-cdp
# (satu-satunya driver yg jalan di container `full-tool-browser` -- driver
# `managed` butuh Chromium terpasang di container ini sendiri, TAK ADA by
# design/"slim") berbagi SATU browser context per cdpUrl -- isolasi akun
# dicapai via sessionSave (nama=akun) simpan storageState (cookies+origins)
# ke JSON kecil, sessionLoad muat balik sebelum kerja per-akun. File ini
# JAUH lebih kecil & portable drpd tar profil Chromium penuh (2026-08-30).
#
# KENAPA ADA (persistensi): .60 = Google Cloud Shell EPHEMERAL. `data/
# artifacts` cuma bind-mount ke disk VM -- VM recycle = SEMUA sesi login
# HILANG TOTAL, harus login ulang dari nol. Skrip ini bikin itu TIDAK
# terjadi in-practice: `bring-up-browser.sh` otomatis restore dari backup
# terbaru di sini kalau sessions/ lokal kosong pasca-recycle.
#
# Pola SAMA `ogis-vault-backup.sh` (preflight no-op anggun + validasi +
# rotasi), TAPI tujuan Gdrive (bukan DB-VPS) -- pilihan user 2026-08-30,
# reuse folder Project-Tutorial yg sudah ada dari project lain.
#
# STREAMING PENUH: tar di .60 -> pipe SSH -> `rclone rcat` langsung ke
# Gdrive, TAK PERNAH mendarat di disk akses-vps.
#
# .60 HANYA HIDUP TERJADWAL (bukan 24/7). Karena itu skrip ini:
#   - no-op ANGGUN (exit 0) kalau .60 mati / belum ada sesi tersimpan.
#   - exit != 0 HANYA kalau .60 hidup TAPI backup benar-benar gagal.
set -uo pipefail

C60_HOST="${C60_HOST:-balibruntattour@10.66.66.60}"
C60_KEY="${C60_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
REMOTE="${REMOTE:-project-tutorial:browser-profile}"   # rclone remote:path
RETENTION="${RETENTION:-10}"                            # simpan N tarball terbaru
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="sessions-${STAMP}.tar.gz"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

ssh60() {
  ssh -o ControlPath=none -i "$C60_KEY" -o IdentitiesOnly=yes \
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=10 -o BatchMode=yes -p 22 "$C60_HOST" "$@"
}

# ── 1. Preflight: .60 hidup + ada minimal 1 file sesi tersimpan? ────────────
if ! ssh60 true 2>/dev/null; then
  log "SKIP: .60 tidak bisa di-SSH (Cloud Shell mati / bootstrap belum jalan). Ini normal."
  exit 0
fi

if ! ssh60 'find ~/browser/data/artifacts -path "*/sessions/*.json" -print -quit 2>/dev/null | grep -q .' 2>/dev/null; then
  log "SKIP: belum ada file sesi (*/sessions/*.json) tersimpan di .60. Ini normal."
  exit 0
fi

# ── 2. Stream tar semua */sessions/ .60 -> Gdrive (tak mendarat di disk akses-vps) ──
log "Backup sesi login di .60 -> ${REMOTE}/${NAME}"
if ! ssh60 'cd ~/browser/data/artifacts && find . -path "*/sessions/*.json" -print0 | tar --null -T - -czf -' 2>/dev/null \
     | rclone rcat "${REMOTE}/${NAME}" 2>&1; then
  log "GAGAL: pipe tar(.60) -> rclone rcat terputus."
  rclone deletefile "${REMOTE}/${NAME}" 2>/dev/null
  exit 1
fi

# ── 3. Validasi ukuran (tak bisa gzip -t tanpa landing di disk, cukup size) ──
SIZE=$(rclone size "${REMOTE}/${NAME}" --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('bytes',0))" 2>/dev/null || echo 0)
if [ "${SIZE:-0}" -lt 50 ]; then
  log "GAGAL: backup cuma ${SIZE}B (< 50B) - dianggap rusak, dibuang."
  rclone deletefile "${REMOTE}/${NAME}" 2>/dev/null
  exit 1
fi
log "OK: ${NAME} (${SIZE}B) tersimpan di ${REMOTE}/"

# ── 4. Rotasi: sisakan N terbaru ─────────────────────────────────────────────
rclone lsf "$REMOTE" --include 'sessions-*.tar.gz' 2>/dev/null | sort | head -n -"$RETENTION" | while read -r f; do
  [ -n "$f" ] && rclone deletefile "${REMOTE}/${f}" 2>/dev/null && log "rotasi: buang ${f}"
done

exit 0
