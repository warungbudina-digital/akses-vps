# Audit + Peta ZTE Modem/ONT `192.168.60.60` (jaringan "ruang tamu")

> Diaudit 2026-08-24 dari Pi 4B (`ssh pi4b`, `wlan0` di WiFi "ruang tamu" — lihat [[project_rpi4b_setup]]). Login web admin `user`/`user`. Konteks jaringan sama dgn [[project_pi_cctv_audit]] (DVR Hikvision `192.168.60.240` di subnet yang sama).

## Identitas device
- **Model: ZTE F670L** (dari `<title>` halaman login, hex-encoded `&#70;&#54;&#55;&#48;&#76;`).
- Hostname reverse-DNS: `gpon.net` — konfirmasi ini **ONT/modem GPON** (terminal fiber-optik), bukan router WiFi biasa. Umum dipakai ISP Indonesia (mis. IndiHome) sbg CPE bawaan.

## Port terbuka (full scan 1-65535, dari Pi)
| Port | Status | Servis |
|---|---|---|
| 21 | open | FTP — ⚠️ lihat temuan keamanan di bawah |
| 23 | **filtered** | Telnet — tak merespons SYN (kemungkinan diblokir dari LAN, tapi tak 100% pasti tertutup total) |
| 53 | open | DNS (resolver lokal modem) |
| 80 | open | HTTP (web admin) |
| 443 | open | HTTPS (web admin) |

## 🔴 TEMUAN KEAMANAN: FTP menerima kredensial APA PUN
```
USER anonymous / PASS test        -> 230 Login successful.
USER user / PASS user             -> 230 Login successful.
```
**FTP service ("virtual FTP service") tampak menerima SEMBARANG kombinasi username/password** — dicoba 2 kombinasi berbeda, KEDUANYA "berhasil login". Setelah masuk, `LIST` di root `/` mengembalikan **direktori kosong** (0 bytes, tak ada file) — jadi dampak nyata saat ini TERBATAS (tak ada file yang bisa dibaca/mengintip), tapi ini tetap postur otentikasi yang lemah/rusak pada servis yang ter-expose ke seluruh LAN. **Rekomendasi:** matikan FTP kalau tak dipakai (menu **Local Network → FTP**, lihat peta menu di bawah), atau pastikan tak ada folder sensitif ter-mount di baliknya.

## ✅ Mekanisme login web admin — DIBEDAH TUNTAS, reusable via script

Bukan RSA/basic-auth — pola **challenge-response SHA256**, murni JS `crypto` (tanpa `jsencrypt`/RSA yg sempat dikira di awal, itu dipakai fitur lain bukan login):

1. `GET /?_type=loginData&_tag=login_entry` → JSON `{"sess_token": "<token>"}` (simpan token ini, dan cookie `SID` yg ikut ter-set).
2. `GET /?_type=loginData&_tag=login_token` → XML `<ajax_response_xml_root>NNNNNNNN</ajax_response_xml_root>` — angka ini "challenge" sekali-pakai.
3. Hitung `hash = SHA256(password + challenge)` (string concat biasa, BUKAN password dulu di-hash terpisah).
4. `POST /?_type=loginData&_tag=login_entry` dgn body `action=login&Username=<user>&Password=<hash>&_sessionTOKEN=<token dari langkah 1>`.
5. Sukses → JSON `{"sess_token": "...", "login_need_refresh": true}` + cookie `SID` (dipakai request berikutnya).

**Script Python siap pakai (login only, TERUJI live 2026-08-24):**
```python
import hashlib, json, re, urllib.request, urllib.parse, http.cookiejar

BASE = "http://192.168.60.60"
USER, PASS = "user", "user"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def get(url):
    with opener.open(BASE + url, timeout=8) as r:
        return r.read().decode("utf-8", "replace")

def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + url, data=body, method="POST")
    with opener.open(req, timeout=8) as r:
        return r.read().decode("utf-8", "replace")

sess_token = json.loads(get("/?_type=loginData&_tag=login_entry"))["sess_token"]
challenge = re.search(r">(\d+)<", get("/?_type=loginData&_tag=login_token")).group(1)
h = hashlib.sha256((PASS + challenge).encode()).hexdigest()
result = json.loads(post("/?_type=loginData&_tag=login_entry", {
    "action": "login", "Password": h, "Username": USER, "_sessionTOKEN": sess_token,
}))
assert result.get("login_need_refresh")  # True = sukses login
# `opener`/`cj` sekarang bawa cookie SID -- pakai `get()`/`post()` yg sama utk request lanjutan
```

## Peta menu admin LENGKAP (dari `menuTreeJSON` di halaman utama pasca-login)

```
Home
Topology
Internet
├─ Status: WAN, 3G/4G, DSLite, 6RD, L2TP
├─ Security: Firewall, Filter Criteria, DMZ
├─ DDNS
└─ SNTP
Local Network
├─ Status (LAN info, WLAN status, WLAN client, LAN client, USB storage -- semua dlm 1 halaman gabungan)
├─ WLAN: WLAN Basic (on/off, advanced, SSID config), WLAN Advanced (MAC filter ACL+rule), WPS
├─ LAN: IPv4 (LAN mgr, DHCP, dev-DHCP-source)
├─ FTP  ⚠️ lihat temuan di atas
├─ DMS/DLNA
├─ Samba Service
└─ USB
VoIP
└─ Status: Line status, Phone status
Management & Diagnosis
├─ Status: Status manager
├─ System Management: Device Management (reboot/reset), User Configuration Management (backup/restore config)
└─ Account Management: account manager, web login timeout
```

**Cara ambil isi tiap halaman via script (POLA, BELUM sepenuhnya tuntas — lihat kendala di bawah):**
- Template/form kosong: `GET /?_type=menuView&_tag=<id>` (`<id>` dari `menuTreeJSON`, mis. `dmz`, `firewall`, `wlanBasic`, `localNetStatus`) — **TERBUKTI JALAN**, balikin HTML+JS lengkap termasuk nama field form (`name="Enable:Ipv4Dmz"` dst) DAN membocorkan nama endpoint data yg terkait (lihat pola di bawah).
- Data/nilai LIVE saat ini: `GET /?_type=menuData&_tag=<area>_lua.lua` (nama `_lua.lua` didapat dari teks halaman `menuView`-nya, mis. `firewall_dmz_lua.lua`, `wlan_wlanstatus_lua.lua`) — **⚠️ SELALU BALIK `SessionTimeout` di setiap percobaan sesi ini**, meski dicoba: sesi baru fresh tiap kali, tambah header `Referer`+`X-Requested-With`, gabung banyak tag jadi 1 request koma-terpisah (pola yg sukses di `menuView`). **Kuirk ini BELUM terpecahkan** — kemungkinan butuh parameter tersembunyi lain (mis. instance-ID, nonce kedua, atau memang HANYA bisa dipicu dari konteks in-page JS yg tak bisa direplikasi murni via HTTP client biasa). **TODO sesi depan** kalau perlu nilai LIVE (SSID/password WiFi asli, status DMZ aktif/tidak, level firewall, daftar client LAN): coba proxy MITM (mis. `mitmproxy` dari Pi) sambil buka halaman via browser sungguhan sekali, baru bandingkan request asli vs yg direplikasi utk temukan parameter yg hilang.

**Yang SUDAH terkonfirmasi dari form KOSONG (template, bukan live-value) halaman DMZ:** kedua radio `Enable:Ipv4Dmz` (value 1/0) TAK ADA yg `checked` di HTML mentah form-nya — konsisten dgn (tapi TAK 100% membuktikan) DMZ dalam keadaan belum pernah dikonfigurasi/nonaktif. Field `InternalClient` (target IP DMZ) juga kosong.

## Kesimpulan audit
- ✅ Postur port terbuka wajar utk ONT (web admin + FTP servis file lokal) — tak ada yg genuinely alarming SELAIN temuan FTP.
- 🔴 **FTP auth lemah/rusak** (terima kredensial apa pun) — dampak saat ini terbatas krn direktori kosong, tapi tetap direkomendasikan dimatikan kalau tak dipakai.
- ✅ Login admin BERHASIL direplikasi via script (reusable utk automasi ke depan) — mekanismenya SHA256 challenge-response, bukan RSA.
- ✅ Peta menu LENGKAP tersedia (semua kategori config: WAN/Firewall/DMZ/DDNS/WLAN/LAN/FTP/Samba/VoIP/Account).
- ⚠️ Ekstraksi NILAI LIVE tiap setting (WiFi SSID/password asli, status DMZ, firewall level, daftar client) **BELUM tuntas** — endpoint `menuData` konsisten menolak dgn "SessionTimeout" meski title mekanisme login sendiri terbukti benar. Kalau perlu nilai-nilai ini scr pasti, opsi realistis: (a) baca langsung via browser manual sekali lalu screenshot, atau (b) lanjutkan reverse-engineering dgn traffic-capture (mitmproxy) drpd tebak-tebak parameter.
