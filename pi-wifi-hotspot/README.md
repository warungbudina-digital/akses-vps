# WIFI-gratis — hotspot internet umum via Pi 4B

Backup config untuk hotspot **"WIFI-gratis"** (open/tanpa password) yang jalan di `wlan2` (adapter USB RT5370 terpisah dari `wlan0`). Berbagi internet dari uplink `wlan0` ("ruang tamu") lewat NAT — **beda dari `../cctv-pi/` yang isolasi tanpa internet** untuk audit kamera.

Detail lengkap + hasil pengujian: memori Claude `project_pi_cctv_audit.md`.

## Pasang di Pi
```bash
scp hostapd.conf dnsmasq-ap.conf hotspot.sh pi4b:/opt/wifi-hotspot/
ssh pi4b chmod +x /opt/wifi-hotspot/hotspot.sh
```

## Pakai
```bash
ssh pi4b
sudo /opt/wifi-hotspot/hotspot.sh up      # nyalakan (wlan0 tak tersentuh)
sudo /opt/wifi-hotspot/hotspot.sh status  # cek hostapd/dnsmasq/NAT/klien
sudo /opt/wifi-hotspot/hotspot.sh down    # matikan
```

Subnet klien: `10.20.50.0/24` (DHCP `.50`-`.150`). Password: **tidak ada** (`hostapd.conf` sengaja tanpa baris `wpa=`) — tambahkan `wpa=2`/`wpa_key_mgmt=WPA-PSK`/`wpa_passphrase=...` kalau nanti mau dikunci.
