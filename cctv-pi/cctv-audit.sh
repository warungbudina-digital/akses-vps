#!/usr/bin/env bash
# CCTV-audit interface role manager - ON-DEMAND, non-persistent (tak auto-boot).
# Peran: wlan0=uplink+wg (JANGAN disentuh) | wlan2=AP | wlan1=monitor | eth0=LAN kamera
# Fase 2: discover/audit perangkat CCTV (ONVIF/RTSP + cek kredensial default).
set -uo pipefail
export PATH=/usr/sbin:/sbin:/usr/bin:/bin
DIR=/opt/cctv-audit
AP_IF=wlan2; MON_IF=wlan1; CAM_IF=eth0
AP_ADDR=10.20.30.1/24
CAM_ADDR=192.168.100.1/24
HPID=/run/cctv-hostapd.pid
DPID=/run/cctv-dnsmasq.pid
OUTDIR=/tmp

need_root(){ [ "$(id -u)" = 0 ] || { echo "perlu root (sudo)"; exit 1; }; }

up(){
  need_root
  rfkill unblock wifi 2>/dev/null
  # --- LAN kamera (eth0) : siap walau NO-CARRIER ---
  ip addr flush dev $CAM_IF 2>/dev/null
  ip addr add $CAM_ADDR dev $CAM_IF 2>/dev/null
  ip link set $CAM_IF up 2>/dev/null
  # --- Access Point (wlan2) ---
  ip link set $AP_IF down 2>/dev/null
  ip addr flush dev $AP_IF 2>/dev/null
  ip addr add $AP_ADDR dev $AP_IF
  ip link set $AP_IF up
  hostapd -B -P $HPID $DIR/hostapd.conf && echo "hostapd UP ($AP_IF)"
  dnsmasq --conf-file=$DIR/dnsmasq-ap.conf --pid-file=$DPID && echo "dnsmasq UP (AP DHCP)"
  # --- Monitor/capture (wlan1) ---
  ip link set $MON_IF down 2>/dev/null
  iw dev $MON_IF set type monitor 2>/dev/null && echo "$MON_IF -> monitor"
  ip link set $MON_IF up 2>/dev/null
  # --- forwarding (isolasi: TANPA NAT ke internet secara default) ---
  sysctl -qw net.ipv4.ip_forward=1
  echo "=== CCTV-audit UP ==="
}

down(){
  need_root
  [ -f $HPID ] && { kill "$(cat $HPID)" 2>/dev/null; rm -f $HPID; }
  [ -f $DPID ] && { kill "$(cat $DPID)" 2>/dev/null; rm -f $DPID; }
  ip addr flush dev $AP_IF 2>/dev/null; ip link set $AP_IF down 2>/dev/null
  ip link set $MON_IF down 2>/dev/null; iw dev $MON_IF set type managed 2>/dev/null; ip link set $MON_IF up 2>/dev/null
  ip addr flush dev $CAM_IF 2>/dev/null
  echo "=== CCTV-audit DOWN (wlan0/wg0 tak tersentuh) ==="
}

# cam-route <IP> {add|del}
# Rutekan satu kamera lewat eth0. Menangani kasus subnet kamera BENTROK dgn wlan0
# (mis. kamera Hikvision default 192.168.1.64 sedangkan wlan0 juga 192.168.1.0/24):
# pakai alamat /32 di eth0 + host-route /32 -> lebih spesifik dari route wlan0.
cam_route(){
  need_root
  local ip="${1:?usage: cam-route IP add|del}"; local op="${2:-add}"
  local net="${ip%.*}"; local src="$net.222"
  [ "$src" = "$ip" ] && src="$net.223"
  if [ "$op" = del ]; then
    ip route del "$ip/32" dev $CAM_IF 2>/dev/null
    ip addr del "$src/32" dev $CAM_IF 2>/dev/null
    echo "cam-route DEL $ip (via $CAM_IF) dibersihkan"
  else
    ip link set $CAM_IF up 2>/dev/null
    ip addr add "$src/32" dev $CAM_IF 2>/dev/null
    ip route replace "$ip/32" dev $CAM_IF src "$src"
    echo "cam-route ADD $ip via $CAM_IF (src $src)"
    ping -c2 -W2 "$ip" >/dev/null 2>&1 && echo "  ping OK" || echo "  ping GAGAL (cek kabel/link eth0)"
  fi
}

# discover <target-cidr-atau-ip> [iface]
discover(){
  need_root
  local tgt="${1:?usage: discover <cidr|ip> [iface]}"; local ifc="${2:-$CAM_IF}"
  python3 $DIR/cctv-discover.py --scan "$tgt" --onvif --ssdp --iface "$ifc" -o "$OUTDIR/cctv-disc.json"
}

# audit <IP> [max-tries] -- rute (jika perlu) + discover + cek kredensial default
audit(){
  need_root
  local ip="${1:?usage: audit <IP> [max-tries]}"; local mt="${2:-4}"
  # auto host-route bila IP satu subnet dgn wlan0 (hindari salah-antarmuka)
  local w0; w0=$(ip -4 -o addr show wlan0 | grep -oE 'inet [0-9.]+' | awk '{print $2}')
  if [ -n "$w0" ] && [ "${w0%.*}" = "${ip%.*}" ]; then
    echo "# IP $ip satu subnet dgn wlan0 ($w0) -> host-route via $CAM_IF"
    cam_route "$ip" add
  fi
  echo "=== DISCOVER $ip ==="
  python3 $DIR/cctv-discover.py --scan "$ip/32" --onvif --ssdp --iface "$CAM_IF" -o "$OUTDIR/cctv-disc.json"
  echo "=== CRED-CHECK $ip (default creds, max-tries=$mt) ==="
  python3 $DIR/cctv-credcheck.py --from-json "$OUTDIR/cctv-disc.json" --all --max-tries "$mt" --delay 1.0 -o "$OUTDIR/cctv-cred.json"
  echo "=== hasil: $OUTDIR/cctv-disc.json + $OUTDIR/cctv-cred.json ==="
}

status(){
  echo "== interface =="; ip -br addr show $CAM_IF; ip -br addr show $MON_IF; ip -br addr show $AP_IF; ip -br addr show wlan0
  echo "== proses =="
  [ -f $HPID ] && echo "hostapd PID $(cat $HPID) $(kill -0 "$(cat $HPID)" 2>/dev/null && echo alive || echo DEAD)" || echo "hostapd: off"
  [ -f $DPID ] && echo "dnsmasq PID $(cat $DPID) $(kill -0 "$(cat $DPID)" 2>/dev/null && echo alive || echo DEAD)" || echo "dnsmasq: off"
  echo "== wlan1 tipe =="; iw dev $MON_IF info 2>/dev/null | grep -E 'type|channel'
  echo "== klien AP (DHCP leases) =="; cat /var/lib/misc/dnsmasq.leases 2>/dev/null || echo "(none)"
  echo "== forwarding =="; sysctl -n net.ipv4.ip_forward
  echo "== cam-route eth0 =="; ip route show dev $CAM_IF 2>/dev/null | grep -E '/32' || echo "(tak ada host-route kamera)"
}

case "${1:-}" in
  up) up;; down) down;; status) status;;
  cam-route) shift; cam_route "$@";;
  discover) shift; discover "$@";;
  audit) shift; audit "$@";;
  *) echo "usage: $0 {up|down|status|cam-route <IP> {add|del}|discover <cidr|ip> [iface]|audit <IP> [max-tries]}";;
esac
