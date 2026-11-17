#!/usr/bin/env python3
"""
Panen percakapan asisten AI web di RN7 -> Postgres `ai_chatlog` (DB-VPS).
Sumber: chatgpt | claude. Menggantikan harvest-rn7-chatgpt.py yg hanya
menangani 1 sumber (file itu tetap ada & dipakai ulang sbg pustaka -
lihat impor di bawah, jadi logika DB/RDP tidak diduplikasi).

KENAPA TIAP SUMBER BEDA CARA (hasil probe langsung 2026-09-13):
  - chatgpt: backend-api rapi (daftar + detail), butuh Bearer token.
  - claude : JUGA punya API bersih -> /api/organizations/<org>/chat_conversations
             (+ detail `?tree=True&rendering_mode=messages`). Cukup cookie,
             TANPA Bearer. Peran pesan sudah terlabel di JSON.

CATATAN ISI AKUN saat dibangun: chatgpt 19 percakapan, claude 0. Adapter
claude sengaja tetap dibuat walau kosong supaya percakapan BARU otomatis
ikut terpanen.

⚠️ GEMINI DIHAPUS PERMANEN 2026-11-08: RN7 TAK PERNAH login akun Google di
perangkatnya - bukan soal kalibrasi/timing, adapter gemini (DOM-scraping +
fallback real-tap OS-level) SELALU gagal buka drawer riwayat, diverifikasi
ulang 8/11 (koordinat tap terbukti presisi lewat pengukuran screenshot,
tapi drawer tetap tak pernah terbuka). Bukan kegagalan sementara yg bisa
diperbaiki kalibrasi ulang -> dihapus drpd terus gagal tiap hari. Riwayat
implementasi lama: lihat `harvest-rn7-ai.py.bak-20260920` / git log.
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Pakai ulang seluruh mesin DB + RDP dari skrip chatgpt (jangan duplikasi):
# to_epoch, psql, load_payload, ensure_rdp, js_json, log, dll.
_spec = importlib.util.spec_from_file_location("cg", os.path.join(HERE, "harvest-rn7-chatgpt.py"))
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

log, to_epoch, psql, load_payload = cg.log, cg.to_epoch, cg.psql, cg.load_payload
ensure_rdp, js_json, RDP_PORT = cg.ensure_rdp, cg.js_json, cg.RDP_PORT
# (code-review fix #11) open_tab dipindah ke harvest-rn7-chatgpt.py supaya
# main() standalone skrip itu JUGA dapat hardening retry/poll yg sama --
# dulu ada 2 implementasi (satu di-harden di sini, satu lama di sana).
open_tab = cg.open_tab


# ----------------------------- CHATGPT -----------------------------

def harvest_chatgpt(client, max_new, force, known, skip):
    console = open_tab(client, "chatgpt.com", "https://chatgpt.com/")
    email, token = cg.check_login(client, console)
    listing = cg.fetch_list(client, console, 100, token)
    items = listing.get("items", [])
    log(f"chatgpt: {listing.get('total')} percakapan di akun")
    todo = [c for c in items
            if force or c["id"] not in known
            or abs(known[c["id"]] - (to_epoch(c.get("update_time")) or 0)) > 1]
    todo = [c for c in todo if c["id"] not in skip][:max_new]
    out = []
    for i, c in enumerate(todo, 1):
        try:
            full = cg.fetch_conversation(client, console, c["id"], token)
        except Exception as e:
            log(f"  chatgpt [{i}/{len(todo)}] GAGAL {str(c.get('title'))[:40]!r}: {e}")
            continue
        msgs = full.get("messages", [])
        out.append({"id": c["id"], "source": "chatgpt", "account": email,
                    "title": full.get("title") or c.get("title"),
                    "created_at": to_epoch(full.get("create_time") or c.get("create_time")),
                    # WAJIB pakai update_time dari endpoint DAFTAR (`c`), bukan
                    # DETAIL (`full`) - lihat harvest-rn7-chatgpt.py:344-349.
                    # Keduanya beda ~1,4 detik utk percakapan yg sama; kalau yg
                    # disimpan versi DETAIL tapi yg dibandingkan tiap run versi
                    # DAFTAR (baris 92 di atas), selisih itu bikin SEMUA
                    # percakapan selalu dianggap "berubah" & dipanen ulang terus.
                    "updated_at": to_epoch(c.get("update_time")),
                    "message_count": len(msgs), "messages": msgs,
                    "raw": {"detail_update_time": full.get("update_time")}})
        log(f"  chatgpt [{i}/{len(todo)}] {(full.get('title') or '?')[:42]!r} - {len(msgs)} pesan")
    return out


# ----------------------------- CLAUDE ------------------------------

def harvest_claude(client, max_new, force, known, skip):
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

    todo = [c for c in items
            if force or c["id"] not in known
            or abs(known[c["id"]] - (to_epoch(c.get("updated")) or 0)) > 1]
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


# ------------------------------ umum -------------------------------

# (code-review fix #9/#14) existing() dihapus dari sini -- dulu duplikat
# nyaris baris-per-baris dari existing_state() di harvest-rn7-chatgpt.py,
# cuma beda parameter source. Sekarang pakai cg.existing_state(sources)
# langsung (sudah digeneralisasi nerima BEBERAPA source dlm SATU query).

def ignored(sources):
    """source -> {id, ...} yg SENGAJA tak mau diarsipkan (mis. percakapan uji
    coba yg sudah dibersihkan manual). WAJIB dihormati tiap panen - tanpa
    ini, menghapus baris di database percuma: sumbernya masih ada di akun
    AI, jadi panen berikutnya menariknya kembali.

    (code-review fix #9) Digeneralisasi nerima BEBERAPA source sekaligus
    dlm SATU query, sama pola dgn cg.existing_state() -- dulu 1 query per
    source (3x round-trip SSH utk 3 source, sekarang 1x)."""
    src_list = ",".join(f"'{s}'" for s in sources)
    out = psql(f"SELECT source, id FROM ignored_conversations WHERE source IN ({src_list});")
    skip = {s: set() for s in sources}
    for line in out.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2:
            src, cid = parts
            skip.setdefault(src.strip(), set()).add(cid.strip())
    return skip


ADAPTERS = {"chatgpt": harvest_chatgpt, "claude": harvest_claude}


def main():
    ap = argparse.ArgumentParser(description="Panen percakapan AI web RN7 -> Postgres")
    ap.add_argument("--source", choices=list(ADAPTERS), action="append",
                    help="boleh diulang; default: semua")
    ap.add_argument("--max-new", type=int, default=25)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    sources = a.source or list(ADAPTERS)

    log("pastikan RDP RN7 siap...")
    ensure_rdp()
    from rdp import RDP
    client = RDP(port=RDP_PORT, timeout=40)

    # (code-review fix #9) dulu existing()/ignored() dipanggil 1x PER SOURCE
    # (6 round-trip SSH utk 3 source) dan load_payload() juga 1x per source
    # (3 round-trip cat/psql/rm lagi) -- sekarang dedup di-fetch SEKALI utk
    # SEMUA source diminta (2 query total), dan payload semua source yg
    # berhasil digabung lalu di-load SEKALI di akhir (bukan per-source).
    # Trade-off yg disadari: kalau proses mati total di tengah (bukan error
    # per-source yg sudah ditangani try/except di bawah), record source yg
    # SUDAH berhasil dipanen tapi BELUM sempat ter-load jadi tertunda ke run
    # berikutnya -- bukan hilang (existing_state() blm mencatatnya sbg known,
    # jadi otomatis dipanen ulang), cuma telat satu siklus cron.
    known_all = {s: {} for s in sources} if a.force else cg.existing_state(sources)
    skip_all = ignored(sources)

    results = {}
    all_records = []
    try:
        for src in sources:
            try:
                recs = ADAPTERS[src](client, a.max_new, a.force,
                                      known_all.get(src, {}), skip_all.get(src, set()))
                all_records.extend(recs)
                results[src] = len(recs)
                log(f"{src}: {len(recs)} percakapan dipanen")
            except (ConnectionError, OSError) as e:
                # HARDEN (code-review fix #3): dulu client RDP yg sudah MATI
                # (mis. adb-over-WireGuard glitch) tetap dipakai ulang tanpa
                # reconnect utk source berikutnya -> satu glitch jaringan
                # sesaat bikin SEMUA source sisa gagal, masing2 dilaporkan
                # sbg kegagalan independen yg tak berhubungan. Sekarang:
                # kegagalan TRANSPORT (socket putus, bukan error aplikasi
                # spt "tak login") memicu reconnect sebelum lanjut.
                log(f"{src}: GAGAL (transport RDP putus): {e} -- reconnect sebelum lanjut...")
                results[src] = f"error (transport): {e}"
                try:
                    client.close()
                except Exception:
                    pass
                try:
                    ensure_rdp()
                    client = RDP(port=RDP_PORT, timeout=40)
                    log("reconnect RDP berhasil, lanjut ke source berikutnya.")
                except Exception as e2:
                    log(f"reconnect RDP GAGAL: {e2} -- source sisa kemungkinan ikut gagal.")
            except Exception as e:
                log(f"{src}: GAGAL TOTAL: {e}")
                results[src] = f"error: {e}"
    finally:
        client.close()

    if all_records:
        load_payload(all_records)
        log(f"tersimpan/diperbarui: {len(all_records)} percakapan (semua source digabung)")
    else:
        log("tak ada yg perlu disimpan.")

    tot = psql("SELECT (SELECT count(*) FROM conversations) || '|' || (SELECT count(*) FROM messages);")
    cc, mc = tot.split("|")
    log(f"DB sekarang: {cc} percakapan, {mc} pesan")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
