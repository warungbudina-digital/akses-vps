#!/usr/bin/env bash
# tvctl.sh — kontrol TV Changhong "AI PONT" via ADB (jalankan DI Pi 4B; adb key Pi ter-otorisasi)
# Aksi: on | off | toggle | wol | voldown [N] | volup [N] | vol <0-100> | mute | status
# TV IP DHCP bergeser (.234/.220) → dicari otomatis lewat MAC. Keycode terbukti: POWER=26, VOL_DOWN=25.
# CATATAN PENTING: ADB hanya bisa membangunkan TV dari STANDBY (WiFi masih hidup). Kalau TV MATI PENUH
# (WiFi putus, ping gagal) → satu-satunya jalur jaringan = Wake-on-LAN (aksi `wol`/fallback di `on`),
# dan itu HANYA jalan kalau TV mendukung + "Wake on LAN/WLAN" DIAKTIFKAN di setelan TV.
set -uo pipefail

MAC="ac:ac:e2:52:1f:a7"                 # MAC TV (tetap walau IP berubah)
WOL_MAC="ACACE2521FA7"                  # MAC tanpa pemisah utk magic packet
BCAST="192.168.60.255"                  # broadcast LAN ruang-tamu
PORT=5555
CANDIDATES=(192.168.60.234 192.168.60.220 10.66.66.12)
ACTION="${1:-status}"; N="${2:-3}"

log(){ echo "[tvctl] $*" >&2; }

send_wol(){
  python3 - "$WOL_MAC" "$BCAST" <<'PY' 2>/dev/null && log "magic packet WoL terkirim ke $WOL_MAC via $BCAST" || log "gagal kirim WoL"
import socket,sys
mac,bcast=sys.argv[1],sys.argv[2]
pkt=bytes.fromhex('ff'*6 + mac*16)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
for _ in range(3): s.sendto(pkt,(bcast,9)); s.sendto(pkt,(bcast,7))
PY
}

# konfirmasi IP LAN benar milik TV (lawan lease DHCP yg bergeser ke perangkat lain saat entri neigh basi).
# WG tunnel (10.66.66.x) dikecualikan: beda L2, tak muncul di neigh dgn MAC TV.
mac_ok(){
  case "$1" in 10.66.66.*) return 0 ;; esac
  ip neigh show "$1" 2>/dev/null | grep -qi "$MAC"
}

find_ip(){
  # HANYA terima IP yg ping-nya hidup (hindari entri ARP basi saat TV mati → biar connect() lapor rc=10 → WoL).
  # entri by-MAC dari neigh sudah otoritatif; kandidat statis WAJIB dikonfirmasi MAC-nya setelah ping
  # (DHCP bergeser → .234/.220 bisa dipegang perangkat lain yg juga membalas ping).
  local c ipn
  ipn=$(ip neigh 2>/dev/null | awk -v m="$MAC" 'tolower($0) ~ tolower(m){print $1}')
  for c in $ipn; do
    [ -n "$c" ] || continue
    ping -c1 -W1 "$c" >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  for c in "${CANDIDATES[@]}"; do
    [ -n "$c" ] || continue
    ping -c1 -W1 "$c" >/dev/null 2>&1 || continue
    mac_ok "$c" && { echo "$c"; return 0; }
  done
  return 1
}

# konek+otorisasi; set TVIP global. return 0 kalau siap adb, non-0 kalau tidak.
connect(){
  TVIP=$(find_ip) || return 10        # 10 = TV tak di jaringan (mati penuh)
  adb connect "$TVIP:$PORT" >/dev/null 2>&1; sleep 1
  local st; st=$(adb devices | awk -v d="$TVIP:$PORT" '$1==d{print $2}')
  case "$st" in
    device) return 0 ;;
    unauthorized) log "ADB UNAUTHORIZED — approve popup 'Allow USB debugging' di layar TV."; return 11 ;;
    offline) adb disconnect "$TVIP:$PORT" >/dev/null 2>&1; return 13 ;;   # standby-dalam (remote-off): adbd tak responsif
    *) return 12 ;;
  esac
}

T(){ adb -s "$TVIP:$PORT" shell "$@"; }
key(){ T input keyevent "$1" >/dev/null 2>&1; }
rep(){ local k="$1" n="$2" i; for ((i=0;i<n;i++)); do key "$k"; done; }
# volume ASLI = STREAM_MUSIC dumpsys audio (0-100); `settings volume_music` PALSU/statis di TV MediaTek ini
vol_now(){ T dumpsys audio 2>/dev/null | grep -A6 -- "- STREAM_MUSIC:" | grep -m1 -o "streamVolume:[0-9]*" | grep -o "[0-9]*"; }
wake_now(){ T dumpsys power 2>/dev/null | grep -m1 -o "mWakefulness=[A-Za-z]*" | cut -d= -f2 | tr -d "\r"; }
# bangunkan HANYA bila state eksplisit tidur (Asleep/Dozing/Dreaming). kosong/tak dikenal → JANGAN kirim POWER
# (kalau tidak, saat dumpsys gagal-baca padahal TV Awake, keyevent 26 malah MEMATIKAN TV — kebalikan dari 'on').
wake_if_asleep(){ local w; w=$(wake_now); case "$w" in
    Asleep|Dozing|Dreaming) key 26; sleep 1 ;;
    Awake) : ;;
    *) log "wakefulness tak terbaca ('$w') — POWER TIDAK dikirim (hindari salah-mematikan TV)" ;;
  esac; }
vol_set(){ local target="$1" cur d; cur=$(vol_now); [ -z "${cur:-}" ] && { log "gagal baca volume"; return 1; }
  d=$((target-cur)); if [ "$d" -lt 0 ]; then rep 25 $((-d)); elif [ "$d" -gt 0 ]; then rep 24 "$d"; fi
  log "volume $cur → $(vol_now) (target $target)"; }

case "$ACTION" in
  wol) send_wol; exit 0 ;;

  on|wake)
    connect; rc=$?
    case "$rc" in
      0)  wake_if_asleep; log "TV ON → $(wake_now) (ip=$TVIP)" ;;
      11) log "TV ON tapi ADB unauthorized — approve popup di layar TV, lalu ulangi."; exit 3 ;;
      13) # standby-DALAM (dimatikan via REMOTE): jaringan hidup tapi adbd 'offline' & tak bisa di-wake via jaringan
          log "TV standby-DALAM (kemungkinan dimatikan via REMOTE): jaringan hidup tapi ADB 'offline'."
          send_wol
          for i in 1 2 3; do sleep 3; if connect; then wake_if_asleep; log "TV ON → $(wake_now)"; exit 0; fi; done
          log "GAGAL wake via jaringan (TV ini tak bisa dibangunkan dari standby-remote lewat ADB/WoL)."
          log "→ Nyalakan pakai REMOTE fisik. TIPS: agar 'on' via script BISA nanti, matikan pakai '~/bin/tv off' (BUKAN remote) — itu standby dangkal yg ADB-nya tetap hidup."
          exit 2 ;;
      10) log "TV mati-penuh (tak di jaringan) → coba Wake-on-LAN…"; send_wol
          for i in 1 2 3 4 5; do sleep 3; if connect; then wake_if_asleep; log "TV ON via WoL → $(wake_now)"; exit 0; fi; done
          log "TV tak merespons WoL → nyalakan pakai remote / aktifkan 'Wake on LAN' di setelan TV."; exit 2 ;;
      *)  log "ADB tak konek (state tak dikenal) di ${TVIP:-?}."; exit "$rc" ;;
    esac
    ;;

  off|sleep)
    connect || exit $?
    if [ "$(wake_now)" = "Awake" ]; then key 26; sleep 1; log "TV OFF/standby → $(wake_now)"; else log "TV sudah OFF ($(wake_now))"; fi
    ;;

  toggle|power)   connect || exit $?; key 26; sleep 1; log "power toggle → $(wake_now)" ;;
  voldown|down|vd) connect || exit $?; rep 25 "$N"; log "volume -$N (ip=$TVIP) → $(vol_now)/100" ;;
  volup|up|vu)     connect || exit $?; rep 24 "$N"; log "volume +$N (ip=$TVIP) → $(vol_now)/100" ;;
  vol|set)         [ -n "${2:-}" ] || { log "aksi '$ACTION' butuh target 0-100, mis: '~/bin/tv vol 30'"; exit 1; }
                   connect || exit $?; vol_set "$2" ;;
  mute|m)          connect || exit $?; key 164; log "toggle mute (ip=$TVIP)" ;;
  status|st)       connect || exit $?; echo "ip=$TVIP  wakefulness=$(wake_now)  volume=$(vol_now)/100" ;;
  *) log "aksi tak dikenal: '$ACTION'"; echo "pakai: on | off | toggle | wol | voldown [N] | volup [N] | vol <0-100> | mute | status" >&2; exit 1 ;;
esac
