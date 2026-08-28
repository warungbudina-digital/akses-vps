#!/usr/bin/env bash
# =====================================================================
# analyzer-pipeline-trigger.sh — pemicu terjadwal pipeline viral_analyzer
# (permintaan user 2026-08-28): "kalau semua Cloud Shell sudah aktif,
# jalankan pipeline analyzer". Dijalankan dari HUB (akses-vps) via cron.
#
# Gerbang: SEMUA 3 profil Cloud Shell (.50 yuni / .60 balibruntattour /
# .61 gogobuda) harus reachable dulu -- baru panggil run-drain.sh
# (pemicu on-demand orchestrator.py yg sudah ada, lihat
# ~/viral-pipeline/README.md "Belum ada: cron poster untuk run-drain").
#
# CATATAN TEKNIS: orchestrator.py SENDIRI cuma butuh .50 + DB-VPS (bukan
# .60/.61) utk menguras antrean -- gerbang "ketiganya aktif" di sini murni
# preferensi user (sinyal "node hari ini benar2 hidup semua"), bukan
# keharusan teknis pipeline. run-drain.sh SENDIRI sudah aman dipanggil
# kapan saja (no-op diam kalau antrean kosong / .50 belum aktif) --
# gerbang di sini cuma lapisan tambahan, bukan pengganti safety run-drain.
#
# Aman dipanggil berulang dari cron: no-op diam (exit 0, log 1 baris)
# kalau salah satu profil belum reachable ATAU antrean kosong.
# =====================================================================
set -uo pipefail

LOG="$HOME/analyzer-pipeline-trigger.log"
log(){ echo "[analyzer-trigger $(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }

# cap log
[ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 500 ] && tail -n 200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

# shellcheck disable=SC1091
. "$HOME/akses-vps/backup/lib-cs-deploy.sh"

PROFILES=(
  "yuni:warungbudina@10.66.66.50"
  "balibruntattour:balibruntattour@10.66.66.60"
  "gogobuda:gogobuda65@10.66.66.61"
)

not_ready=()
for spec in "${PROFILES[@]}"; do
  name="${spec%%:*}"; host="${spec#*:}"
  if ! reachable_cs "$host"; then
    not_ready+=("$name")
  fi
done

if [ "${#not_ready[@]}" -gt 0 ]; then
  log "belum semua Cloud Shell aktif (belum reachable: ${not_ready[*]}) -> lewati, tak sentuh pipeline."
  exit 0
fi

log "ketiga profil Cloud Shell reachable -> panggil run-drain.sh (no-op diam kalau antrean kosong)."
bash "$HOME/viral-pipeline/run-drain.sh"
