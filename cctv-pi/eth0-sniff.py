#!/usr/bin/env python3
"""Passive L2 sniffer on eth0: identify connected device IP/subnet from ARP + IPv4 broadcast.
No IP is assigned to our side. Root required (AF_PACKET raw)."""
import socket, struct, sys, time
from collections import defaultdict

IFACE = sys.argv[1] if len(sys.argv) > 1 else "eth0"
DUR = int(sys.argv[2]) if len(sys.argv) > 2 else 20

def mac(b): return ":".join("%02x" % x for x in b)
def ip(b): return ".".join(str(x) for x in b)

s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
s.bind((IFACE, 0))
s.settimeout(1.0)

hosts = defaultdict(lambda: {"macs": set(), "proto": set(), "count": 0})
end = time.time() + DUR
print(f"# sniffing {IFACE} for {DUR}s ...", flush=True)
while time.time() < end:
    try:
        raw, _ = s.recvfrom(65535)
    except socket.timeout:
        continue
    if len(raw) < 14:
        continue
    eth_dst, eth_src, etype = raw[0:6], raw[6:12], struct.unpack("!H", raw[12:14])[0]
    p = raw[14:]
    if etype == 0x0806 and len(p) >= 28:  # ARP
        sha = p[8:14]; spa = p[14:18]; tpa = p[24:28]
        src = ip(spa)
        if src != "0.0.0.0":
            h = hosts[src]; h["macs"].add(mac(sha)); h["proto"].add("ARP"); h["count"] += 1
        # also record ARP target subnet hint
    elif etype == 0x0800 and len(p) >= 20:  # IPv4
        src = ip(p[12:16]); dst = ip(p[16:20])
        proto = p[9]
        pname = {1:"ICMP",6:"TCP",17:"UDP",2:"IGMP"}.get(proto, str(proto))
        if src != "0.0.0.0":
            h = hosts[src]; h["macs"].add(mac(eth_src)); h["proto"].add(pname); h["count"] += 1
        # note multicast/broadcast dsts to infer discovery
s.close()
print(f"# {len(hosts)} source IP(s) seen", flush=True)
for k, v in sorted(hosts.items()):
    print(f"{k:16} macs={','.join(v['macs'])} proto={','.join(sorted(v['proto']))} pkts={v['count']}")
