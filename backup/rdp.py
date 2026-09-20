#!/usr/bin/env python3
"""Klien minimal Firefox Remote Debugging Protocol (RDP) utk Fennec di RN7.

Protokol: tiap paket = "<panjang-byte>:<json>". Server mengirim BANYAK
notifikasi tak diminta (frameUpdate, tabNavigated, dll) - wajib disaring
sampai ketemu paket yg dicari, jangan asumsikan balasan pertama = jawaban.

Prasyarat: adb -s 10.66.66.6:5555 forward tcp:6001 \
  localabstract:org.mozilla.fennec_fdroid/firefox-debugger-socket
(forward HILANG tiap adb server restart - pasang ulang sebelum dipakai)
"""
import json
import socket
import time


class RDP:
    def __init__(self, host="127.0.0.1", port=6001, timeout=30):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""
        self.hello = self._read_packet()  # server menyapa duluan

    # --- transport ---
    def _read_packet(self):
        while True:
            if b":" in self.buf:
                raw_len, rest = self.buf.split(b":", 1)
                if raw_len.isdigit():
                    n = int(raw_len)
                    if len(rest) >= n:
                        payload, self.buf = rest[:n], rest[n:]
                        return json.loads(payload.decode("utf-8"))
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("koneksi RDP tertutup server")
            self.buf += chunk

    def send(self, msg):
        data = json.dumps(msg).encode("utf-8")
        self.sock.sendall(f"{len(data)}:".encode() + data)

    def request(self, msg, want_keys=(), timeout=30):
        """Kirim lalu saring notifikasi sampai dapat paket dari `to` yg sama
        DAN memuat salah satu `want_keys` (atau error)."""
        self.send(msg)
        actor = msg.get("to")
        deadline = time.time() + timeout
        while time.time() < deadline:
            pkt = self._read_packet()
            if pkt.get("from") != actor:
                continue
            if "error" in pkt:
                raise RuntimeError(f"RDP error: {pkt.get('error')} {pkt.get('message','')}")
            if not want_keys or any(k in pkt for k in want_keys):
                return pkt
        raise TimeoutError(f"tak dapat balasan utk {msg}")

    # --- API tingkat tinggi ---
    def list_tabs(self):
        root = self.hello.get("from", "root")
        pkt = self.request({"to": root, "type": "listTabs"}, want_keys=("tabs",))
        return pkt["tabs"]

    def attach_tab(self, tab):
        """Kembalikan consoleActor siap pakai. Tab WAJIB di-SELECT dulu -
        ini fix nyata (commit e38df0b): tab yg tak terpilih bisa balas
        target basi/kosong."""
        actor = tab["actor"]
        try:
            self.request({"to": actor, "type": "select"}, timeout=10)
        except Exception:
            pass  # sebagian versi tak punya "select"; lanjut saja
        pkt = self.request({"to": actor, "type": "getTarget"}, want_keys=("frame", "consoleActor"))
        frame = pkt.get("frame", pkt)
        return frame.get("consoleActor") or pkt.get("consoleActor")

    def resolve(self, grip):
        """Ubah hasil evaluasi jadi nilai Python biasa.

        JEBAKAN NYATA (ditemukan saat panen percakapan besar): string panjang
        TIDAK dikirim utuh - Firefox membungkusnya jadi grip
        {"type":"longString","initial":"...","length":N,"actor":...}. Kalau
        grip ini diperlakukan sbg string biasa, `.get("value")` = None dan
        json.loads langsung meledak ("must be str... not NoneType"). Isi
        penuhnya harus diambil bertahap lewat permintaan `substring`.
        """
        if not isinstance(grip, dict):
            return grip
        if "value" in grip:
            return grip["value"]
        if grip.get("type") == "longString":
            actor, total = grip["actor"], int(grip["length"])
            parts, pos, CHUNK = [], 0, 100_000
            while pos < total:
                end = min(pos + CHUNK, total)
                pkt = self.request({"to": actor, "type": "substring",
                                    "start": pos, "end": end},
                                   want_keys=("substring",), timeout=60)
                parts.append(pkt["substring"])
                pos = end
            return "".join(parts)
        if grip.get("type") == "null":
            return None
        return grip

    def eval_js(self, console_actor, expr, timeout=30):
        pkt = self.request(
            {"to": console_actor, "type": "evaluateJSAsync", "text": expr},
            want_keys=("result", "resultID", "exception"), timeout=timeout)
        # evaluateJSAsync membalas 2 tahap: resultID dulu, lalu hasil nyata
        if "resultID" in pkt and "result" not in pkt:
            deadline = time.time() + timeout
            while time.time() < deadline:
                nxt = self._read_packet()
                if nxt.get("from") == console_actor and ("result" in nxt or "exception" in nxt):
                    pkt = nxt
                    break
        if pkt.get("exception") not in (None, False):
            raise RuntimeError(f"JS exception: {pkt.get('exceptionMessage') or pkt.get('exception')}")
        return pkt.get("result")

    def eval_async(self, console_actor, expr_body, timeout=60, poll=0.5):
        """Utk kode yg mengandung Promise/fetch: evaluateJSAsync TIDAK
        meng-await Promise (jebakan terdokumentasi). Pola wajib: simpan hasil
        ke window.__rdp_out lalu polling sinkron sampai terisi."""
        self.eval_js(console_actor, "window.__rdp_out = null; window.__rdp_err = null;")
        self.eval_js(console_actor, f"(async () => {{ try {{ {expr_body} }} "
                                    f"catch(e) {{ window.__rdp_err = String(e); }} }})();")
        deadline = time.time() + timeout
        while time.time() < deadline:
            err = self.eval_js(console_actor, "window.__rdp_err")
            if isinstance(err, str) and err:
                raise RuntimeError(f"async error: {err}")
            out = self.eval_js(console_actor, "window.__rdp_out")
            val = self.resolve(out)
            if val not in (None, False, ""):
                return val
            time.sleep(poll)
        raise TimeoutError("hasil async tak kunjung terisi")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    r = RDP()
    tabs = r.list_tabs()
    print(f"{len(tabs)} tab:")
    for t in tabs:
        # judul/url bisa None utk tab yg belum selesai dimuat - jangan diiris mentah
        print(f"  - {(t.get('title') or '?')[:60]!r}")
        print(f"    {(t.get('url') or '?')[:100]}")
    r.close()
