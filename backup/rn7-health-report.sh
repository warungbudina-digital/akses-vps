#!/usr/bin/env bash
# Laporan kesehatan RN7 (Redmi Note 7, node VN otomasi 24/7 — WG peer 10.66.66.6).
#
# KONTEKS (2026-08-14): RN7 = node 24/7 (BEDA dari Pi yang terjadwal) → tak
# terjangkau = MASALAH, bukan normal. Temuan akar instabilitas: tunnel RN7 SUDAH
# lewat WiFi "Kantor" (bukan seluler); drop berulang wireless-debugging = DAYA —
# saat HP tak tercolok → Doze → WiFi power-save → tunnel+adbd putus. Karena itu
# HEADLINE skrip ini = STATUS CHARGING. Detail: [[project_redmi_vn_node]] + repo
# tool-appium docs/vn-automation-map.md §27g/§27j-F.
#
# Tiga lapisan yang dicek (dari sisi akses-vps):
#   1) TUNNEL  — ping 10.66.66.6 + umur handshake WireGuard (sisi server, sudo wg).
#   2) ADB     — wireless-debugging (port acak 30000-45000, connect-scan) + adb echo.
#                adb mati tapi tunnel hidup = wireless-debug drop (butuh toggle fisik).
#   3) DEVICE  — HANYA jika adb hidup: charging/baterai (HEADLINE), stayon/layar,
#                WiFi SSID+RSSI, keberadaan app VN.
#
# Akses adb via container tool-appium (adb-over-tunnel). wg handshake butuh
# `sudo wg` (passwordless OK). nmap pakai connect-scan (-sT, tanpa root).
#
# Exit: 0 sehat · 1 ada masalah (tunnel/adb/daya).
set -uo pipefail

PEER="${RN7_PEER:-rE+lI8Num}"            # prefiks pubkey peer RN7 (unik)
RN7_IP="${RN7_IP:-10.66.66.6}"
ADB_CTR="${ADB_CTR:-tool-appium-appium-1}"
PORT_LO="${PORT_LO:-30000}"; PORT_HI="${PORT_HI:-45000}"
HS_WARN="${HS_WARN:-300}"                # detik; handshake > ini = tunnel diragukan
BATT_LOW="${BATT_LOW:-30}"              # % baterai rendah (peringatan meski charging)

# RN7_BRIEF=1 → saat SEHAT cetak 1 baris saja (untuk cron/log ringkas); saat ADA
# MASALAH selalu cetak laporan penuh. Output di-buffer lalu di-flush di akhir.
BRIEF="${RN7_BRIEF:-0}"
PROBLEMS=0
BUF=""
say()  { BUF="${BUF}$*"$'\n'; }
warn() { BUF="${BUF}  !! $*"$'\n'; PROBLEMS=$((PROBLEMS + 1)); }
ok()   { BUF="${BUF}  ok  $*"$'\n'; }
flush() {
  if [ "$BRIEF" = "1" ] && [ "$PROBLEMS" -eq 0 ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M UTC') RN7 SEHAT — tunnel+adb+charger OK."
  else
    printf '%s' "$BUF"
  fi
}

adbsh() { docker exec "$ADB_CTR" sh -c "adb -s ${RN7_IP}:${PORT} shell '$1'" 2>/dev/null; }

say "=== Laporan kesehatan RN7 (node VN 24/7, ${RN7_IP}) — $(date -u '+%Y-%m-%d %H:%M UTC') ==="

# ── Lapisan 1: TUNNEL ────────────────────────────────────────────────────────
say "[TUNNEL] WireGuard"
if ping -c1 -W2 "$RN7_IP" >/dev/null 2>&1; then ok "ping ${RN7_IP} OK."; PING=1
else warn "ping ${RN7_IP} GAGAL — tunnel/HP tak terjangkau."; PING=0; fi

HS=$(sudo wg show wg0 latest-handshakes 2>/dev/null | grep -m1 "$PEER" | awk '{print $2}')
if [ -n "$HS" ] && [ "$HS" -gt 0 ] 2>/dev/null; then
  AGE=$(( $(date +%s) - HS ))
  if [ "$AGE" -le "$HS_WARN" ]; then ok "handshake ${AGE}s lalu (segar)."
  else warn "handshake ${AGE}s lalu (> ${HS_WARN}s) — tunnel kemungkinan drop / HP tidur."; fi
else
  warn "handshake peer RN7 (${PEER}*) tak ditemukan di wg0 — peer belum pernah/telat handshake."
fi

# Kalau tunnel benar-benar mati, hentikan di sini (lapisan 2-3 mustahil).
if [ "$PING" -eq 0 ]; then
  say; say "RINGKASAN: ${PROBLEMS} masalah — TUNNEL DOWN. Cek: HP hidup+tercolok? WiFi Kantor up? WG app aktif?"
  flush; exit 1
fi

# ── Lapisan 2: ADB / wireless-debugging ──────────────────────────────────────
say "[ADB] wireless-debugging (adb-over-tunnel)"
PORT=$(nmap -sT -Pn -p"${PORT_LO}-${PORT_HI}" --open "$RN7_IP" 2>/dev/null | grep -oE '^[0-9]+' | head -1)
ADB_OK=0
if [ -n "$PORT" ]; then
  docker exec "$ADB_CTR" sh -c "adb connect ${RN7_IP}:${PORT}" >/dev/null 2>&1
  if [ "$(adbsh 'echo ok' | tr -d '\r')" = "ok" ]; then ok "adb tersambung di :${PORT}."; ADB_OK=1
  else warn "port :${PORT} terbuka tapi adb echo gagal (adbd sibuk/unauthorized)."; fi
else
  warn "tak ada port adb di ${PORT_LO}-${PORT_HI} — Wireless debugging OFF (butuh toggle FISIK di HP; crDroid tak persisten). Tunnel tetap hidup."
fi

# ── Lapisan 3: DEVICE (hanya jika adb hidup) ─────────────────────────────────
if [ "$ADB_OK" -eq 1 ]; then
  # Tarik output mentah, parse di sisi akses-vps (hindari substitusi bersarang
  # yang rusak lewat lapisan docker→adb→shell).
  BATT=$(adbsh 'dumpsys battery')
  POW=$(adbsh 'dumpsys power')
  WIFI=$(adbsh 'dumpsys wifi | grep -m1 mWifiInfo')
  VNPKG=$(adbsh 'pm list packages com.frontrow.vlog')

  AC=$(echo "$BATT"     | grep -m1 'AC powered'  | grep -oE 'true|false')
  LVL=$(echo "$BATT"    | grep -m1 '  level'     | grep -oE '[0-9]+')
  BST=$(echo "$BATT"    | grep -m1 '  status'    | grep -oE '[0-9]+$')
  STAYON=$(echo "$POW"  | grep -m1 'mStayOn='    | grep -oE 'true|false')
  WAKE=$(echo "$POW"    | grep -m1 'mWakefulness=' | sed -E 's/.*mWakefulness=([A-Za-z]+).*/\1/')
  SSID=$(echo "$WIFI"   | grep -oE 'SSID: "[^"]*"' | head -1 | sed -E 's/SSID: "([^"]*)"/\1/')
  RSSI=$(echo "$WIFI"   | grep -oE 'RSSI: -?[0-9]+' | grep -oE '\-?[0-9]+')
  VN=$(echo "$VNPKG"    | grep -c 'com.frontrow.vlog')

  say "[DAYA] HEADLINE — akar stabilitas node"
  case "$AC" in
    true)  ok "AC charging (tercolok). Doze tak aktif → WiFi stabil." ;;
    false) warn "TAK tercolok charger (status=${BST:-?}) — akan Doze → WiFi power-save → tunnel/adb DROP. COLOK CHARGER." ;;
    *)     warn "status charging tak terbaca (AC=${AC:-?})." ;;
  esac
  if [ -n "$LVL" ]; then
    [ "$LVL" -lt "$BATT_LOW" ] && warn "baterai ${LVL}% (< ${BATT_LOW}%) — rawan (baterai RN7 sekarat)." || ok "baterai ${LVL}%."
  fi

  say "[KEEP-AWAKE]"
  [ "$STAYON" = "true" ] && ok "mStayOn=true (layar nyala saat plugged)." || warn "mStayOn=${STAYON:-?} — layar bisa mati → Doze (cek stay_on_while_plugged_in & charger)."
  [ "$WAKE" = "Awake" ]  && ok "layar Awake." || say "  -- wakefulness=${WAKE:-?} (Asleep/Dozing = sumber drop kalau menetap)."

  say "[WIFI]"
  if [ -n "$SSID" ]; then
    if [ -n "$RSSI" ]; then
      [ "$RSSI" -le -75 ] && warn "WiFi \"${SSID}\" RSSI ${RSSI}dBm (lemah)." || ok "WiFi \"${SSID}\" RSSI ${RSSI}dBm (kuat)."
    else ok "WiFi \"${SSID}\" tersambung (RSSI tak terbaca)."; fi
  else warn "SSID WiFi tak terbaca — mungkin lepas dari WiFi (jalur WG bisa lari ke seluler)."; fi

  say "[APP]"
  [ "${VN:-0}" -ge 1 ] && ok "VN (com.frontrow.vlog) terpasang." || warn "VN TIDAK terpasang (node kehilangan tujuan)."
fi

say
if [ "$PROBLEMS" -eq 0 ]; then
  say "RINGKASAN: SEHAT — tunnel+adb hidup, RN7 tercolok & stabil."
else
  say "RINGKASAN: ${PROBLEMS} masalah (lihat '!!'). Cek DAYA dulu — drop RN7 hampir selalu soal charger/Doze."
fi
flush
exit $(( PROBLEMS > 0 ? 1 : 0 ))
