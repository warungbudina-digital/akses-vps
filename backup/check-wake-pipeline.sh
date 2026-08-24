#!/usr/bin/env bash
# =====================================================================
# check-wake-pipeline.sh — cek hasil RUN TERAKHIR wake-orchestrator.sh
# (jalur utama pasca-wake laptop SUARAHATI, lihat docs/17-sop-laptop-
# cloudshell-wake-cycle.md) lalu kirim ringkasan ke Telegram.
#
# Dipakai utk pengecekan SATU KALI (cron day-specific "cek besok pagi")
# atau manual kapan saja. Schedule-agnostic -- baca log terakhir apa
# adanya, tak peduli jam berapa dipanggil.
#
# ⚠️ v2 (2026-08-16): ditulis ulang total. Versi lama baca open-cs.log
# pola all-3-profil + cs-auto-deploy.log (skema lama gogobuda clone-only)
# -- SUDAH TAK COCOK dgn wake-orchestrator.sh sekuensial yg baru. Sumber
# kebenaran sekarang = wake-orchestrator.log SAJA.
#
# Pemakaian: ./check-wake-pipeline.sh
# =====================================================================
set -uo pipefail

TG="$HOME/akses-vps/backup/send-telegram.sh"
OUT="$HOME/check-wake-pipeline.$(date -u +%Y%m%d-%H%M).log"
WLOG="$HOME/wake-orchestrator.log"

log(){ echo "$*" | tee -a "$OUT"; }

log "=== check-wake-pipeline $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

if [ ! -f "$WLOG" ]; then
  MSG="⚠️ check-wake-pipeline: $WLOG tak ditemukan sama sekali -- wake-orchestrator.sh belum pernah jalan?"
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  exit 0
fi

# Ambil BLOK run terakhir: dari baris "laptop terjangkau -> mulai" ATAU
# "laptop TAK terjangkau" yang PALING BAWAH, sampai akhir file.
LAST_START_LINE="$(grep -n "mulai alur bertahap\|TAK terjangkau -> batal" "$WLOG" | tail -1 | cut -d: -f1)"
if [ -z "$LAST_START_LINE" ]; then
  MSG="⚠️ check-wake-pipeline: $WLOG ada tapi tak ketemu baris mulai run manapun -- format log berubah? Cek manual."
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  exit 0
fi
BLOCK="$(tail -n +"$LAST_START_LINE" "$WLOG")"
log "--- blok run terakhir (dari baris $LAST_START_LINE) ---"
log "$BLOCK"

# Jam run terakhir (dari timestamp UTC di awal baris blok)
RUN_TS="$(echo "$BLOCK" | head -1 | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}Z' | head -1)"

if echo "$BLOCK" | grep -q "TAK terjangkau -> batal total"; then
  MSG="⚠️ check-wake-pipeline (run ${RUN_TS:-?} UTC): laptop TAK terjangkau -- wake gagal atau masih hibernasi.
Kalau ini jam kerja (08:30-12:35 / 13:00-22:45 WITA), cek fisik laptop / jadwal RTC-wake.
Detail: $OUT (di akses-vps)"
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  log "=== selesai ==="
  exit 0
fi

# v3 (2026-08-24): wake-orchestrator.sh tak lagi strict-sequential murni
# (soft-fail kini lanjut ke profil berikutnya, lihat wake-orchestrator.sh
# header) -- jadi bisa ada LEBIH dari satu "!!! X GAGAL" per run, dan pola
# lama (deteksi STOPPED_AT dari baris gagal terakhir) sudah tak akurat.
# Sumber kebenaran sekarang = baris "=== RINGKASAN AKHIR: ..." yg SELALU
# ditulis wake-orchestrator.sh di ujung tiap run (sukses penuh, soft-fail,
# ATAU hard-fail-abort) -- satu anchor tunggal, tak perlu nebak lagi.
RINGKASAN="$(echo "$BLOCK" | grep "=== RINGKASAN AKHIR:" | tail -1)"

if echo "$BLOCK" | grep -q "SEMUA 3 PROFIL TUNTAS SEHAT\|=== RINGKASAN AKHIR: yuni=OK, balibruntattour=OK, gogobuda=OK"; then
  MSG="✅ check-wake-pipeline (run ${RUN_TS:-?} UTC): SUKSES PENUH -- yuni+balibruntattour+gogobuda semua sehat."
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  log "=== selesai ==="
  exit 0
fi

if [ -n "$RINGKASAN" ]; then
  # Run TUNTAS (baik ada hard-fail-abort maupun soft-fail lanjut-terus)
  # tapi TAK semua sehat -- tampilkan ringkasan per-profil apa adanya.
  MSG="⚠️ check-wake-pipeline (run ${RUN_TS:-?} UTC): TUNTAS tapi TAK SEMUA SEHAT.
$RINGKASAN
3 baris terakhir log:
$(echo "$BLOCK" | grep "^\[wake-orch" | tail -3)
Detail lengkap: $OUT (di akses-vps) / $WLOG"
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  log "=== selesai ==="
  exit 0
fi

# Tak ada baris RINGKASAN AKHIR sama sekali -> run kemungkinan MASIH
# berjalan saat log ini dibaca (build ML bisa 15mnt+), atau macet total
# sebelum sempat tulis ringkasan (mis. skrip crash tak terduga).
STOPPED_AT="?"
if echo "$BLOCK" | grep -q "=== PROFIL"; then
  STOPPED_AT="masih berjalan saat log ini dibaca (belum ada baris ringkasan) -- run mungkin masih lama (build ML bisa 15mnt), atau macet total tak terduga"
fi

LAST_REASON="$(echo "$BLOCK" | grep "^\[wake-orch" | tail -3)"

MSG="⚠️ check-wake-pipeline (run ${RUN_TS:-?} UTC): BERHENTI/BELUM TUNTAS (tak ada baris ringkasan akhir).
Status: $STOPPED_AT
3 baris terakhir log:
$LAST_REASON
Detail lengkap: $OUT (di akses-vps) / $WLOG"
log "$MSG"
"$TG" "$MSG" || log "WARN: kirim Telegram gagal."
log "=== selesai ==="
