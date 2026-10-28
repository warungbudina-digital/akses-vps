#!/usr/bin/env python3
# Driver terminal Cloud Shell via CDP. Alamat = TARGET ID (stabil).
# Input xterm: insertText TAK tembus -> pakai key events. Bulk = fire-and-forget + drain.
#   list | ident | scrape <id> [n] | ctrlc <id> | run <id> "<cmd>" [wait] [key] | runfile <id> <path> [wait] [key]
import json, sys, time, urllib.request
from websocket import create_connection

PORT = 9222

def targets():
    with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=5) as r:
        return json.load(r)

def shell_targets():
    return [t for t in targets() if t.get("type") == "page" and "shell.cloud.google" in t.get("url", "")]

def resolve(sel):
    for t in shell_targets():
        if t.get("id", "").startswith(sel):
            return t
    raise SystemExit("target id diawali '%s' tak ditemukan" % sel)

class CDP:
    def __init__(self, ws_url):
        self.ws = create_connection(ws_url, timeout=20, max_size=None); self.mid = 0
    def _raw(self, method, params=None):
        self.mid += 1; m = {"id": self.mid, "method": method}
        if params: m["params"] = params
        self.ws.send(json.dumps(m)); return self.mid
    def send(self, method, params=None):
        cur = self._raw(method, params)
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == cur: return r
    def drain(self):
        self.ws.settimeout(0.02)
        try:
            while True: self.ws.recv()
        except Exception:
            pass
        finally:
            self.ws.settimeout(20)
    def evaluate(self, js):
        r = self.send("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("result", {}).get("value")
    def front(self):
        try: self.send("Page.bringToFront")
        except Exception: pass
    def focus(self):
        self.evaluate("(function(){var t=document.querySelector('.xterm-helper-textarea')||document.querySelector('textarea');if(t){t.focus();return 1}return 0})()")
    def click_terminal(self):
        # (2026-10-28 fix, insiden pasca-outage-listrik 27/10) Cloud Shell kadang
        # merender overlay invisible full-viewport (ketemu nyata: tag custom
        # <security-blocking-indicator>, position:fixed z-index:99999
        # pointer-events:auto, outerHTML KOSONG "<!---->" -- diduga gate sisi-
        # Google utk browser EOL spt Chrome 109 ini, dgn fallback blocking-nya
        # tetap aktif walau dialog peringatannya sendiri gagal render). Klik
        # KOORDINAT lama MENEMBAK overlay ini, bukan terminal -> fokus
        # textarea JUSTRU TERCABUT tepat sblm mengetik -> SEMUA karakter
        # silent-drop (reproduksi live: scrape tetap bersih, nol jejak command,
        # walau op_run lapor "selesai"). Verified live 2026-10-28: fokus JS
        # LANGSUNG ke textarea (tanpa klik koordinat) tetap tembus ke xterm
        # walau overlay ini ada. Jadi: cek elementFromPoint dulu; kalau titik
        # klik DIBLOK elemen di luar xterm, lewati klik koordinat & cukup
        # andalkan focus() (dipanggil pemanggil sblm/sesudah ini) -- JANGAN
        # hardcode nama tag overlay spesifik, supaya varian lain di masa depan
        # (selector Google bisa berubah) tetap aman ditangani sama.
        chk = self.evaluate(
            "(function(){var e=document.querySelector('.xterm-screen')||document.querySelector('.xterm');"
            "if(!e)return null;var r=e.getBoundingClientRect();var x=r.left+r.width/2,y=r.top+r.height/2;"
            "var hit=document.elementFromPoint(x,y);"
            "return {x:x,y:y,blocked:!(hit===e||e.contains(hit))};})()")
        if not chk:
            return
        if chk.get("blocked"):
            self.focus()
            return
        x, y = chk["x"], chk["y"]
        for tp in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {"type": tp, "x": x, "y": y, "button": "left", "clickCount": 1})
    def key(self, **p):
        self._raw("Input.dispatchKeyEvent", p)
    def enter(self):
        self.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter",
                  "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "text": "\r"})
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                  "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    def ctrlc(self):
        for ev in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {"type": ev, "key": "c", "code": "KeyC",
                    "windowsVirtualKeyCode": 67, "nativeVirtualKeyCode": 67, "modifiers": 2})
    def ctrlu(self):
        # (2026-08-28) bersihkan SISA input di baris prompt sblm ngetik baru --
        # bukti nyata: retry type_cmd() (mis. attempt-2 op_run) numpuk teks di
        # atas sisa attempt-1 yg gagal/kepotong ("chm" lama + "chmod..." baru
        # -> "chmchmod", diamati live 28/8). Ctrl+U = clear-line standar bash.
        for ev in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {"type": ev, "key": "u", "code": "KeyU",
                    "windowsVirtualKeyCode": 85, "nativeVirtualKeyCode": 85, "modifiers": 2})
    def keytype(self, s):
        # keyDown+keyUp dgn text (xterm ini TAK proses event 'char'). OK utk perintah pendek.
        for ch in s:
            self.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
            self.send("Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})
    def esc(self):
        for ev in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {"type": ev, "key": "Escape", "code": "Escape",
                    "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
    def type_cmd(self, cmd, mode="key"):
        # tutup panel overlay (mis. panel transfer file) yg bisa curi fokus
        self.esc(); time.sleep(0.15)
        # (2026-08-28 fix #2, temuan user) klik kursor terminal, TAPI kasih
        # jeda lebih panjang pasca-klik sblm ngetik apa pun -- pemanggil
        # (open-and-bootstrap-cs.py) sudah kasih jeda settle besar sblm
        # sampai sini, ini jeda TERAKHIR khusus mastikan klik fokus beneran
        # "nempel" (bukan race dgn repaint) sblm keystroke pertama ditembak.
        self.click_terminal(); time.sleep(0.4)
        # (2026-08-28) bersihkan baris SEBELUM mulai ngetik -- lihat ctrlu().
        self.ctrlu(); time.sleep(0.15)
        # WARMUP (2026-08-15): karakter PERTAMA pasca-focus/klik kerap drop di xterm
        # ini (bukti nyata: "chmod" -> "hmod") -> kirim char+backspace buang dulu.
        self.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": " "})
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", "text": " "})
        time.sleep(0.05)
        self.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8, "text": "\u0008"})
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
        time.sleep(0.05)
        if cmd:
            if mode == "insert":
                self.send("Input.insertText", {"text": cmd})
            else:
                self.keytype(cmd)
            time.sleep(0.2)
        self.enter()
    def scrape(self):
        return self.evaluate("(function(){var r=document.querySelector('.xterm-rows');return r?r.innerText:(document.body?document.body.innerText:'')})()") or ""
    def close(self):
        try: self.ws.close()
        except Exception: pass

def op_list():
    for t in shell_targets():
        print("%s  %s" % (t.get("id"), t.get("url")))

def op_ident():
    import re
    for t in shell_targets():
        c = CDP(t["webSocketDebuggerUrl"]); acct = "?"
        try:
            c.front(); time.sleep(0.6); c.focus(); c.enter(); time.sleep(0.8)
            m = re.findall(r"([A-Za-z0-9._%+-]+)@cloudshell", c.scrape())
            if m: acct = m[-1]
        except Exception as e:
            acct = "ERR:%s" % e
        finally:
            c.close()
        print("%s  akun=%s" % (t.get("id"), acct))

def op_scrape(sel, n=40):
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.front(); time.sleep(0.4); txt = c.scrape()
    finally:
        c.close()
    print("\n".join(txt.split("\n")[-n:]))

def op_ctrlc(sel):
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.front(); time.sleep(0.4); c.focus(); c.ctrlc(); time.sleep(1.0)
        c.front(); time.sleep(0.3); print("\n".join(c.scrape().split("\n")[-8:]))
    finally:
        c.close()

def op_feed(sel, b64path, remote, chunk=180):
    # tulis file base64 di remote via banyak perintah pendek `printf %s 'CHUNK' >> remote`
    with open(b64path, "r", encoding="utf-8") as f:
        data = f.read().strip()
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.front(); time.sleep(0.3); c.focus()
        c.type_cmd("rm -f %s" % remote, "key"); time.sleep(0.4); c.drain()
        nchunks = 0
        for i in range(0, len(data), chunk):
            ck = data[i:i+chunk]
            c.click_terminal()
            c.keytype("printf %%s '%s' >> %s" % (ck, remote))
            c.enter(); nchunks += 1
            time.sleep(0.3); c.drain()
        # verifikasi ukuran base64 di remote
        c.type_cmd("wc -c %s" % remote, "key"); time.sleep(1.5)
        c.front(); time.sleep(0.3)
        print("fed %d chars in %d chunks -> %s" % (len(data), nchunks, remote))
        print("\n".join(c.scrape().split("\n")[-6:]))
    finally:
        c.close()

def op_click(sel, needle):
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.front(); time.sleep(0.3)
        js = ("(function(n){var re=new RegExp('^'+n+'$','i');"
              "var els=Array.from(document.querySelectorAll('button,[role=button],[aria-label]'));"
              "var cs=els.filter(function(e){var t=(e.innerText||e.textContent||'').trim();"
              "var a=(e.getAttribute&&e.getAttribute('aria-label'))||'';return re.test(t)||re.test(a);});"
              "if(cs.length){cs[cs.length-1].click();return 'CLICKED:'+cs.length;}return 'NONE';})(%r)" % needle)
        print(c.evaluate(js))
    finally:
        c.close()

def op_run(sel, cmd, wait=2.5, mode="key"):
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        # (2026-08-25 fix) verifikasi command benar2 ter-echo di terminal --
        # dikonfirmasi live: kadang type_cmd() "sukses" (rc=0) TAPI nol
        # karakter nyampai ke xterm (tab idle di prompt kosong, dibuktikan
        # scrape). Kemungkinan besar race di click_terminal() saat xterm
        # belum sepenuhnya siap render walau wait_ready() bilang "prompt
        # siap". Retry SEKALI (re-front+re-focus+re-type) sblm menyerah.
        # (2026-08-28 fix) 2 attempt TERBUKTI kadang tak cukup (balibruntattour
        # reproduksi live: attempt 1 DAN 2 sama2 gagal ter-echo, WG tunnel tak
        # pernah naik) -- naikkan ke 3 attempt. Caller (open-and-bootstrap-cs.py)
        # ikut dinaikkan timeout-nya (90->130s) supaya attempt ke-3 tak kepotong.
        marker = cmd.strip().split(" ", 1)[0] if cmd.strip() else ""
        out = ""
        MAX_ATTEMPT = 3
        for attempt in range(1, MAX_ATTEMPT + 1):
            c.front(); time.sleep(0.4); c.focus(); c.type_cmd(cmd, mode)
            time.sleep(wait); c.front(); time.sleep(0.3)
            out = c.scrape()
            if not marker or marker in out or attempt == MAX_ATTEMPT:
                break
            sys.stderr.write("WARN: '%s' tak ter-echo, retry ke-%d...\n" % (marker, attempt + 1))
            time.sleep(1.0)
        print("\n".join(out.split("\n")[-40:]))
    finally:
        c.close()

def op_runfile(sel, path, wait=3.0, mode="key"):
    with open(path, "r", encoding="utf-8") as f:
        cmd = f.read().rstrip("\n")
    t = resolve(sel); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.front(); time.sleep(0.4); c.focus(); c.type_cmd(cmd, mode)
        print("typed %d chars -> %s" % (len(cmd), t.get("id")))
        time.sleep(wait); c.front(); time.sleep(0.3)
        print("\n".join(c.scrape().split("\n")[-30:]))
    finally:
        c.close()

def main():
    if len(sys.argv) < 2:
        print("usage: list | ident | scrape <id>[n] | ctrlc <id> | run <id> <cmd> [wait] [insert] | runfile <id> <path> [wait] [insert]"); return
    op = sys.argv[1]
    def mode_of(av): return "insert" if "insert" in av else "key"
    def wait_of(av, d): return next((float(a) for a in av if a.replace('.','',1).isdigit()), d)
    if op == "list": op_list()
    elif op == "ident": op_ident()
    elif op == "scrape": op_scrape(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 40)
    elif op == "ctrlc": op_ctrlc(sys.argv[2])
    elif op == "run": op_run(sys.argv[2], sys.argv[3], wait_of(sys.argv[4:], 2.5), mode_of(sys.argv[4:]))
    elif op == "runfile": op_runfile(sys.argv[2], sys.argv[3], wait_of(sys.argv[4:], 3.0), mode_of(sys.argv[4:]))
    elif op == "feed": op_feed(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 180)
    elif op == "click": op_click(sys.argv[2], sys.argv[3])
    else: print("op tak dikenal")

if __name__ == "__main__":
    main()
