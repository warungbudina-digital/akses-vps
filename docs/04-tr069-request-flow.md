# 04 — Diagram Alur Request TR-069

## Alur Inform standar (CPE → ACS)

```mermaid
sequenceDiagram
    autonumber
    participant CPE
    participant MT as MikroTik CHR (Firewall/NAT)
    participant NG as nginx (TLS terminate)
    participant CWMP as genieacs-cwmp
    participant DB as MongoDB
    participant NBI as genieacs-nbi
    participant UI as genieacs-ui / Operator

    CPE->>MT: TCP SYN :7547 (atau :443 jika via SNI cwmp.domain.com)
    MT->>MT: firewall filter (raw prerouting: drop invalid, allow established)
    MT->>NG: dst-nat forward
    NG->>CWMP: proxy_pass http (internal, plain HTTP di belakang TLS)
    CPE->>CWMP: SOAP/HTTP Inform (DeviceId, Events: 0 BOOTSTRAP / 1 BOOT / 4 VALUE CHANGE / 6 CONNECTION REQUEST)
    CWMP->>DB: upsert device doc (_id = OUI-SerialNumber)
    CWMP-->>CPE: HTTP 200 InformResponse
    CWMP->>DB: cek task queue untuk device ini
    alt ada task pending (preset/provision)
        CWMP->>CPE: kirim RPC (SetParameterValues / GetParameterValues / Download / Reboot)
        CPE-->>CWMP: RPC Response
        CWMP->>DB: simpan hasil, update parameter tree
    end
    CWMP->>CPE: kirim empty HTTP response (tutup sesi) atau HoldRequests jika masih ada task
    NBI-->>DB: operator/aplikasi lain query status device via REST
    UI->>NBI: tampilkan device list, tag, faults
```

## Alur Connection Request (ACS → CPE, untuk trigger instan)

```mermaid
sequenceDiagram
    autonumber
    participant Operator
    participant NBI as genieacs-nbi
    participant DB as MongoDB
    participant CWMP as genieacs-cwmp
    participant MT as MikroTik (NAT/Firewall)
    participant CPE

    Operator->>NBI: POST /devices/{id}/tasks (task baru)
    NBI->>DB: simpan task, set pending
    NBI->>CWMP: trigger connection request ke ConnectionRequestURL milik CPE
    CWMP->>MT: HTTP GET ke IP:port CPE (butuh CPE reachable — biasanya via STUN/NAT traversal jika CPE di belakang NAT ISP)
    MT-->>CPE: forward (bila ada port-forward / STUN binding)
    CPE->>CWMP: buka sesi Inform baru (Event: 6 CONNECTION REQUEST)
    Note over CWMP,CPE: lanjut seperti alur Inform di atas — task dieksekusi saat sesi ini
```

## Firmware / File Download (genieacs-fs)

```mermaid
sequenceDiagram
    participant CPE
    participant NG as nginx (fs.domain.com)
    participant FS as genieacs-fs
    participant DB as MongoDB (GridFS)

    CPE->>NG: HTTP GET /firmware/xyz.bin (Download RPC dari ACS berisi URL ini)
    NG->>FS: proxy_pass genieacs-fs:7567
    FS->>DB: stream file dari GridFS
    FS-->>CPE: HTTP 200 + binary stream (chunked)
```

## Catatan Desain

- **TR-069 (CWMP)** = protokol transport/RPC dasar. **TR-098** (InternetGatewayDevice) dan **TR-181** (Device:2 data model) adalah *skema data model* di atas CWMP — GenieACS mendukung keduanya secara otomatis berdasarkan data model yang dikirim CPE saat Inform.
- **Virtual Parameter** dipakai untuk expose nilai turunan (mis. gabungan RSSI dari beberapa parameter) tanpa mengubah data model asli — didefinisikan sebagai script JS kecil di GenieACS UI, dieksekusi oleh `genieacs-cwmp`.
- **Preset** = aturan otomatis "jika device match filter X, terapkan konfigurasi Y" — dievaluasi setiap Inform masuk.
- **Provision** = script JS yang benar-benar dieksekusi (preset memanggil provision).
- Kalau banyak CPE di belakang NAT berlapis (ISP-grade), **Connection Request langsung sering gagal** — mitigasi: gunakan **periodic inform interval pendek** (mis. 300s) atau **STUN** (`genieacs-cwmp` mendukung STUN client hint dari CPE), atau **XMPP/MQTT wake-up** kalau CPE mendukung TR-069 Annex K (di luar scope default GenieACS, butuh custom bridge — inilah salah satu use case `grpc-server` + `mosquitto` di arsitektur ini: menerima event dari sistem lain lalu memicu connection-request via NBI API).
