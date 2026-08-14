# cctv-pi — backup tooling audit CCTV (Pi 4B pentest, 10.66.66.4)

Cadangan off-Pi dari `/opt/cctv-audit/` (root-owned) di Raspberry Pi 4B.
Sumber utama tetap di Pi; ini salinan durabilitas (Pi punya riwayat boot-fail).

## Isi
- `cctv-audit.sh` — manajer peran interface ON-DEMAND (non-persisten, tak auto-boot).
  Subcommand: `up|down|status`, `cam-route <IP> {add|del}`, `discover <cidr|ip> [iface]`,
  `audit <IP> [max-tries]`.
- `cctv-discover.py` — discovery: ONVIF WS-Discovery + **SSDP/UPnP M-SEARCH** + nmap port-sweep CCTV.
  Flag: `--onvif --ssdp --scan <cidr> --iface <if>`.
- `cctv-credcheck.py` — cek KREDENSIAL DEFAULT (defensif) HTTP-ISAPI/RTSP-Digest/ONVIF, sadar-lockout.
- `eth0-sniff.py` — sniff pasif L2 (AF_PACKET) untuk temukan kamera nyaris-diam.
- `hostapd.conf` / `dnsmasq-ap.conf` — config AP audit (wlan2, SSID CCTV-AUDIT).

## Peran interface
wlan0=uplink+wg (JANGAN sentuh) · wlan2=AP · wlan1=monitor · eth0=LAN kamera.

## Pakai (di Pi)
```
ssh pi4b
echo 'Taiku123!' | sudo -S /opt/cctv-audit/cctv-audit.sh audit 192.168.1.64 4
```

## Restore ke Pi (jika tooling di Pi hilang)
```
for f in *.sh *.py *.conf; do
  cat "$f" | ssh pi4b "sudo tee /opt/cctv-audit/$f >/dev/null"
done
ssh pi4b 'sudo chmod +x /opt/cctv-audit/*.sh /opt/cctv-audit/*.py'
```

## Catatan Fase
- Fase 1: peran interface + tooling on-demand (hostapd/dnsmasq masked).
- Fase 2: discovery + cek cred default (teruji kamera Hikvision nyata 192.168.1.64).
- Fase 3 (2026-08-14): tambah discovery **SSDP/UPnP** ke `cctv-discover.py` +
  integrasi `--ssdp` ke `discover`/`audit`. Kamera Hik pakai SADP proprietary (bukan UPnP)
  → tak muncul di SSDP; berguna untuk vendor lain (Dahua/XiongMai/Reolink dll).
