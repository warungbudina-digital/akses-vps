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

## Syarat hardware
Butuh **2 dongle USB RT5370** tercolok bersamaan: `wlan1` (monitor, dipakai sesi audit CCTV) + `wlan2` (AP, dipakai hotspot ini). Kalau cuma 1 tercolok, `wlan2` tidak muncul dan `hotspot.sh up` gagal (`Cannot find device "wlan2"`). Interface name di Pi ini stabil per-port USB fisik (bukan urutan colok), jadi kalau salah satu dongle dicabut lalu device lain dicolok di port yang sama, interface itu akan re-enumerasi dengan MAC baru.

## Log & audit klien
`dnsmasq-ap.conf` mengaktifkan `log-dhcp` + `log-queries` ke `/var/log/hotspot-dnsmasq.log` (butuh `sudo` untuk baca) — kasih hostname/vendor-class DHCP dan setiap query DNS klien, berguna untuk fingerprint & audit device yang connect. Contoh alur audit yang sudah dipakai (detail penuh di memori `project_pi_cctv_audit.md`):
1. `sudo hotspot.sh status` → lihat MAC+IP klien di leases.
2. `sudo grep <mac atau ip> /var/log/hotspot-dnsmasq.log` → hostname DHCP + query DNS yang di-resolve.
3. `sudo nmap -Pn --disable-arp-ping -p- <ip>` → port scan (⚠️ wajib `--disable-arp-ping` juga, `-Pn` saja tak cukup untuk target se-subnet).
4. `sudo nmap -Pn --disable-arp-ping -O --osscan-guess <ip>` → tebakan OS/stack (berguna kalau semua port closed, cross-check hostname/TTL).
5. `sudo tcpdump -i wlan2 -n host <ip> -w capture.pcap` → tangkap traffic mentah kalau perlu lihat lebih dari sekadar DNS.

**Contoh temuan:** device "Satellite Finder V8 Pro" (stack lwIP embedded, TTL 255, 0/65535 port terbuka) ketahuan diam-diam query `googleapis.com`/`youtube.com`/`i.ytimg.com` saat boot — indikasi ada komponen Android/GMS/iklan tersembunyi di firmware combo murah, bukan sekadar meter analog. Device jenis ini juga polanya connect → burst aktivitas singkat (~20 detik) → radio idle/diam, jadi window audit sempit — capture traffic sebaiknya dimulai TEPAT saat device baru dinyalakan.
