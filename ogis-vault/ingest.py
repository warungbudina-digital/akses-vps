#!/usr/bin/env python3
"""
Ingest the ogis-vault knowledge base into a SQLite semantic-search index using
Ollama's nomic-embed-text. Pure stdlib (no pip deps) — adapted 1:1 from Pi4B
~/vault-search/ingest.py (same chunking/frontmatter/embed logic, already
proven there — do NOT redesign, only the default paths/vault label changed).

Walks vault roots (default: scrape:~/ogis-vault/wiki). Only notes with
`corpus: true` are embedded. Body is chunked by H2 section. Each chunk is
embedded with the required "search_document: " nomic prefix and tagged with
its vault + domain.

Usage:
  python3 ingest.py                                   # default vault
  python3 ingest.py --vault scrape:~/ogis-vault/wiki  # explicit override
  python3 ingest.py --db index.db --host http://127.0.0.1:11434
"""
import os, re, sys, json, sqlite3, time, argparse, urllib.request

MODEL = "nomic-embed-text"

def embed(host, text):
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(host + "/api/embed", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["embeddings"][0] if "embeddings" in d else d["embedding"]

def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n").splitlines()
    body = text[end+4:].lstrip("\n")
    meta, i = {}, 0
    while i < len(fm):
        m = re.match(r'^(\w+):\s*(.*)$', fm[i])
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in (">", "|", ""):
                block, j = [], i + 1
                while j < len(fm) and (fm[j].startswith("  ") or fm[j].strip() == ""):
                    block.append(fm[j].strip()); j += 1
                items = [b[2:].strip().strip('"') for b in block if b.startswith("- ")]
                meta[key] = items if items else " ".join(x for x in block if x)
                i = j; continue
            meta[key] = val.strip().strip('"')
        i += 1
    return meta, body

def chunk_body(body, max_words=850):
    # split by H2 heading
    lines = body.splitlines()
    secs, cur_title, cur = [], "(intro)", []
    for ln in lines:
        if ln.startswith("# "):
            continue
        if ln.startswith("## "):
            if any(x.strip() for x in cur):
                secs.append((cur_title, "\n".join(cur).strip()))
            cur_title, cur = ln[3:].strip(), []
        else:
            cur.append(ln)
    if any(x.strip() for x in cur):
        secs.append((cur_title, "\n".join(cur).strip()))
    # secondary split: keep every chunk under ~max_words (nomic 8192-token safety)
    out = []
    for t, c in secs:
        if len(c) <= 15:
            continue
        if len(c.split()) <= max_words:
            out.append((t, c)); continue
        # break oversized section at paragraph boundaries, hard-splitting huge paras
        units = []
        for p in (re.split(r'\n\s*\n', c) or [c]):
            if not p.strip():
                continue
            w = p.split()
            if len(w) > max_words:
                for i in range(0, len(w), max_words):
                    units.append(" ".join(w[i:i+max_words]))
            else:
                units.append(p.strip())
        buf, wc, part = [], 0, 1
        for u in units:
            uw = len(u.split())
            if wc + uw > max_words and buf:
                out.append((f"{t} (part {part})", "\n\n".join(buf)))
                part += 1; buf, wc = [], 0
            buf.append(u); wc += uw
        if buf:
            out.append((f"{t} (part {part})" if part > 1 else t, "\n\n".join(buf)))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", action="append", default=None,
                    help="label:path (repeatable). Default: scrape:~/ogis-vault/wiki")
    ap.add_argument("--db", default=os.path.expanduser("~/ogis-vault/index.db"))
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args()

    vaults = a.vault or ["scrape:~/ogis-vault/wiki"]
    roots = []
    for v in vaults:
        label, _, path = v.partition(":")
        roots.append((label, os.path.expanduser(path)))

    con = sqlite3.connect(a.db)
    con.execute("DROP TABLE IF EXISTS chunks")
    con.execute("""CREATE TABLE chunks(
        id INTEGER PRIMARY KEY, vault TEXT, doc_id TEXT, domain TEXT, title TEXT,
        section TEXT, source_urls TEXT, text TEXT, embedding TEXT)""")

    t0, n_doc, n_chunk = time.time(), 0, 0
    for vault, root in roots:
        if not os.path.isdir(root):
            print(f"(skip missing vault {vault} -> {root})"); continue
        files = sorted(os.path.join(dp, f)
                       for dp, _, fs in os.walk(root) for f in fs if f.endswith(".md"))
        for path in files:
            meta, body = parse_frontmatter(open(path, encoding="utf-8").read())
            if str(meta.get("corpus", "")).lower() != "true":
                continue
            n_doc += 1
            doc_id = meta.get("id", os.path.relpath(path, root))
            domain = meta.get("domain", "")
            title = meta.get("title", doc_id)
            src = meta.get("source_urls", [])
            src = json.dumps(src if isinstance(src, list) else [src])
            for sect, ctext in chunk_body(body):
                payload = f"[{domain}] {title} > {sect}\n{ctext}"
                vec = embed(a.host, "search_document: " + payload)
                con.execute("INSERT INTO chunks(vault,doc_id,domain,title,section,source_urls,text,embedding)"
                            " VALUES(?,?,?,?,?,?,?,?)",
                            (vault, doc_id, domain, title, sect, src, payload, json.dumps(vec)))
                n_chunk += 1
                print(f"  [{n_chunk:3d}] {vault}:{domain}/{title[:26]:26s} > {sect[:30]}", flush=True)
            con.commit()
    con.close()
    print(f"\nDONE: {n_doc} notes, {n_chunk} chunks in {time.time()-t0:.1f}s -> {a.db}")

if __name__ == "__main__":
    main()
