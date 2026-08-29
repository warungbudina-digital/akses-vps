#!/usr/bin/env python3
"""
Semantic search over the ogis-vault knowledge base built by ingest.py.
Pure stdlib (no numpy) — adapted 1:1 from Pi4B ~/vault-search/search.py.

Usage:
  python3 search.py "how do I decrypt WPA2 traffic"
  python3 search.py --domain scrape-example "..."
  python3 search.py --full "correlation rule anatomy"
"""
import os, sys, json, sqlite3, math, argparse, urllib.request

MODEL = "nomic-embed-text"

def embed(host, text):
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(host + "/api/embed", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["embeddings"][0] if "embeddings" in d else d["embedding"]

def cosine(a, b):
    dot = sa = sb = 0.0
    for x, y in zip(a, b):
        dot += x * y; sa += x * x; sb += y * y
    return 0.0 if sa == 0 or sb == 0 else dot / (math.sqrt(sa) * math.sqrt(sb))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--db", default=os.path.expanduser("~/ogis-vault/index.db"))
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--vault", default=None, help="restrict to a vault label")
    ap.add_argument("--domain", default=None, help="restrict to a domain (profil browser)")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    qv = embed(a.host, "search_query: " + a.query)

    con = sqlite3.connect(a.db)
    where, args = [], []
    if a.vault:
        where.append("vault=?"); args.append(a.vault)
    if a.domain:
        where.append("domain=?"); args.append(a.domain)
    sql = "SELECT vault,domain,title,section,source_urls,text,embedding FROM chunks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = con.execute(sql, args).fetchall()
    con.close()

    scored = [(cosine(qv, json.loads(r[6]), ), *r[:6]) for r in rows]
    scored.sort(reverse=True, key=lambda x: x[0])

    scope = []
    if a.vault:  scope.append(f"vault={a.vault}")
    if a.domain: scope.append(f"domain={a.domain}")
    scope = ("  [" + ", ".join(scope) + "]") if scope else ""
    print(f'\nQuery: "{a.query}"{scope}   ({len(rows)} chunks searched)\n' + "=" * 72)
    for i, (score, vault, domain, title, section, srcs, text) in enumerate(scored[:a.k], 1):
        try:
            src = (json.loads(srcs) or [""])[0]
        except Exception:
            src = ""
        print(f"\n#{i}  score={score:.3f}  [{vault}:{domain}]  {title} > {section}")
        if src:
            print(f"    source: {src}")
        snippet = text if a.full else " ".join(text.split())[:300] + ("..." if len(text) > 300 else "")
        for line in (snippet.splitlines() if a.full else [snippet]):
            print("    " + line)
    print()

if __name__ == "__main__":
    main()
