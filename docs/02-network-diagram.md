# 02 — Network Diagram

## Physical / Virtual Network Layers

```mermaid
flowchart LR
    subgraph WAN["WAN (Public Internet)"]
        PUBIP["Public IP\n(VPS Provider assigned)"]
    end

    subgraph VPSHOST["VPS Host NIC"]
        ETH0["eth0 (host physical/virtual NIC)"]
    end

    subgraph CHRNET["CHR Virtual Networking"]
        ETHER1["ether1 (WAN, DHCP/static from host)"]
        BR_LAN["bridge-lan (internal)"]
        BR_CONTAINER["bridge-container (veth aggregation)"]
    end

    subgraph VETHS["veth per container (RouterOS Container)"]
        V_NGINX["veth-nginx 172.20.0.10"]
        V_GRPC["veth-grpc 172.20.0.11"]
        V_MQTT["veth-mqtt 172.20.0.12"]
        V_GENIE["veth-genieacs-* 172.20.0.13-16"]
        V_MONGO["veth-mongo 172.20.0.17"]
        V_REDIS["veth-redis 172.20.0.18"]
        V_MON["veth-prom/grafana/loki 172.20.0.20-23"]
    end

    PUBIP --> ETH0 --> ETHER1
    ETHER1 -->|firewall filter+raw, NAT| BR_LAN
    BR_LAN --> BR_CONTAINER
    BR_CONTAINER --- V_NGINX
    BR_CONTAINER --- V_GRPC
    BR_CONTAINER --- V_MQTT
    BR_CONTAINER --- V_GENIE
    BR_CONTAINER --- V_MONGO
    BR_CONTAINER --- V_REDIS
    BR_CONTAINER --- V_MON
```

## IP Addressing Plan

| Segment | CIDR | Keterangan |
|---|---|---|
| WAN (ether1) | dari provider VPS | Public IP VPS, satu-satunya interface yang "terlihat" dari internet |
| bridge-lan | 192.168.88.0/24 | Manajemen RouterOS, akses admin (winbox/ssh) dibatasi IP tertentu |
| bridge-container | 172.20.0.0/24 | Segment khusus veth container, **tidak di-NAT keluar kecuali lewat masquerade terkontrol** |
| Docker internal (`container-network`) | 172.28.0.0/24 (jika host-Docker) | Nama service dipakai untuk resolusi, IP hanya untuk referensi diagram |

> Container **tidak** diberi IP publik langsung. Satu-satunya jalur masuk dari WAN adalah dst-nat `ether1 -> veth-nginx:443` (dan `:7547` untuk TR-069 jika CPE butuh koneksi langsung tanpa TLS SNI routing — lihat catatan di `docs/04-tr069-request-flow.md`).

## Port Map (Publik → Internal)

| Port Publik | Protokol | Diteruskan ke | Keterangan |
|---|---|---|---|
| 443/tcp | HTTPS/HTTP2/WSS | nginx:443 | Satu-satunya entrypoint utama, SNI routing ke semua subdomain |
| 7547/tcp | HTTP/HTTPS (TR-069) | nginx → genieacs-cwmp:7547 | Sebagian ACS/CPE tidak support SNI, port ini opsional dibuka langsung |
| 80/tcp | HTTP | nginx:80 | Hanya untuk ACME HTTP-01 challenge + redirect ke 443 |
| 22/tcp | SSH | dibatasi source-address list `admin-allowed` | Manajemen RouterOS |

Seluruh port lain (27017, 6379, 1883, 3000, 50051, 9090, 3100, 3001, dst) **hanya listen di jaringan internal container**, tidak pernah di-dst-nat ke WAN.
