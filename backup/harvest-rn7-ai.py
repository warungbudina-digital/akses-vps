#!/usr/bin/env python3
"""
Panen percakapan SEMUA asisten AI web di RN7 -> Postgres `ai_chatlog` (DB-VPS).
Sumber: chatgpt | claude | gemini. Menggantikan harvest-rn7-chatgpt.py yg
hanya menangani 1 sumber (file itu tetap ada & dipakai ulang sbg pustaka -
lihat impor di bawah, jadi logika DB/RDP tidak diduplikasi).

KENAPA TIAP SUMBER BEDA CARA (hasil probe langsung 2026-09-13):
  - chatgpt: backend-api rapi (daftar + detail), butuh Bearer token.
  - claude : JUGA punya API bersih -> /api/organizations/<org>/chat_conversations
             (+ detail `?tree=True&rendering_mode=messages`). Cukup cookie,
             TANPA Bearer. Peran pesan sudah terlabel di JSON.
  - gemini : TIDAK punya API yg bisa dipakai -> terpaksa DOM.
             ⚠️ Jebakan yg memakan waktu: tombol pembuka daftar riwayat itu
             `[aria-label="Menu utama"]`. Tombol `side-nav-sparkle-button`
             ("Buka sidebar") TAMPAK benar tapi TIDAK memunculkan seksi
             "Terbaru" - sempat menyesatkan sampai dikira akunnya kosong.
             Setelah menu utama dibuka: `a[href^="/app/"]` = daftar
             percakapan (href -> id, teks -> judul). Isi percakapan dibaca
             dr `user-query` (giliran user) & `model-response` (giliran AI).

CATATAN ISI AKUN saat dibangun: chatgpt 19 percakapan, claude 0, gemini 0
(lalu 1 setelah percakapan uji dibuat). Adapter claude/gemini sengaja tetap
dibuat walau kosong supaya percakapan BARU otomatis ikut terpanen.

⚠️ Gemini JAUH lebih lambat & rapuh drpd 2 lainnya (buka tiap percakapan satu
per satu di browser sungguhan, bukan 1 panggilan API) - karena itu ada
`--max-new` terpisah dan kegagalan 1 percakapan tidak menggagalkan sisanya.
"""
import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Pakai ulang seluruh mesin DB + RDP dari skrip chatgpt (jangan duplikasi):
# to_epoch, psql, load_payload, ensure_rdp, js_json, log, dll.
_spec = importlib.util.spec_from_file_location("cg", os.path.join(HERE, "harvest-rn7-chatgpt.py"))
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

log, to_epoch, psql, load_payload = cg.log, cg.to_epoch, cg.psql, cg.load_payload
ensure_rdp, js_json, sh = cg.ensure_rdp, cg.js_json, cg.sh
ADB, RN7, FENNEC, RDP_PORT = cg.ADB, cg.RN7, cg.FENNEC, cg.RDP_PORT


def open_tab(client, url_match, url_open, tries=3):
    """Cari tab yg URL-nya memuat `url_match`; buka `url_open` kalau belum ada.

    HARDEN 2026-09-20: jam 05:00 (load RN7 tinggi / Fennec baru di-restart oleh
    ensure_rdp) tab sering belum muncul dlm sleep tetap 10 dtk -> dulu langsung
    "gagal membuka tab" & harvest gagal total. Sekarang: retry `am start`
    beberapa kali, tiap kali POLLING daftar tab (bukan tidur tunggal) sampai
    tab muncul. Idempoten: kalau tab keburu ada, langsung pakai."""
    def find():
        tabs = client.list_tabs()
        return next((t for t in tabs if url_match in (t.get("url") or "")), None)

    tab = find()
    if tab is not None:
        return client.attach_tab(tab)

    for attempt in range(1, tries + 1):
        log(f"tab {url_match} belum ada - membuka (coba {attempt}/{tries})...")
        sh([ADB, "-s", RN7, "shell",
            f'am start -a android.intent.action.VIEW -d "{url_open}" '
            f'-n {FENNEC}/org.mozilla.fenix.IntentReceiverActivity'])
        for _ in range(8):            # polling ~24 dtk per percobaan
            time.sleep(3)
            tab = find()
            if tab is not None:
                return client.attach_tab(tab)
    raise RuntimeError(f"gagal membuka tab {url_open}")


# ----------------------------- CHATGPT -----------------------------

def harvest_chatgpt(client, max_new, force):
    console = open_tab(client, "chatgpt.com", "https://chatgpt.com/")
    email = cg.check_login(client, console)
    listing = cg.fetch_list(client, console, 100)
    items = listing.get("items", [])
    log(f"chatgpt: {listing.get('total')} percakapan di akun")
    skip = ignored("chatgpt")
    known = {} if force else existing("chatgpt")
    todo = [c for c in items
            if force or abs(known.get(c["id"], -1) - (to_epoch(c.get("update_time")) or 0)) > 1]
    todo = [c for c in todo if c["id"] not in skip][:max_new]
    out = []
    for i, c in enumerate(todo, 1):
        try:
            full = cg.fetch_conversation(client, console, c["id"])
        except Exception as e:
            log(f"  chatgpt [{i}/{len(todo)}] GAGAL {str(c.get('title'))[:40]!r}: {e}")
            continue
        msgs = full.get("messages", [])
        out.append({"id": c["id"], "source": "chatgpt", "account": email,
                    "title": full.get("title") or c.get("title"),
                    "created_at": to_epoch(full.get("create_time") or c.get("create_time")),
                    "updated_at": to_epoch(c.get("update_time")),
                    "message_count": len(msgs), "messages": msgs,
                    "raw": {"detail_update_time": full.get("update_time")}})
        log(f"  chatgpt [{i}/{len(todo)}] {(full.get('title') or '?')[:42]!r} - {len(msgs)} pesan")
    return out


# ----------------------------- CLAUDE ------------------------------

def harvest_claude(client, max_new, force):
    console = open_tab(client, "claude.ai", "https://claude.ai/new")
    info = js_json(client, console, """
      const res = await fetch('/api/organizations', {credentials:'include'});
      const orgs = await res.json().catch(() => null);
      window.__rdp_out = JSON.stringify({status: res.status,
        org: Array.isArray(orgs) && orgs.length ? orgs[0].uuid : null,
        name: Array.isArray(orgs) && orgs.length ? orgs[0].name : null});
    """)
    if not info.get("org"):
        raise RuntimeError(f"Claude tak login / organisasi tak terbaca (HTTP {info.get('status')})")
    org = info["org"]
    account = (info.get("name") or "").replace("'s Organization", "") or "?"
    log(f"claude: organisasi {account}")

    lst = js_json(client, console, f"""
      const res = await fetch('/api/organizations/{org}/chat_conversations', {{credentials:'include'}});
      const j = await res.json();
      window.__rdp_out = JSON.stringify({{n: j.length, items: j.map(x => ({{
        id: x.uuid, title: x.name, created: x.created_at, updated: x.updated_at}}))}});
    """, timeout=90)
    items = lst.get("items", [])
    log(f"claude: {lst.get('n')} percakapan di akun")

    skip = ignored("claude")
    known = {} if force else existing("claude")
    todo = [c for c in items
            if force or abs(known.get(c["id"], -1) - (to_epoch(c.get("updated")) or 0)) > 1]
    todo = [c for c in todo if c["id"] not in skip][:max_new]
    out = []
    for i, c in enumerate(todo, 1):
        try:
            d = js_json(client, console, f"""
              const res = await fetch('/api/organizations/{org}/chat_conversations/{c["id"]}'
                 + '?tree=True&rendering_mode=messages', {{credentials:'include'}});
              const j = await res.json();
              const msgs = (j.chat_messages || []).map(m => ({{
                msg_id: m.uuid,
                role: m.sender === 'human' ? 'user' : 'assistant',
                created_at: m.created_at,
                content: (m.content || []).filter(p => p.type === 'text')
                          .map(p => p.text).join('\\n') || (m.text || '')
              }})).filter(m => m.content && m.content.trim());
              window.__rdp_out = JSON.stringify({{title: j.name, created: j.created_at,
                updated: j.updated_at, messages: msgs}});
            """, timeout=120)
        except Exception as e:
            log(f"  claude [{i}/{len(todo)}] GAGAL {str(c.get('title'))[:40]!r}: {e}")
            continue
        msgs = d.get("messages", [])
        for k, m in enumerate(msgs, 1):
            m["created_at"] = to_epoch(m.get("created_at"))
        out.append({"id": c["id"], "source": "claude", "account": account,
                    "title": d.get("title") or c.get("title"),
                    "created_at": to_epoch(d.get("created") or c.get("created")),
                    "updated_at": to_epoch(c.get("updated")),
                    "message_count": len(msgs), "messages": msgs, "raw": {}})
        log(f"  claude [{i}/{len(todo)}] {(d.get('title') or '?')[:42]!r} - {len(msgs)} pesan")
    return out


# ----------------------------- GEMINI ------------------------------

def harvest_gemini(client, max_new, force):
    console = open_tab(client, "gemini.google", "https://gemini.google.com/app")
    # Mulai dari kondisi yg PASTI. Panen sebelumnya meninggalkan tab di
    # halaman percakapan (/app/<id>); membaca menu dari sana bisa menggantung
    # (kejadian nyata: "hasil async tak kunjung terisi"). Kembalikan dulu ke
    # /app, lalu attach ULANG krn navigasi menghancurkan konteks JS.
    try:
        client.eval_js(console, "location.href='https://gemini.google.com/app';", timeout=10)
    except Exception:
        pass
    time.sleep(9)
    console = open_tab(client, "gemini.google", "https://gemini.google.com/app")
    # Buka MENU UTAMA lalu baca daftarnya DALAM SATU panggilan JS.
    # ⚠️ Jangan dipisah jadi 2 panggilan: menunya keburu tertutup di antara
    # keduanya sehingga daftar terbaca 0 (akun tampak kosong padahal ada) -
    # jebakan nyata saat pengujian.
    # Tombolnya `[aria-label="Menu utama"]`; `side-nav-sparkle-button`
    # ("Buka sidebar") TIDAK memunculkan seksi "Terbaru".
    lst = js_json(client, console, """
      const bacaLink = () => {
        const links = [...document.querySelectorAll('a[href^="/app/"]')]
          .map(a => ({id: (a.getAttribute('href')||'').split('/app/')[1],
                      title: (a.innerText||'').trim()}))
          .filter(x => x.id && x.title);
        const seen = new Set(); const out = [];
        for (const l of links) { if (!seen.has(l.id)) { seen.add(l.id); out.push(l); } }
        return out;
      };
      // Menu utama itu TOGGLE: kalau daftar sudah tampak, JANGAN diklik lagi
      // (klik kedua menutupnya -> daftar terbaca 0 dan akun tampak kosong).
      // SPA Gemini butuh waktu hidrasi setelah navigasi: tombol menu bisa
      // BELUM ADA saat percobaan pertama. Coba beberapa kali, dan klik HANYA
      // kalau daftar memang belum tampak (menu bersifat toggle).
      let items = bacaLink();
      for (let att = 0; att < 4 && !items.length; att++) {
        const b = document.querySelector('[aria-label="Menu utama"]')
               || document.querySelector('[aria-label="Main menu"]');
        if (b) b.click();
        await new Promise(r => setTimeout(r, 4000));
        items = bacaLink();
      }
      // Bedakan "daftar memang kosong" dari "tak bisa dibaca". Tanpa ini,
      // halaman yg gagal hidrasi melaporkan 0 dan TAMPAK sehat padahal
      // sebenarnya buta - bug senyap yg paling berbahaya di pipeline ini.
      const menuAda = !!(document.querySelector('[aria-label="Menu utama"]')
                      || document.querySelector('[aria-label="Main menu"]'));
      window.__rdp_out = JSON.stringify({n: items.length, items, menuAda});
    """, timeout=90)
    items = lst.get("items", [])
    if not items and not lst.get("menuAda"):
        # Halaman tak ter-render penuh -> JANGAN laporkan "0" seolah akun kosong.
        raise RuntimeError("daftar Gemini TAK BISA DIBACA (tombol 'Menu utama' tak ada - "
                           "halaman belum ter-render penuh). Bukan berarti akun kosong.")
    log(f"gemini: {len(items)} percakapan terlihat di daftar 'Terbaru'")

    # Gemini tak memberi timestamp di daftar -> dedup pakai KEBERADAAN id saja.
    # Konsekuensinya percakapan lama yg DILANJUTKAN tak otomatis ter-refresh;
    # pakai --force kalau perlu ambil ulang.
    skip = ignored("gemini")
    known = set() if force else set(existing("gemini").keys())
    todo = [c for c in items
            if (force or c["id"] not in known) and c["id"] not in skip][:max_new]
    out = []
    for i, c in enumerate(todo, 1):
        try:
            # Navigasi MENGHANCURKAN konteks JS -> perintah pindah halaman
            # dikirim "tembak-lalu-lupakan", ditunggu dr sisi Python, baru
            # tab di-attach ULANG dan isinya dibaca di konteks yg baru.
            # (Membaca hasil di panggilan yg sama SELALU gagal: balasannya
            # bukan string JSON lagi - jebakan nyata saat pengujian.)
            try:
                client.eval_js(console, f"location.href='/app/{c['id']}';", timeout=10)
            except Exception:
                pass
            time.sleep(9)
            console = open_tab(client, "gemini.google", "https://gemini.google.com/app")
            d = js_json(client, console, r"""
              // DOM Gemini menyisipkan label aksesibilitas di awal tiap
              // pesan ("Anda berkata" / "Gemini berkata", versi Inggris
              // "You said" / "Gemini said") - itu bukan isi percakapan,
              // dibuang supaya arsipnya bersih.
              const bersih = t => (t||'').trim()
                .replace(/^(Anda berkata|You said|Gemini berkata|Gemini said)\s*/i, '')
                .trim();
              const users = [...document.querySelectorAll('user-query')]
                  .map(e => bersih(e.innerText)).filter(Boolean);
              const bots  = [...document.querySelectorAll('model-response')]
                  .map(e => bersih(e.innerText)).filter(Boolean);
              const msgs = [];
              const n = Math.max(users.length, bots.length);
              for (let k = 0; k < n; k++) {
                if (users[k]) msgs.push({role:'user', content: users[k]});
                if (bots[k])  msgs.push({role:'assistant', content: bots[k]});
              }
              window.__rdp_out = JSON.stringify({title: document.title, messages: msgs});
            """, timeout=90)
        except Exception as e:
            log(f"  gemini [{i}/{len(todo)}] GAGAL {c['title'][:40]!r}: {e}")
            continue
        msgs = d.get("messages", [])
        # DOM tak memberi id/waktu per-pesan -> pakai urutan sbg identitas stabil
        for k, m in enumerate(msgs, 1):
            m["msg_id"] = f"{c['id']}-{k}"
            m["created_at"] = None
        if not msgs:
            log(f"  gemini [{i}/{len(todo)}] {c['title'][:42]!r} - KOSONG, dilewati")
            continue
        out.append({"id": c["id"], "source": "gemini", "account": "clawapp810@gmail.com",
                    "title": c["title"], "created_at": None, "updated_at": time.time(),
                    "message_count": len(msgs), "messages": msgs,
                    "raw": {"catatan": "diekstrak dari DOM; waktu per-pesan tak tersedia"}})
        log(f"  gemini [{i}/{len(todo)}] {c['title'][:42]!r} - {len(msgs)} pesan")
    return out


# ------------------------------ umum -------------------------------

def existing(source):
    out = psql("SELECT id, COALESCE(EXTRACT(EPOCH FROM updated_at),0) FROM conversations "
               f"WHERE source = '{source}';")
    st = {}
    for line in out.splitlines():
        if "|" in line:
            cid, ts = line.split("|", 1)
            try:
                st[cid.strip()] = float(ts.strip())
            except ValueError:
                pass
    return st


def ignored(source):
    """Id yg SENGAJA tak mau diarsipkan (mis. percakapan uji coba yg sudah
    dibersihkan manual). WAJIB dihormati tiap panen - tanpa ini, menghapus
    baris di database percuma: sumbernya masih ada di akun AI, jadi panen
    berikutnya menariknya kembali."""
    out = psql(f"SELECT id FROM ignored_conversations WHERE source = '{source}';")
    return {l.strip() for l in out.splitlines() if l.strip()}


ADAPTERS = {"chatgpt": harvest_chatgpt, "claude": harvest_claude, "gemini": harvest_gemini}


def main():
    ap = argparse.ArgumentParser(description="Panen percakapan AI web RN7 -> Postgres")
    ap.add_argument("--source", choices=list(ADAPTERS), action="append",
                    help="boleh diulang; default: semua")
    ap.add_argument("--max-new", type=int, default=25)
    ap.add_argument("--gemini-max-new", type=int, default=5,
                    help="Gemini jauh lebih lambat (buka tiap percakapan di browser)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    sources = a.source or list(ADAPTERS)

    log("pastikan RDP RN7 siap...")
    ensure_rdp()
    from rdp import RDP
    client = RDP(port=RDP_PORT, timeout=40)
    results = {}
    try:
        for src in sources:
            cap = a.gemini_max_new if src == "gemini" else a.max_new
            try:
                recs = ADAPTERS[src](client, cap, a.force)
                if recs:
                    load_payload(recs)
                results[src] = len(recs)
                log(f"{src}: {len(recs)} percakapan disimpan/diperbarui")
            except Exception as e:
                log(f"{src}: GAGAL TOTAL: {e}")
                results[src] = f"error: {e}"
    finally:
        client.close()

    tot = psql("SELECT (SELECT count(*) FROM conversations) || '|' || (SELECT count(*) FROM messages);")
    cc, mc = tot.split("|")
    log(f"DB sekarang: {cc} percakapan, {mc} pesan")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
