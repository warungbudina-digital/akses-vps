#!/usr/bin/env bash
# WIFI-gratis - hotspot internet OPEN (tanpa password) via wlan2, share internet
# dari uplink wlan0 (JANGAN disentuh, tetap dipakai WireGuard/SSH ke hub).
# Beda dari cctv-audit.sh: hotspot ini PAKAI NAT (klien dapat internet asli).
set -uo pipefail
export PATH=/usr/sbin:/sbin:/usr/bin:/bin
DIR=/opt/wifi-hotspot
AP_IF=wlan2
UP_IF=wlan0
AP_ADDR=10.20.50.1/24
HPID=/run/hotspot-hostapd.pid
DPID=/run/hotspot-dnsmasq.pid

need_root(){ [ "$(id -u)" = 0 ] || { echo "perlu root (sudo)"; exit 1; }; }

up(){
  need_root
  rfkill unblock wifi 2>/dev/null
  ip link set $AP_IF down 2>/dev/null
  ip addr flush dev $AP_IF 2>/dev/null
  ip addr add $AP_ADDR dev $AP_IF
  ip link set $AP_IF up
  hostapd -B -P $HPID $DIR/hostapd.conf && echo "hostapd UP ($AP_IF, SSID: WIFI-gratis, OPEN)"
  dnsmasq --conf-file=$DIR/dnsmasq-ap.conf --pid-file=$DPID && echo "dnsmasq UP (AP DHCP, 10.20.50.0/24)"
  sysctl -qw net.ipv4.ip_forward=1
  # NAT: keluarkan trafik klien hotspot lewat wlan0 (internet asli "ruang tamu")
  iptables -t nat -C POSTROUTING -o $UP_IF -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -o $UP_IF -j MASQUERADE
  iptables -C FORWARD -i $AP_IF -o $UP_IF -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i $AP_IF -o $UP_IF -j ACCEPT
  iptables -C FORWARD -i $UP_IF -o $AP_IF -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i $UP_IF -o $AP_IF -m state --state RELATED,ESTABLISHED -j ACCEPT
  echo "=== WIFI-gratis UP (internet via $UP_IF) ==="
}

down(){
  need_root
  [ -f $HPID ] && { kill "$(cat $HPID)" 2>/dev/null; rm -f $HPID; }
  [ -f $DPID ] && { kill "$(cat $DPID)" 2>/dev/null; rm -f $DPID; }
  iptables -t nat -D POSTROUTING -o $UP_IF -j MASQUERADE 2>/dev/null
  iptables -D FORWARD -i $AP_IF -o $UP_IF -j ACCEPT 2>/dev/null
  iptables -D FORWARD -i $UP_IF -o $AP_IF -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null
  ip addr flush dev $AP_IF 2>/dev/null
  ip link set $AP_IF down 2>/dev/null
  echo "=== WIFI-gratis DOWN (wlan0/wg0 tak tersentuh) ==="
}

status(){
  echo "== interface =="; ip -br addr show $AP_IF; ip -br addr show $UP_IF
  echo "== proses =="
  [ -f $HPID ] && echo "hostapd PID $(cat $HPID) $(kill -0 "$(cat $HPID)" 2>/dev/null && echo alive || echo DEAD)" || echo "hostapd: off"
  [ -f $DPID ] && echo "dnsmasq PID $(cat $DPID) $(kill -0 "$(cat $DPID)" 2>/dev/null && echo alive || echo DEAD)" || echo "dnsmasq: off"
  echo "== klien terhubung (DHCP leases) =="; cat /var/lib/misc/dnsmasq.leases 2>/dev/null || echo "(none)"
  echo "== forwarding =="; sysctl -n net.ipv4.ip_forward
  echo "== NAT rule =="; iptables -t nat -L POSTROUTING -n -v | grep MASQUERADE || echo "(tak ada)"
}

case "${1:-}" in
  up) up;; down) down;; status) status;;
  *) echo "usage: $0 {up|down|status}";;
esac
