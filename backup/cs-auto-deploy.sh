#!/usr/bin/env bash
# =====================================================================
# cs-auto-deploy.sh — cron poller (HUB akses-vps): JARING PENGAMAN yang
# jalan tiap 5 menit sepanjang hari. Kalau profil Cloud Shell laptop
# (yuni/.50, balibruntattour/.60, gogobuda/.61, ogis/.8) reachable tapi projectnya
# belum/tak lagi sehat (mis. VM Cloud Shell di-refresh manual siang hari,
# atau container sempat mati), skrip ini idempoten membangunkannya lagi.
#
# ⚠️ Jalur UTAMA pasca-wake pagi sekarang = wake-orchestrator.sh (alur
# bertahap satu-per-satu dgn gerbang tunggu-sehat, lihat file itu). Skrip
# INI cuma pelengkap/fallback -- logika deploy-nya di-share lewat
# lib-cs-deploy.sh supaya TIDAK dobel-tulis dgn wake-orchestrator.sh.
#
# flock cegah tumpang-tindih antar-tick cron (build/clone bisa makan menit).
# =====================================================================
set -uo pipefail

LOCK="$HOME/.cs-auto-deploy.lock"
LOG="$HOME/cs-auto-deploy.log"

exec 200>"$LOCK"
flock -n 200 || { echo "[cs-auto-deploy $(date -u +%H:%M:%S)Z] sudah berjalan (lock) - skip." >> "$LOG"; exit 0; }

# shellcheck disable=SC1091
. "$HOME/akses-vps/backup/lib-cs-deploy.sh"

log(){ echo "[cs-auto-deploy $(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }

# cap log (jaga ringan)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 800 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Jalankan 1 fungsi deploy, log SEMUA outputnya apa adanya (fungsi sendiri
# yg menentukan pesan sukses/gagal lewat teksnya) -- exit code dipakai
# cuma internal (tak perlu dibedakan di sini, sudah kebaca dari teks).
run_and_log() { "$1" 2>&1 | sed 's/^/[cs-auto-deploy] /' | tee -a "$LOG" >/dev/null; }

run_and_log deploy_yuni
run_and_log deploy_balibruntattour
run_and_log deploy_gogobuda
# ⏸️ 2026-08-31 (permintaan user): ogis dinonaktifkan dari pipeline (bukan
# dihapus). Lihat catatan lengkap di wake-orchestrator.sh. Aktifkan lagi:
# hapus tanda komentar baris di bawah.
# run_and_log deploy_ogis

log "cs-auto-deploy selesai."
