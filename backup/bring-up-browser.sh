#!/usr/bin/env bash
# =====================================================================
# bring-up-browser.sh — siapkan full-tool-browser di .60 (Cloud Shell
# balibruntattour, EPHEMERAL). Dijalankan DI akses-vps, MENGGERAKKAN .60.
#
# Kenapa jalan di akses-vps (bukan di .60 seperti bring-up-analyzer di .50):
# SOP 2026-08-07 = pemicu dari tier 24/7, dan API_KEY kanonik hidup di
# akses-vps (~/.config/browser-api/credentials.env). Skrip ini menanam kunci
# itu ke .env .60 otomatis -> auth .60 & akses-vps selalu sinkron tanpa
# menyalin kunci manual. Paritas peran dgn run-drain.sh (akses-vps -> .50).
#
# Idempoten:
#   - .60 sudah live + auth aktif        -> verifikasi lalu exit 0.
#   - .60 live tapi auth OFF (.env basi) -> re-sync .env + recreate.
#   - VM fresh (repo/image hilang)       -> clone + build DETACHED + poll.
#
# Prasyarat: user sudah menyalakan Cloud Shell balibruntattour + paste
# bootstrap (WG+SSH+watchdog). Kalau .60 tak bisa di-SSH, skrip berhenti
# dgn instruksi jelas (ayam-telur: tak bisa dibangunkan dari luar).
#
# Pemakaian: ./bring-up-browser.sh
# Exit: 0 live & terverifikasi · 1 gagal / .60 belum dinyalakan user.
# =====================================================================
set -uo pipefail

C60_HOST="${C60_HOST:-balibruntattour@10.66.66.60}"
C60_KEY="${C60_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
API="${BROWSER_API:-http://10.66.66.60:8080}"
CRED="${BROWSER_API_CRED:-$HOME/.config/browser-api/credentials.env}"
REPO_URL="https://github.com/warungbudina-digital/browser.git"
BUILD_WAIT="${BUILD_WAIT:-360}"    # detik; build Chromium cold ~3-4mnt

log(){ echo "[bring-up-browser $(date -u +%H:%M:%S)] $*"; }
# (2026-08-28 fix) .60 EPHEMERAL -> host-key BEDA tiap wake (VM baru, IP
# sama). `accept-new` cuma otomatis-terima host BARU, tapi MENOLAK TOTAL
# kalau ada entri lama yg beda ("Host key has changed", dikira MITM) --
# persis Bug KELIMA yg sudah difix di reachable_cs()/lib-cs-deploy.sh
# (2026-08-24) TAPI lupa ikut diterapkan di sini. Reproduksi live 28/8:
# bootstrap .60 sukses penuh (WG+SSH ready, manual-verified reachable)
# TAPI bring-up-browser.sh tetap lapor "GAGAL: .60 tak bisa di-SSH" --
# `ssh -v` konfirmasi persis "WARNING: REMOTE HOST IDENTIFICATION HAS
# CHANGED". Fix: StrictHostKeyChecking=no + UserKnownHostsFile=/dev/null
# (aman, .60 cuma reachable via WireGuard privat sendiri).
ssh60(){ ssh -o ControlPath=none -i "$C60_KEY" -o IdentitiesOnly=yes \
         -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
         -o BatchMode=yes -p 22 "$C60_HOST" "$@"; }
hs(){ curl -m8 -s -o /dev/null -w '%{http_code}' "$API$1" 2>/dev/null; }

# ── Kunci API kanonik (dari file durable, JANGAN hardcode) ──────────────────
[ -f "$CRED" ] && { set -a; . "$CRED"; set +a; }
KEY="${BROWSER_API_KEY:-}"
if [ -z "$KEY" ]; then
  log "GAGAL: BROWSER_API_KEY kosong — set env atau isi ${CRED}."
  exit 1
fi

# ── 0. Fast path: sudah live? ───────────────────────────────────────────────
if [ "$(hs /health)" = "200" ]; then
  if [ "$(hs /sessions)" = "401" ]; then
    log "SUDAH live & auth AKTIF. Verifikasi kunci..."
    if [ "$(curl -m8 -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $KEY" "$API/sessions")" = "200" ]; then
      log "OK: kunci cocok, /sessions 200. Tak ada yang perlu dilakukan."
      exit 0
    fi
    log "!! Auth aktif TAPI kunci akses-vps DITOLAK (.env .60 pakai kunci lain) -> re-sync."
  else
    log "Live tapi auth OFF (/sessions != 401) -> re-sync .env + recreate."
  fi
else
  log ".60 belum melayani :8080 -> perlu (re)deploy."
fi

# ── 1. .60 bisa di-SSH? (kalau tidak = user belum nyalakan/bootstrap) ───────
if ! ssh60 true 2>/dev/null; then
  log "GAGAL: .60 tak bisa di-SSH."
  log "  -> Nyalakan Cloud Shell 'balibruntattour' + paste bootstrap"
  log "     (~/key-testing-cloudshell/balibruntattour-bootstraps.sh) lalu ulangi."
  exit 1
fi

# Host key .60 berubah tiap VM baru -> bersihkan supaya poll curl/ssh mulus
ssh-keygen -f "$HOME/.ssh/known_hosts" -R 10.66.66.60 >/dev/null 2>&1 || true

# ── 2. Provisioning DI .60: clone + .env (sync kunci) + launch build detached
# Kunci diinject via env remote. Heredoc 'REMOTE' = tanpa ekspansi lokal.
log "Provisioning .60 (clone bila perlu, sinkronkan .env, jalankan build)..."
ssh60 "BROWSER_API_KEY='$KEY' bash -s" <<'REMOTE'
set -e
REPO_DIR="$HOME/browser"

# repo (public, HTTPS keyless) — clone kalau hilang pasca-recycle
if [ ! -d "$REPO_DIR/.git" ]; then
  echo "  [.60] repo absen -> git clone"
  git clone --depth 1 https://github.com/warungbudina-digital/browser.git "$REPO_DIR"
fi
cd "$REPO_DIR"

# .env: DB_PASSWORD HANYA di-set saat .env FRESH (regenerasi = mismatch dgn
# volume postgres yg sudah ter-init, lihat .nudge). API_KEY SELALU disinkron.
if [ ! -f .env ]; then
  echo "  [.60] .env absen -> buat dari .env.example (+DB_PASSWORD acak)"
  cp .env.example .env
  sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(openssl rand -hex 24)|" .env
fi
sed -i "s|^API_KEY=.*|API_KEY=${BROWSER_API_KEY}|" .env
sed -i "s|^MQTT_ENABLED=.*|MQTT_ENABLED=false|" .env
chmod 600 .env

# Build Chromium bisa >2mnt -> DETACHED + sentinel (jangan tahan channel SSH).
rm -f "$HOME/browser-done" "$HOME/browser-fail"
nohup bash -c 'cd "$HOME/browser" && docker compose up -d --build && touch "$HOME/browser-done" || touch "$HOME/browser-fail"' \
  > "$HOME/browser-deploy.log" 2>&1 &
echo "  [.60] build dilepas detached (log ~/browser-deploy.log)"
REMOTE

# ── 3. Poll dari akses-vps sampai selesai / gagal / timeout ─────────────────
log "Menunggu build+up selesai (maks ${BUILD_WAIT}s)..."
deadline=$(( $(date +%s) + BUILD_WAIT ))
state=timeout
while [ "$(date +%s)" -lt "$deadline" ]; do
  r=$(ssh60 'if [ -f ~/browser-done ]; then echo done; elif [ -f ~/browser-fail ]; then echo fail; else echo run; fi' 2>/dev/null)
  case "$r" in
    done) state=done; break ;;
    fail) state=fail; break ;;
  esac
  sleep 12
done

if [ "$state" = fail ]; then
  log "!!! build GAGAL di .60. Cek: ssh .60 'tail -40 ~/browser-deploy.log'"
  exit 1
fi
if [ "$state" = timeout ]; then
  log "!!! timeout ${BUILD_WAIT}s — build mungkin masih jalan. Cek sentinel ~/browser-done."
  exit 1
fi

# ── 4. Verifikasi dari hub: health + auth benar-benar menggigit ─────────────
sleep 3
H=$(hs /health); A=$(hs /sessions)
AK=$(curl -m8 -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $KEY" "$API/sessions")
log "health=$H  /sessions(tanpa-kunci)=$A  /sessions(dengan-kunci)=$AK"
if [ "$H" = "200" ] && [ "$A" = "401" ] && [ "$AK" = "200" ]; then
  log "OK: .60 LIVE, auth AKTIF, kunci akses-vps cocok."
  # rapikan build cache (disk .60 ketat, sempat 96% pasca-build)
  ssh60 'docker builder prune -af >/dev/null 2>&1; df -h /home | tail -1' 2>/dev/null | sed 's/^/  disk .60: /'
  exit 0
fi
log "!!! Verifikasi GAGAL (health=$H auth=$A kunci=$AK). Cek container di .60."
exit 1
