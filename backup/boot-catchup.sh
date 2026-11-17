#!/usr/bin/env bash
# boot-catchup.sh — dipanggil via @reboot crontab. Hub akses-vps kini
# dinyalakan/dimatikan on-demand oleh user (hemat biaya), BUKAN lagi 24/7.
# Akibatnya job cron harian/mingguan jam-tetap (social-trend, health-report,
# backup vault, dst) berisiko TERLEWAT TOTAL kalau jendela hidup hub tak
# menyentuh jam itu (kejadian nyata 2026-11-02: laporan tren mingguan hilang
# krn hub cuma hidup 13:22-15:12 UTC, tak menyentuh 3 jam cron 03:10/06:10/09:10).
#
# Fix: begitu hub boot, coba SEMUA job harian/mingguan sekali di sini.
# AMAN dipanggil berkali-kali/hari (hub bisa reboot >1x/hari) karena SETIAP
# script di bawah sudah "no-op anggun" / punya penanda last_ok_day sendiri
# (prinsip proyek ini, lihat docs/16-sop-node-terjadwal.md) -- re-run ekstra
# cuma bikin cek lebih sering, bukan kerja dobel yg merusak.
#
# Delay 90s: tunggu network/WG/docker benar2 siap pasca-boot sebelum
# menyentuh DB-VPS/.60/.61/Pi dll (hindari false-negatif "No route to host"
# krn routing belum pulih).
set -uo pipefail
sleep 90

LOG="$HOME/boot-catchup.log"
ts(){ date -u +%FT%TZ; }
run(){
  local label="$1"; shift
  echo "[$(ts)] -> $label" >>"$LOG"
  "$@" >>"$LOG" 2>&1
  echo "[$(ts)]    (exit=$?) $label selesai" >>"$LOG"
}

echo "[$(ts)] ===== boot-catchup MULAI =====" >>"$LOG"

run "social-trend (data+laporan mingguan Senin)" "$HOME/akses-vps/social-analytics/social-trend-cron.sh"
run "social-trend-healthcheck" env ST_ALERT=1 ST_BRIEF=1 "$HOME/akses-vps/social-analytics/social-trend-healthcheck.sh"
run "viral-scorecard" "$HOME/akses-vps/scraper-worker/scorecard-cron.sh"
run "vault-check (.61 sesi login)" "$HOME/akses-vps/vault/vault-check.sh" 7
run "browser-health-report (.60)" "$HOME/akses-vps/backup/browser-health-report.sh"
run "pi-health-report" "$HOME/akses-vps/backup/pi-health-report.sh"
run "analytics creator (dashboard)" "$HOME/analytics/run.sh"
run "pi-vault-backup" "$HOME/akses-vps/backup/pi-vault-backup.sh"
run "harvest-rn7-ai (chat ChatGPT/Claude)" python3 "$HOME/akses-vps/backup/harvest-rn7-ai.py" --max-new 25
run "ai-chatlog-db-backup" "$HOME/akses-vps/backup/ai-chatlog-db-backup.sh"
run "browser-db-backup (.60)" "$HOME/akses-vps/backup/browser-db-backup.sh"
run "browser-profile-backup (.60)" "$HOME/akses-vps/backup/browser-profile-backup.sh"

# Jaga ukuran log.
[ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ] && tail -n 1000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

echo "[$(ts)] ===== boot-catchup SELESAI =====" >>"$LOG"
