#!/usr/bin/env python3
"""
cctv-discover.py - Fase 2 discovery untuk lab audit CCTV (Pi 4B).
Menemukan perangkat DVR/NVR/IP-Cam di subnet audit:
  1. ONVIF WS-Discovery (multicast SOAP Probe 239.255.255.250:3702)
  2. Sweep port khas CCTV via nmap (RTSP/HTTP/SDK vendor)
Output JSON terstruktur (dipakai cctv-credcheck.py).

HANYA untuk jaringan milik/berwenang (lab kamera sendiri). Tidak melakukan
brute-force di sini - hanya identifikasi (non-destruktif).

Contoh:
  ./cctv-discover.py --onvif --ssdp --iface eth0
  ./cctv-discover.py --scan 192.168.100.0/24 --onvif --iface eth0 -o /tmp/cctv.json
"""
import argparse, json, socket, struct, subprocess, sys, time, uuid, re
import xml.etree.ElementTree as ET

# Port khas perangkat CCTV + tebakan vendor dari fingerprint port
CCTV_PORTS = {
    554:  "RTSP",
    322:  "RTSP-alt",
    80:   "HTTP-webui",
    81:   "HTTP-alt",
    8080: "HTTP-alt",
    8000: "Hikvision-SDK",
    8443: "HTTPS-alt",
    443:  "HTTPS",
    37777:"Dahua-DVRIP",
    37778:"Dahua-DVRIP-udp",
    34567:"XiongMai-DVRIP",   # NetSurveillance / XM (Sofia)
    8899: "XiongMai-alt",
    9000: "DVRIP-alt",
    5000: "ONVIF-alt",
    49152:"ONVIF-webservice",
    2020: "ONVIF-alt",
    88:   "Hik-alt",
}
VENDOR_HINT = {
    8000: "Hikvision", 37777: "Dahua", 37778: "Dahua",
    34567: "XiongMai/Sofia", 8899: "XiongMai/Sofia",
}

WSD_ADDR = "239.255.255.250"
WSD_PORT = 3702
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

def ws_discovery(iface=None, timeout=4):
    """Kirim ONVIF Probe multicast, kumpulkan ProbeMatch (XAddrs perangkat)."""
    msg_id = "urn:uuid:" + str(uuid.uuid4())
    probe = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
        ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
        ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        '<e:Header>'
        f'<w:MessageID>{msg_id}</w:MessageID>'
        '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>'
        '</e:Body></e:Envelope>'
    ).encode()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if iface:
        try:
            local = _iface_ip(iface)
            if local:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local))
        except OSError:
            pass
    s.settimeout(0.6)
    found = {}
    # kirim 2x (mitigasi drop UDP)
    for _ in range(2):
        try:
            s.sendto(probe, (WSD_ADDR, WSD_PORT))
        except OSError as e:
            print(f"# WS-Discovery send gagal: {e}", file=sys.stderr)
            break
        time.sleep(0.2)
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        ip = addr[0]
        info = found.setdefault(ip, {"xaddrs": set(), "types": "", "scopes": ""})
        try:
            xa, types, scopes = _parse_probematch(data)
            info["xaddrs"].update(xa)
            if types: info["types"] = types
            if scopes: info["scopes"] = scopes
        except Exception:
            pass
    s.close()
    out = {}
    for ip, v in found.items():
        out[ip] = {"xaddrs": sorted(v["xaddrs"]), "types": v["types"], "scopes": v["scopes"]}
    return out


def ssdp_discovery(iface=None, timeout=4):
    """M-SEARCH SSDP/UPnP (banyak DVR/NVR/IP-cam umumkan diri di sini).
    Kirim ke 239.255.255.250:1900, kumpulkan balasan unicast (SERVER/LOCATION/ST/USN)."""
    targets = ["ssdp:all", "upnp:rootdevice"]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if iface:
        try:
            local = _iface_ip(iface)
            if local:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local))
        except OSError:
            pass
    s.settimeout(0.6)
    found = {}
    for st in targets:
        msearch = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 2\r\n"
            f"ST: {st}\r\n\r\n"
        ).encode()
        for _ in range(2):
            try:
                s.sendto(msearch, (SSDP_ADDR, SSDP_PORT))
            except OSError as e:
                print(f"# SSDP send gagal: {e}", file=sys.stderr)
                break
            time.sleep(0.2)
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        ip = addr[0]
        hdrs = _parse_ssdp(data)
        if not hdrs:
            continue
        info = found.setdefault(ip, {"server": "", "location": set(), "st": set(), "usn": set()})
        if hdrs.get("server"):
            info["server"] = hdrs["server"]
        if hdrs.get("location"):
            info["location"].add(hdrs["location"])
        if hdrs.get("st"):
            info["st"].add(hdrs["st"])
        if hdrs.get("usn"):
            info["usn"].add(hdrs["usn"])
    s.close()
    out = {}
    for ip, v in found.items():
        out[ip] = {"server": v["server"], "location": sorted(v["location"]),
                   "st": sorted(v["st"]), "usn": sorted(v["usn"])}
    return out

def _parse_ssdp(data):
    txt = data.decode("utf-8", "replace")
    lines = txt.split("\r\n")
    if not lines or "200 OK" not in lines[0].upper():
        return None
    h = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower(); v = v.strip()
        if k in ("server", "location", "st", "usn"):
            h[k] = v
    return h

# Petunjuk vendor dari string SERVER/USN SSDP (huruf-kecil match)
SSDP_VENDOR_HINT = ("hikvision", "dahua", "xiongmai", "sofia", "reolink",
                    "dlink", "d-link", "tp-link", "tplink", "axis", "uniview",
                    "ipcamera", "ip camera", "nvr", "dvr", "webcam", "gsoap")

def _ssdp_vendor(server, usns):
    hay = (server + " " + " ".join(usns)).lower()
    return sorted({v for v in SSDP_VENDOR_HINT if v in hay})

def _parse_probematch(data):
    txt = data.decode("utf-8", "replace")
    ns = {"d": "http://schemas.xmlsoap.org/ws/2005/04/discovery"}
    root = ET.fromstring(txt)
    xaddrs, types, scopes = [], "", ""
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "XAddrs" and el.text:
            xaddrs.extend(el.text.split())
        elif tag == "Types" and el.text:
            types = el.text.strip()
        elif tag == "Scopes" and el.text:
            scopes = el.text.strip()
    return xaddrs, types, scopes

def _iface_ip(iface):
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", iface],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None

def nmap_scan(target, extra_ports=None, fast=True):
    """Sweep port CCTV via nmap -sS (butuh root) atau -sT. Return dict ip->[ports]."""
    ports = sorted(set(CCTV_PORTS) | set(extra_ports or []))
    pspec = ",".join(str(p) for p in ports)
    cmd = ["nmap", "-n", "-Pn", "--open", "-p", pspec, "-oX", "-", target]
    if fast:
        cmd[1:1] = ["-T4", "--max-retries", "1", "--host-timeout", "30s"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        print("# nmap tidak ada - lewati port scan", file=sys.stderr)
        return {}
    except subprocess.TimeoutExpired:
        print("# nmap timeout", file=sys.stderr)
        return {}
    hosts = {}
    try:
        root = ET.fromstring(res.stdout)
    except ET.ParseError:
        print("# nmap XML parse gagal", file=sys.stderr)
        return {}
    for host in root.findall("host"):
        st = host.find("status")
        addr_el = host.find("address[@addrtype='ipv4']")
        if addr_el is None:
            continue
        ip = addr_el.get("addr")
        openp = []
        for port in host.findall(".//port"):
            state = port.find("state")
            if state is not None and state.get("state") == "open":
                openp.append(int(port.get("portid")))
        if openp:
            hosts[ip] = sorted(openp)
    return hosts

def classify(ports):
    vendors = set()
    for p in ports:
        if p in VENDOR_HINT:
            vendors.add(VENDOR_HINT[p])
    svc = [f"{p}/{CCTV_PORTS.get(p, '?')}" for p in ports]
    return sorted(vendors), svc

def main():
    ap = argparse.ArgumentParser(description="Discovery perangkat CCTV (ONVIF + port sweep)")
    ap.add_argument("--onvif", action="store_true", help="jalankan ONVIF WS-Discovery")
    ap.add_argument("--ssdp", action="store_true", help="jalankan SSDP/UPnP M-SEARCH")
    ap.add_argument("--iface", help="interface untuk multicast (mis. eth0)")
    ap.add_argument("--scan", metavar="CIDR", help="subnet untuk nmap port sweep (mis. 192.168.100.0/24)")
    ap.add_argument("--ports", help="port ekstra dipisah koma")
    ap.add_argument("--timeout", type=int, default=4, help="timeout WS-Discovery (dtk)")
    ap.add_argument("-o", "--out", help="tulis JSON ke file")
    args = ap.parse_args()

    if not (args.onvif or args.ssdp or args.scan):
        ap.error("pilih minimal salah satu: --onvif / --ssdp / --scan CIDR")

    devices = {}  # ip -> record

    if args.onvif:
        print("# ONVIF WS-Discovery ...", file=sys.stderr)
        for ip, info in ws_discovery(args.iface, args.timeout).items():
            d = devices.setdefault(ip, {"ip": ip})
            d["onvif"] = True
            d["onvif_xaddrs"] = info["xaddrs"]
            d["onvif_scopes"] = info["scopes"]
            # tebak nama/model dari scopes
            m = re.search(r"onvif://www\.onvif\.org/name/([^ ]+)", info["scopes"])
            if m: d["name"] = m.group(1).replace("%20", " ")
            mh = re.search(r"onvif://www\.onvif\.org/hardware/([^ ]+)", info["scopes"])
            if mh: d["hardware"] = mh.group(1).replace("%20", " ")

    if args.ssdp:
        print("# SSDP/UPnP M-SEARCH ...", file=sys.stderr)
        for ip, info in ssdp_discovery(args.iface, args.timeout).items():
            d = devices.setdefault(ip, {"ip": ip})
            d["ssdp"] = True
            d["ssdp_server"] = info["server"]
            d["ssdp_location"] = info["location"]
            d["ssdp_st"] = info["st"]
            vh = _ssdp_vendor(info["server"], info["usn"])
            if vh:
                d.setdefault("vendor_guess", [])
                d["vendor_guess"] = sorted(set(d["vendor_guess"]) | set(vh))

    if args.scan:
        print(f"# nmap port sweep {args.scan} ...", file=sys.stderr)
        extra = [int(x) for x in args.ports.split(",")] if args.ports else None
        for ip, ports in nmap_scan(args.scan, extra).items():
            d = devices.setdefault(ip, {"ip": ip})
            d["ports"] = ports
            vendors, svc = classify(ports)
            d["services"] = svc
            if vendors:
                d["vendor_guess"] = vendors

    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "device_count": len(devices),
              "devices": sorted(devices.values(), key=lambda x: x["ip"])}
    txt = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(txt)
        print(f"# {len(devices)} perangkat -> {args.out}", file=sys.stderr)
    print(txt)

if __name__ == "__main__":
    main()
