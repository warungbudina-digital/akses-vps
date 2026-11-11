#!/usr/bin/env python3
"""dashboard_api.py — backend MINIMAL utk pipeline.obc-crypto.com.
Terima POST /api/enqueue {url, category, note} -> insert ke media.video_ingest,
pakai logika SAMA dgn enqueue.py (import langsung, bukan duplikasi regex deteksi
platform). Tujuan: kurasi pribadi (video hasil pilahan user) jadi gampang masuk
antrean lewat browser, tanpa buka SSH/CLI -- job baru memicu run-drain.sh SENDIRI
(fire-and-forget, lihat trigger_drain() di enqueue.py) begitu masuk, TAK lagi
menunggu cron 10mnt (analyzer-pipeline-trigger.sh kini cuma jaring-pengaman,
lihat audit+pemisahan permanen 3/11 di memory project_viral_analyzer.md).

(2026-10-30, permintaan user) GET /api/status -> JSON antrean+hasil TERKINI
(reuse fetch() dari dashboard.py, SQL sama persis -- jangan duplikasi query).
Dipakai index.html (dashboard root "/") utk poll tiap beberapa detik & render
client-side -- dashboard.py (generator HTML statis lama, sekali-jalan sejak
11/8 tak pernah di-regen ulang) KINI SUPERSEDED utk tampilan; fetch()-nya
sendiri masih dipakai live di sini. Cache ringan (TTL 2s) supaya poll
ber-tab-banyak/berbarengan tak membanjiri SSH ke DB-VPS tiap request.
Endpoint ini TAK pakai token (baca-saja, domain sudah di belakang Cloudflare
Access -- pola sama /api/health).

Auth: Bearer token (pola sama persis BROWSER_API_KEY punya browser_enqueue.py)
-- WAJIB utk /api/enqueue (tulis DB) krn domain publik (Cloudflare di depan
pipeline.obc-crypto.com). Token dibaca dari ~/.config/viral-dashboard/credentials.env (600).

Jalan di 172.19.0.1:<PORT> (gateway docker akses-vps_app-net -- SAMA pola dgn
systemd/chrome-vps-tunnel.service: nginx jalan di container, 127.0.0.1 di situ
BUKAN host, jadi backend host harus bind ke gateway bridge biar nginx bisa
reverse-proxy ke sini). TIDAK reachable dari luar host sama sekali.

Env: DASHBOARD_API_PORT (default 8097), DASHBOARD_API_BIND (default 172.19.0.1).
"""
import json, os, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enqueue import detect, esc, lit, DBVPS, CATS, LANGS, trigger_drain  # reuse, jangan duplikasi
from dashboard import fetch as fetch_status  # reuse SQL+parse, jangan duplikasi

_status_cache = {"t": 0.0, "data": None}
_STATUS_TTL = 2.0  # detik

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


def insert_url(category, url, note, language=None):
    if category not in CATS:
        return None, f"kategori tak valid (harus salah satu: {sorted(CATS)})"
    if not url.startswith(("http://", "https://")):
        return None, "url harus http/https"
    if language and language not in LANGS:
        return None, f"language tak valid (harus salah satu: {sorted(LANGS)}, atau kosongkan)"
    plat, eid = detect(url)
    note_lit = lit((note or "").strip()[:300])
    sql = ("INSERT INTO media.video_ingest (category,platform,source_url,external_id,enqueued_by,user_notes,language) "
           f"VALUES ('{esc(category)}',{lit(plat)},'{esc(url)}',{lit(eid)},'dashboard',{note_lit},{lit(language)}) "
           "ON CONFLICT (source_url) DO NOTHING RETURNING id;")
    r = subprocess.run(["ssh", DBVPS, "sudo -n -u postgres psql -d scraper -tAq"],
                        input=sql, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None, "DB error: " + r.stderr.strip()[:300]
    ids = [x for x in r.stdout.split() if x.strip().isdigit()]
    if ids:
        jid = int(ids[0])
        trigger_drain()  # fire-and-forget, non-blocking -- lihat enqueue.py
        return jid, None
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
        language = (data.get("language") or "").strip() or None
        if not url:
            self._send(400, {"ok": False, "error": "url wajib diisi"}); return
        jid, err = insert_url(category, url, note, language)
        if err:
            log("tolak:", category, url[:80], "->", err)
            self._send(200, {"ok": False, "error": err}); return
        log("enqueue id", jid, category, url[:80])
        self._send(200, {"ok": True, "id": jid})

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, {"ok": True}); return
        if self.path == "/api/status":
            now = time.monotonic()
            if _status_cache["data"] is None or now - _status_cache["t"] > _STATUS_TTL:
                try:
                    _status_cache["data"] = fetch_status()
                    _status_cache["t"] = now
                except Exception as e:
                    self._send(502, {"ok": False, "error": f"DB error: {e}"[:300]}); return
            self._send(200, _status_cache["data"]); return
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
