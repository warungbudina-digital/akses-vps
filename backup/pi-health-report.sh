#!/usr/bin/env bash
# Laporan kesehatan + TERMAL Raspberry Pi 4B pentest (10.66.66.4).
#
# KONTEKS SOP (2026-08-07): Pi kini node TERJADWAL (bukan 24/7), dijadwalkan OFF
# oleh user karena HARDWARE KADANG ERROR AKIBAT PANAS. Karena itu:
#   - Pi OFF = KONDISI NORMAL -> no-op anggun (exit 0), BUKAN alarm.
#   - Saat Pi HIDUP, TERMAL adalah headline: throttled-flags (bukti under-voltage/
#     throttling PERNAH terjadi) + suhu + tegangan. Inilah sinyal "error karena panas".
#
# Sisi akses-vps sudah toleran Pi mati: Prometheus tak scrape Pi, pentest-grpc-server
# cuma penerima heartbeat pasif (tak ada alert heartbeat-basi). Jadi skrip ini murni
# alat PANTAU on-demand/terjadwal, bukan penambal alarm.
#
# Pi = disk PERSISTEN + service systemd enabled (wg-quick/docker/spiderfoot/ollama)
# -> bring-up ZERO-TOUCH saat power-on (beda dari Cloud Shell). Tak perlu skrip deploy.
#
# Akses: password (belum ada kunci ke Pi). Kredensial dari env atau
# ~/.config/pi-access/credentials.env (600) — TIDAK di-hardcode/di-repo.
#
# Exit: 0 sehat / Pi memang OFF · 1 Pi HIDUP tapi ada masalah (termal/service/disk).
set -uo pipefail

CRED="${PI_CRED_FILE:-$HOME/.config/pi-access/credentials.env}"
[ -f "$CRED" ] && { set -a; . "$CRED"; set +a; }
PI_HOST="${PI_HOST:-admin@10.66.66.4}"
PI_PASS="${PI_PASS:-}"
TEMP_WARN="${TEMP_WARN:-70}"       # °C, ambang peringatan suhu
DISK_WARN="${DISK_WARN:-90}"       # % pemakaian disk

PROBLEMS=0
say()  { echo "$*"; }
warn() { echo "  !! $*"; PROBLEMS=$((PROBLEMS + 1)); }
ok()   { echo "  ok  $*"; }

if [ -z "$PI_PASS" ]; then
  say "GAGAL: PI_PASS kosong — set env atau isi ${CRED} (PI_PASS=...)."
  exit 1
fi

pissh() {
  sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 -o BatchMode=no "$PI_HOST" "$@" 2>/dev/null
}

say "=== Laporan kesehatan + termal Pi 4B (10.66.66.4) — $(date -u '+%Y-%m-%d %H:%M UTC') ==="

# ── Preflight: Pi hidup? (mati = NORMAL untuk node terjadwal) ────────────────
if ! pissh true 2>/dev/null; then
  say "  -- Pi OFF / tak terjangkau via WireGuard. NORMAL untuk node terjadwal."
  say "     (Pi dijadwalkan mati untuk mencegah error termal. Nyalakan saat butuh"
  say "      pentest-agent / SpiderFoot / RAG vault Ollama.)"
  say "RINGKASAN: 0 masalah (Pi memang OFF)."
  exit 0
fi

# ── Kumpulkan semua metrik dalam SATU koneksi (Pi lambat, hemat round-trip) ──
# Remote script emit KEY=VALUE; di-parse di akses-vps. Robust: tiap nilai
# fallback 'unknown' kalau perintahnya gagal (mis. vcgencmd butuh grup video).
RAW=$(pissh 'bash -s' <<'REMOTE'
val() { "$@" 2>/dev/null || echo unknown; }
echo "TEMP=$(val vcgencmd measure_temp | sed 's/[^0-9.]//g')"
echo "THROTTLED=$(val vcgencmd get_throttled | sed 's/.*=//')"
echo "VOLT=$(val vcgencmd measure_volts core | sed 's/.*=//')"
echo "UPTIME=$(val cut -d. -f1 /proc/uptime)"
echo "LOAD=$(val cat /proc/loadavg | awk '{print $1}')"
echo "AGENT=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -q pentest-agent && echo up || echo down)"
echo "SPIDERFOOT=$(systemctl is-active spiderfoot 2>/dev/null || echo unknown)"
echo "OLLAMA=$(systemctl is-active ollama 2>/dev/null || echo unknown)"
echo "WG=$(systemctl is-active wg-quick@wg0 2>/dev/null || echo unknown)"
echo "DISK_ROOT=$(df / | awk 'NR==2{gsub(/%/,"",$5);print $5}')"
echo "DISK_DOCKER=$(df /var/lib/docker 2>/dev/null | awk 'NR==2{gsub(/%/,"",$5);print $5}')"
REMOTE
)

get() { echo "$RAW" | grep -m1 "^$1=" | cut -d= -f2-; }
TEMP=$(get TEMP);       THROTTLED=$(get THROTTLED); VOLT=$(get VOLT)
UP=$(get UPTIME);       LOAD=$(get LOAD)
AGENT=$(get AGENT);     SF=$(get SPIDERFOOT);       OL=$(get OLLAMA); WG=$(get WG)
DR=$(get DISK_ROOT);    DD=$(get DISK_DOCKER)

UP_H=$(( ${UP:-0} / 3600 )); UP_M=$(( (${UP:-0} % 3600) / 60 ))

# ── TERMAL (headline — alasan Pi dijadwalkan) ───────────────────────────────
say "[TERMAL] alasan Pi dijadwalkan OFF-berkala"
say "  suhu=${TEMP:-?}°C · tegangan-core=${VOLT:-?} · load=${LOAD:-?} · uptime=${UP_H}j${UP_M}m"
# get_throttled: bitfield. 0x0 = sehat. Bit 0-3 = SEDANG terjadi; bit 16-19 = PERNAH terjadi.
if [ -z "$THROTTLED" ] || [ "$THROTTLED" = "unknown" ]; then
  warn "throttled tak terbaca (vcgencmd gagal — admin mungkin bukan anggota grup 'video')."
elif [ "$THROTTLED" = "0x0" ]; then
  ok "throttled=0x0 — tak ada under-voltage / throttling termal (sehat)."
else
  T=$(( THROTTLED ))
  MSG=""
  (( T & 0x1 ))     && MSG="$MSG under-voltage-SEKARANG;"
  (( T & 0x4 ))     && MSG="$MSG throttling-SEKARANG;"
  (( T & 0x8 ))     && MSG="$MSG batas-suhu-lunak-SEKARANG;"
  (( T & 0x10000 )) && MSG="$MSG under-voltage-PERNAH;"
  (( T & 0x40000 )) && MSG="$MSG throttling-PERNAH;"
  (( T & 0x80000 )) && MSG="$MSG batas-suhu-lunak-PERNAH;"
  warn "throttled=${THROTTLED} →${MSG:- flag tak dikenal} (INI sinyal error-karena-panas)."
fi
# suhu ambang
if [ -n "$TEMP" ] && [ "$TEMP" != "unknown" ]; then
  TI=${TEMP%.*}
  [ "${TI:-0}" -ge "$TEMP_WARN" ] && warn "suhu ${TEMP}°C ≥ ${TEMP_WARN}°C — pertimbangkan hentikan beban berat / matikan Pi."
fi

# ── Service (auto-start systemd saat boot) ──────────────────────────────────
say "[SERVICE]"
[ "$WG" = "active" ]    && ok "wg-quick@wg0 aktif."            || warn "wg-quick@wg0 = ${WG:-?} (tunnel admin!)."
[ "$AGENT" = "up" ]     && ok "pentest-agent container jalan." || warn "pentest-agent = ${AGENT:-?} (heartbeat MQTT mati)."
[ "$SF" = "active" ]    && ok "spiderfoot aktif (10.66.66.4:5001)." || say "  -- spiderfoot=${SF:-?} (on-demand, wajar kalau inactive)."
[ "$OL" = "active" ]    && ok "ollama aktif (RAG vsearch siap)."     || say "  -- ollama=${OL:-?} (on-demand, wajar kalau inactive)."

# ── Disk ────────────────────────────────────────────────────────────────────
say "[DISK]"
if [ -n "$DR" ]; then
  [ "$DR" -ge "$DISK_WARN" ] && warn "/ (SD card) ${DR}% ≥ ${DISK_WARN}%." || ok "/ (SD card) ${DR}% terpakai."
fi
[ -n "$DD" ] && { [ "$DD" -ge "$DISK_WARN" ] && warn "/var/lib/docker (SanDisk) ${DD}%." || ok "/var/lib/docker (SanDisk) ${DD}% terpakai."; }

say
if [ "$PROBLEMS" -eq 0 ]; then
  say "RINGKASAN: SEHAT — Pi hidup, termal & service normal."
else
  say "RINGKASAN: ${PROBLEMS} masalah (lihat baris '!!'). Cek termal dulu — Pi rawan panas."
fi
exit $(( PROBLEMS > 0 ? 1 : 0 ))
