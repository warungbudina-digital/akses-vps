#!/usr/bin/env python3
"""dashboard.py - tarik media.* (antrean+hasil viral_analyzer) dari DB-VPS -> HTML
self-contained (CSP-safe), gaya visual sama dengan ~/analytics/dashboard.py.
Output: /home/warungbudina/viral-pipeline/dashboard.html . Ringan (VPS-light)."""
import os, sys, json, subprocess, html

HERE = os.path.dirname(os.path.abspath(__file__))
DB_SSH, DB_NAME = "db-vps", "scraper"
OUT = os.path.join(HERE, "dashboard.html")

SQL = """SELECT json_build_object(
 'generated_at', to_char(now() at time zone 'Asia/Makassar','YYYY-MM-DD HH24:MI')||' WITA',
 'counts', COALESCE((SELECT json_agg(x ORDER BY x.n DESC) FROM (
     SELECT status, count(*) n FROM media.video_ingest GROUP BY status) x),'[]'::json),
 'by_platform', COALESCE((SELECT json_agg(x ORDER BY x.n DESC) FROM (
     SELECT COALESCE(platform,'?') platform, count(*) n FROM media.video_ingest GROUP BY platform) x),'[]'::json),
 'by_category', COALESCE((SELECT json_agg(x ORDER BY x.n DESC) FROM (
     SELECT category, count(*) n FROM media.video_ingest GROUP BY category) x),'[]'::json),
 'recent', COALESCE((SELECT json_agg(x ORDER BY x.created_at DESC) FROM (
     SELECT id, COALESCE(platform,'?') platform, category, status, source_url, attempts,
            to_char(created_at,'YYYY-MM-DD HH24:MI') created_at,
            to_char(analyzed_at,'YYYY-MM-DD HH24:MI') analyzed_at,
            duration_sec, last_error
     FROM media.video_ingest ORDER BY created_at DESC LIMIT 25) x),'[]'::json),
 'astats', (SELECT json_build_object(
     'n', count(*),
     'avg_bpm', round(avg((analysis->>'bpm')::numeric),1),
     'avg_scenes', round(avg(jsonb_array_length(analysis->'scene_analysis')),1),
     'avg_dur', round(avg((analysis->>'duration_sec')::numeric),1)
   ) FROM media.video_analysis WHERE analysis ? 'scene_analysis')
);"""

def fetch():
    p = subprocess.run(["ssh", DB_SSH, f"sudo -n -u postgres psql -d {DB_NAME} -tAc \"{SQL}\""],
                       capture_output=True, timeout=45)
    out = p.stdout.decode()
    i, j = out.find("{"), out.rfind("}")
    if i < 0 or j < 0:
        raise RuntimeError("query kosong/gagal: " + (p.stderr.decode() or out)[-400:])
    return json.loads(out[i:j + 1])

STATUS_COLOR = {"analyzed": "good", "processing": "warn", "pending": "muted",
                "failed": "bad", "dead": "bad"}
STATUS_ICON = {"analyzed": "●", "processing": "◐", "pending": "○", "failed": "✕", "dead": "✕"}
PLATFORM_SLOT = {"instagram": 1, "facebook": 2, "youtube": 3, "tiktok": 4}

def esc(v): return html.escape("" if v is None else str(v))
def num(v): return "—" if v is None else (f"{int(v):,}".replace(",", ".") if float(v) == int(v) else str(v))

def render(d):
    counts = d.get("counts") or []
    by_platform = d.get("by_platform") or []
    by_category = d.get("by_category") or []
    recent = d.get("recent") or []
    astats = d.get("astats") or {}

    cmap = {c["status"]: c["n"] for c in counts}
    total = sum(cmap.values())
    kpis = [
        ("Total job", num(total), "seluruh antrean"),
        ("Analyzed", num(cmap.get("analyzed", 0)), "sukses dianalisa"),
        ("Pending", num(cmap.get("pending", 0)), "menunggu drain"),
        ("Processing", num(cmap.get("processing", 0)), "sedang diproses"),
        ("Failed/Dead", num(cmap.get("failed", 0) + cmap.get("dead", 0)), "gagal (bisa retry/mati)"),
        ("Rata bpm (IR)", num(astats.get("avg_bpm")), f"dari {num(astats.get('n'))} analisa"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-l">{esc(l)}</div>'
        f'<div class="kpi-s">{esc(s)}</div></div>' for l, v, s in kpis)

    maxp = max([p.get("n", 0) for p in by_platform] + [1])
    bars = ""
    for p in by_platform:
        slot = PLATFORM_SLOT.get(p["platform"], 8)
        w = round(100 * (p.get("n") or 0) / maxp)
        bars += (f'<div class="bar-row"><div class="bar-name"><span class="dot s{slot}"></span>'
                 f'{esc(p["platform"])} <span class="bar-n">×{p.get("n",0)}</span></div>'
                 f'<div class="bar-track"><div class="bar-fill s{slot}" style="width:{w}%"></div></div></div>')

    cat_html = "".join(
        f'<span class="pill muted">{esc(c["category"])} ×{c.get("n",0)}</span> ' for c in by_category)

    rows = ""
    for r in recent:
        st = r.get("status", "")
        pill = STATUS_COLOR.get(st, "muted")
        icon = STATUS_ICON.get(st, "○")
        slot = PLATFORM_SLOT.get(r.get("platform"), 8)
        url_short = (r.get("source_url") or "")[:46]
        err = f' title="{esc(r.get("last_error") or "")}"' if r.get("last_error") else ""
        rows += (f'<tr{err}><td class="mut">{r["id"]}</td>'
                 f'<td><span class="dot s{slot}"></span>{esc(r["platform"])}</td>'
                 f'<td class="mut">{esc(r.get("category") or "")}</td>'
                 f'<td><span class="pill {pill}">{icon} {esc(st)}</span></td>'
                 f'<td class="urlcell">{esc(url_short)}</td>'
                 f'<td class="r">{num(r.get("attempts"))}</td>'
                 f'<td class="mut">{esc(r.get("created_at") or "—")}</td>'
                 f'<td class="mut">{esc(r.get("analyzed_at") or "—")}</td></tr>')

    return PAGE.format(gen=esc(d.get("generated_at", "")), kpis=kpi_html, bars=bars or
                        '<span class="mut">Belum ada job.</span>', cats=cat_html, rows=rows or
                        '<tr><td colspan="8" class="mut">Belum ada job.</td></tr>',
                        avg_scenes=num(astats.get("avg_scenes")), avg_dur=num(astats.get("avg_dur")))

PAGE = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Viral Pipeline — Antrean & Analisa</title>
<style>
:root{{
 --plane:#f9f9f7; --surf:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --mut:#898781;
 --grid:#e1e0d9; --border:rgba(11,11,11,.10);
 --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300; --s7:#4a3aa7; --s8:#e34948;
 --good:#0ca30c; --warn:#fab219; --bad:#e34948;
}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme=light])){{
 --plane:#0d0d0d; --surf:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --mut:#898781;
 --grid:#2c2c2a; --border:rgba(255,255,255,.10);
 --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
}}}}
:root[data-theme=dark]{{
 --plane:#0d0d0d; --surf:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --mut:#898781;
 --grid:#2c2c2a; --border:rgba(255,255,255,.10);
 --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5;
 font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
header{{border-bottom:1px solid var(--border);padding-bottom:20px;margin-bottom:28px}}
h1{{font-size:22px;margin:0 0 4px}}
.mut{{color:var(--mut)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:28px}}
.kpi{{background:var(--surf);border:1px solid var(--border);border-radius:10px;padding:14px 16px}}
.kpi-v{{font-size:22px;font-weight:700}}
.kpi-l{{font-size:12.5px;color:var(--ink2);margin-top:2px}}
.kpi-s{{font-size:11.5px;color:var(--mut);margin-top:2px}}
section{{margin-bottom:28px}}
h2{{font-size:15px;margin:0 0 12px;color:var(--ink2)}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}}
.s1{{background:var(--s1)}}.s2{{background:var(--s2)}}.s3{{background:var(--s3)}}.s4{{background:var(--s4)}}
.s5{{background:var(--s5)}}.s6{{background:var(--s6)}}.s7{{background:var(--s7)}}.s8{{background:var(--s8)}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:13px}}
.bar-name{{width:140px;flex-shrink:0}}
.bar-n{{color:var(--mut);font-size:11.5px}}
.bar-track{{flex:1;height:8px;background:var(--grid);border-radius:5px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:5px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;
 letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border)}}
td{{padding:7px 8px;border-bottom:1px solid var(--border)}}
.r{{text-align:right}}
.urlcell{{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}}
.pill{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}}
.pill.good{{background:rgba(12,163,12,.12);color:var(--good)}}
.pill.warn{{background:rgba(250,178,25,.16);color:#a06600}}
.pill.bad{{background:rgba(227,73,72,.14);color:var(--bad)}}
.pill.muted{{background:var(--grid);color:var(--ink2)}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--border);font-size:11.5px;color:var(--mut)}}
</style>
<div class="wrap">
<header>
<h1>Viral Pipeline — Antrean &amp; Analisa</h1>
<div class="mut">media.video_ingest / media.video_analysis · rata durasi klip {avg_dur}s · rata {avg_scenes} scene/klip</div>
</header>

<section class="kpis">{kpis}</section>

<section>
<h2>Sebaran platform</h2>
{bars}
</section>

<section>
<h2>Kategori</h2>
{cats}
</section>

<section>
<h2>Job terbaru (25 terakhir)</h2>
<table>
<tr><th>ID</th><th>Platform</th><th>Kategori</th><th>Status</th><th>URL</th><th class="r">Percobaan</th><th>Dibuat</th><th>Dianalisa</th></tr>
{rows}
</table>
</section>

<footer>Diperbarui {gen} · sumber: DB-VPS schema media.* · dibangun via viral-pipeline/dashboard.py</footer>
</div>
"""

def main():
    d = fetch()
    open(OUT, "w", encoding="utf-8").write(render(d))
    print(f"dashboard ditulis: {OUT} ({os.path.getsize(OUT)} bytes)")

if __name__ == "__main__":
    main()
