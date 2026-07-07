# =====================================================================
# MikroTik CHR — RouterOS CLI Configuration
# Target: RouterOS v7.x (Container feature GA sejak 7.4+)
# Skenario: CHR sebagai VM di VPS host, ether1 = WAN (public IP dari
#           hypervisor via bridge/macvtap), container berjalan di CHR.
# =====================================================================

# ---------------------------------------------------------------------
# 1. IDENTITY & BASIC SAFETY (jalankan pertama, sebelum firewall lain)
# ---------------------------------------------------------------------
/system identity set name=CHR-TR069-EDGE

# Ganti port winbox/API default & disable service yang tidak dipakai
/ip service disable telnet,ftp,www,api,api-ssl
/ip service set ssh port=22
/ip service set winbox port=8291

# ---------------------------------------------------------------------
# 2. INTERFACES: WAN, BRIDGE LAN, BRIDGE CONTAINER
# ---------------------------------------------------------------------
# ether1 dianggap WAN, IP publik didapat dari provider (DHCP client atau
# static — sesuaikan dengan cara VPS provider menghubungkan network ke CHR)
/ip dhcp-client add interface=ether1 disabled=no add-default-route=yes

# Bridge untuk manajemen (opsional, kalau ada interface LAN kedua)
/interface bridge add name=bridge-lan protocol-mode=none
/ip address add address=192.168.88.1/24 interface=bridge-lan

# Bridge khusus agregasi veth container — TIDAK di-NAT langsung ke WAN,
# semua trafik keluar/masuk lewat firewall rule eksplisit
/interface bridge add name=bridge-container protocol-mode=none
/ip address add address=172.20.0.1/24 interface=bridge-container

# ---------------------------------------------------------------------
# 3. VIRTUAL ETHERNET (veth) — satu per container
# ---------------------------------------------------------------------
/interface veth add name=veth-nginx      address=172.20.0.10/24 gateway=172.20.0.1
/interface veth add name=veth-grpc       address=172.20.0.11/24 gateway=172.20.0.1
/interface veth add name=veth-mqtt       address=172.20.0.12/24 gateway=172.20.0.1
/interface veth add name=veth-cwmp       address=172.20.0.13/24 gateway=172.20.0.1
/interface veth add name=veth-nbi        address=172.20.0.14/24 gateway=172.20.0.1
/interface veth add name=veth-fs         address=172.20.0.15/24 gateway=172.20.0.1
/interface veth add name=veth-genie-ui   address=172.20.0.16/24 gateway=172.20.0.1
/interface veth add name=veth-mongo      address=172.20.0.17/24 gateway=172.20.0.1
/interface veth add name=veth-redis      address=172.20.0.18/24 gateway=172.20.0.1
/interface veth add name=veth-prom       address=172.20.0.20/24 gateway=172.20.0.1
/interface veth add name=veth-grafana    address=172.20.0.21/24 gateway=172.20.0.1
/interface veth add name=veth-loki       address=172.20.0.22/24 gateway=172.20.0.1

# Masukkan semua veth ke bridge-container
:foreach i in={"veth-nginx";"veth-grpc";"veth-mqtt";"veth-cwmp";"veth-nbi";"veth-fs";"veth-genie-ui";"veth-mongo";"veth-redis";"veth-prom";"veth-grafana";"veth-loki"} do={
    /interface bridge port add bridge=bridge-container interface=$i
}

# ---------------------------------------------------------------------
# 4. CONTAINER ENGINE SETUP
# ---------------------------------------------------------------------
# Disk/partisi khusus untuk container (wajib RouterOS Container)
/disk
# (pastikan sudah ada extra disk terpasang di CHR, mis. via VPS panel, lalu:)
# format-disk disk=disk1 file-system=ext4
# /container config set registry-url=https://registry-1.docker.io tmpdir=disk1/pull

/container config set ram-high=80% registry-url=https://registry-1.docker.io tmpdir=disk1/pull

# Contoh menambahkan container nginx (ulangi pola ini untuk service lain,
# atau — lebih disarankan untuk stack sebesar ini — build image di CI lalu
# push ke registry privat dan tarik satu per satu di sini)
/container mounts add name=nginx-conf src=disk1/nginx/conf dst=/etc/nginx
/container mounts add name=nginx-certs src=disk1/certbot/certs dst=/etc/letsencrypt

/container add remote-image=nginx:1.27-alpine interface=veth-nginx \
    root-dir=disk1/containers/nginx \
    mounts=nginx-conf,nginx-certs \
    logging=yes start-on-boot=yes

# Contoh grpc-server (image hasil build sendiri, lihat grpc-server/Dockerfile)
/container add remote-image=registry.internal/akses-vps/grpc-server:latest \
    interface=veth-grpc root-dir=disk1/containers/grpc-server \
    envlist=grpc-env logging=yes start-on-boot=yes

/container envs add name=grpc-env key=JWT_SECRET value="CHANGE_ME_USE_SECRET_STORE"
/container envs add name=grpc-env key=REDIS_ADDR value="172.20.0.18:6379"
/container envs add name=grpc-env key=MONGO_URI value="mongodb://172.20.0.17:27017"

# Ulangi pola /container add + /container mounts + /container envs untuk:
# mosquitto (veth-mqtt), genieacs-cwmp (veth-cwmp), genieacs-nbi (veth-nbi),
# genieacs-fs (veth-fs), genieacs-ui (veth-genie-ui), mongo (veth-mongo),
# redis (veth-redis), prometheus/grafana/loki (veth-prom/grafana/loki)

# ---------------------------------------------------------------------
# 5. NAT (dst-nat port-forward WAN -> nginx, masquerade untuk trafik keluar)
# ---------------------------------------------------------------------
/ip firewall nat add chain=dstnat in-interface=ether1 protocol=tcp dst-port=443 \
    action=dst-nat to-addresses=172.20.0.10 to-ports=443 comment="WAN->nginx HTTPS"
/ip firewall nat add chain=dstnat in-interface=ether1 protocol=tcp dst-port=80 \
    action=dst-nat to-addresses=172.20.0.10 to-ports=80 comment="WAN->nginx ACME HTTP-01"
/ip firewall nat add chain=dstnat in-interface=ether1 protocol=tcp dst-port=7547 \
    action=dst-nat to-addresses=172.20.0.10 to-ports=7547 comment="WAN->nginx TR-069 direct (opsional, non-SNI CPE)"

# Masquerade agar container bisa akses internet (pull image update, NTP, dst)
/ip firewall nat add chain=srcnat src-address=172.20.0.0/24 out-interface=ether1 \
    action=masquerade comment="container outbound"

# ---------------------------------------------------------------------
# 6. RAW FIREWALL (diproses sebelum connection tracking — buang paket
#    sampah sedini mungkin, hemat CPU conntrack)
# ---------------------------------------------------------------------
/ip firewall raw add chain=prerouting action=drop protocol=tcp \
    tcp-flags=syn,fin comment="drop invalid syn+fin"
/ip firewall raw add chain=prerouting action=drop protocol=tcp \
    tcp-flags=fin,!ack comment="drop invalid fin without ack"
/ip firewall raw add chain=prerouting action=drop protocol=tcp tcp-flags=!syn connection-state=new \
    comment="drop new connection tanpa SYN flag"
/ip firewall raw add chain=prerouting in-interface=ether1 src-address-list=blocklist \
    action=drop comment="drop IP di blocklist (diisi fail2ban/manual)"
/ip firewall raw add chain=prerouting in-interface=ether1 action=accept \
    comment="fasttrack candidate lolos ke filter"

# ---------------------------------------------------------------------
# 7. FIREWALL FILTER — default DROP, whitelist eksplisit
# ---------------------------------------------------------------------
# --- Input chain (trafik ke CHR sendiri) ---
/ip firewall filter add chain=input connection-state=established,related action=accept comment="allow established/related"
/ip firewall filter add chain=input connection-state=invalid action=drop comment="drop invalid"
/ip firewall filter add chain=input protocol=icmp action=accept comment="allow ping (rate-limit di bawah jika perlu)"
/ip firewall filter add chain=input in-interface=bridge-lan action=accept comment="allow LAN management"
/ip firewall filter add chain=input protocol=tcp dst-port=22 src-address-list=admin-allowed action=accept \
    comment="SSH hanya dari IP admin"
/ip firewall filter add chain=input protocol=tcp dst-port=8291 src-address-list=admin-allowed action=accept \
    comment="Winbox hanya dari IP admin"
/ip firewall filter add chain=input action=drop comment="default DROP input"

# --- Forward chain (trafik lewat CHR menuju container) ---
/ip firewall filter add chain=forward connection-state=established,related action=accept comment="allow established/related"
/ip firewall filter add chain=forward connection-state=invalid action=drop comment="drop invalid"
/ip firewall filter add chain=forward in-interface=ether1 dst-address=172.20.0.10 protocol=tcp dst-port=80,443 \
    action=accept comment="WAN -> nginx"
/ip firewall filter add chain=forward in-interface=ether1 dst-address=172.20.0.10 protocol=tcp dst-port=7547 \
    action=accept comment="WAN -> nginx (TR-069 direct)"
/ip firewall filter add chain=forward src-address=172.20.0.0/24 out-interface=ether1 action=accept \
    comment="container -> internet (update, ntp, dns)"
/ip firewall filter add chain=forward in-interface=ether1 action=drop comment="default DROP forward dari WAN selain rule di atas"
/ip firewall filter add chain=forward action=drop comment="default DROP forward"

# --- Address list untuk admin & rate-limit brute force SSH ---
/ip firewall address-list add list=admin-allowed address=203.0.113.10/32 comment="Kantor/VPN admin - GANTI dengan IP asli"
/ip firewall filter add chain=input protocol=tcp dst-port=22 connection-state=new \
    action=add-src-to-address-list address-list=ssh-attempt address-list-timeout=1m
/ip firewall filter add chain=input protocol=tcp dst-port=22 connection-state=new \
    src-address-list=ssh-attempt address-list-timeout=1m action=add-src-to-address-list \
    address-list=ssh-blacklist address-list-timeout=1d
/ip firewall filter add chain=input src-address-list=ssh-blacklist action=drop comment="fail2ban-style SSH blacklist"

# ---------------------------------------------------------------------
# 8. FASTTRACK (percepat trafik established/related yang sudah lolos filter)
# ---------------------------------------------------------------------
/ip firewall filter add chain=forward connection-state=established,related action=fasttrack-connection \
    hw-offload=yes comment="fasttrack established/related" place-before=1
# Catatan: fasttrack MELEWATI filter/mangle rule berikutnya untuk paket yang
# match — pastikan rule ini ditempatkan SETELAH rule drop-invalid tapi
# SEBELUM rule accept biasa, dan jangan aktifkan bila butuh inspeksi L7 penuh
# (mis. deep packet filtering) untuk trafik tsb.

# ---------------------------------------------------------------------
# 9. DNS
# ---------------------------------------------------------------------
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=no cache-size=2048KiB
/ip dns static add name=acs.domain.com address=172.20.0.10 comment="opsional, resolusi internal jika perlu"

# ---------------------------------------------------------------------
# 10. IPv6 READY
# ---------------------------------------------------------------------
/ipv6 settings set disable-ipv6=no forward=yes
/ipv6 address add address=2001:db8::1/64 interface=ether1 advertise=no comment="GANTI dengan prefix asli dari provider"
/ipv6 firewall filter add chain=input connection-state=established,related action=accept
/ipv6 firewall filter add chain=input connection-state=invalid action=drop
/ipv6 firewall filter add chain=input protocol=icmpv6 action=accept comment="wajib untuk NDP/ping6"
/ipv6 firewall filter add chain=input protocol=tcp dst-port=22 src-address-list=admin-allowed action=accept
/ipv6 firewall filter add chain=input action=drop comment="default DROP input v6"
/ipv6 firewall filter add chain=forward connection-state=established,related action=accept
/ipv6 firewall filter add chain=forward protocol=tcp dst-port=443,80 dst-address=2001:db8::10 action=accept comment="jika nginx dapat v6 dari NAT66/routed"
/ipv6 firewall filter add chain=forward action=drop comment="default DROP forward v6"

# ---------------------------------------------------------------------
# 11. STATIC ROUTE (jika VPS provider butuh next-hop khusus / multi-homed)
# ---------------------------------------------------------------------
# /ip route add dst-address=0.0.0.0/0 gateway=<GATEWAY_WAN_DARI_PROVIDER> distance=1
# /ip route add dst-address=10.122.31.0/24 gateway=<GATEWAY_PRIVATE_NETWORK> distance=1 comment="akses ke VM lain via private network provider"

# ---------------------------------------------------------------------
# 12. LOGGING (kirim log firewall ke syslog eksternal agar bisa masuk Loki)
# ---------------------------------------------------------------------
/system logging action add name=remote-syslog target=remote remote=172.20.0.22 remote-port=1514
/system logging add topics=firewall action=remote-syslog
/system logging add topics=critical,error,warning action=remote-syslog
