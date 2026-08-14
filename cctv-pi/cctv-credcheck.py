#!/usr/bin/env python3
"""
cctv-credcheck.py - Fase 2 cek KREDENSIAL DEFAULT untuk lab audit CCTV (Pi 4B).
Menguji apakah perangkat kamera/DVR MASIH memakai kredensial pabrik pada:
  - HTTP web-UI  (Basic / Digest)
  - RTSP stream  (DESCRIBE + Digest/Basic)
  - ONVIF        (GetDeviceInformation, WS-Security UsernameToken PasswordDigest)

TUJUAN DEFENSIF: temukan kamera ber-kredensial default agar bisa DIGANTI.
HANYA untuk perangkat milik / berwenang (lab sendiri).

⚠️  Beberapa perangkat (mis. Hikvision) MENGUNCI akun setelah beberapa kali
    gagal login. Alat ini memakai daftar KECIL + jeda antar percobaan dan
    berhenti pada match pertama per-layanan. Gunakan --max-tries untuk membatasi.

Contoh:
  ./cctv-credcheck.py --target 192.168.100.108 --http --rtsp
  ./cctv-credcheck.py --from-json /tmp/cctv.json --all -o /tmp/cctv-cred.json
"""
import argparse, base64, hashlib, json, socket, ssl, sys, time, uuid
import urllib.request, urllib.error

# --- Kredensial default per vendor (user:pass). Sengaja RINGKAS utk hindari lockout. ---
DEFAULT_CREDS = [
    ("admin", "admin"),
    ("admin", "12345"),      # Hikvision lama
    ("admin", "123456"),
    ("admin", ""),           # XiongMai/Sofia sering kosong
    ("admin", "888888"),     # Dahua lama
    ("admin", "admin12345"),
    ("admin", "9999"),
    ("root", "root"),
    ("root", "pass"),
    ("root", "12345"),
    ("user", "user"),
    ("888888", "888888"),    # Dahua
    ("666666", "666666"),
]

RTSP_PATHS = [
    "/Streaming/Channels/101",     # Hikvision
    "/cam/realmonitor?channel=1&subtype=0",  # Dahua
    "/h264/ch1/main/av_stream",
    "/live/ch0", "/live0", "/11", "/0", "/stream0", "/stream1",
    "/onvif1", "/media/video1", "/videoMain", "/ch0_0.264",
    "/",
]

# ------------------------- util Digest (HTTP + RTSP) -------------------------
def _h(s): return hashlib.md5(s.encode()).hexdigest()

def parse_www_auth(header):
    """Parse 'Digest realm=..,nonce=..,qop=..' -> dict. Juga deteksi Basic."""
    header = header.strip()
    scheme = header.split(" ", 1)[0].lower()
    params = {}
    rest = header[len(scheme):].strip()
    import re
    for m in re.finditer(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', rest):
        params[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
    return scheme, params

def digest_response(user, passwd, method, uri, params, nc="00000001", cnonce=None):
    realm = params.get("realm", "")
    nonce = params.get("nonce", "")
    qop = params.get("qop")
    algo = params.get("algorithm", "MD5")
    ha1 = _h(f"{user}:{realm}:{passwd}")
    if algo.lower() == "md5-sess":
        cnonce = cnonce or uuid.uuid4().hex[:16]
        ha1 = _h(f"{ha1}:{nonce}:{cnonce}")
    ha2 = _h(f"{method}:{uri}")
    if qop:
        cnonce = cnonce or uuid.uuid4().hex[:16]
        resp = _h(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
        auth = (f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
                f'response="{resp}", qop={qop}, nc={nc}, cnonce="{cnonce}"')
    else:
        resp = _h(f"{ha1}:{nonce}:{ha2}")
        auth = (f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
                f'response="{resp}"')
    if "opaque" in params:
        auth += f', opaque="{params["opaque"]}"'
    return auth

# ------------------------------- HTTP -------------------------------
# Endpoint admin yang MEMANG butuh auth (probe utk temukan 401 nyata, bukan halaman login).
HTTP_PROBE_PATHS = [
    "/ISAPI/System/deviceInfo",                      # Hikvision (ISAPI)
    "/cgi-bin/magicBox.cgi?action=getSystemInfo",    # Dahua
    "/axis-cgi/param.cgi?action=list",               # Axis
    "/onvif/device_service",                         # ONVIF generic
    "/cgi-bin/hi3510/param.cgi?cmd=getserverinfo",   # XM/Sofia beberapa OEM
    "/System/configurationFile",                     # varian Hik lama
    "/",                                             # fallback
]

def _http_get(url, timeout, ctx, auth=None):
    hdrs = {"Authorization": auth} if auth else {}
    req = urllib.request.Request(url, method="GET", headers=hdrs)
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)

def check_http(ip, port=80, tls=False, creds=None, max_tries=6, delay=0.5, timeout=5):
    scheme = "https" if tls else "http"
    ctx = ssl.create_default_context() if tls else None
    if ctx:
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    # 1) temukan endpoint admin yg balas 401 (bukan sekadar halaman login 200)
    probe_url = www = None
    for path in HTTP_PROBE_PATHS:
        url = f"{scheme}://{ip}:{port}{path}"
        try:
            _http_get(url, timeout, ctx)
            continue  # 200 tanpa auth -> bukan endpoint terproteksi, coba path lain
        except urllib.error.HTTPError as e:
            if e.code == 401:
                probe_url = url; www = e.headers.get("WWW-Authenticate", ""); break
            # 403/404/dll -> path lain
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
            return {"service": f"http:{port}", "error": str(e)}
    if not probe_url:
        return {"service": f"http:{port}", "auth_required": False,
                "note": "tak ada endpoint admin dikenal yg minta auth (cek manual)"}
    scheme_a, params = parse_www_auth(www)
    path_only = probe_url.split(f":{port}", 1)[1] or "/"
    tried = 0
    for user, pw in (creds or DEFAULT_CREDS):
        if tried >= max_tries: break
        tried += 1
        try:
            if scheme_a == "digest":
                auth = digest_response(user, pw, "GET", path_only, params)
            else:
                tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
                auth = f"Basic {tok}"
            r = _http_get(probe_url, timeout, ctx, auth)
            return {"service": f"http:{port}", "auth_required": True, "auth_scheme": scheme_a,
                    "endpoint": path_only, "VULNERABLE": True, "cred": f"{user}:{pw}",
                    "http_code": r.getcode(), "tries": tried}
        except urllib.error.HTTPError as e:
            if 200 <= e.code < 300:
                return {"service": f"http:{port}", "auth_required": True, "endpoint": path_only,
                        "VULNERABLE": True, "cred": f"{user}:{pw}", "tries": tried}
            # 401/403 -> cred salah, lanjut
        except (socket.timeout, ConnectionError, OSError):
            break
        time.sleep(delay)
    return {"service": f"http:{port}", "auth_required": True, "auth_scheme": scheme_a,
            "endpoint": path_only, "VULNERABLE": False, "tries": tried}

# ------------------------------- RTSP -------------------------------
# Banyak kamera (Hikvision dsb) menutup koneksi TCP tiap respons -> buka socket BARU per request.
def _rtsp_request(ip, port, path, cseq, auth_hdr=None, timeout=5):
    """Kirim satu DESCRIBE lewat koneksi baru. Return (code, resp, tcp_connected)."""
    url = f"rtsp://{ip}:{port}{path}"
    req = f"DESCRIBE {url} RTSP/1.0\r\nCSeq: {cseq}\r\nAccept: application/sdp\r\n"
    if auth_hdr: req += f"Authorization: {auth_hdr}\r\n"
    req += "User-Agent: cctv-audit\r\n\r\n"
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
    except (socket.timeout, ConnectionError, OSError):
        return None, "", False
    try:
        sock.settimeout(timeout)
        sock.sendall(req.encode())
        data = b""
        while b"\r\n\r\n" not in data:
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, ConnectionResetError, OSError):
                break
            if not chunk: break
            data += chunk
        txt = data.decode("utf-8", "replace")
        return _rtsp_code(txt), txt, True
    except (ConnectionError, OSError):
        return None, "", True
    finally:
        try: sock.close()
        except OSError: pass

def check_rtsp(ip, port=554, creds=None, paths=None, max_tries=6, delay=0.4, timeout=5):
    paths = paths or RTSP_PATHS
    result = {"service": f"rtsp:{port}", "reachable": False}
    cseq = 0
    tcp_ok = False
    for path in paths:
        cseq += 1
        code, resp, connected = _rtsp_request(ip, port, path, cseq, timeout=timeout)
        tcp_ok = tcp_ok or connected
        if code is None:
            time.sleep(delay); continue
        result["reachable"] = True
        url = f"rtsp://{ip}:{port}{path}"
        if code == 200:
            result.update({"path": path, "url": url, "auth_required": False,
                           "VULNERABLE": True, "note": "stream TANPA auth"})
            return result
        if code == 401:
            www = _rtsp_header(resp, "WWW-Authenticate")
            if not www:
                time.sleep(delay); continue
            scheme_a, params = parse_www_auth(www)
            tried = 0
            for user, pw in (creds or DEFAULT_CREDS):
                if tried >= max_tries: break
                tried += 1
                if scheme_a == "digest":
                    auth = digest_response(user, pw, "DESCRIBE", url, params)
                else:
                    tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
                    auth = f"Basic {tok}"
                cseq += 1
                c2, _, _ = _rtsp_request(ip, port, path, cseq, auth, timeout=timeout)
                if c2 == 200:
                    result.update({"path": path, "url": url, "auth_required": True,
                                   "auth_scheme": scheme_a, "VULNERABLE": True,
                                   "cred": f"{user}:{pw}", "tries": tried})
                    return result
                time.sleep(delay)
            # path valid (minta auth) tapi default gagal -> selesai
            result.update({"path": path, "url": url, "auth_required": True,
                           "auth_scheme": scheme_a, "VULNERABLE": False, "tries": tried})
            return result
        # 404 / lainnya -> coba path berikut
        time.sleep(delay)
    if not result["reachable"]:
        if tcp_ok:
            result["tcp_open"] = True
            result["note"] = ("TCP 554 terbuka tapi TAK ada respons RTSP di semua path "
                              "(kemungkinan LOCKOUT proteksi brute-force / IP diblokir sementara)")
        else:
            result["error"] = "tak bisa buka koneksi TCP 554 (tertutup/timeout)"
    else:
        result["note"] = "tak ada path RTSP dikenal cocok (200/401)"
    return result

def _rtsp_code(resp):
    if resp.startswith("RTSP/1.0"):
        try: return int(resp.split()[1])
        except Exception: return None
    return None

def _rtsp_header(resp, name):
    for line in resp.split("\r\n"):
        if line.lower().startswith(name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None

# ------------------------------- ONVIF -------------------------------
def _onvif_token(user, passwd):
    nonce = uuid.uuid4().bytes
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + passwd.encode()).digest()).decode()
    nonce_b64 = base64.b64encode(nonce).decode()
    return (
        '<Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        f'<UsernameToken><Username>{user}</Username>'
        f'<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password>'
        f'<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</Nonce>'
        f'<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>'
        '</UsernameToken></Security>'
    )

def check_onvif(xaddr, creds=None, max_tries=6, delay=0.4, timeout=6):
    import re as _re
    result = {"service": "onvif", "xaddr": xaddr}
    tried = 0
    for user, pw in (creds or DEFAULT_CREDS):
        if tried >= max_tries: break
        tried += 1
        body = (
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
            f'<s:Header>{_onvif_token(user, pw)}</s:Header>'
            '<s:Body><GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body>'
            '</s:Envelope>'
        ).encode()
        try:
            req = urllib.request.Request(xaddr, data=body, method="POST", headers={
                "Content-Type": 'application/soap+xml; charset=utf-8',
                "Content-Length": str(len(body))})
            ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode("utf-8", "replace")
            if "GetDeviceInformationResponse" in resp:
                def g(tag):
                    m = _re.search(rf"<[^>]*{tag}[^>]*>([^<]*)</[^>]*{tag}>", resp)
                    return m.group(1) if m else ""
                result.update({"VULNERABLE": True, "cred": f"{user}:{pw}", "tries": tried,
                               "manufacturer": g("Manufacturer"), "model": g("Model"),
                               "firmware": g("FirmwareVersion"), "serial": g("SerialNumber")})
                return result
        except urllib.error.HTTPError as e:
            # 400/401 dgn SOAP fault NotAuthorized -> cred salah, lanjut
            pass
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
            result["error"] = str(e); return result
        time.sleep(delay)
    result["VULNERABLE"] = False; result["tries"] = tried
    return result

# ------------------------------- main -------------------------------
def audit_target(rec, do_http, do_rtsp, do_onvif, max_tries, delay):
    ip = rec.get("ip")
    ports = rec.get("ports", [])
    findings = []
    if do_http:
        for p in [x for x in (80, 8080, 81, 88, 8000) if not ports or x in ports]:
            findings.append(check_http(ip, p, tls=False, max_tries=max_tries, delay=delay))
        for p in [x for x in (443, 8443) if x in ports]:
            findings.append(check_http(ip, p, tls=True, max_tries=max_tries, delay=delay))
    if do_rtsp and (not ports or 554 in ports or 322 in ports):
        findings.append(check_rtsp(ip, 554, max_tries=max_tries, delay=delay))
    if do_onvif:
        for xa in rec.get("onvif_xaddrs", []):
            findings.append(check_onvif(xa, max_tries=max_tries, delay=delay))
    return {"ip": ip, "vendor_guess": rec.get("vendor_guess"),
            "name": rec.get("name"), "findings": findings}

def main():
    ap = argparse.ArgumentParser(description="Cek kredensial DEFAULT perangkat CCTV (defensif)")
    ap.add_argument("--target", help="satu IP")
    ap.add_argument("--from-json", help="baca hasil cctv-discover.py")
    ap.add_argument("--onvif-xaddr", help="URL ONVIF langsung utk --onvif")
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--rtsp", action="store_true")
    ap.add_argument("--onvif", action="store_true")
    ap.add_argument("--all", action="store_true", help="http+rtsp+onvif")
    ap.add_argument("--max-tries", type=int, default=6, help="maks kredensial per layanan (hindari lockout)")
    ap.add_argument("--delay", type=float, default=0.5, help="jeda antar percobaan (dtk)")
    ap.add_argument("-o", "--out", help="tulis JSON")
    args = ap.parse_args()

    if args.all: args.http = args.rtsp = args.onvif = True
    if not (args.http or args.rtsp or args.onvif):
        ap.error("pilih --http/--rtsp/--onvif atau --all")
    if not (args.target or args.from_json or args.onvif_xaddr):
        ap.error("butuh --target IP, --from-json file, atau --onvif-xaddr URL")

    print("⚠  DEFAULT-CRED CHECK: hanya perangkat berwenang. Beberapa unit mengunci akun "
          f"setelah gagal login (dibatasi --max-tries={args.max_tries}).", file=sys.stderr)

    targets = []
    if args.from_json:
        with open(args.from_json) as f:
            data = json.load(f)
        targets = data.get("devices", [])
    if args.target:
        targets.append({"ip": args.target})
    results = []
    if args.onvif_xaddr:
        results.append({"ip": args.onvif_xaddr,
                        "findings": [check_onvif(args.onvif_xaddr, max_tries=args.max_tries, delay=args.delay)]})
    for rec in targets:
        print(f"# audit {rec.get('ip')} ...", file=sys.stderr)
        results.append(audit_target(rec, args.http, args.rtsp, args.onvif, args.max_tries, args.delay))

    vuln = [r for r in results for fi in r.get("findings", []) if fi.get("VULNERABLE")]
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "targets": len(results), "vulnerable_count": len(vuln), "results": results}
    txt = json.dumps(out, indent=2)
    if args.out:
        with open(args.out, "w") as f: f.write(txt)
        print(f"# hasil -> {args.out} (VULNERABLE: {len(vuln)})", file=sys.stderr)
    print(txt)

if __name__ == "__main__":
    main()
