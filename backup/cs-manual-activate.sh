#!/usr/bin/env bash
# =====================================================================
# cs-manual-activate.sh — aktivasi ON-DEMAND satu profil Cloud Shell dari
# HUB (tanpa menunggu cron */5). Reuse PENUH logika proven, TIDAK dobel-
# tulis: bootstrap = open-cs.ps1 (laptop, sama persis dipakai
# run-daily-launch.ps1), deploy = lib-cs-deploy.sh (sama dgn
# cs-auto-deploy.sh/wake-orchestrator.sh).
#
# Tambahan (permintaan user 2026-10-16, pasca-temuan: ketiga Cloud Shell
# pagi itu mati 17-40mnt pasca-deploy walau keepalive "seharusnya" jalan
# dari bootstrap.sh): verifikasi EKSPLISIT proses `ping 8.8.8.8` di VM
# sesudah deploy, restart kalau hilang.
#
# ⚠️ JUJUR: keepalive ping ini BEST-EFFORT, BUKAN jaminan -- riwayat +
# verifikasi 16/10 pagi membuktikan Google tetap bisa reclaim VM
# ephemeral dlm hitungan puluhan menit meski ping jalan. Mode --watch di
# bawah ada justru supaya ketahuan CEPAT kalau itu terjadi lagi, bukan
# berasumsi sesi otomatis awet.
#
# Pakai: cs-manual-activate.sh <yuni|balibruntattour|gogobuda> [--watch]
# =====================================================================
set -uo pipefail

PROFILE="${1:-}"
WATCH="${2:-}"

case "$PROFILE" in
  yuni)             CS_HOST="warungbudina@10.66.66.50";    DEPLOY_FN="deploy_yuni" ;;
  balibruntattour)  CS_HOST="balibruntattour@10.66.66.60"; DEPLOY_FN="deploy_balibruntattour" ;;
  # ⛔ 2026-10-16: deploy_gogobuda() (scraper-worker TikTok) DIHAPUS dari
  # lib-cs-deploy.sh -- .61 sekarang cuma punya peran GUI-login, jadi target
  # deploy utk profil ini dialihkan ke deploy_gogobuda_gui.
  gogobuda)         CS_HOST="gogobuda65@10.66.66.61";       DEPLOY_FN="deploy_gogobuda_gui" ;;
  *)
    echo "Usage: $0 <yuni|balibruntattour|gogobuda> [--watch]" >&2
    exit 2
    ;;
esac

# shellcheck disable=SC1091
. "$HOME/akses-vps/backup/lib-cs-deploy.sh"

# (2026-10-28 fix, insiden pasca-outage-listrik 27/10) DUA bug akar ditemukan
# & diperbaiki di open-and-bootstrap-cs.py/cshell.py (dipanggil skrip ini via
# open-cs.ps1 -- SAMA PERSIS, tak dobel-tulis di sini):
#   1. click_terminal() dulu klik KOORDINAT -> kena overlay invisible Cloud
#      Shell (<security-blocking-indicator>, muncul utk browser EOL spt
#      Chrome 109 di laptop ini) -> fokus tercabut -> command silent-drop
#      total (reproduksi live: scrape tetap bersih, nol jejak command).
#   2. open_profile() vonis "tab tak terdeteksi" kalau tab profil ini SUDAH
#      terbuka dari attempt sebelumnya (klik shortcut cuma fokus ke tab lama,
#      bukan buka baru) -> bootstrap di-skip total, padahal tab lama itu
#      justru live & siap pakai.
# Kedua fix di atas membuat retype PRODUKTIF (Fix 2 = pakai ulang tab
# lama, Fix 1 = ketikan ke tab itu tak lagi silent-drop).
#
# Tambahan DI SKRIP INI (bukan sekadar warisan fix di atas): kalau node
# SUDAH reachable (kasus paling umum -- dipanggil cuma utk verifikasi ulang,
# bukan recovery), bootstrap.sh di VM biasanya SEDANG menjalankan `ping
# 8.8.8.8` FOREGROUND sbg keepalive (lihat akhir bootstrap.sh) -- shell tak
# punya prompt kosong utk diketik ulang. Memaksa retype ke sesi sibuk begini
# percuma/membingungkan (karakter nyasar ke stream ping, bukan command baru).
# Jadi: cek reachable DULU, skip step bootstrap kalau sudah sehat.
echo "=== [0/4] Cek apakah $PROFILE SUDAH reachable (hindari ganggu sesi sehat) ==="
if reachable_cs "$CS_HOST"; then
  echo "OK: $CS_HOST SUDAH reachable -- skip bootstrap Chrome, langsung ke deploy."
  up=1
else
  echo "$CS_HOST belum reachable -- lanjut bootstrap via laptop."

  echo
  echo "=== [1/4] Bootstrap via laptop (open-cs.ps1 -Profile $PROFILE) ==="
  echo "(Kalau tab Cloud Shell profil ini SUDAH ada & live, skrip laptop PAKAI ULANG tab itu -- tak selalu buka tab baru.)"
  ssh ltap-mini "powershell -NoProfile -ExecutionPolicy Bypass -File C:\chrome-cdp\open-cs.ps1 -Profile $PROFILE; echo EXITCODE=\$LASTEXITCODE" 2>&1 \
    | grep -v '^#<\|^<Objs\|CLIXML'
  echo "(exit code di atas cuma indikasi KASAR -- lihat catatan di open-and-bootstrap-cs.py; kebenaran = reachable_cs di bawah.)"

  echo
  echo "=== [2/4] Tunggu WireGuard+SSH naik (maks 90s) ==="
  up=0
  for i in $(seq 1 18); do
    if reachable_cs "$CS_HOST"; then up=1; break; fi
    sleep 5
  done
fi
if [ "$up" -ne 1 ]; then
  echo "GAGAL: $CS_HOST tetap tak reachable setelah bootstrap. ${CS_LAST_SSH_ERR:-(timeout, VM kemungkinan belum/tak naik)}"
  exit 1
fi
echo "OK: $CS_HOST reachable."

echo
echo "=== [3/4] Deploy project ($DEPLOY_FN) ==="
"$DEPLOY_FN"
deploy_rc=$?
if [ "$deploy_rc" -eq 0 ]; then
  echo ">>> DEPLOY SEHAT TERVERIFIKASI."
else
  echo ">>> DEPLOY GAGAL/belum sehat (rc=$deploy_rc) -- lihat pesan di atas."
fi

echo
echo "=== [4/4] Verifikasi + pastikan keepalive ping jalan di VM ==="
ssh "${CS_SSHOPTS[@]}" "$CS_HOST" '
  if pgrep -f "ping 8.8.8.8" >/dev/null 2>&1; then
    echo "keepalive SUDAH jalan:"; pgrep -af "ping 8.8.8.8"
  else
    echo "keepalive TAK ditemukan -- restart..."
    pkill -f "ping 8.8.8.8" 2>/dev/null
    setsid bash -c "ping 8.8.8.8 >/tmp/keepalive-ping.log 2>&1 </dev/null" & disown
    sleep 1
    pgrep -af "ping 8.8.8.8" && echo "keepalive RESTART OK" || echo "keepalive GAGAL direstart"
  fi
'

echo
echo "=== SELESAI: $PROFILE (deploy_rc=$deploy_rc) ==="
echo "Catatan: tab Chrome TERBUKA di laptop = tanda sesi masih hidup;"
echo "popup 'Sambungan terputus'/tab hilang = sesi sudah mati (lihat README)."

if [ "$WATCH" = "--watch" ]; then
  echo
  echo "=== MODE WATCH $PROFILE (Ctrl+C utk stop) -- cek tiap 20s ==="
  while true; do
    sleep 20
    ts="$(date -u +%H:%M:%S)Z"
    if reachable_cs "$CS_HOST"; then
      ka="$(ssh "${CS_SSHOPTS[@]}" "$CS_HOST" 'pgrep -af "ping 8.8.8.8" | head -1' 2>/dev/null)"
      echo "[$ts] $CS_HOST reachable. keepalive: ${ka:-TAK ADA}"
    else
      echo "[$ts] $CS_HOST TAK REACHABLE LAGI -- sesi mati. ${CS_LAST_SSH_ERR:-}"
    fi
  done
fi
