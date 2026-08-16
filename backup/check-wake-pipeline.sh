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

if echo "$BLOCK" | grep -q "SEMUA 3 PROFIL TUNTAS SEHAT"; then
  MSG="✅ check-wake-pipeline (run ${RUN_TS:-?} UTC): SUKSES PENUH -- yuni+balibruntattour+gogobuda semua sehat."
  log "$MSG"
  "$TG" "$MSG" || log "WARN: kirim Telegram gagal."
  log "=== selesai ==="
  exit 0
fi

# Belum ada baris akhir (SEMUA TUNTAS / gagal jelas) -> deteksi berhenti di profil mana
STOPPED_AT="?"
if echo "$BLOCK" | grep -q "!!! gogobuda GAGAL"; then STOPPED_AT="gogobuda (profil ke-3, terakhir)"
elif echo "$BLOCK" | grep -q "!!! balibruntattour GAGAL"; then STOPPED_AT="balibruntattour (profil ke-2) -- gogobuda TAK dicoba"
elif echo "$BLOCK" | grep -q "!!! yuni GAGAL"; then STOPPED_AT="yuni (profil ke-1) -- balibruntattour & gogobuda TAK dicoba"
elif echo "$BLOCK" | grep -q "=== PROFIL"; then STOPPED_AT="masih berjalan saat log ini dibaca (belum ada baris akhir) -- run mungkin masih lama (build ML bisa 15mnt), atau macet"
fi

LAST_REASON="$(echo "$BLOCK" | grep "^\[wake-orch" | tail -3)"

MSG="⚠️ check-wake-pipeline (run ${RUN_TS:-?} UTC): BERHENTI/BELUM TUNTAS.
Berhenti di: $STOPPED_AT
3 baris terakhir log:
$LAST_REASON
Detail lengkap: $OUT (di akses-vps) / $WLOG"
log "$MSG"
"$TG" "$MSG" || log "WARN: kirim Telegram gagal."
log "=== selesai ==="
