#!/usr/bin/env bash
# =====================================================================
# bring-up-chromevps.sh — siapkan 1 profil chromium-cookie-station di
# CHROME-VPS (idcloudhost, VM PERSISTEN — bukan Cloud Shell ephemeral).
# Dijalankan DI akses-vps (hub), MENGGERAKKAN CHROME-VPS. Paritas peran
# dgn bring-up-browser.sh (hub -> .60), TAPI infra beda total:
#
#   node .60 (Cloud Shell)      CHROME-VPS (idcloudhost)
#   -----------------------     --------------------------
#   ephemeral, IP tetap tapi    VM persisten, disk persisten,
#   VM baru tiap wake, disk     restart cuma restart biasa
#   hilang total tiap recycle
#   perlu shell.cloud.google.com/CDP+bootstrap-paste utk SSH pertama
#   kali nyala (ayam-telur)     SSH admin key SELALU bisa (bukan ayam-telur)
#   repo publik -> git clone    repo TANPA git remote -> rsync dari hub
#
# Jadi TIDAK ADA di sini: shell.cloud.google.com, klik "Izinkan", CDP,
# upload+chmod+sudo bootstrap script. VM ini sudah bisa di-SSH langsung
# kapan saja (selama instance-nya sendiri tidak di-stop).
#
# Idempoten:
#   - VM idcloudhost stopped        -> nyalakan via API, tunggu SSH.
#   - VM live, repo/.git hilang     -> rsync repo dari hub (BUKAN clone,
#                                      repo ini tak ada remote git publik).
#   - VM live, image belum ke-build -> docker compose build (detached+poll).
#   - VM live, profil belum nyala   -> docker compose up -d <profil>.
#   - VM live, profil sudah sehat   -> verifikasi lalu exit 0 (fast path).
#
# ⚠️ CATATAN: profiles/<nama>/ (sesi login asli) TIDAK direstore otomatis
# di sini (beda dari bring-up-browser.sh yg restore dari Gdrive) — kalau
# VPS pernah wipe/reinstall total, sesi login harus login ulang manual
# lewat KasmVNC. Backup/restore sesi belum ada utk chromium-cookie-station,
# ini scope terpisah kalau nanti dibutuhkan.
#
# ⚠️ SENGAJA TIDAK dipasang ke cron apapun (di hub maupun di CHROME-VPS).
# CHROME-VPS sudah punya jadwalnya sendiri lokal (crontab VM itu sendiri:
# auto-start-balibruntattour.sh + safety-stop.sh). Menambah pemicu KEDUA
# dari hub berisiko rebutan state persis seperti race lama wake-orchestrator
# vs cs-auto-deploy di node .60 (lihat memori project_laptop_wol_power) —
# skrip ini murni alat pemulihan manual/on-demand.
#
# Pemakaian: ./bring-up-chromevps.sh [profil]   (default: balibruntattour)
# Exit: 0 live & terverifikasi · 1 gagal.
# =====================================================================
set -uo pipefail

PROFILE="${1:-balibruntattour}"
VPS_HOST="${VPS_HOST:-warungbudina@10.122.31.254}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/chrome-vps-admin}"
VPS_UUID="${VPS_UUID:-98f7c5e0-d60c-4801-aba7-61424bce6bd8}"
IDCLOUD_CRED="${IDCLOUD_CRED:-$HOME/.config/idcloudhost/credentials.env}"
REPO_LOCAL="${REPO_LOCAL:-$HOME/chromium-cookie-station}"
REPO_REMOTE="chromium-cookie-station"
BOOT_WAIT="${BOOT_WAIT:-90}"      # detik tunggu VM boot sampai SSH nyahut
BUILD_WAIT="${BUILD_WAIT:-300}"   # detik; docker compose build image ~4.6GB

declare -A PORTS=( [yuni]=3050 [balibruntattour]=3060 [gogobuda]=3070 [maydualapan]=3080 [sahabat-nutrilite]=3090 )
PORT="${PORTS[$PROFILE]:-}"
if [ -z "$PORT" ]; then
  echo "GAGAL: profil '$PROFILE' tak dikenal (pilihan: ${!PORTS[*]})"
  exit 1
fi

log(){ echo "[bring-up-chromevps $(date -u +%H:%M:%S)] $*"; }
sv(){ ssh -o ControlPath=none -i "$VPS_KEY" -o IdentitiesOnly=yes \
      -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o BatchMode=yes "$VPS_HOST" "$@"; }

[ -f "$IDCLOUD_CRED" ] && { set -a; . "$IDCLOUD_CRED"; set +a; }
if [ -z "${IDCLOUDHOST_API_KEY:-}" ]; then
  log "GAGAL: IDCLOUDHOST_API_KEY kosong — isi ${IDCLOUD_CRED}."
  exit 1
fi

api_status(){ curl -s -H "apikey: $IDCLOUDHOST_API_KEY" \
  "https://api.idcloudhost.com/v1/user-resource/vm?uuid=$VPS_UUID" \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("status","unknown"))
except Exception: print("unknown")' 2>/dev/null; }
api_start(){ curl -s -X POST -H "apikey: $IDCLOUDHOST_API_KEY" -d "uuid=$VPS_UUID" \
  "https://api.idcloudhost.com/v1/user-resource/vm/start" >/dev/null; }

# ── 0. Fast path: VPS bisa di-SSH & profil sudah nyala+sehat? ──────────────
if sv true 2>/dev/null; then
  live=1
else
  live=0
fi

if [ "$live" = 1 ] && sv "cd $REPO_REMOTE && docker compose ps $PROFILE --status running --format '{{.Name}}' 2>/dev/null | grep -q ."; then
  code=$(sv "curl -s -o /dev/null -w '%{http_code}' -m5 http://127.0.0.1:$PORT" 2>/dev/null)
  if [ "$code" = "200" ] || [ "$code" = "401" ]; then
    log "OK: profil '$PROFILE' SUDAH nyala & sehat (HTTP $code di :$PORT). Tak ada yang perlu dilakukan."
    exit 0
  fi
  log "profil '$PROFILE' nyala tapi belum menjawab (HTTP $code) — lanjut cek/tunggu."
fi

# ── 1. VPS idcloudhost hidup? kalau tidak, nyalakan via API ─────────────────
if [ "$live" = 0 ]; then
  status=$(api_status)
  log "VPS tak bisa di-SSH. Status API idcloudhost: ${status:-unknown}."
  if [ "$status" != "running" ]; then
    log "Menyalakan CHROME-VPS via API idcloudhost..."
    api_start
  fi
  log "Menunggu VPS boot & SSH siap (maks ${BOOT_WAIT}s)..."
  deadline=$(( $(date +%s) + BOOT_WAIT ))
  ok=0
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if sv true 2>/dev/null; then ok=1; break; fi
    sleep 5
  done
  if [ "$ok" -ne 1 ]; then
    log "GAGAL: VPS tak kunjung bisa di-SSH dlm ${BOOT_WAIT}s."
    exit 1
  fi
  log "VPS live & bisa di-SSH."
fi

# ── 2. Repo ada di VPS? (TANPA git remote publik -> rsync dari hub) ─────────
if ! sv "[ -d $REPO_REMOTE/.git ]" 2>/dev/null; then
  log "Repo absen di VPS -> rsync dari hub ($REPO_LOCAL), profiles/ DIKECUALIKAN (sesi asli cuma di VPS)..."
  rsync -az --exclude 'profiles/' -e "ssh -i $VPS_KEY -o StrictHostKeyChecking=accept-new" \
    "$REPO_LOCAL/" "$VPS_HOST:$REPO_REMOTE/" || { log "GAGAL rsync repo."; exit 1; }
  log "Repo tersalin. profiles/ TIDAK direstore -- sesi login perlu login ulang manual via KasmVNC."
fi

# ── 3. Image ada? kalau tidak, build (detached + sentinel, bisa >2mnt) ──────
if ! sv "docker image inspect chromium-cookie-station:latest >/dev/null 2>&1"; then
  log "Image absen -> docker compose build (detached)..."
  sv "cd $REPO_REMOTE && rm -f build-done build-fail && nohup bash -c 'docker compose build && touch build-done || touch build-fail' > build.log 2>&1 &"
  deadline=$(( $(date +%s) + BUILD_WAIT ))
  state=timeout
  while [ "$(date +%s)" -lt "$deadline" ]; do
    r=$(sv "cd $REPO_REMOTE && { [ -f build-done ] && echo done; } || { [ -f build-fail ] && echo fail; } || echo run" 2>/dev/null)
    case "$r" in done) state=done; break;; fail) state=fail; break;; esac
    sleep 10
  done
  case "$state" in
    fail) log "GAGAL build. Cek: ssh CHROME-VPS 'tail -40 $REPO_REMOTE/build.log'"; exit 1 ;;
    timeout) log "GAGAL: timeout build ${BUILD_WAIT}s, mungkin masih jalan."; exit 1 ;;
  esac
  log "Image selesai di-build."
fi

# ── 4. Nyalakan profil kalau belum nyala ─────────────────────────────────────
if ! sv "cd $REPO_REMOTE && docker compose ps $PROFILE --status running --format '{{.Name}}' 2>/dev/null | grep -q ."; then
  log "Menyalakan profil '$PROFILE'..."
  sv "cd $REPO_REMOTE && docker compose up -d $PROFILE" || { log "GAGAL docker compose up."; exit 1; }
  sleep 5
fi

# ── 5. Verifikasi akhir ──────────────────────────────────────────────────────
code=$(sv "curl -s -o /dev/null -w '%{http_code}' -m8 http://127.0.0.1:$PORT" 2>/dev/null)
if [ "$code" = "200" ] || [ "$code" = "401" ]; then
  log "OK: profil '$PROFILE' LIVE & menjawab (HTTP $code di :$PORT)."
  exit 0
fi
log "!!! Verifikasi GAGAL (HTTP $code di :$PORT). Cek: ssh CHROME-VPS 'cd $REPO_REMOTE && docker compose logs $PROFILE'"
exit 1
