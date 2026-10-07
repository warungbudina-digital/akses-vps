#!/usr/bin/env python3
"""cdp_cookies.py — ekspor/impor cookie Chromium via CDP (stdlib saja).

Dipakai gui-session.sh di akses-vps lewat tunnel `ssh -L <port>:127.0.0.1:9222 .61`.
Hub tak punya lib websocket -> klien WebSocket minimal ditulis di sini.

  cdp_cookies.py export <domain> <out_cookies.txt> <out_storage_state.json> [--port 9222]
  cdp_cookies.py import <cookies.txt | storage_state.json> [--port 9222]

storage_state = format Playwright {"cookies":[...],"origins":[]} — menyimpan
sameSite yg hilang di Netscape; impor memakai file ini bila tersedia.
"""
import base64, json, os, socket, struct, sys, urllib.request
from urllib.parse import urlparse


class CDP:
    def __init__(self, port):
        ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))
        u = urlparse(ver["webSocketDebuggerUrl"])
        self.s = socket.create_connection(("127.0.0.1", port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        hdr = b""
        while b"\r\n\r\n" not in hdr:
            hdr += self.s.recv(1)
        if b" 101 " not in hdr.split(b"\r\n")[0]:
            raise SystemExit(f"handshake CDP gagal: {hdr[:120]!r}")
        self.n = 0

    def _recv_exact(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise SystemExit("koneksi CDP tertutup")
            b += c
        return b

    def _recv_msg(self):
        data = b""
        while True:
            b0, b1 = self._recv_exact(2)
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            data += self._recv_exact(ln)
            if b0 & 0x80:  # FIN
                return data

    def call(self, method, params=None):
        self.n += 1
        payload = json.dumps({"id": self.n, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        h = bytes([0x81])
        ln = len(payload)
        if ln < 126:
            h += bytes([0x80 | ln])
        elif ln < 65536:
            h += bytes([0x80 | 126]) + struct.pack(">H", ln)
        else:
            h += bytes([0x80 | 127]) + struct.pack(">Q", ln)
        self.s.sendall(h + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))
        while True:
            m = json.loads(self._recv_msg())
            if m.get("id") == self.n:
                if "error" in m:
                    raise SystemExit(f"{method}: {m['error']}")
                return m.get("result", {})


def match(cookie_domain, domain):
    d = cookie_domain.lstrip(".")
    return d == domain or d.endswith("." + domain)


def export(domain, out_txt, out_ss, port):
    cookies = [c for c in CDP(port).call("Storage.getCookies")["cookies"] if match(c["domain"], domain)]
    with open(out_txt, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            dom = ("#HttpOnly_" if c.get("httpOnly") else "") + c["domain"]
            exp = 0 if c.get("session") or c.get("expires", -1) < 0 else int(c["expires"])
            f.write("\t".join([dom, "TRUE" if c["domain"].startswith(".") else "FALSE", c["path"],
                               "TRUE" if c.get("secure") else "FALSE", str(exp), c["name"], c["value"]]) + "\n")
    ss = {"cookies": [{"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c["path"],
                       "expires": -1 if c.get("session") else c.get("expires", -1),
                       "httpOnly": c.get("httpOnly", False), "secure": c.get("secure", False),
                       "sameSite": c.get("sameSite", "Lax")} for c in cookies], "origins": []}
    with open(out_ss, "w") as f:
        json.dump(ss, f)
    exps = [c["expires"] for c in ss["cookies"] if c["expires"] > 0]
    # baris terakhir stdout = jumlah + expiry terdekat (epoch) utk dicatat pemanggil
    print(f"{len(cookies)} {int(min(exps)) if exps else 0}")


def parse_netscape(path):
    out = []
    for line in open(path):
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_"):]
        if not line.strip() or line.startswith("#"):
            continue
        p = line.rstrip("\n").split("\t")
        if len(p) < 7:
            continue
        c = {"name": p[5], "value": p[6], "domain": p[0], "path": p[2],
             "secure": p[3] == "TRUE", "httpOnly": http_only}
        if int(p[4] or 0) > 0:
            c["expires"] = int(p[4])
        out.append(c)
    return out


def do_import(path, port):
    if path.endswith(".json"):
        cookies = []
        for c in json.load(open(path)).get("cookies", []):
            c = {k: v for k, v in c.items() if k in ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "expires")}
            if c.get("expires", -1) <= 0:
                c.pop("expires", None)
            cookies.append(c)
    else:
        cookies = parse_netscape(path)
    CDP(port).call("Storage.setCookies", {"cookies": cookies})
    print(len(cookies))


if __name__ == "__main__":
    a = sys.argv[1:]
    port = 9222
    if "--port" in a:
        i = a.index("--port"); port = int(a[i + 1]); del a[i:i + 2]
    if a[:1] == ["export"] and len(a) == 4:
        export(a[1], a[2], a[3], port)
    elif a[:1] == ["import"] and len(a) == 2:
        do_import(a[1], port)
    else:
        raise SystemExit(__doc__)
