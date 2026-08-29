#!/usr/bin/env python3
"""Embed inkremental SATU domain ke index.db ogis-vault yang SUDAH ADA (tanpa
drop+rebuild). Adaptasi 1:1 dari Pi4B ~/vault-search/ingest-append.py — pakai
ulang parse_frontmatter/chunk_body/embed dari ingest.py agar identik.
Idempoten: hapus dulu chunk domain ini kalau sudah ada, lalu sisipkan ulang.

Usage: python3 ingest-append.py <domain>   # domain = nama profil browser,
                                            # baca ~/ogis-vault/wiki/<domain>/*.md
"""
import os, sys, json, sqlite3, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest

DOMAIN = sys.argv[1] if len(sys.argv) > 1 else "scrape-example"
DDIR   = os.path.expanduser(f"~/ogis-vault/wiki/{DOMAIN}")
DB     = os.path.expanduser("~/ogis-vault/index.db")
HOST   = "http://127.0.0.1:11434"
VAULT  = "scrape"

con = sqlite3.connect(DB)
before = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
con.execute("DELETE FROM chunks WHERE domain=?", (DOMAIN,)); con.commit()

files = sorted(os.path.join(DDIR, f) for f in os.listdir(DDIR) if f.endswith(".md"))
t0, nd, nc = time.time(), 0, 0
for path in files:
    meta, body = ingest.parse_frontmatter(open(path, encoding="utf-8").read())
    if str(meta.get("corpus", "")).lower() != "true":
        continue
    nd += 1
    doc_id = meta.get("id", os.path.basename(path))
    domain = meta.get("domain", "")
    title  = meta.get("title", doc_id)
    src    = meta.get("source_urls", [])
    src    = json.dumps(src if isinstance(src, list) else [src])
    for sect, ctext in ingest.chunk_body(body):
        payload = f"[{domain}] {title} > {sect}\n{ctext}"
        vec = ingest.embed(HOST, "search_document: " + payload)
        con.execute("INSERT INTO chunks(vault,doc_id,domain,title,section,source_urls,text,embedding)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (VAULT, doc_id, domain, title, sect, src, payload, json.dumps(vec)))
        nc += 1
        print(f"  [{nc:2d}] {domain}/{title[:22]:22s} > {sect[:30]}", flush=True)
    con.commit()
after = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
con.close()
print(f"\nDONE: {nd} notes, {nc} chunks baru dlm {time.time()-t0:.1f}s. Index {before} -> {after} total.")
