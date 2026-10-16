#!/usr/bin/env python3
"""Laporan tren Instagram + YouTube (Go Go Bud, akses resmi via token Page/API)
dari DB-VPS schema `trend.social_*` -> Markdown (+ ringkasan Telegram).

⛔ TikTok DIHAPUS dari pipeline ini 2026-10-16 (keputusan user): scraping TikTok
anonim (embed .60/requests-only .61) terus-menerus kena CAPTCHA/WAF/rate-limit,
DAN jadi sumber bug tersembunyi 48 hari (Tier-2 analyzer selalu `dead` krn
orchestrator.py tak pernah dukung TikTok -- lihat project_viral_analyzer.md).
Diganti akses platform MILIK Go Go Bud sendiri yang sudah TERBUKTI nyata jalan
(Graph API Business Discovery dgn token Page, dan YouTube publik) -- bebas dari
hambatan firewall/anti-bot krn bukan scraping anonim.

Pakai:
  social_trend_report.py                 # tulis reports/social-trend-<tgl>.md
  social_trend_report.py --days 14       # jendela post (default 30 hari)
  social_trend_report.py --telegram      # juga kirim ringkasan ke Telegram
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "reports")
TELEGRAM = os.path.expanduser("~/akses-vps/backup/send-telegram.sh")
WITA = dt.timezone(dt.timedelta(hours=8))
DB_CMD = ["ssh", "-o", "BatchMode=yes", "db-vps",
          "sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -At -f -"]

QUERY = """
SELECT json_build_object(
 'social_posts', (SELECT coalesce(json_agg(x), '[]') FROM (
   SELECT p.platform, p.handle, p.post_id, p.url, p.caption, p.media_type, p.hashtags, p.created_at,
          l.views, l.likes, l.comments, l.taken_at,
          (SELECT followers FROM trend.social_account_snapshot a WHERE a.platform = p.platform
             AND a.handle = p.handle AND a.status = 'ok' ORDER BY taken_at DESC LIMIT 1) AS followers
   FROM trend.social_post p
   JOIN LATERAL (SELECT * FROM trend.social_post_snapshot s WHERE s.platform = p.platform
                 AND s.post_id = p.post_id ORDER BY taken_at DESC LIMIT 1) l ON true
   WHERE p.created_at > now() - make_interval(days => %(days)d)) x),
 'social_accounts', (SELECT coalesce(json_agg(a), '[]') FROM (
   SELECT DISTINCT ON (platform, handle) platform, handle, name, status, followers, taken_at,
     (SELECT followers FROM trend.social_account_snapshot o WHERE o.platform = s.platform
        AND o.handle = s.handle AND o.status = 'ok' AND o.taken_at < now() - interval '6 days'
        ORDER BY taken_at DESC LIMIT 1) AS followers_7d
   FROM trend.social_account_snapshot s ORDER BY platform, handle, taken_at DESC) a)
);
"""


def fetch(days):
    p = subprocess.run(DB_CMD, input=QUERY % {"days": days}, text=True,
                       capture_output=True, timeout=120)
    if p.returncode != 0:
        sys.exit("query gagal: " + p.stderr.strip()[-400:])
    out = p.stdout
    return json.loads(out[out.index("{"): out.rindex("}") + 1])  # json_agg bisa sisip \n


def fmt(n):
    if n is None:
        return "–"
    for unit, div in (("M", 1e6), ("rb", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return f"{n:.0f}" if isinstance(n, float) else str(n)


def pct(x):
    if x is None:
        return "–"
    v = x * 100
    return f"{v:.1f}%" if v >= 1 or v == 0 else f"{v:.2f}%" if v >= 0.01 else f"{v:.3f}%"


def med(xs):
    import statistics
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def table(rows, cols):
    head = "| " + " | ".join(c[0] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(c[1](r) for c in cols) + " |\n" for r in rows)


CTA_KOMEN = re.compile(r"\b(komen|comment|ketik)\b", re.I)
PLATFORM_NAME = {"instagram": "Instagram", "youtube": "YouTube", "facebook": "Facebook"}
MEDIA_NAME = {"reel": "Reel", "carousel": "Carousel", "image": "Foto", "video": "Video", "short": "Shorts"}


def build_social(d, now):
    """Metrik dibagi pengikut supaya akun raksasa tak otomatis menang:
    `views/pengikut` = seberapa jauh post melampaui basis audiensnya sendiri;
    `interaksi/pengikut` = (like+komentar)/pengikut."""
    posts = d.get("social_posts") or []
    out = []
    for p in posts:
        f = p.get("followers") or 0
        inter = (p.get("likes") or 0) + (p.get("comments") or 0)
        p["reach_ratio"] = (p["views"] / f) if f and p.get("views") is not None else None
        p["eng_ratio"] = (inter / f) if f and (p.get("likes") is not None or p.get("comments") is not None) else None
        p["cta_komen"] = bool(CTA_KOMEN.search(p.get("caption") or ""))
        p["hook"] = (p.get("caption") or "").strip().split("\n")[0][:80].replace("|", "/")
    for plat in ("instagram", "youtube", "facebook"):
        ps = [p for p in posts if p["platform"] == plat]
        accts = [a for a in d.get("social_accounts") or [] if a["platform"] == plat]
        if not ps and not accts:
            continue
        out.append(f"# {PLATFORM_NAME[plat]} — akun teratas niche AI/tech")
        bad = [a for a in accts if a["status"] != "ok"]
        out.append(f"{len(accts)} akun · {len(ps)} post (≤30 hari)" +
                   (f" · ⚠️ gagal terbaca: {', '.join('@' + a['handle'] for a in bad)}" if bad else " ✅") + "\n")
        out.append(table(sorted(accts, key=lambda a: -(a["followers"] or 0)), [
            ("Akun", lambda a: "@" + a["handle"]), ("Nama", lambda a: (a["name"] or "–")[:30].replace("|", "/")),
            ("Pengikut", lambda a: fmt(a["followers"])),
            ("Δ 7 hari", lambda a: fmt((a["followers"] or 0) - a["followers_7d"])
             if a.get("followers_7d") is not None and a.get("followers") is not None else "–")]))

        rv = [p for p in ps if p["reach_ratio"] is not None]
        if rv:
            out.append(f"## 🚀 {PLATFORM_NAME[plat]}: paling melampaui audiensnya (views ÷ pengikut)")
            out.append(table(sorted(rv, key=lambda p: -p["reach_ratio"])[:8], [
                ("Akun", lambda p: "@" + p["handle"]), ("Hook", lambda p: p["hook"]),
                ("Format", lambda p: MEDIA_NAME.get(p["media_type"], p["media_type"] or "?")),
                ("Views", lambda p: fmt(p["views"])), ("Views/pengikut", lambda p: f"{p['reach_ratio']:.2f}×"),
                ("Link", lambda p: f"[buka]({p['url']})")]))
        ev = [p for p in ps if p["eng_ratio"] is not None]
        if ev:
            out.append(f"## 💬 {PLATFORM_NAME[plat]}: interaksi tertinggi (like+komentar ÷ pengikut)")
            out.append(table(sorted(ev, key=lambda p: -p["eng_ratio"])[:8], [
                ("Akun", lambda p: "@" + p["handle"]), ("Hook", lambda p: p["hook"]),
                ("Format", lambda p: MEDIA_NAME.get(p["media_type"], p["media_type"] or "?")),
                ("Like", lambda p: fmt(p["likes"])), ("Komentar", lambda p: fmt(p["comments"])),
                ("Interaksi/pengikut", lambda p: pct(p["eng_ratio"])), ("Link", lambda p: f"[buka]({p['url']})")]))

        rows = []
        for m in sorted({p["media_type"] for p in ps if p["media_type"]}):
            b = [p for p in ps if p["media_type"] == m]
            rows.append((MEDIA_NAME.get(m, m), len(b), med([p["reach_ratio"] for p in b]),
                         med([p["eng_ratio"] for p in b])))
        out.append(f"## 🧩 {PLATFORM_NAME[plat]}: format")
        out.append(table(rows, [("Format", lambda r: r[0]), ("Post", lambda r: str(r[1])),
                                ("Median views/pengikut", lambda r: f"{r[2]:.2f}×" if r[2] is not None else "–"),
                                ("Median interaksi/pengikut", lambda r: pct(r[3]))]))

        yes = [p["eng_ratio"] for p in ev if p["cta_komen"]]
        no = [p["eng_ratio"] for p in ev if not p["cta_komen"]]
        if yes and no:
            out.append(f"**Ajakan \"komen …\" di caption:** {len(yes)} post, median interaksi/pengikut "
                       f"{pct(med(yes))} vs tanpa ajakan {len(no)} post {pct(med(no))}.\n")

        tags = defaultdict(list)
        for p in ps:
            for t in set(p.get("hashtags") or []):
                tags[t].append(p["eng_ratio"] or 0)
        top = sorted(((t, len(v), med(v)) for t, v in tags.items() if len(v) >= 2), key=lambda x: -x[2])[:10]
        if top:
            out.append(f"## #️⃣ {PLATFORM_NAME[plat]}: hashtag (≥2 post, urut median interaksi/pengikut)")
            out.append(table(top, [("Hashtag", lambda x: "#" + x[0]), ("Post", lambda x: str(x[1])),
                                   ("Median interaksi/pengikut", lambda x: pct(x[2]))]))
    return "\n".join(out)


def build(d, days):
    now = dt.datetime.now(dt.timezone.utc)
    posts = d.get("social_posts") or []
    out = [f"# Riset tren konten — niche AI/tech (Instagram · YouTube)",
           f"_Dibuat {now.astimezone(WITA):%d %b %Y %H:%M} WITA · {len(posts)} post (tayang ≤{days} hari)_\n"]
    if not posts and not d.get("social_accounts"):
        out.append("_Belum ada data. Tunggu beberapa run `social_trend.py`._\n")
        return "\n".join(out), posts
    out.append(build_social(d, now))
    return "\n".join(out), posts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    d = fetch(args.days)
    md, posts = build(d, args.days)
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"social-trend-{dt.datetime.now(WITA):%Y-%m-%d}.md")
    open(path, "w").write(md)
    print(path)

    if args.telegram:
        for p in posts:
            f = p.get("followers") or 0
            inter = (p.get("likes") or 0) + (p.get("comments") or 0)
            p["reach_ratio"] = (p["views"] / f) if f and p.get("views") is not None else None
            p["eng_ratio"] = (inter / f) if f and (p.get("likes") is not None or p.get("comments") is not None) else None
            p["hook"] = (p.get("caption") or "").strip().split("\n")[0][:55].replace("|", "/")
        lines = ["📊 Tren konten AI/tech (Instagram · YouTube, mingguan)",
                 f"{len(posts)} post terbaca"]
        ig = max((p for p in posts if p["platform"] == "instagram" and p.get("eng_ratio") is not None),
                 key=lambda p: p["eng_ratio"], default=None)
        yt = max((p for p in posts if p["platform"] == "youtube" and p.get("reach_ratio") is not None),
                 key=lambda p: p["reach_ratio"], default=None)
        if ig:
            lines.append(f"💬 IG @{ig['handle']}: {ig['hook']} — interaksi {pct(ig['eng_ratio'])} pengikut")
        if yt:
            lines.append(f"▶️ YT @{yt['handle']}: {yt['hook']} — {yt['reach_ratio']:.2f}× pengikut")
        lines.append(f"Laporan lengkap: {path}")
        rc = subprocess.run([TELEGRAM, "\n".join(lines)], timeout=60).returncode
        print("telegram:", "terkirim" if rc == 0 else f"GAGAL (rc={rc})")
        if rc != 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
