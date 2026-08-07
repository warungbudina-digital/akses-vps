#!/usr/bin/env python3
"""browser_enqueue.py — jembatan HULU: scrape URL video via browser API (.60)
lalu masukkan ke antrean media.video_ingest lewat enqueue.py.

Jalan di akses-vps. Panggil `full-tool-browser` di .60 (http://10.66.66.60:8080):
  POST /scraper/jobs {platform,targetUrl} -> job async -> poll GET /scraper/jobs/:id
  sampai status 'done'/'failed' -> ambil posts[].postUrl -> pipe ke enqueue.py.

⚠️ GAGAL SENYAP: scraper sosial dari IP datacenter sering kena CAPTCHA (TikTok)
/ login-wall (IG). Gejalanya job 'done' TAPI posts=[] (result_count 0). Skrip ini
TIDAK menelan itu — exit code 4 + pesan jelas + saran fallback manual enqueue.py.

  browser_enqueue.py <category> <platform> <targetUrl> [opsi]
    category : viral_video | menuju_viral_video
    platform : instagram | tiktok | twitter
    targetUrl: URL PROFIL (scraper ambil grid post dari situ)
  opsi: --limit N (maks URL, default 15) --max-wait S (default 120)
        --min-posts N (di bawah ini = anggap gagal-senyap, default 1)
        --dry-run (scrape + tampilkan, jangan enqueue) --api URL

AUTH: browser API .60 kini WAJIB Bearer token (API_KEY di .env-nya). Kunci dibaca
dari env BROWSER_API_KEY, atau file ~/.config/browser-api/credentials.env (600).
Tanpa kunci -> semua endpoint selain /health balas 401.

Exit: 0 ok · 2 usage · 3 job failed · 4 gagal-senyap (0 post) · 5 API/timeout
"""
import sys, os, json, time, argparse, subprocess, urllib.request, urllib.error

DEFAULT_API = os.getenv("BROWSER_API", "http://10.66.66.60:8080")
PLATFORMS   = {"instagram", "tiktok", "twitter"}
CATS        = {"viral_video", "menuju_viral_video"}
HERE        = os.path.dirname(os.path.abspath(__file__))
ENQUEUE     = os.path.join(HERE, "enqueue.py")
CRED_FILE   = os.path.expanduser("~/.config/browser-api/credentials.env")

def load_api_key():
    """Kunci dari env, fallback ke file kredensial durable di akses-vps."""
    key = os.getenv("BROWSER_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(CRED_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("BROWSER_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""

API_KEY = load_api_key()

def api(method, url, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req  = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return 0, {"ok": False, "error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category"); ap.add_argument("platform"); ap.add_argument("target_url")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--max-wait", type=int, default=120)
    ap.add_argument("--min-posts", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--api", default=DEFAULT_API)
    a = ap.parse_args()

    if a.category not in CATS:  sys.exit(f"[2] kategori tak valid: {a.category} (harus {sorted(CATS)})")
    if a.platform not in PLATFORMS: sys.exit(f"[2] platform tak valid: {a.platform} (harus {sorted(PLATFORMS)})")

    # preflight: browser API hidup?
    st, h = api("GET", f"{a.api}/health", timeout=10)
    if st != 200 or not h.get("ok"):
        print(f"[5] browser API .60 tak sehat ({a.api}/health): {h.get('error','?')}")
        print("    -> minta user redeploy .60 (lihat memori browser_automation), atau pakai enqueue.py manual.")
        sys.exit(5)

    # 1. submit job
    st, r = api("POST", f"{a.api}/scraper/jobs",
                {"platform": a.platform, "targetUrl": a.target_url})
    if st == 401:
        print("[5] 401 Unauthorized dari browser API .60 — kunci API salah/tak ada.")
        print(f"    Set env BROWSER_API_KEY, atau pastikan {CRED_FILE} berisi BROWSER_API_KEY=<kunci>.")
        print("    Kunci harus SAMA dengan API_KEY di ~/browser/.env pada .60.")
        sys.exit(5)
    if st != 202 or not r.get("ok"):
        print(f"[3] submit job gagal (HTTP {st}): {r.get('error','?')}"); sys.exit(3)
    jid = r["job"]["id"]
    print(f"job {jid} submitted ({a.platform} {a.target_url})")

    # 2. poll sampai terminal
    deadline = time.time() + a.max_wait
    data = None
    while time.time() < deadline:
        st, r = api("GET", f"{a.api}/scraper/jobs/{jid}", timeout=20)
        if st == 200 and r.get("ok"):
            status = (r.get("job") or {}).get("status")
            if status in ("done", "failed"):
                data = r; break
            print(f"  ... status={status}")
        time.sleep(5)
    if data is None:
        print(f"[5] timeout {a.max_wait}s menunggu job {jid} (masih berjalan). Cek: GET {a.api}/scraper/jobs/{jid}")
        sys.exit(5)

    job = data.get("job") or {}
    if job.get("status") == "failed":
        print(f"[3] job {jid} FAILED: {job.get('error','?')}"); sys.exit(3)

    posts = data.get("posts") or []
    urls  = [p["postUrl"] for p in posts if p.get("postUrl")]
    print(f"job {jid} done: {len(posts)} post, {len(urls)} punya URL.")

    # 3. GUARD gagal-senyap (CAPTCHA/login-wall): 'done' tapi kosong
    if len(urls) < a.min_posts:
        print(f"[4] GAGAL-SENYAP: job 'done' tapi cuma {len(urls)} URL (<{a.min_posts}).")
        print("    Kemungkinan CAPTCHA (TikTok) / login-wall (IG) dari IP datacenter .60.")
        print("    FALLBACK: suplai URL manual -> enqueue.py --stdin (baris '<category> <url>').")
        sys.exit(4)

    urls = urls[:a.limit]
    print("URL discrape:")
    for u in urls: print("  ", u)

    # 4. serahkan ke enqueue.py (satu sumber: deteksi platform + dedup ON CONFLICT)
    stdin = "".join(f"{a.category} {u}\n" for u in urls)
    cmd = [sys.executable, ENQUEUE, "--stdin"] + (["--dry-run"] if a.dry_run else [])
    print(f"--> enqueue.py {'(dry-run)' if a.dry_run else ''}")
    p = subprocess.run(cmd, input=stdin, text=True)
    sys.exit(p.returncode)

if __name__ == "__main__":
    main()
