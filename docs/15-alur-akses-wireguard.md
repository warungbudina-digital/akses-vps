# 15 — Alur Akses End-to-End: Cloud Shell / Laptop / Smartphone lewat WireGuard

## Kenapa dokumen ini ada

`docs/12-wireguard-vpn.md` menjelaskan **konfigurasi** WireGuard (siapa saja
peer-nya, cara tambah/hapus). Dokumen ini melengkapi dengan **alur trafik
konkret** — dari perangkat user, lewat tunnel, sampai ke tujuan, dan
kembali lagi ke user — untuk tiga jenis endpoint yang benar-benar dipakai
saat ini: **Google Cloud Shell**, **Laptop/LAN di belakang `ltap-mini`**,
dan **Smartphone (ADB)**.

## WireGuard bukan jalur GenieACS/subscriber — penting dipahami dulu

Stack ini punya **dua jalur masuk yang terpisah total**, jangan tertukar:

| Jalur | Dipakai untuk | Contoh domain/port |
|---|---|---|
| **Cloudflare Tunnel** (`cloudflared`) + **CWMP publik** (`nginx :7547`) | Trafik produksi: CPE TR-069, GenieACS UI, API gRPC | `acs.obc-crypto.com`, `cwmp.obc-crypto.com`, `api.obc-crypto.com`, `fs.obc-crypto.com` |
| **WireGuard** (`wg0`, `51820/udp`) | Akses **admin/privat**: masuk ke LAN pribadi di belakang `ltap-mini`, akses langsung ke host VPS, kontrol smartphone via ADB | `10.66.66.0/24` (hub-and-spoke, bukan mesh — lihat `docs/12`) |

`genieacs-ui`, `genieacs-nbi`, dll **tidak** di-reach lewat WireGuard —
mereka cuma reachable dari dalam jaringan Docker (`app-net`), diteruskan
nginx ke domain publik lewat Cloudflare Tunnel. WireGuard di dokumen ini
murni tentang jalur kedua di atas.

## Topologi keseluruhan

```mermaid
graph TB
    subgraph internet["Internet"]
        CS["Google Cloud Shell<br/>(VM ephemeral, sesi test/admin)"]
        SP1["Smartphone: Redmi Note 5<br/>tunnel IP 10.66.66.3"]
        SP2["Smartphone: Infinix Hot 11<br/>tunnel IP 10.66.66.2"]
    end

    subgraph lan_ltap["LAN pribadi di belakang ltap-mini (192.168.70.0/24)"]
        LAP["Laptop 'SuaraHati'<br/>192.168.70.254"]
        CAM["Kamera TBS 2603SE<br/>192.168.70.217"]
        SW["Switch Ruijie<br/>192.168.70.253"]
    end

    LTAP["ltap-mini — MikroTik RB912R-2nD<br/>tunnel IP 10.66.66.5<br/>AllowedIPs juga cakup 192.168.70.0/24"]
    LAP --- SW --- LTAP
    CAM --- SW

    HUB[["AKSES-VPS — hub WireGuard<br/>wg0: 10.66.66.1, port 51820/udp<br/>hub-and-spoke: spoke cuma bisa reach hub"]]
    ADB["adb server (127.0.0.1:5037)<br/>jalan di host AKSES-VPS"]

    CS -- "tunnel WireGuard terenkripsi" --> HUB
    SP1 -- "tunnel WireGuard terenkripsi" --> HUB
    SP2 -- "tunnel WireGuard terenkripsi" --> HUB
    LTAP -- "tunnel WireGuard terenkripsi" --> HUB
    HUB -.-> ADB
    ADB -. "adb connect 10.66.66.3:5555 /<br/>10.66.66.2:5555 (lewat wg0)" .-> SP1
    ADB -. " " .-> SP2
```

Catatan topologi (detail lengkap di `docs/12`):
- **Hub-and-spoke** — tiap spoke (`Cloud Shell`, `Redmi-Note-5`,
  `Infinix-Hot-11`) cuma bisa reach `10.66.66.1` (hub), tidak bisa saling
  reach satu sama lain.
- **`ltap-mini` adalah satu-satunya spoke dengan `AllowedIPs` berupa subnet**
  (`192.168.70.0/24`), bukan cuma `/32` — karena dia bertindak sebagai
  gateway/router untuk LAN pribadi di baliknya, bukan endpoint tunggal.

## Alur 1 — Google Cloud Shell: akses admin ke host AKSES-VPS

Skenario: developer/admin buka Google Cloud Shell dari browser, mau
menjalankan perintah administratif langsung di VPS (mis. `docker ps`, cek
log) lewat jalur privat, bukan lewat SSH publik `:22` biasa.

```mermaid
sequenceDiagram
    actor U as User (browser)
    participant CS as Google Cloud Shell (VM)
    participant NET as Internet
    participant HUB as AKSES-VPS — wg0 (10.66.66.1)
    participant HOST as Host AKSES-VPS (sshd, docker)

    U->>CS: Buka Cloud Shell, sesi baru dimulai
    CS->>CS: .customize_environment jalan otomatis:<br/>wireguard/client-setup.sh bawa wg0 up<br/>(keypair persisten, retry sampai handshake OK)
    U->>CS: ssh warungbudina@10.66.66.1
    CS->>NET: Paket terenkripsi WireGuard (UDP/51820)
    NET->>HUB: Diterima di wg0 interface publik VPS
    HUB->>HUB: Dekripsi, cek AllowedIPs peer<br/>(cocok dengan tunnel IP Cloud Shell ini)
    HUB->>HOST: Trafik plaintext hasil dekripsi -> sshd :22 host
    HOST-->>HOST: Eksekusi perintah (docker ps, dst.)
    HOST-->>HUB: Output shell
    HUB-->>NET: Enkripsi ulang lewat WireGuard
    NET-->>CS: Paket balik ke Cloud Shell
    CS-->>U: Output tampil di terminal browser
```

Catatan realistis: sesi Cloud Shell **reset ~20 menit setelah sesi
berakhir** — makanya keypair WireGuard-nya harus persisten lewat
`.customize_environment` (bukan generate ulang tiap sesi), seperti dicatat
di `docs/12`.

## Alur 2 — Laptop/kamera di LAN `ltap-mini`: audit perangkat privat

Skenario: admin perlu SSH ke laptop `SuaraHati` (atau device lain) di LAN
`192.168.70.0/24` yang **tidak reachable dari internet sama sekali** —
satu-satunya jalur masuk adalah lewat hub WireGuard, diteruskan RouterOS di
`ltap-mini`.

```mermaid
sequenceDiagram
    actor U as Admin (di AKSES-VPS)
    participant HUB as AKSES-VPS — wg0 (10.66.66.1)
    participant LTAP as ltap-mini — RouterOS (10.66.66.5)
    participant DEV as Laptop SuaraHati (192.168.70.254)

    U->>HUB: ssh warungbudina@192.168.70.254
    HUB->>HUB: Route lookup: 192.168.70.0/24 -> dev wg0<br/>(peer ltap-mini, AllowedIPs mencakup subnet ini)
    HUB->>LTAP: Paket terenkripsi ke peer ltap-mini
    LTAP->>LTAP: RouterOS decrypt, firewall filter<br/>chain=forward: hanya src-address=10.66.66.1<br/>yang diizinkan (hardened 2026-07-11, lihat docs/12)
    LTAP->>DEV: Forward plaintext ke ether1 LAN -> sshd :22 laptop
    DEV-->>LTAP: Output shell / hasil audit
    LTAP-->>HUB: Forward balik lewat tunnel
    HUB-->>U: Output tampil di terminal admin
```

Variasi yang sama juga berlaku untuk mengakses **kamera TBS 2603SE**
(`192.168.70.217`, protokol RTSP/HTTP RPC alih-alih SSH) — jalur
enkripsi/forwarding-nya identik, cuma port dan protokol tujuan yang beda.

Catatan penting (sudah dicatat di `docs/12`): RouterOS **tidak otomatis**
menambahkan route balik untuk `AllowedIPs` seperti `wg-quick` di Linux —
`ltap-mini` butuh `/ip route add dst-address=10.66.66.1/32 gateway=wg-akses-vps`
manual supaya arah baliknya (LAN → hub) juga jalan, bukan cuma
handshake/keepalive.

## Alur 3 — Smartphone: kontrol/audit via ADB lewat tunnel

Skenario: admin ingin menjalankan `adb shell`/`adb logcat`/dsb. ke
smartphone (`Redmi-Note-5` atau `Infinix-Hot-11`) yang terhubung sebagai
spoke WireGuard, dari AKSES-VPS langsung — tanpa laptop perantara.

```mermaid
sequenceDiagram
    actor U as Admin (di AKSES-VPS)
    participant ADBSRV as adb server (127.0.0.1:5037, host VPS)
    participant HUB as wg0 (10.66.66.1)
    participant PHONE as Smartphone (mis. Redmi-Note-5, 10.66.66.3)
    participant ADBD as adbd di smartphone (:5555)

    Note over PHONE: Prasyarat: Developer Options aktif,<br/>USB debugging ON, `adb tcpip 5555` sudah<br/>dijalankan sekali (USB/local Wi-Fi), lalu<br/>app WireGuard Android bawa wg0 up
    U->>ADBSRV: adb connect 10.66.66.3:5555
    ADBSRV->>HUB: Buka koneksi TCP ke tunnel IP phone
    HUB->>HUB: Route ke peer Redmi-Note-5 (AllowedIPs 10.66.66.3/32)
    HUB->>PHONE: Paket terenkripsi lewat wg0
    PHONE->>ADBD: Decrypt, teruskan ke adbd :5555 lokal
    ADBD-->>PHONE: Handshake ADB berhasil
    PHONE-->>HUB: Response terenkripsi balik
    HUB-->>ADBSRV: Sampai di adb server host
    ADBSRV-->>U: "connected to 10.66.66.3:5555"
    U->>ADBSRV: adb -s 10.66.66.3:5555 shell / logcat / install ...
    ADBSRV->>HUB: (jalur sama seperti di atas)
    HUB->>PHONE: (jalur sama)
    PHONE->>ADBD: Eksekusi perintah di device
    ADBD-->>PHONE: Output
    PHONE-->>HUB: Terenkripsi balik
    HUB-->>ADBSRV: Sampai di host
    ADBSRV-->>U: Output ditampilkan di terminal admin
```

Catatan keamanan (sudah dicek saat setup, lihat `wireguard/install-adb-tools.sh`):
`adb server` bind ke `127.0.0.1:5037` saja — **tidak** membuka port ke
jaringan manapun. Yang membawa trafik ke smartphone adalah `adb connect`
memakai tunnel IP `10.66.66.x` yang sudah terenkripsi WireGuard, bukan ADB
network mode yang di-expose langsung ke internet.

## Ringkasan pola umum (berlaku di ketiga alur)

Setiap alur di atas mengikuti pola yang sama, cuma beda titik awal/akhir:

```
User (di titik manapun)
  -> aplikasi lokal (browser/SSH/adb client)
  -> WireGuard encrypt (di sisi pengirim)
  -> Internet (UDP 51820, opaque - isi paket tidak terbaca)
  -> WireGuard decrypt (di hub AKSES-VPS ATAU di ltap-mini untuk trafik LAN)
  -> service tujuan (sshd / adbd / RouterOS forward)
  -> response mengikuti jalur yang sama terbalik
  -> kembali ke User
```

Referensi terkait: `docs/12-wireguard-vpn.md` (konfigurasi peer & hardening),
`docs/02-network-diagram.md` (diagram jaringan keseluruhan termasuk jalur
Cloudflare Tunnel/CWMP yang terpisah dari WireGuard).
