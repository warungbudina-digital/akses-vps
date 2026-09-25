#!/usr/bin/env python3
"""Laporan tren TikTok dari DB-VPS schema `trend` → Markdown (+ ringkasan Telegram).

Pakai:
  tiktok_trend_report.py                 # tulis reports/tiktok-trend-<tgl>.md, cetak path
  tiktok_trend_report.py --days 14       # jendela video (default 30 hari)
  tiktok_trend_report.py --telegram      # juga kirim ringkasan singkat ke Telegram
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
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
 'videos', (SELECT coalesce(json_agg(x), '[]') FROM (
   SELECT v.handle, v.video_id, v.url, v.description, v.hashtags, v.duration_s,
          coalesce(v.media_type, 'video') AS media_type, v.n_images,
          v.created_at, l.plays, l.likes, l.comments, l.shares, l.saves, l.taken_at,
          f.plays AS first_plays, f.taken_at AS first_taken
   FROM trend.tiktok_video v
   JOIN LATERAL (SELECT * FROM trend.tiktok_video_snapshot s WHERE s.video_id = v.video_id
                 ORDER BY taken_at DESC LIMIT 1) l ON true
   JOIN LATERAL (SELECT * FROM trend.tiktok_video_snapshot s WHERE s.video_id = v.video_id
                 ORDER BY taken_at ASC LIMIT 1) f ON true
   WHERE v.created_at > now() - make_interval(days => %(days)d)) x),
 'accounts', (SELECT coalesce(json_agg(a), '[]') FROM (
   SELECT handle,
     (SELECT followers FROM trend.tiktok_account_snapshot s WHERE s.handle = h.handle AND status = 'ok'
        ORDER BY taken_at DESC LIMIT 1) AS followers_now,
     (SELECT followers FROM trend.tiktok_account_snapshot s WHERE s.handle = h.handle AND status = 'ok'
        AND taken_at < now() - interval '6 days' ORDER BY taken_at DESC LIMIT 1) AS followers_7d
   FROM (SELECT DISTINCT handle FROM trend.tiktok_account_snapshot) h) a),
 'runs', (SELECT coalesce(json_agg(r ORDER BY r.run_id DESC), '[]') FROM (
   SELECT run_id, count(*) FILTER (WHERE status IN ('ok','no_videos')) AS ok,
          count(*) FILTER (WHERE status = 'captcha') AS captcha,
          count(*) FILTER (WHERE status NOT IN ('ok','no_videos','captcha')) AS failed
   FROM trend.tiktok_account_snapshot
   WHERE taken_at > now() - interval '7 days' GROUP BY run_id) r),
 'candidates', (SELECT coalesce(json_agg(c), '[]') FROM (
   SELECT handle, found_via, times_seen FROM trend.tiktok_candidate
   ORDER BY times_seen DESC, last_seen DESC LIMIT 15) c),
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


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


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
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def enrich(v, now):
    created, taken = ts(v["created_at"]), ts(v["taken_at"])
    plays = v["plays"] or 0
    inter = sum((v[k] or 0) for k in ("likes", "comments", "shares", "saves"))
    age_h = max((taken - created).total_seconds() / 3600, 1) if created else None
    v["age_d"] = (now - created).days if created else None
    v["age_h"] = age_h
    v["velocity"] = plays / age_h if age_h else None            # views/jam sejak tayang
    v["er"] = inter / plays if plays else None                  # interaksi / views
    v["save_rate"] = (v["saves"] or 0) / plays if plays else None
    v["share_rate"] = (v["shares"] or 0) / plays if plays else None
    ft = ts(v["first_taken"])
    span_h = (taken - ft).total_seconds() / 3600 if ft else 0
    v["momentum"] = ((plays - (v["first_plays"] or 0)) / span_h) if span_h >= 12 else None
    v["hook"] = (v["description"] or "").split("\n")[0][:90]
    v["posted_wita"] = created.astimezone(WITA) if created else None
    return v


def fmt_media(v):
    return f"carousel {v['n_images'] or '?'} foto" if v["media_type"] == "photo" else f"video {v['duration_s']}s"


def table(rows, cols):
    head = "| " + " | ".join(c[0] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(c[1](r) for c in cols) + " |\n" for r in rows)


def build(d, days):
    now = dt.datetime.now(dt.timezone.utc)
    vids = [enrich(v, now) for v in d["videos"]]
    out = [f"# Riset tren konten — niche AI/tech (TikTok · Instagram · YouTube)",
           f"_Dibuat {now.astimezone(WITA):%d %b %Y %H:%M} WITA · {len(vids)} video (tayang ≤{days} hari) "
           f"dari {len({v['handle'] for v in vids})} akun_\n"]

    runs = d["runs"]
    out.append("## Kesehatan pengumpulan (7 hari)")
    if not runs:
        out.append("⚠️ **Belum ada run** dalam 7 hari — cek cron / VM .60.\n")
    else:
        cap = sum(r["captcha"] for r in runs)
        fail = sum(r["failed"] for r in runs)
        out.append(f"{len(runs)} run · akun terbaca {sum(r['ok'] for r in runs)} · "
                   f"CAPTCHA {cap} · gagal {fail}" + (" ⚠️" if cap or fail else " ✅") + "\n")

    if not vids:
        out.append("_Belum ada data video. Tunggu beberapa run._\n")
        return "\n".join(out), vids

    # Umur <6 jam terlalu bising (views/jam bisa melonjak semu) → tak diperingkat.
    fresh = [v for v in vids if v["age_d"] is not None and v["age_d"] <= 14 and v["velocity"]
             and (v["age_h"] or 0) >= 6]
    out.append("## 🚀 Paling cepat naik (views/jam, video umur 6 jam–14 hari)")
    out.append(table(sorted(fresh, key=lambda v: -v["velocity"])[:10], [
        ("Akun", lambda v: "@" + v["handle"]), ("Hook / caption", lambda v: v["hook"].replace("|", "/")),
        ("Views", lambda v: fmt(v["plays"])), ("Views/jam", lambda v: fmt(v["velocity"])),
        ("ER", lambda v: pct(v["er"])), ("Format", fmt_media),
        ("Link", lambda v: f"[buka]({v['url']})")]))

    useful = [v for v in vids if (v["plays"] or 0) >= 1000]
    out.append("## 💾 Paling banyak DISIMPAN (sinyal konten tips yg dianggap berguna, min 1rb views)")
    out.append(table(sorted(useful, key=lambda v: -(v["save_rate"] or 0))[:8], [
        ("Akun", lambda v: "@" + v["handle"]), ("Hook / caption", lambda v: v["hook"].replace("|", "/")),
        ("Simpan", lambda v: pct(v["save_rate"])), ("Share", lambda v: pct(v["share_rate"])),
        ("Format", fmt_media),
        ("Views", lambda v: fmt(v["plays"])), ("Link", lambda v: f"[buka]({v['url']})")]))

    mom = [v for v in vids if v["momentum"] is not None]
    if mom:
        out.append("## 📈 Masih bertambah (views/jam antar pengamatan)")
        out.append(table(sorted(mom, key=lambda v: -v["momentum"])[:5], [
            ("Akun", lambda v: "@" + v["handle"]), ("Hook", lambda v: v["hook"].replace("|", "/")),
            ("Tambah views/jam", lambda v: fmt(v["momentum"])), ("Umur", lambda v: f"{v['age_d']} hr")]))

    tags = defaultdict(list)
    for v in vids:
        for t in set(v["hashtags"] or []):
            tags[t].append(v["plays"] or 0)
    top_tags = sorted(((t, len(p), med(p)) for t, p in tags.items() if len(p) >= 2),
                      key=lambda x: -x[2])[:12]
    out.append("## #️⃣ Hashtag (muncul ≥2 video, urut median views)")
    out.append(table(top_tags, [("Hashtag", lambda x: "#" + x[0]), ("Jumlah video", lambda x: str(x[1])),
                                ("Median views", lambda x: fmt(x[2]))]) if top_tags
               else "_Belum cukup data._\n")

    buckets = [("<15s", 0, 15), ("15–30s", 15, 30), ("30–60s", 30, 60), ("60–90s", 60, 90), (">90s", 90, 10**6)]
    rows = []
    for name, lo, hi in buckets:
        b = [v for v in vids if v["media_type"] == "video" and v["duration_s"] is not None
             and lo <= v["duration_s"] < hi]
        if b:
            rows.append((name, len(b), med([v["plays"] for v in b]), med([v["er"] for v in b])))
    fmt_rows = []
    for m, label in (("video", "Video"), ("photo", "Carousel foto")):
        b = [v for v in vids if v["media_type"] == m]
        if b:
            fmt_rows.append((label, len(b), med([v["plays"] for v in b]), med([v["er"] for v in b]),
                             med([v["save_rate"] for v in b])))
    out.append("## 🧩 Format: video vs carousel foto")
    out.append(table(fmt_rows, [("Format", lambda r: r[0]), ("Jumlah", lambda r: str(r[1])),
                                ("Median views", lambda r: fmt(r[2])), ("Median ER", lambda r: pct(r[3])),
                                ("Median simpan", lambda r: pct(r[4]))]))

    out.append("## ⏱️ Durasi (video saja)")
    out.append(table(rows, [("Durasi", lambda r: r[0]), ("Video", lambda r: str(r[1])),
                            ("Median views", lambda r: fmt(r[2])), ("Median ER", lambda r: pct(r[3]))]))

    slots = defaultdict(list)
    for v in vids:
        if v["posted_wita"]:
            h = v["posted_wita"].hour
            slots[f"{h // 3 * 3:02d}–{h // 3 * 3 + 3:02d}"].append(v["plays"] or 0)
    out.append("## 🕒 Jam posting (WITA, per blok 3 jam)")
    out.append(table(sorted(slots.items()), [("Jam", lambda s: s[0]), ("Video", lambda s: str(len(s[1]))),
                                             ("Median views", lambda s: fmt(med(s[1])))]))

    out.append("## 👥 Akun yg dipantau")
    out.append(table(sorted(d["accounts"], key=lambda a: -(a["followers_now"] or 0)), [
        ("Akun", lambda a: "@" + a["handle"]), ("Pengikut", lambda a: fmt(a["followers_now"])),
        ("Δ 7 hari", lambda a: fmt((a["followers_now"] or 0) - a["followers_7d"])
         if a["followers_7d"] is not None and a["followers_now"] is not None else "–")]))

    if d["candidates"]:
        out.append("## 🔎 Kandidat akun baru (dari 'Suggested accounts' — belum dipantau)")
        out.append("Kalau cocok niche AI/tech, tambahkan ke `tiktok_watchlist.json`.\n")
        out.append(", ".join(f"[@{c['handle']}](https://www.tiktok.com/@{c['handle']}) ({c['times_seen']}×)"
                             for c in d["candidates"]) + "\n")
    out.append(build_social(d, now))
    return "\n".join(out), vids


CTA_KOMEN = re.compile(r"\b(komen|comment|ketik)\b", re.I)
PLATFORM_NAME = {"instagram": "Instagram", "youtube": "YouTube", "facebook": "Facebook"}
MEDIA_NAME = {"reel": "Reel", "carousel": "Carousel", "image": "Foto", "video": "Video", "short": "Shorts"}


def build_social(d, now):
    """Bagian IG/YouTube (social_trend.py). Metrik dibagi pengikut supaya akun
    raksasa tak otomatis menang: `views/pengikut` = seberapa jauh post melampaui
    basis audiensnya sendiri; `interaksi/pengikut` = (like+komentar)/pengikut."""
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
        out.append(f"# {PLATFORM_NAME[plat]} — 5 akun teratas niche AI/tech")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    d = fetch(args.days)
    md, vids = build(d, args.days)
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"tiktok-trend-{dt.datetime.now(WITA):%Y-%m-%d}.md")
    open(path, "w").write(md)
    print(path)

    if args.telegram:
        fresh = sorted([v for v in vids if v["velocity"] and (v["age_d"] or 99) <= 14
                        and (v["age_h"] or 0) >= 6],
                       key=lambda v: -v["velocity"])[:3]
        runs = d["runs"]
        lines = ["📊 Tren konten AI/tech (TikTok·IG·YouTube, mingguan)",
                 f"{len(runs)} run/7hr · CAPTCHA {sum(r['captcha'] for r in runs)} · {len(vids)} video"]
        lines += [f"🚀 TikTok @{v['handle']}: {v['hook'][:55]} — {fmt(v['velocity'])} views/jam" for v in fresh]
        sp = d.get("social_posts") or []  # rasio sudah dihitung build_social()
        ig = max((p for p in sp if p["platform"] == "instagram" and p.get("eng_ratio") is not None),
                 key=lambda p: p["eng_ratio"], default=None)
        yt = max((p for p in sp if p["platform"] == "youtube" and p.get("reach_ratio") is not None),
                 key=lambda p: p["reach_ratio"], default=None)
        if ig:
            lines.append(f"💬 IG @{ig['handle']}: {ig['hook'][:55]} — interaksi {pct(ig['eng_ratio'])} pengikut")
        if yt:
            lines.append(f"▶️ YT @{yt['handle']}: {yt['hook'][:55]} — {yt['reach_ratio']:.2f}× pengikut")
        lines.append(f"Laporan lengkap: {path}")
        rc = subprocess.run([TELEGRAM, "\n".join(lines)], timeout=60).returncode
        print("telegram:", "terkirim" if rc == 0 else f"GAGAL (rc={rc})")
        if rc != 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
