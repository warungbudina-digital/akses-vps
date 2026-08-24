#!/usr/bin/env bash
# =====================================================================
# wake-orchestrator.sh — JALUR UTAMA pasca-wake laptop SUARAHATI.
# Dijalankan DI HUB (akses-vps, 24/7) lewat cron, beberapa menit setelah
# jadwal RTC-wake laptop (NodeWake-0845, lihat project_laptop_wol_power).
#
# ALUR BERTAHAP KETAT (permintaan user 2026-08-16): satu profil selesai
# TUNTAS (bootstrap WG+SSH -> deploy project -> SEHAT terverifikasi)
# sebelum profil berikutnya dibuka. TUJUAN: laptop lemah (AMD E1-2500)
# tak lagi kewalahan buka 3 tab Cloud Shell berat sekaligus (akar
# masalah kegagalan berulang sebelumnya).
#
# KEBIJAKAN GAGAL (direvisi 2026-08-24) = SEQUENTIAL + BERHENTI BERSYARAT,
# dibedakan berdasar TAHAP kegagalan -- bukan lagi "sekali gagal, semua
# berhenti" polos:
#   - HARD-FAIL (trigger task open-cs-<profil> gagal / laptop tak kunjung
#     lapor selesai bootstrap dlm batas waktu): profil berikutnya TIDAK
#     dicoba, skrip berhenti total. Alasan: kegagalan di tahap INI berarti
#     laptop (CPU lemah) sendiri sedang bermasalah/kewalahan -- menambah
#     beban buka tab lagi cuma bikin kegagalan beruntun.
#   - SOFT-FAIL (bootstrap laptop SUDAH selesai/sukses, tapi node Cloud
#     Shell tak kunjung reachable ATAU deploy_<profil> gagal/tak sehat):
#     profil berikutnya TETAP DICOBA. Alasan: di tahap ini laptop sudah
#     tuntas bagiannya (tab sudah terbuka & idle) -- kegagalannya murni
#     di sisi cloud (VM/deploy), tak ada risiko tambahan beban ke laptop
#     kalau lanjut buka tab profil berikutnya.
# Kejadian nyata yg memicu revisi ini (2026-08-24): yuni SUKSES bootstrap
# di laptop, tapi deploy-nya kalah race lock 27 detik lawan cron
# cs-auto-deploy.sh (lihat lib-cs-deploy.sh) -> dulu ini bikin
# balibruntattour+gogobuda ikut TAK PERNAH dicoba padahal tak ada
# hubungannya sama sekali dgn kondisi laptop.
#
# TIAP PROFIL cuma dianggap SELESAI kalau tahap deploy-nya SEHAT PENUH
# (healthz/health returns true, BUKAN cuma "container ada") -- fungsi
# deploy_<profil> di lib-cs-deploy.sh sudah menjamin ini secara sinkron.
#
# Prasyarat di laptop (sekali-setup, sudah dikerjakan 2026-08-16):
#   - 3 scheduled task tanpa auto-trigger: open-cs-yuni, open-cs-
#     balibruntattour, open-cs-gogobuda (masing2 InteractiveToken, cuma
#     bisa dipicu `schtasks /run` dari hub via ssh ltap-mini).
#   - Task lama `open-cs` (buka 3 sekaligus) auto-trigger-nya DICABUT,
#     tapi tasknya tetap ada utk fallback manual/darurat kalau perlu.
#
# Exit code: 0 = SEMUA 3 profil selesai sehat. 1 = berhenti di tengah
# (lihat log utk tahu di profil mana & kenapa).
# =====================================================================
set -uo pipefail

LOCK="$HOME/.wake-orchestrator.lock"
LOG="$HOME/wake-orchestrator.log"
STATE_LOG="$HOME/ltap-mini-open-cs.log-snapshot"  # snapshot open-cs.log laptop, per-profil

exec 201>"$LOCK"
flock -n 201 || { echo "[wake-orch $(date -u +%H:%M:%S)Z] sudah berjalan (lock) - skip." >> "$LOG"; exit 0; }

# shellcheck disable=SC1091
. "$HOME/akses-vps/backup/lib-cs-deploy.sh"

log(){ echo "[wake-orch $(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }

# cap log
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 3000 ]; then
  tail -n 1000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

TELEGRAM_SCRIPT="$HOME/akses-vps/backup/send-telegram.sh"
notify(){
  [ -x "$TELEGRAM_SCRIPT" ] && bash "$TELEGRAM_SCRIPT" "$1" >/dev/null 2>&1 || true
}

# ---- Prasyarat: laptop hidup? ----
# ⚠️ TAK notify tiap kali (2x/hari, false-alarm wajar kalau laptop resume
# telat beberapa detik) -- TAPI kalau sampai gagal 2x TICK BERTURUT-TURUT
# (state file), itu pola nyata (mis. jadwal RTC-wake salah/rusak) -> alert.
STATE="$HOME/.wake-orchestrator-unreachable.count"
if ! timeout 8 ssh -o ConnectTimeout=6 -o BatchMode=yes ltap-mini 'exit' 2>/dev/null; then
  log "laptop TAK terjangkau -> batal total (normal kalau belum wake/masih hibernasi)."
  n=0; [ -f "$STATE" ] && n="$(cat "$STATE" 2>/dev/null || echo 0)"
  n=$((n + 1))
  echo "$n" > "$STATE"
  if [ "$n" -ge 2 ]; then
    notify "⚠️ wake-orchestrator: laptop TAK terjangkau ${n}x tick berturut-turut. Kemungkinan RTC-wake gagal/jadwal salah -- cek fisik laptop."
  fi
  exit 0
fi
rm -f "$STATE"
log "laptop terjangkau -> mulai alur bertahap 3 profil."

# open_cs_profile <task-name-suffix> -> trigger task open-cs-<X> di laptop
# via schtasks/run (InteractiveToken, WAJIB lewat Scheduled Task -- SSH
# langsung TAK bisa fokus window Chrome, lihat project_medsos_agent.md).
open_cs_profile() {
  local prof="$1" out
  out="$(timeout 15 ssh ltap-mini "schtasks /run /tn open-cs-$prof" 2>&1)"
  log "trigger open-cs-$prof: $out"
  echo "$out" | grep -qi "SUCCESS"
}

# wait_bootstrap_result <profil> <batas-detik> -> poll open-cs.log laptop
# (via powershell tail, UTF-16LE) cari baris "selesai (single-profile
# <profil>" TERBARU setelah fungsi ini dipanggil. Return 0 kalau ketemu
# baris exit=0 dlm batas waktu, 1 kalau timeout/gagal/exit!=0.
#
# CATATAN: ini cuma sinyal "laptop sudah SELESAI mencoba" (bukan jaminan
# sukses -- heuristik string-match di python suka bilang "TAK PASTI"
# padahal sukses). Ground-truth sebenarnya = reachable_cs di bawah.
wait_bootstrap_result() {
  local prof="$1" limit="$2" host="$3" deadline elapsed line
  deadline=$(( $(date +%s) + limit ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    line="$(timeout 12 ssh ltap-mini "powershell -NoProfile -Command \"Get-Content 'C:\\chrome-cdp\\open-cs.log' -Tail 5 -Encoding Unicode | Select-String 'selesai \\(single-profile'\"" 2>/dev/null | tail -1)"
    if echo "$line" | grep -q "single-profile $prof"; then
      log "laptop lapor selesai: $line"
      return 0
    fi
    sleep 8
  done
  log "TIMEOUT ${limit}s menunggu laptop selesai proses profil $prof (cek C:\\chrome-cdp\\open-cs.log manual)."
  # ⚠️ FALLBACK (ditambah 2026-08-24): polling di atas lewat SSH-ke-laptop,
  # yang TERBUKTI bisa false-negative -- laptop (CPU AMD E1-2500 lemah)
  # kadang sesaat tak responsif SSH pas render Chrome+terminal Cloud Shell,
  # PADAHAL bootstrap-nya sendiri sudah sukses & cepat (log lokal lapor
  # selesai <2mnt). Sebelum benar2 menyerah, cek LANGSUNG ke VM tujuan
  # (tak bergantung SSH-ke-laptop yg rawan macet itu) sbg jaring pengaman.
  log "$prof: fallback -- cek langsung ke VM tujuan (barangkali SSH-ke-laptop yg macet, bukan bootstrap-nya)..."
  if reachable_cs "$host"; then
    log "$prof: fallback BERHASIL -- VM tujuan sudah reachable meski polling log laptop gagal/timeout. Anggap selesai."
    return 0
  fi
  log "$prof: fallback juga gagal -- VM tujuan belum reachable. Bootstrap kemungkinan benar2 gagal."
  return 1
}

# wait_wg_reachable <user@ip> <batas-detik> -> poll SSH langsung (bukan cuma
# ping WG) sampai node beneran bisa di-SSH, atau timeout.
wait_wg_reachable() {
  local host="$1" limit="$2" deadline
  deadline=$(( $(date +%s) + limit ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    reachable_cs "$host" && return 0
    sleep 10
  done
  return 1
}

# process_profile <nama> <host-ssh> <fungsi-deploy> <batas-bootstrap> <batas-reachable>
# Return 0 = profil ini TUNTAS SEHAT.
#        1 = SOFT-FAIL (gagal di tahap reachable/deploy -- laptop SUDAH
#            beres bagiannya; pemanggil aman lanjut ke profil berikutnya).
#        2 = HARD-FAIL (gagal di tahap trigger/bootstrap -- laptop sendiri
#            lagi bermasalah; pemanggil WAJIB berhenti total).
process_profile() {
  local name="$1" host="$2" deploy_fn="$3" bs_limit="$4" reach_limit="$5"

  log "=== PROFIL $name: mulai ==="

  if ! open_cs_profile "$name"; then
    log "!!! $name GAGAL (hard): trigger task open-cs-$name tak sukses."
    return 2
  fi

  if ! wait_bootstrap_result "$name" "$bs_limit" "$host"; then
    log "!!! $name GAGAL (hard): laptop tak kunjung selesai proses bootstrap."
    return 2
  fi

  log "$name: cek reachability node (maks ${reach_limit}s, sshd VM butuh sesaat pasca-bootstrap)..."
  if ! wait_wg_reachable "$host" "$reach_limit"; then
    log "!!! $name GAGAL (soft, laptop sudah beres): node tak reachable via SSH dlm ${reach_limit}s pasca-bootstrap (WG/sshd VM belum siap)."
    return 1
  fi
  log "$name: node reachable. Lanjut deploy (menunggu SEHAT PENUH, bisa beberapa menit)..."

  local deploy_out deploy_rc
  deploy_out="$("$deploy_fn" 2>&1)"; deploy_rc=$?
  echo "$deploy_out" | sed "s/^/[wake-orch:$name] /" | tee -a "$LOG" >/dev/null

  if [ "$deploy_rc" -ne 0 ]; then
    log "!!! $name GAGAL (soft, laptop sudah beres): deploy tak sehat (lihat detail di atas)."
    return 1
  fi

  log "=== PROFIL $name: TUNTAS SEHAT ==="
  return 0
}

# ---------------------------------------------------------------------
# ALUR UTAMA — sequential, berhenti total HANYA kalau hard-fail (lihat
# kebijakan di header file). Batas waktu per tahap: bootstrap generous
# (laptop lemah + Cloud Shell VM cold-start bisa 3-4mnt), reachable
# pendek (begitu WG up biasanya sshd VM langsung siap), deploy TANPA
# batas eksternal tambahan di sini (fungsi deploy_* sendiri sudah punya
# batas internal -- analyzer V2 bisa ~15mnt kalau image belum ada,
# browser ~6mnt, n8n ~90dtk).
#
# finish() SELALU dipanggil sebelum exit (jalur sukses PENUH, soft-fail,
# maupun hard-fail-abort) -- satu baris "=== RINGKASAN AKHIR" jadi
# SATU-SATUNYA anchor yg dibaca check-wake-pipeline.sh, supaya laporan
# Telegram tak perlu nebak-nebak dari pola baris "!!! X GAGAL" yg kini
# bisa muncul lebih dari sekali per run (beda dari desain lama).
# ---------------------------------------------------------------------
STATUS_YUNI="BELUM DICOBA"; STATUS_BALI="BELUM DICOBA"; STATUS_GOGO="BELUM DICOBA"

finish() {
  log "=== RINGKASAN AKHIR: yuni=$STATUS_YUNI, balibruntattour=$STATUS_BALI, gogobuda=$STATUS_GOGO ==="
  if [ "$STATUS_YUNI" = "OK" ] && [ "$STATUS_BALI" = "OK" ] && [ "$STATUS_GOGO" = "OK" ]; then
    notify "✅ wake-orchestrator SUKSES PENUH: yuni+balibruntattour+gogobuda semua sehat & jalan."
    exit 0
  fi
  notify "⚠️ wake-orchestrator SELESAI (tak semua sehat) -- yuni=$STATUS_YUNI, balibruntattour=$STATUS_BALI, gogobuda=$STATUS_GOGO. Detail: ~/wake-orchestrator.log (hub)."
  exit 1
}

process_profile "yuni" "warungbudina@10.66.66.50" deploy_yuni 240 60
rc=$?
if [ "$rc" -eq 0 ]; then
  STATUS_YUNI="OK"
elif [ "$rc" -eq 2 ]; then
  STATUS_YUNI="GAGAL (hard, bootstrap laptop)"
  log "BERHENTI TOTAL -- yuni hard-fail (bootstrap laptop bermasalah), balibruntattour & gogobuda TIDAK dicoba."
  finish
else
  STATUS_YUNI="GAGAL (soft, pasca-bootstrap)"
  log "yuni soft-fail (laptop sudah beres bagiannya) -- LANJUT ke balibruntattour."
fi

process_profile "balibruntattour" "balibruntattour@10.66.66.60" deploy_balibruntattour 240 60
rc=$?
if [ "$rc" -eq 0 ]; then
  STATUS_BALI="OK"
elif [ "$rc" -eq 2 ]; then
  STATUS_BALI="GAGAL (hard, bootstrap laptop)"
  log "BERHENTI TOTAL -- balibruntattour hard-fail (bootstrap laptop bermasalah), gogobuda TIDAK dicoba."
  finish
else
  STATUS_BALI="GAGAL (soft, pasca-bootstrap)"
  log "balibruntattour soft-fail (laptop sudah beres bagiannya) -- LANJUT ke gogobuda."
fi

process_profile "gogobuda" "gogobuda65@10.66.66.61" deploy_gogobuda 240 60
rc=$?
if [ "$rc" -eq 0 ]; then
  STATUS_GOGO="OK"
elif [ "$rc" -eq 2 ]; then
  STATUS_GOGO="GAGAL (hard, bootstrap laptop)"
else
  STATUS_GOGO="GAGAL (soft, pasca-bootstrap)"
fi
log "gogobuda ini profil TERAKHIR -- tak ada lagi yg menyusul."

finish
