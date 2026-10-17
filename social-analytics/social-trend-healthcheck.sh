#!/usr/bin/env bash
# Laporan kesehatan pipeline riset tren (Instagram+YouTube, hub akses-vps).
#
# KONTEKS (2026-10-17): dibuat krn gap operasional yang ketemu saat audit
# TikTok-removal -- bug 48-hari lama TERBUKTI hanya ketahuan krn AI diminta
# mengaudit manual, bukan via alert otomatis. Gap KEDUA yang lebih halus:
# `social-trend-cron.sh` pakai retry-dedup "1x sukses/hari cukup" dengan
# exit-code GLOBAL (gabung Instagram+YouTube) -- kalau SATU platform total
# gagal berhari-hari tapi platform LAIN masih punya >=1 akun ok, exit tetap 0,
# `last_ok_day` tetap ter-set, cron TAK PERNAH retry platform yang rusak itu,
# DAN tak ada alert. Skrip ini mengecek per-platform (bukan cuma "cron exit 0
# sekali hari ini"), supaya kelas kegagalan itu tak terulang senyap lagi.
#
# Dua lapisan dicek (teknis, utk pemeliharaan skrip ini ke depan):
#   1) FRESHNESS -- run_id snapshot TERBARU per platform (format
#                   YYYYMMDDTHHMMSSZ dari social_trend.py) di trend.social_
#                   post_snapshot (DB-VPS). Stale di salah satu platform saja
#                   sudah cukup utk WARN, biarpun platform lain sehat.
#   2) OK-RATIO  -- baris "ringkasan: X/Y ok" TERAKHIR di ~/social-trend.log.
#                   Menangkap persis skenario di atas: exit 0 tapi mayoritas
#                   akun gagal (ok-ratio rendah walau "sukses").
#
# ⚠️ 17/10: SEMUA teks yang tercetak/terkirim (bukan komentar ini) SENGAJA
# ditulis bahasa awam, nol istilah teknis (run_id/ok-ratio/stale/snapshot dsb
# tak pernah muncul di output) -- permintaan user, supaya log & pesan
# Telegram bisa dibaca orang yang tak paham teknologi.
#
# Alert Telegram HANYA saat status BERUBAH (normal<->bermasalah) -- anti-spam,
# pola identik rn7-health-report.sh. State: ~/.config/telegram-alert/
# social-trend.state. Kredensial: lihat send-telegram.sh (NO-OP anggun kalau
# belum dikonfigurasi, cron tak error).
#
# Pakai: social-trend-healthcheck.sh            # laporan penuh
#        ST_BRIEF=1 social-trend-healthcheck.sh # 1 baris kalau normal (cron)
#        ST_ALERT=1 social-trend-healthcheck.sh # + kirim Telegram saat berubah
# Exit: 0 normal / 1 ada masalah.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/social-trend.log"
STALE_H="${STALE_H:-30}"            # jam; lebih tua dari ini = dianggap macet
OK_RATIO_MIN="${OK_RATIO_MIN:-50}"  # %; keberhasilan di bawah ini = warn

BRIEF="${ST_BRIEF:-0}"
# date -u '+%B' ikut locale sistem (bisa keluar nama bulan Inggris) -- map
# manual ke Indonesia supaya konsisten dgn sisa teks (nol locale id_ID
# terpasang di host ini, lih. `locale -a`).
BULAN_ID=(- Januari Februari Maret April Mei Juni Juli Agustus September Oktober November Desember)
TGL="$(date -u '+%d') ${BULAN_ID[$((10#$(date -u '+%m')))]} $(date -u '+%Y, %H:%M UTC')"
PROBLEMS=0
GOOD=""; BAD=""
add_good() { GOOD="${GOOD}• $*"$'\n'; }
add_bad()  { BAD="${BAD}• $*"$'\n'; PROBLEMS=$((PROBLEMS + 1)); }

# ── Lapisan 1: data terbaru per platform ─────────────────────────────────────
ROWS=$(ssh -o BatchMode=yes -o ConnectTimeout=10 db-vps \
  "sudo -n -u postgres psql -d scraper -t -A -c \"SELECT platform, max(run_id) FROM trend.social_post_snapshot GROUP BY platform;\"" 2>/dev/null \
  | grep -E '^(instagram|youtube)\|')
if [ -z "$ROWS" ]; then
  add_bad "Tidak bisa memeriksa data Instagram/YouTube saat ini — kemungkinan server database sedang tidak bisa diakses."
else
  NOW_EPOCH=$(date -u +%s)
  for plat in instagram youtube; do
    case "$plat" in instagram) NAMA="Instagram";; youtube) NAMA="YouTube";; esac
    RID=$(printf '%s\n' "$ROWS" | awk -F'|' -v p="$plat" '$1==p{print $2}')
    if [ -z "$RID" ]; then
      add_bad "Data $NAMA belum pernah berhasil diambil sama sekali."
      continue
    fi
    RID_EPOCH=$(date -u -d "${RID:0:4}-${RID:4:2}-${RID:6:2}T${RID:9:2}:${RID:11:2}:${RID:13:2}Z" +%s 2>/dev/null || echo 0)
    if [ "$RID_EPOCH" -eq 0 ]; then
      add_bad "Catatan waktu terakhir pengambilan data $NAMA tidak bisa dibaca (perlu dicek teknisnya)."
      continue
    fi
    AGE_H=$(( (NOW_EPOCH - RID_EPOCH) / 3600 ))
    if [ "$AGE_H" -gt "$STALE_H" ]; then
      add_bad "Data $NAMA sudah ${AGE_H} jam tidak diperbarui (biasanya tiap hari) — kemungkinan pengambilan data $NAMA gagal berturut-turut."
    else
      add_good "Data $NAMA baru diperbarui ${AGE_H} jam lalu — normal."
    fi
  done
fi

# ── Lapisan 2: berapa akun yang berhasil pada pengambilan terakhir ───────────
LAST=$(grep 'ringkasan:' "$LOG" 2>/dev/null | tail -1)
if [ -z "$LAST" ]; then
  add_bad "Belum ada catatan pengambilan data sama sekali — pipeline mungkin belum pernah jalan."
else
  NUM=$(printf '%s' "$LAST" | grep -oE '[0-9]+/[0-9]+ ok' | head -1)
  N_OK=${NUM%%/*}; N_TOT=${NUM#*/}; N_TOT=${N_TOT%% ok}
  if [ -n "${N_OK:-}" ] && [ -n "${N_TOT:-}" ] && [ "$N_TOT" -gt 0 ] 2>/dev/null; then
    PCT=$(( N_OK * 100 / N_TOT ))
    if [ "$PCT" -lt "$OK_RATIO_MIN" ]; then
      add_bad "Pengambilan data terakhir cuma berhasil untuk ${N_OK} dari ${N_TOT} akun (${PCT}%) — ada akun yang gagal diambil datanya."
    else
      add_good "Pengambilan data terakhir berhasil untuk ${N_OK} dari ${N_TOT} akun (${PCT}%)."
    fi
  else
    add_bad "Catatan hasil pengambilan data terakhir tidak bisa dibaca (perlu dicek teknisnya)."
  fi
fi

if [ "$PROBLEMS" -eq 0 ]; then
  JUDUL="✅ SEMUA BAIK-BAIK SAJA"
  ISI="$GOOD"
  SARAN="Tidak ada yang perlu dilakukan."
else
  JUDUL="⚠️ ADA YANG PERLU DIPERHATIKAN"
  ISI="${BAD}${GOOD}"
  SARAN="Saran: minta Claude memeriksa & membenarkan pengambilan data yang gagal."
fi
REPORT="📊 Status Pengambilan Data Instagram & YouTube — ${TGL}

${JUDUL}

${ISI%$'\n'}

${SARAN}"

# ── Alert Telegram, HANYA saat status berubah (anti-spam) ───────────────────
SENDTG="$HERE/../backup/send-telegram.sh"
STATE_FILE="${ST_STATE_FILE:-$HOME/.config/telegram-alert/social-trend.state}"
if [ "${ST_ALERT:-0}" = "1" ]; then
  NOW_STATE=$([ "$PROBLEMS" -eq 0 ] && echo OK || echo PROBLEM)
  PREV_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo INIT)
  if [ "$NOW_STATE" != "$PREV_STATE" ]; then
    mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null
    echo "$NOW_STATE" > "$STATE_FILE" 2>/dev/null
    if [ -x "$SENDTG" ]; then
      if [ "$NOW_STATE" = "PROBLEM" ]; then
        "$SENDTG" "⚠️ Pengambilan data Instagram/YouTube BERMASALAH — ${TGL}

${BAD%$'\n'}

Saran: minta Claude memeriksa & membenarkan ini." >/dev/null 2>&1
      else
        "$SENDTG" "✅ Pengambilan data Instagram/YouTube sudah normal kembali — ${TGL}." >/dev/null 2>&1
      fi
    fi
  fi
fi

# ── Cetak laporan ─────────────────────────────────────────────────────────
if [ "$BRIEF" = "1" ] && [ "$PROBLEMS" -eq 0 ]; then
  echo "${TGL} — ✅ Pengambilan data Instagram & YouTube: semua normal."
else
  printf '%s\n' "$REPORT"
fi
exit $(( PROBLEMS > 0 ? 1 : 0 ))
