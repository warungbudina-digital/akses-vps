#!/usr/bin/env python3
"""dashboard_api.py — backend MINIMAL utk form input URL di pipeline.obc-crypto.com.
Terima POST /api/enqueue {url, category, note} -> insert ke media.video_ingest,
pakai logika SAMA dgn enqueue.py (import langsung, bukan duplikasi regex deteksi
platform). Tujuan: kurasi pribadi (video hasil pilahan user) jadi gampang masuk
antrean lewat browser, tanpa buka SSH/CLI -- antrean yg sama dikuras otomatis
tiap 10mnt oleh analyzer-pipeline-trigger.sh (cron akses-vps) via orchestrator.py.

Auth: Bearer token (pola sama persis BROWSER_API_KEY punya browser_enqueue.py)
-- WAJIB krn domain publik (Cloudflare di depan pipeline.obc-crypto.com).
Token dibaca dari ~/.config/viral-dashboard/credentials.env (600).

Jalan di 172.19.0.1:<PORT> (gateway docker akses-vps_app-net -- SAMA pola dgn
systemd/chrome-vps-tunnel.service: nginx jalan di container, 127.0.0.1 di situ
BUKAN host, jadi backend host harus bind ke gateway bridge biar nginx bisa
reverse-proxy ke sini). TIDAK reachable dari luar host sama sekali.

Env: DASHBOARD_API_PORT (default 8097), DASHBOARD_API_BIND (default 172.19.0.1).
"""
import json, os, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enqueue import detect, esc, lit, DBVPS, CATS  # reuse, jangan duplikasi

BIND = os.getenv("DASHBOARD_API_BIND", "172.19.0.1")
PORT = int(os.getenv("DASHBOARD_API_PORT", "8097"))
TOKEN_FILE = os.path.expanduser("~/.config/viral-dashboard/credentials.env")


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DASHBOARD_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


TOKEN = load_token()


def log(*a):
    print("[dashboard_api]", *a, file=sys.stderr, flush=True)


def insert_url(category, url, note):
    if category not in CATS:
        return None, f"kategori tak valid (harus salah satu: {sorted(CATS)})"
    if not url.startswith(("http://", "https://")):
        return None, "url harus http/https"
    plat, eid = detect(url)
    note_lit = lit((note or "").strip()[:300])
    sql = ("INSERT INTO media.video_ingest (category,platform,source_url,external_id,enqueued_by,user_notes) "
           f"VALUES ('{esc(category)}',{lit(plat)},'{esc(url)}',{lit(eid)},'dashboard',{note_lit}) "
           "ON CONFLICT (source_url) DO NOTHING RETURNING id;")
    r = subprocess.run(["ssh", DBVPS, "sudo -n -u postgres psql -d scraper -tAq"],
                        input=sql, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None, "DB error: " + r.stderr.strip()[:300]
    ids = [x for x in r.stdout.split() if x.strip().isdigit()]
    if ids:
        return int(ids[0]), None
    return None, "duplikat -- URL ini sudah ada di antrean"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        if not TOKEN:
            return False
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def do_POST(self):
        if self.path != "/api/enqueue":
            self._send(404, {"ok": False, "error": "not found"}); return
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"}); return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw or b"{}")
        except Exception:
            self._send(400, {"ok": False, "error": "JSON tak valid"}); return
        url = (data.get("url") or "").strip()
        category = (data.get("category") or "").strip()
        note = data.get("note") or ""
        if not url:
            self._send(400, {"ok": False, "error": "url wajib diisi"}); return
        jid, err = insert_url(category, url, note)
        if err:
            log("tolak:", category, url[:80], "->", err)
            self._send(200, {"ok": False, "error": err}); return
        log("enqueue id", jid, category, url[:80])
        self._send(200, {"ok": True, "id": jid})

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, {"ok": True}); return
        self._send(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt, *args):
        pass  # pakai log() sendiri di atas, jangan dobel access-log bawaan


def main():
    if not TOKEN:
        sys.exit(f"DASHBOARD_TOKEN tak ketemu di {TOKEN_FILE} -- buat file berisi baris 'DASHBOARD_TOKEN=<acak>' (mode 600)")
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    log(f"listen {BIND}:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
