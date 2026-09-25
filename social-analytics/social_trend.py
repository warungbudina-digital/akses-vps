#!/usr/bin/env python3
"""Riset tren lintas platform (Instagram + YouTube) → DB-VPS schema `trend.social_*`.

Pendamping tiktok_trend.py. Berbeda dgn TikTok, dua platform ini TIDAK butuh
browser .60 (jalan penuh dari hub, jadi tak tergantung laptop/Cloud Shell):
  - Instagram: Graph API **Business Discovery** memakai token Page gogobud
    (`~/.config/meta-gogobud/app.env`). Resmi, tanpa scraping. Hanya bisa membaca
    akun Business/Creator (akun pribadi → "Invalid user id"). Reels memberi view_count.
  - YouTube: halaman `/@handle/about` (subscriber/views/jumlah video, locale en-US)
    + RSS publik `feeds/videos.xml` (15 video terbaru + views + likes). Shorts
    dibedakan lewat `/shorts/<id>` (200 = Shorts, 303 = video biasa).
  - Facebook: belum — Graph API utk Page orang lain butuh App Review (PPCA), dan
    .60 kena login-wall. Lihat README.

Pakai:
  social_trend.py                              # run semua platform (cron)
  social_trend.py --only instagram             # satu platform
  social_trend.py --dry-run
  social_trend.py --check instagram myskill.id # cek akun sebelum masuk watchlist
Exit: 0 ok · 1 semua akun gagal.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(HERE, "social_watchlist.json")
META_ENV = os.path.expanduser("~/.config/meta-gogobud/app.env")
GRAPH = "https://graph.facebook.com/v23.0"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NS = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/",
      "yt": "http://www.youtube.com/xml/schemas/2015"}
DB_CMD = ["ssh", "-o", "BatchMode=yes", "db-vps",
          "sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -q -f -"]
HASHTAG = re.compile(r"#([0-9A-Za-z_À-ɏ]+)")


def log(msg):
    print(f"[social-trend {dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {msg}", flush=True)


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\x00", "").replace("'", "''") + "'"


def q_arr(items):
    return "ARRAY[" + ",".join(q(i) for i in items) + "]::text[]" if items else "'{}'::text[]"


def tags_of(text):
    return sorted({t.lower() for t in HASHTAG.findall(text or "")})


def run_sql(sql, dry):
    if dry:
        return
    p = subprocess.run(DB_CMD, input="SET ROLE scraper;\n" + sql, text=True,
                       capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError("psql gagal: " + p.stderr.strip()[-400:])


def http(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def to_int(v):
    """'14.2M subscribers' / '1,713 videos' / '3,798,784,596 views' → int."""
    if v is None:
        return None
    m = re.search(r"([\d.,]+)\s*([KMB])?", str(v))
    if not m:
        return None
    num, unit = m.group(1).replace(",", ""), m.group(2)
    try:
        return int(float(num) * {"K": 1e3, "M": 1e6, "B": 1e9}.get(unit, 1))
    except ValueError:
        return None


def save(platform, run_id, handle, acct, posts, dry):
    """acct: dict status/name/followers/posts/total_views/error; posts: list dict."""
    sql = [f"""INSERT INTO trend.social_account_snapshot
      (run_id, platform, handle, status, name, followers, posts, total_views, error)
      VALUES ({q(run_id)}, {q(platform)}, {q(handle)}, {q(acct['status'])}, {q(acct.get('name'))},
              {q(acct.get('followers'))}, {q(acct.get('posts'))}, {q(acct.get('total_views'))},
              {q(acct.get('error'))});"""]
    for p in posts:
        sql.append(f"""INSERT INTO trend.social_post
          (platform, post_id, handle, url, caption, media_type, hashtags, created_at)
          VALUES ({q(platform)}, {q(p['id'])}, {q(handle)}, {q(p.get('url'))}, {q(p.get('caption'))},
                  {q(p.get('media_type'))}, {q_arr(tags_of(p.get('caption')))}, {q(p.get('created_at'))})
          ON CONFLICT (platform, post_id) DO UPDATE SET caption = EXCLUDED.caption,
            media_type = EXCLUDED.media_type, hashtags = EXCLUDED.hashtags;
          INSERT INTO trend.social_post_snapshot (run_id, platform, post_id, views, likes, comments)
          VALUES ({q(run_id)}, {q(platform)}, {q(p['id'])}, {q(p.get('views'))},
                  {q(p.get('likes'))}, {q(p.get('comments'))});""")
    run_sql("\n".join(sql), dry)


# ── Instagram (Graph API Business Discovery) ─────────────────────────────────
def meta_env():
    env = {}
    for line in open(META_ENV):
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"\'')
    return env


def ig_fetch(handle, n):
    env = meta_env()
    fields = (f"business_discovery.username({handle})"
              "{username,name,followers_count,media_count,biography,"
              f"media.limit({n}){{id,caption,media_type,media_product_type,timestamp,"
              "like_count,comments_count,view_count,permalink}}")
    url = (f"{GRAPH}/{env['IG_USER_ID']}?fields={urllib.parse.quote(fields, safe='(),.')}"
           f"&access_token={env['PAGE_TOKEN']}")
    try:
        d = json.loads(http(url))
    except urllib.error.HTTPError as e:
        d = json.loads(e.read().decode() or "{}")
    b = d.get("business_discovery")
    if not b:
        msg = (d.get("error") or {}).get("message", "tak ada data")
        status = "not_found" if "Invalid user id" in msg else "error"
        return {"status": status, "error": msg[:200]}, [], None
    posts = []
    for m in (b.get("media") or {}).get("data", []):
        kind = {"CAROUSEL_ALBUM": "carousel", "IMAGE": "image"}.get(m.get("media_type"), "video")
        if m.get("media_product_type") == "REELS":
            kind = "reel"
        posts.append({"id": m["id"], "url": m.get("permalink"), "caption": m.get("caption"),
                      "media_type": kind, "created_at": m.get("timestamp"),
                      "views": m.get("view_count"), "likes": m.get("like_count"),
                      "comments": m.get("comments_count")})
    acct = {"status": "ok", "name": b.get("name"), "followers": b.get("followers_count"),
            "posts": b.get("media_count")}
    return acct, posts, b.get("biography")


# ── YouTube (halaman about + RSS publik) ─────────────────────────────────────
def yt_fetch(handle, n, shorts_max):
    try:
        html = http(f"https://www.youtube.com/@{handle}/about", {"Accept-Language": "en-US"})
    except urllib.error.HTTPError as e:
        return {"status": "not_found" if e.code == 404 else "error", "error": f"HTTP {e.code}"}, [], None
    # canonical = channel milik halaman ini (kemunculan "channelId" pertama di HTML
    # bisa milik channel LAIN — pernah terbaca "Putu Reza" di halaman GadgetIn).
    cid = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', html)
    if not cid:
        return {"status": "error", "error": "canonical channel tak ditemukan"}, [], None
    title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    grab = lambda k: (re.search(rf'"{k}":"([^"]+)"', html) or [None, None])[1]
    feed = ET.fromstring(http(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid.group(1)}"))
    posts = []
    for i, e in enumerate(feed.findall("a:entry", NS)[:n]):
        vid = e.find("yt:videoId", NS).text
        g = e.find("m:group", NS)
        kind = "video"
        if i < shorts_max:  # cek Shorts hanya utk video terbaru (hemat request)
            req = urllib.request.Request(f"https://www.youtube.com/shorts/{vid}", method="HEAD",
                                         headers={"User-Agent": UA})
            opener = urllib.request.build_opener(NoRedirect)
            try:
                kind = "short" if opener.open(req, timeout=15).status == 200 else "video"
            except urllib.error.HTTPError:
                kind = "video"  # 303 → video biasa
        stats = g.find("m:community/m:statistics", NS)
        rating = g.find("m:community/m:starRating", NS)
        desc = g.find("m:description", NS)
        posts.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                      "caption": (e.find("a:title", NS).text or "") + "\n" + ((desc.text or "") if desc is not None else ""),
                      "media_type": kind, "created_at": e.find("a:published", NS).text,
                      "views": int(stats.get("views")) if stats is not None else None,
                      "likes": int(rating.get("count")) if rating is not None else None,
                      "comments": None})
    acct = {"status": "ok", "name": title.group(1) if title else None,
            "followers": to_int(grab("subscriberCountText")), "posts": to_int(grab("videoCountText")),
            "total_views": to_int(grab("viewCountText"))}
    return acct, posts, None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


FETCHERS = {"instagram": lambda h, c: ig_fetch(h, c["posts_per_account"]),
            "youtube": lambda h, c: yt_fetch(h, c["posts_per_account"], c["youtube_shorts_check_max"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(FETCHERS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", nargs="+", metavar="PLATFORM HANDLE")
    args = ap.parse_args()
    cfg = json.load(open(WATCHLIST))

    if args.check:
        platform, handles = args.check[0], args.check[1:]
        for h in handles:
            acct, posts, bio = FETCHERS[platform](h.lstrip("@"), cfg)
            last = max((p["created_at"] for p in posts if p.get("created_at")), default="–")[:10]
            print(f"{platform} @{h}: {acct['status']} · {acct.get('name')} · pengikut {acct.get('followers')}"
                  f" · post {acct.get('posts')} · terakhir {last}" + (f" · {acct.get('error')}" if acct.get("error") else ""))
            if bio:
                print("   bio:", bio.replace("\n", " / ")[:150])
        return 0

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = {}
    for platform, fetch in FETCHERS.items():
        if args.only and platform != args.only:
            continue
        for h in cfg.get(platform, []):
            try:
                acct, posts, _ = fetch(h, cfg)
                save(platform, run_id, h, acct, posts, args.dry_run)
                results[f"{platform}:{h}"] = acct["status"]
                log(f"{platform} @{h}: {acct['status']} · pengikut={acct.get('followers')} · post={len(posts)}"
                    + (f" · {acct.get('error')}" if acct.get("error") else ""))
            except Exception as e:  # satu akun gagal tak menggagalkan yg lain
                results[f"{platform}:{h}"] = "error"
                log(f"{platform} @{h}: ERROR {e}")
                try:
                    save(platform, run_id, h, {"status": "error", "error": str(e)[:200]}, [], args.dry_run)
                except Exception:
                    pass
            time.sleep(2)
    ok = sum(1 for s in results.values() if s == "ok")
    log(f"ringkasan: {ok}/{len(results)} ok · {json.dumps(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
