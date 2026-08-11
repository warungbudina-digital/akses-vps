#!/usr/bin/env python3
"""dashboard.py - tarik media.* (antrean+hasil viral_analyzer) dari DB-VPS -> HTML
self-contained (CSP-safe), gaya visual sama dengan ~/analytics/dashboard.py.
Output: /home/warungbudina/viral-pipeline/dashboard.html . Ringan (VPS-light).

+ ALUR NASKAH & ALUR FOOTAGE per URL teranalisa (bahan ide & analisa): reuse
  ir_to_vn (phases/story-script) + pexels_fetch (query stok per semantic)."""
import os, sys, json, subprocess, html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ir_to_vn as iv
try:
    from pexels_fetch import SEMANTIC_QUERY_MAP, DEFAULT_FALLBACK
except Exception:
    SEMANTIC_QUERY_MAP, DEFAULT_FALLBACK = {}, "cinematic b roll background"

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
   ) FROM media.video_analysis WHERE analysis ? 'scene_analysis'),
 'analyses', COALESCE((SELECT json_agg(x ORDER BY x.id DESC) FROM (
     SELECT id, COALESCE(platform,'?') platform, category, source_url,
            to_char(created_at,'YYYY-MM-DD HH24:MI') created_at, analysis
     FROM media.video_analysis WHERE analysis ? 'scene_analysis'
     ORDER BY id DESC LIMIT 6) x),'[]'::json)
);"""

def fetch():
    p = subprocess.run(["ssh", DB_SSH, f"sudo -n -u postgres psql -d {DB_NAME} -tAc \"{SQL}\""],
                       capture_output=True, timeout=90)
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

# ---- ALUR NASKAH + ALUR FOOTAGE (reuse ir_to_vn) --------------------------------

def _adjust_from_lighting(lg):
    # replika ir_to_vn (fungsi itu bersarang di main(), tak bisa diimpor)
    acts = []
    if not lg:
        return acts
    bl, cl, tl = lg.get("brightness_label"), lg.get("contrast_label"), lg.get("temperature_label")
    if bl == "dark":     acts.append({"param": "KECERAHAN", "dir": "naik"})
    elif bl == "bright": acts.append({"param": "KECERAHAN", "dir": "turun"})
    if cl == "low":      acts.append({"param": "KONTRAS", "dir": "naik"})
    elif cl == "high":   acts.append({"param": "KONTRAS", "dir": "turun"})
    if tl == "warm":     acts.append({"param": "SUHU", "dir": "hangat"})
    elif tl == "cool":   acts.append({"param": "SUHU", "dir": "dingin"})
    return acts

def build_bp(d):
    """Replikasi konstruksi blueprint ir_to_vn.main() TANPA tulis file."""
    scenes = d.get("scene_analysis") or []
    segs = d.get("subtitle_segments") or []
    durs = [iv.dur_of(s) for s in scenes]
    total = sum(durs)
    ratio_lab, ratio_known = iv.ratio_from_ir(d)
    n_fade = sum(1 for s in scenes if s.get("transition") == "fade")
    n_cut = sum(1 for s in scenes if s.get("transition") == "cut")
    beat_on = sum(1 for s in scenes if s.get("beat_sync"))
    strong = [round(s.get("start", 0), 1) for s in scenes if s.get("hook_strength") == "strong_hook"]
    med = sorted(durs)[len(durs) // 2] if durs else 0
    ph = iv.phases(scenes, 6.0)
    segments = []
    for idx, s in enumerate(scenes):
        cm = s.get("camera_movement"); zoom = None
        if cm in ("zoom_in", "zoom_out"):
            zoom = {"dir": cm, "vn": {"zoom_in": "Perbesar", "zoom_out": "Perkecil"}[cm]}
        elif cm == "zoom":
            zoom = {"dir": "zoom", "vn": "Perbesar/Perkecil?"}
        segments.append({"i": idx, "start": round(s.get("start", 0), 2),
                         "end": round(s.get("end", 0), 2), "dur": round(s.get("duration", 0), 2),
                         "zoom": zoom, "adjust": _adjust_from_lighting(s.get("lighting"))})
    lit = [s.get("lighting") for s in scenes if s.get("lighting")]
    lighting_summary = {}
    if lit:
        lighting_summary = {"brightness": iv.top((l.get("brightness_label") for l in lit), 3),
                            "contrast": iv.top((l.get("contrast_label") for l in lit), 3),
                            "temperature": iv.top((l.get("temperature_label") for l in lit), 3)}
    bp = {
        "source": {"bpm": d.get("bpm"), "total_sec": round(total, 2),
                   "aspect_ratio": ratio_lab, "aspect_ratio_known": ratio_known},
        "format": {"orientation_hint": ratio_lab, "duration_sec": round(total, 2),
                   "duration_mmss": f"{int(total // 60)}:{int(total % 60):02d}", "long_form": total > 90},
        "pacing": {"n_scenes": len(scenes), "cuts": n_cut, "fades": n_fade,
                   "median_cut_sec": round(med, 2),
                   "style": "jump-cut cepat" if med < 3.5 else "cut sedang"},
        "beat": {"bpm": d.get("bpm"), "on_beat_ratio": round(beat_on / len(scenes), 2) if scenes else 0},
        "hook": {"opening_semantic": scenes[0].get("semantic") if scenes else None,
                 "opening_dur_sec": round(durs[0], 2) if durs else None,
                 "strong_hook_count": len(strong), "strong_hook_timestamps": strong[:20]},
        "lighting": lighting_summary, "phases": ph, "segments": segments,
    }
    return bp, scenes, segs

def narrative_html(bp, scenes, segs):
    """Alur naskah babak-per-babak (HTML) — mirror build_story_script."""
    ph = bp["phases"]; n = len(ph)
    opening = bp["hook"]["opening_semantic"] or "tidak diketahui"
    on_beat = (f"{int(bp['beat']['on_beat_ratio']*100)}% on-beat" if bp['beat']['on_beat_ratio'] else "tanpa data beat")
    out = [f'<p class="premis"><b>Premis:</b> buka dengan <i>{esc(opening)}</i>, mengalir '
           f'{n} babak ({esc(bp["pacing"]["style"])}, {esc(on_beat)}), tutup di '
           f'<i>{esc(ph[-1]["semantic"] if ph else opening)}</i>.</p>']
    for i, p in enumerate(ph):
        sip = [s for s in scenes if p["start"] <= (s.get("start", 0) or 0) <= p["end"]] or scenes
        is_hook = (n == 1) or (i == 0)
        is_pen = (n == 1) or (i == n - 1)
        label = ("HOOK+ISI+PENUTUP" if n == 1 else "HOOK" if i == 0 else
                 "PENUTUP / CTA" if i == n - 1 else f"ISI {i}")
        lg = [s.get("lighting") for s in sip if s.get("lighting")]
        bl = next(iter(iv.top((l.get("brightness_label") for l in lg), 1)), None)
        cl = next(iter(iv.top((l.get("contrast_label") for l in lg), 1)), None)
        tl = next(iter(iv.top((l.get("temperature_label") for l in lg), 1)), None)
        subs = iv._subs_in_range(segs, p["start"], p["end"])
        sub_txt = " / ".join(f'"{esc(t)}"' for t in subs) if subs else \
            '<span class="mut">(tak ada narasi suara — kemungkinan teks-di-layar)</span>'
        strong = [t for t in bp["hook"]["strong_hook_timestamps"] if p["start"] <= t <= p["end"]]
        out.append(
            f'<div class="babak"><div class="babak-h"><span class="tag">Babak {i+1}</span>'
            f'<span class="tag alt">{esc(label)}</span>'
            f'<span class="mut">{p["start"]}s–{p["end"]}s · {p["dur_sec"]}s · {p["n_cuts"]} potongan</span></div>'
            f'<div class="babak-b">'
            f'<div><b>Layar:</b> <span class="sem">{esc(p["semantic"])}</span>, emosi {esc(p["emotion"])}; '
            f'{esc(iv._camera_desc(p["camera"]))}</div>'
            f'<div><b>Cahaya:</b> {esc(iv._lighting_desc(bl, cl, tl))}</div>'
            f'<div><b>Framing:</b> {esc(iv._framing_desc(sip))}</div>'
            f'<div><b>Teks/dialog:</b> {sub_txt}</div>'
            + (f'<div class="hook">⚡ Hook kuat @ {esc(strong)}s — momen paling menahan perhatian</div>' if strong else '')
            + f'<div class="rekam"><b>Rekam:</b> {esc(iv._shot_direction(is_hook, is_pen, p, sip, bl))}</div>'
            f'</div></div>')
    out.append(f'<div class="pesan"><b>Pesan inti:</b><br>' +
               esc(iv._core_message(bp, ph, segs)).replace("\n\n", "<br><br>").replace("**", "") + '</div>')
    return "".join(out)

def footage_html(bp):
    """Alur footage per-babak: semantic -> query stok, rasio, durasi, zoom/adjust."""
    ph = bp["phases"]; segments = bp["segments"]; ratio = bp["source"]["aspect_ratio"]
    rows = (f'<div class="fnote">Rasio target <b>{esc(ratio)}</b>'
            f'{"" if bp["source"]["aspect_ratio_known"] else " <span class=mut>(perkiraan)</span>"} · '
            f'{len(ph)} babak footage · query = saran cari b-roll stok (Pexels/Pixabay) atau tema rekam.</div>'
            '<table class="ftab"><tr><th>Babak</th><th>Konten (semantic)</th><th>Cari footage / tema</th>'
            '<th class="r">Durasi</th><th>Gerak & koreksi</th></tr>')
    for i, p in enumerate(ph):
        sem = p["semantic"]
        query = SEMANTIC_QUERY_MAP.get(sem, DEFAULT_FALLBACK)
        sip = [s for s in segments if p["start"] <= s["start"] <= p["end"]]
        zooms = sorted({s["zoom"]["vn"] for s in sip if s.get("zoom")})
        adjs = sorted({f'{a["param"]} {a["dir"]}' for s in sip for a in (s.get("adjust") or [])})
        fx = " · ".join(([("zoom: " + ", ".join(zooms))] if zooms else []) +
                        ([("adjust: " + ", ".join(adjs))] if adjs else [])) or '<span class="mut">—</span>'
        rows += (f'<tr><td class="r mut">{i+1}</td>'
                 f'<td><span class="sem">{esc(sem)}</span></td>'
                 f'<td class="q">“{esc(query)}”</td>'
                 f'<td class="r">{p["dur_sec"]}s</td>'
                 f'<td class="mut">{fx}</td></tr>')
    return rows + "</table>"

def analyses_html(analyses):
    if not analyses:
        return '<p class="mut">Belum ada video teranalisa. Enqueue URL lalu jalankan drain.</p>'
    cards = []
    for a in analyses:
        d = a.get("analysis") or {}
        try:
            bp, scenes, segs = build_bp(d)
        except Exception as e:
            cards.append(f'<div class="card"><div class="mut">IR #{a.get("id")} tak bisa diproses: {esc(e)}</div></div>')
            continue
        slot = PLATFORM_SLOT.get(a.get("platform"), 8)
        url = a.get("source_url") or ""
        meta = (f'{bp["format"]["duration_mmss"]} ({bp["format"]["duration_sec"]}s) · rasio '
                f'{bp["source"]["aspect_ratio"]} · {bp["pacing"]["n_scenes"]} scene · '
                f'bpm {num(bp["beat"]["bpm"])} · hook: {esc(bp["hook"]["opening_semantic"] or "—")}')
        cards.append(
            f'<div class="card"><div class="card-h">'
            f'<span class="dot s{slot}"></span><b>{esc(a.get("platform"))}</b> '
            f'<span class="pill muted">{esc(a.get("category") or "")}</span> '
            f'<a class="url" href="{esc(url)}" target="_blank" rel="noopener">{esc(url[:70])}</a>'
            f'<span class="mut card-date">{esc(a.get("created_at"))}</span></div>'
            f'<div class="card-meta mut">{meta}</div>'
            f'<details open><summary>📝 Alur naskah (babak-per-babak)</summary>'
            f'<div class="det">{narrative_html(bp, scenes, segs)}</div></details>'
            f'<details><summary>🎬 Alur footage (bahan rekam / stok)</summary>'
            f'<div class="det">{footage_html(bp)}</div></details>'
            f'</div>')
    return "".join(cards)

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
                        avg_scenes=num(astats.get("avg_scenes")), avg_dur=num(astats.get("avg_dur")),
                        analyses=analyses_html(d.get("analyses") or []))

PAGE = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Viral Pipeline — Antrean, Naskah &amp; Footage</title>
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
.card{{background:var(--surf);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:16px}}
.card-h{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:14px}}
.card-h .url{{color:var(--s1);text-decoration:none;font-size:12.5px;overflow:hidden;text-overflow:ellipsis}}
.card-date{{margin-left:auto;font-size:11.5px}}
.card-meta{{font-size:12px;margin:6px 0 10px}}
details{{border-top:1px solid var(--border);padding:8px 0 2px}}
summary{{cursor:pointer;font-size:13px;font-weight:600;color:var(--ink2);padding:4px 0}}
.det{{padding:8px 2px 10px}}
.premis{{font-size:13px;margin:2px 0 12px}}
.babak{{border-left:3px solid var(--s1);background:var(--plane);border-radius:0 8px 8px 0;
 padding:8px 12px;margin-bottom:10px}}
.babak-h{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:5px}}
.tag{{background:var(--s1);color:#fff;font-size:11px;font-weight:700;padding:1px 8px;border-radius:6px}}
.tag.alt{{background:var(--grid);color:var(--ink2)}}
.babak-b{{font-size:12.5px;display:grid;gap:3px}}
.sem{{color:var(--s3);font-weight:600}}
.hook{{color:#a06600;font-weight:600}}
.rekam{{margin-top:3px;padding-top:5px;border-top:1px dashed var(--border);color:var(--ink2)}}
.pesan{{margin-top:8px;background:var(--plane);border-radius:8px;padding:10px 12px;font-size:12.5px}}
.fnote{{font-size:12px;color:var(--ink2);margin-bottom:8px}}
.ftab td,.ftab th{{font-size:12px}}
.ftab .q{{color:var(--s2);font-style:italic}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--border);font-size:11.5px;color:var(--mut)}}
</style>
<div class="wrap">
<header>
<h1>Viral Pipeline — Antrean, Naskah &amp; Footage</h1>
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
<h2>🎥 Analisa video — alur naskah &amp; footage (bahan ide)</h2>
<div class="mut" style="font-size:12px;margin-bottom:14px">Per URL teranalisa: alur cerita babak-per-babak (naskah rekam-ulang) + rencana footage per babak. Sumber: IR viral_analyzer, diterjemahkan lewat ir_to_vn.</div>
{analyses}
</section>

<section>
<h2>Job terbaru (25 terakhir)</h2>
<table>
<tr><th>ID</th><th>Platform</th><th>Kategori</th><th>Status</th><th>URL</th><th class="r">Percobaan</th><th>Dibuat</th><th>Dianalisa</th></tr>
{rows}
</table>
</section>

<footer>Diperbarui {gen} · sumber: DB-VPS schema media.* · dibangun via viral-pipeline/dashboard.py (+ir_to_vn/pexels_fetch)</footer>
</div>
"""

def main():
    d = fetch()
    open(OUT, "w", encoding="utf-8").write(render(d))
    print(f"dashboard ditulis: {OUT} ({os.path.getsize(OUT)} bytes)")

if __name__ == "__main__":
    main()
