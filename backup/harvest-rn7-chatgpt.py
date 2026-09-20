#!/usr/bin/env python3
"""
Panen riwayat percakapan ChatGPT-web di RN7 -> Postgres `ai_chatlog` di DB-VPS.

KENAPA ADA: melengkapi [[project_rn5_chat_harvest]] (RN5, app NATIVE via
uiautomator). RN7 tak bisa pakai pendekatan itu sama sekali - pohon
aksesibilitas WebView Fennec tak terekspos ke `uiautomator dump` (sering cuma
1 node `android.webkit.WebView`). Ganti jalur: **Firefox Remote Debugging
Protocol (RDP)** + **backend-api ChatGPT**.

HASILNYA JUSTRU LEBIH BAIK dari RN5:
  - Peran tiap pesan (user/assistant) TERLABEL PRESISI - di RN5 transkrip
    mentah tanpa label siapa bicara (batasan v1 yg tercatat di sana).
  - Satu panggilan API per percakapan, bukan belasan scroll+dump.
  - Tak membajak layar -> tak bentrok dgn peran RN7 sbg node VN Editor 24/7.
  - Tak perlu kabel USB (RN7 lewat WireGuard; RN5 wajib tercolok).

JEBAKAN YG SUDAH DITANGANI (semua terdokumentasi dr sesi pemetaan sblmnya):
  1. `adb forward` HILANG tiap adb server restart -> dipasang ulang tiap run.
  2. Socket debugger Fennec bisa TAK ADA walau toggle "Pengawakutuan jarak
     jauh" sudah ON - perlu Fennec di-RESTART supaya socket dibuat ulang
     (dikonfirmasi nyata 2026-09-13: restart menghidupkan RDP yg tadinya diam).
     `/proc/net/unix` TIDAK bisa dipakai mengecek ini (shell Android tak
     diizinkan melihat socket proses lain -> selalu tampak "tidak ada").
  3. `evaluateJSAsync` TIDAK meng-await Promise -> pola window.__rdp_out +
     polling (lihat rdp.py).
  4. `/backend-api/*` WAJIB Bearer token dari `/api/auth/session`; cookie saja
     balik jalur anonim (0 percakapan padahal login).
  5. Judul tab BUKAN indikator login yg sah (tab basi menyesatkan) - status
     login diverifikasi lewat /api/auth/session.

POLA SIMPAN: JSONL di-stream lewat pipe SSH ke DB-VPS lalu di-`\\copy` ke
tabel staging, baru UPSERT. Sengaja TANPA driver Postgres di akses-vps
(tak ada pip/psql di sana) - konsisten dgn pola stream-lewat-SSH yg sudah
dipakai backup script lain. QUOTE/DELIMITER memakai karakter kontrol
(\\x01/\\x02) yg mustahil muncul di JSON -> tiap baris masuk apa adanya,
bebas drama escaping.
"""
import argparse
import json
from datetime import datetime
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ADB = os.environ.get("ADB_BIN", "adb")
RN7 = os.environ.get("RN7_SERIAL", "10.66.66.6:5555")
FENNEC = "org.mozilla.fennec_fdroid"
SOCK = f"localabstract:{FENNEC}/firefox-debugger-socket"
RDP_PORT = int(os.environ.get("RDP_PORT", "6001"))
DBVPS = os.environ.get("DBVPS_HOST", "db-vps")
REMOTE_PAYLOAD = "/tmp/ai_chatlog_payload.jsonl"
SOURCE = "chatgpt"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def to_epoch(v):
    """Samakan format waktu. JEBAKAN NYATA: endpoint DAFTAR
    (/backend-api/conversations) mengembalikan waktu sbg STRING ISO-8601
    ('2026-09-11T06:40:30.425266Z'), sedangkan endpoint DETAIL
    (/backend-api/conversation/<id>) mengembalikan FLOAT epoch. Dua-duanya
    dinormalkan ke epoch float di sini supaya perbandingan inkremental dan
    kolom timestamptz di Postgres tak pernah salah tafsir."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sshdb(args, stdin_data=None, timeout=180):
    """db-vps mencetak banner login besar ke STDERR tiap koneksi -> dibuang.
    Deteksi gagal TIDAK bergantung stderr, melainkan returncode + verifikasi
    hasil (pola sama dgn pi-vault-backup.sh)."""
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", DBVPS] + args,
        input=stdin_data, capture_output=True, text=True, timeout=timeout)


def psql(sql, timeout=180):
    # ssh MENGGABUNG argv jadi satu string yg lalu di-parse ulang shell remote
    # -> SQL berisi spasi WAJIB di-quote, kalau tidak pecah jadi banyak argumen
    # dan psql error (jebakan nyata saat run pertama skrip ini).
    r = sshdb(["psql", "-h", "127.0.0.1", "-U", "ai_chatlog", "-d", "ai_chatlog",
               "-v", "ON_ERROR_STOP=1", "-tAc", shlex.quote(sql)], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"psql gagal: {r.stdout.strip()} {r.stderr.strip()[:300]}")
    return r.stdout.strip()


# ---------------- RN7 / RDP ----------------

def ensure_adb_online(retries=6, delay=3):
    """Pastikan RN7 nempel di adb-server & ber-state 'device' SEBELUM apa pun.

    HARDEN 2026-09-20: `ensure_rdp` lama langsung `adb forward` dgn asumsi RN7
    sudah nempel. Nyatanya di cron 05:00 device kerap lepas dr adb-server
    (`device 'x' not found`) atau nyangkut 'offline' -> forward langsung gagal
    & harvest gagal total tiap malam 14->20/9. adb-over-WireGuard: sambungan
    TCP bisa basi diam-diam, jadi 'offline' di-reconnect (disconnect+connect),
    bukan cuma connect ulang."""
    state = ""
    for i in range(retries):
        sh([ADB, "connect", RN7])
        state = (sh([ADB, "-s", RN7, "get-state"]).stdout or "").strip()
        if state == "device":
            return
        log(f"adb RN7 state='{state or 'tak terhubung'}' (coba {i+1}/{retries}) - reconnect...")
        sh([ADB, "disconnect", RN7])
        time.sleep(delay)
    raise RuntimeError(f"RN7 tak online di adb setelah {retries}x (state terakhir='{state}')")


def _forward():
    sh([ADB, "-s", RN7, "forward", "--remove-all"])
    r = sh([ADB, "-s", RN7, "forward", f"tcp:{RDP_PORT}", SOCK])
    if r.returncode != 0:
        raise RuntimeError(f"adb forward gagal: {r.stderr.strip()[:200]}")


def ensure_rdp():
    """Pasang ulang adb forward, dan pastikan RDP benar2 menjawab. Kalau diam,
    RESTART Fennec (socket debugger cuma dibuat saat app start)."""
    ensure_adb_online()
    _forward()

    from rdp import RDP
    try:
        c = RDP(port=RDP_PORT, timeout=8)
        c.close()
        return
    except Exception:
        log("RDP diam - restart Fennec supaya socket debugger dibuat ulang...")

    sh([ADB, "-s", RN7, "shell", f"am force-stop {FENNEC}"])
    time.sleep(2)
    sh([ADB, "-s", RN7, "shell", f"am start -n {FENNEC}/org.mozilla.fenix.HomeActivity"])
    time.sleep(8)
    _forward()

    # HARDEN 2026-09-20: Fennec butuh waktu bervariasi utk membuat socket
    # debugger pasca-restart (apalagi saat RN7 sibuk jam 05:00). Dulu cuma 1
    # percobaan RDP -> sering gagal. Sekarang retry + pasang ulang forward tiap
    # kali (forward bisa raib kalau adb-server sempat reset).
    from rdp import RDP
    last = None
    for i in range(6):
        try:
            RDP(port=RDP_PORT, timeout=15).close()
            return
        except Exception as e:
            last = e
            log(f"RDP belum siap pasca-restart Fennec (coba {i+1}/6)...")
            time.sleep(4)
            _forward()
    raise RuntimeError(f"RDP tetap diam setelah restart Fennec: {repr(last)[:200]}")


def open_chatgpt_tab(client):
    tabs = client.list_tabs()
    tab = next((t for t in tabs if "chatgpt.com" in (t.get("url") or "")), None)
    if tab is None:
        log("tab chatgpt.com belum ada - membuka...")
        sh([ADB, "-s", RN7, "shell",
            'am start -a android.intent.action.VIEW -d "https://chatgpt.com/" '
            f'-n {FENNEC}/org.mozilla.fenix.IntentReceiverActivity'])
        time.sleep(9)
        tabs = client.list_tabs()
        tab = next((t for t in tabs if "chatgpt.com" in (t.get("url") or "")), None)
    if tab is None:
        raise RuntimeError("gagal membuka tab chatgpt.com di RN7")
    return client.attach_tab(tab)


def js_json(client, console, body, timeout=90):
    # resolve() WAJIB: hasil besar datang sbg grip "longString", bukan string
    # biasa - lihat catatan di rdp.py.resolve().
    out = client.eval_async(console, body, timeout=timeout)
    return json.loads(client.resolve(out))


def check_login(client, console):
    d = js_json(client, console, """
      const res = await fetch('/api/auth/session', {credentials:'include'});
      const j = await res.json().catch(() => ({}));
      window.__rdp_out = JSON.stringify({ok: !!(j && j.user),
        email: (j && j.user && j.user.email) || null});
    """)
    if not d.get("ok"):
        raise RuntimeError("ChatGPT-web di RN7 TIDAK login - perlu login manual dulu "
                           "(SOP: kredensial diketik user sendiri, bukan oleh skrip)")
    return d["email"]


def fetch_list(client, console, limit):
    d = js_json(client, console, f"""
      const s = await (await fetch('/api/auth/session', {{credentials:'include'}})).json();
      const res = await fetch('/backend-api/conversations?offset=0&limit={limit}&order=updated', {{
        credentials:'include', headers:{{'Authorization':'Bearer '+s.accessToken}}}});
      const j = await res.json();
      window.__rdp_out = JSON.stringify({{total: j.total, items: (j.items||[]).map(c => ({{
        id: c.id, title: c.title, create_time: c.create_time, update_time: c.update_time}}))}});
    """)
    return d


def fetch_conversation(client, console, cid):
    return js_json(client, console, f"""
      const s = await (await fetch('/api/auth/session', {{credentials:'include'}})).json();
      const res = await fetch('/backend-api/conversation/{cid}', {{
        credentials:'include', headers:{{'Authorization':'Bearer '+s.accessToken}}}});
      const j = await res.json();
      const msgs = Object.values(j.mapping || {{}})
        .filter(n => n.message && n.message.content && n.message.content.parts)
        .map(n => ({{
          msg_id: n.message.id,
          role: (n.message.author && n.message.author.role) || 'unknown',
          created_at: n.message.create_time,
          content: n.message.content.parts.filter(p => typeof p === 'string').join('\\n')
        }}))
        .filter(m => m.content && m.content.trim())
        .sort((a,b) => (a.created_at||0) - (b.created_at||0));
      window.__rdp_out = JSON.stringify({{title: j.title, create_time: j.create_time,
        update_time: j.update_time, messages: msgs}});
    """, timeout=120)


# ---------------- muat ke Postgres ----------------

LOADER_SQL = r"""
BEGIN;
CREATE TEMP TABLE _in (doc jsonb) ON COMMIT DROP;
\copy _in (doc) FROM '%s' WITH (FORMAT csv, QUOTE E'\x01', DELIMITER E'\x02')

INSERT INTO conversations (id, source, account, title, created_at, updated_at, message_count, raw)
SELECT doc->>'id', doc->>'source', doc->>'account', doc->>'title',
       to_timestamp(NULLIF(doc->>'created_at','')::double precision),
       to_timestamp(NULLIF(doc->>'updated_at','')::double precision),
       COALESCE(NULLIF(doc->>'message_count','')::int, 0),
       doc->'raw'
FROM _in
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  updated_at = EXCLUDED.updated_at,
  message_count = EXCLUDED.message_count,
  harvested_at = now(),
  raw = EXCLUDED.raw;

INSERT INTO messages (conversation_id, msg_id, seq, role, created_at, content)
SELECT doc->>'id',
       m.value->>'msg_id',
       (m.ordinality)::int,
       m.value->>'role',
       to_timestamp(NULLIF(m.value->>'created_at','')::double precision),
       m.value->>'content'
FROM _in, LATERAL jsonb_array_elements(doc->'messages') WITH ORDINALITY AS m(value, ordinality)
ON CONFLICT (conversation_id, msg_id) DO NOTHING;
COMMIT;
"""


def load_payload(records):
    """Stream JSONL -> db-vps -> \\copy staging -> UPSERT."""
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    r = sshdb(["cat", ">", REMOTE_PAYLOAD], stdin_data=payload)
    if r.returncode != 0:
        raise RuntimeError(f"gagal kirim payload: {r.stderr.strip()[:200]}")
    r = sshdb(["psql", "-h", "127.0.0.1", "-U", "ai_chatlog", "-d", "ai_chatlog",
               "-v", "ON_ERROR_STOP=1", "-f", "-"],
              stdin_data=LOADER_SQL % REMOTE_PAYLOAD)
    if r.returncode != 0:
        raise RuntimeError(f"loader SQL gagal: {r.stdout.strip()[:400]} {r.stderr.strip()[:400]}")
    sshdb(["rm", "-f", REMOTE_PAYLOAD])


def existing_state():
    """id -> updated_at(epoch) yg sudah tersimpan, utk lewati yg tak berubah."""
    out = psql("SELECT id, COALESCE(EXTRACT(EPOCH FROM updated_at),0) FROM conversations "
               f"WHERE source = '{SOURCE}';")
    state = {}
    for line in out.splitlines():
        if "|" in line:
            cid, ts = line.split("|", 1)
            try:
                state[cid.strip()] = float(ts.strip())
            except ValueError:
                pass
    return state


def main():
    ap = argparse.ArgumentParser(description="Panen ChatGPT-web RN7 -> Postgres DB-VPS")
    ap.add_argument("--limit", type=int, default=100, help="ambil N percakapan teratas dr daftar")
    ap.add_argument("--max-new", type=int, default=25, help="batas percakapan diproses per run")
    ap.add_argument("--force", action="store_true", help="proses ulang walau update_time tak berubah")
    a = ap.parse_args()

    log("pastikan RDP RN7 siap...")
    ensure_rdp()
    from rdp import RDP
    client = RDP(port=RDP_PORT, timeout=40)
    try:
        console = open_chatgpt_tab(client)
        email = check_login(client, console)
        log(f"login OK sbg {email}")

        listing = fetch_list(client, console, a.limit)
        items = listing.get("items", [])
        log(f"{listing.get('total')} percakapan di akun, {len(items)} terambil di daftar")

        known = {} if a.force else existing_state()
        todo = [c for c in items
                if a.force or abs(known.get(c["id"], -1) - (to_epoch(c.get("update_time")) or 0)) > 1]
        log(f"{len(todo)} perlu diambil (baru/berubah); diproses maks {a.max_new}")
        todo = todo[:a.max_new]

        records = []
        for i, c in enumerate(todo, 1):
            try:
                full = fetch_conversation(client, console, c["id"])
            except Exception as e:
                log(f"  [{i}/{len(todo)}] GAGAL {c['title'][:40]!r}: {e}")
                continue
            msgs = full.get("messages", [])
            records.append({
                "id": c["id"], "source": SOURCE, "account": email,
                "title": full.get("title") or c.get("title"),
                "created_at": to_epoch(full.get("create_time") or c.get("create_time")),
                # WAJIB pakai update_time dari endpoint DAFTAR, bukan DETAIL.
                # Keduanya beda ~1,4 detik utk percakapan yg sama (detail selalu
                # sedikit lebih lambat) - kalau yg disimpan versi DETAIL tapi yg
                # dibandingkan tiap run versi DAFTAR, selisih itu bikin SEMUA
                # percakapan selalu dianggap "berubah" dan dipanen ulang terus.
                "updated_at": to_epoch(c.get("update_time")),
                "message_count": len(msgs),
                "messages": msgs,
                "raw": {"list_title": c.get("title"),
                        "detail_update_time": full.get("update_time")},
            })
            log(f"  [{i}/{len(todo)}] {(full.get('title') or '?')[:45]!r} - {len(msgs)} pesan")

        if not records:
            log("tak ada yg perlu disimpan.")
        else:
            load_payload(records)
            log(f"tersimpan/diperbarui: {len(records)} percakapan")

        tot = psql("SELECT (SELECT count(*) FROM conversations) || '|' || (SELECT count(*) FROM messages);")
        cc, mc = tot.split("|")
        log(f"DB sekarang: {cc} percakapan, {mc} pesan")
    finally:
        client.close()


if __name__ == "__main__":
    main()
