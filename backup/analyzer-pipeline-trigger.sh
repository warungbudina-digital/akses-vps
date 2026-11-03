#!/usr/bin/env bash
# =====================================================================
# analyzer-pipeline-trigger.sh — FALLBACK poller pipeline viral_analyzer.
# Dijalankan dari HUB (akses-vps) via cron tiap 10mnt.
#
# (2026-11-03, permintaan user — AUDIT+PEMISAHAN PERMANEN) Gerbang lama
# "SEMUA 3 profil Cloud Shell (.50/.60/.61) harus reachable dulu" DIBUANG.
# Akar masalah nyata: job yg masuk antrean bisa menunggu BERPULUH MENIT
# tanpa dianalisa walau `.50` (satu-satunya node yg benar2 dipakai
# orchestrator.py) sudah sehat, HANYA karena `.60`/`.61` (browser automation
# & GUI n8n -- TAK ADA hubungannya dgn analisa video) kebetulan sedang down.
# Gerbang itu dulu "murni preferensi user" (sinyal kasar "node hari ini
# hidup semua"), BUKAN keharusan teknis -- sekarang dicabut permanen.
#
# PEMICU UTAMA kini bukan di sini lagi: `enqueue.py`/`dashboard_api.py`
# (titik masuk antrean) langsung memicu `run-drain.sh` SENDIRI (fire-and-
# forget, background) begitu 1 job baru berhasil di-INSERT -- lihat kedua
# file itu. Skrip INI cuma JARING PENGAMAN kalau pemicu langsung itu gagal/
# terlewat (proses crash sebelum memicu, race, dll) -- jadi cuma perlu
# panggil run-drain.sh langsung, TANPA gerbang apa pun. run-drain.sh SENDIRI
# sudah no-op diam aman (cek pending + .50 reachable) -- gerbang di sini
# betul-betul tak dibutuhkan lagi, bukan cuma "lapisan tambahan".
# =====================================================================
set -uo pipefail

LOG="$HOME/analyzer-pipeline-trigger.log"
log(){ echo "[analyzer-trigger $(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }

# cap log
[ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 500 ] && tail -n 200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

log "jaring-pengaman 10mnt -> panggil run-drain.sh (no-op diam kalau antrean kosong/.50 mati)."
bash "$HOME/viral-pipeline/run-drain.sh"
