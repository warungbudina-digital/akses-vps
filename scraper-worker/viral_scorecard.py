#!/usr/bin/env python3
"""Viral Scorecard — lapisan KEPUTUSAN (jalan di HUB akses-vps).

Baca metrik objektif dari DB-VPS `trend.*` (hasil scraper .61) → hitung skor
tertimbang 4-grup → zonasi 🟢🟡🔴 → tulis `trend.viral_score`.

Model (bisa disetel di scorecard.config.json):
  Total = G1*0.30 + G2*0.30 + G3*0.20 + G4*0.20 ; tiap grup = rata-rata sub-kriteria (1..5)
  Zona: green >=4.2 · yellow >=3.0 · red <3.0
  Grup: G1 Algoritma/Retensi(Hook,Pacing,Rewatch) · G2 Psikologi/Share(Emosi,Relate,NilaiBerbagi)
        G3 Relevansi/Tren(TrendJacking,Universalitas) · G4 Feasibility(KecepatanEksekusi,BiayaVsHasil)

Sumber tiap dimensi (keputusan 27/9):
  scraper (objektif, SEMUA kandidat) : NilaiBerbagi (save/share-rate) · TrendJacking (plays vs median akun)
  analyzer .50 (Tier-2, top-K)       : Hook · Pacing · Rewatch · Emosi   [STUB: butuh download+analisa video]
  Gemini via ai_wiki_query (Tier-2)  : Relatabilitas · Universalitas
  heuristik                          : KecepatanEksekusi · BiayaVsHasil

Penyaringan bertingkat: Tier-1 objektif utk semua → ranking → hanya top-K (default 10)
dapat Tier-2 (analyzer+Gemini). Dimensi yg belum ada = pending (NULL); total provisional
(bobot dinormalisasi ulang atas grup yg terisi) + complete=false.

Pakai:
  python3 viral_scorecard.py                 # skor run scrape terbaru → tulis DB
  python3 viral_scorecard.py --dry-run       # cetak tabel, JANGAN tulis DB
  python3 viral_scorecard.py --no-llm        # lewati Gemini (Relate/Universal pending)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DB_SSH = ["ssh", "-o", "BatchMode=yes", "db-vps"]
DB_PSQL = "sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 "
AI_WIKI = os.environ.get("AI_WIKI_QUERY",
                         str(Path.home() / "tool-appium/scripts/ai_wiki_query.py"))

# grup → (bobot key, [ (dim, sumber) ... ])
GROUPS = {
    "g1": [("s_hook", "analyzer"), ("s_pacing", "analyzer"), ("s_rewatch", "analyzer")],
    "g2": [("s_emosi", "analyzer"), ("s_relate", "gemini"), ("s_share", "scraper")],
    "g3": [("s_trend", "scraper"), ("s_universal", "gemini")],
    "g4": [("s_speed", "heuristik"), ("s_roi", "heuristik")],
}


def load_config() -> dict:
    p = HERE / "scorecard.config.json"
    cfg = json.loads(p.read_text()) if p.exists() else {}
    cfg.setdefault("weights", {"g1": .30, "g2": .30, "g3": .20, "g4": .20})
    cfg.setdefault("zones", {"green": 4.2, "yellow": 3.0})
    cfg.setdefault("top_k", 10)
    cfg.setdefault("thresholds", {})
    return cfg


# ---------- DB ----------
def db_json(select_sql: str):
    """Jalankan SELECT dan kembalikan list[dict] via json_agg."""
    sql = f"SET ROLE scraper; SELECT COALESCE(json_agg(t), '[]') FROM ({select_sql}) t;"
    p = subprocess.run(DB_SSH + [DB_PSQL + "-tAc " + shquote(sql)],
                       text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("psql read gagal: " + p.stderr.strip()[-300:])
    # ssh db-vps mengawali stdout dgn banner MOTD (login IDCloudHost) & bisa ada sisa
    # di belakang → cari '[' pertama (json_agg = array; banner tak mengandung '[')
    # lalu raw_decode (berhenti di akhir JSON valid, abaikan sisa).
    i = p.stdout.find("[")
    if i < 0:
        return []
    obj, _ = json.JSONDecoder().raw_decode(p.stdout[i:])
    return obj


def db_write(sql: str):
    p = subprocess.run(DB_SSH + [DB_PSQL + "-q -f -"], input="SET ROLE scraper;\n" + sql,
                       text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("psql write gagal: " + p.stderr.strip()[-300:])


def shquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        return "'" + json.dumps(v).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def fetch_candidates(run_id: str | None):
    """Snapshot video TERBARU per video (opsional dibatasi 1 run) + meta."""
    cond = "s.plays IS NOT NULL AND s.plays > 0"
    if run_id:
        cond = f"s.run_id = {q(run_id)} AND " + cond
    return db_json(f"""
      SELECT v.video_id, v.handle, v.description, v.hashtags, v.duration_s,
             s.plays, s.likes, s.comments, s.shares, s.saves, s.run_id
      FROM trend.tiktok_video v
      JOIN LATERAL (
        SELECT * FROM trend.tiktok_video_snapshot s2
        WHERE s2.video_id = v.video_id ORDER BY taken_at DESC LIMIT 1
      ) s ON true
      WHERE {cond}
    """)


# ---------- pemetaan metrik → skala 1..5 ----------
def scale(x, lo, hi):
    if x is None:
        return None
    return round(max(1.0, min(5.0, 1 + 4 * (x - lo) / (hi - lo))), 2)


def rate(part, whole):
    return 100 * (part or 0) / whole if whole else None


# ---------- Tier-2: Gemini (LLM) ----------
def gemini_relate_universal(desc: str, timeout: int = 200):
    """Skor Relatabilitas & Universalitas 1..5 via ai_wiki_query --raw gemini.
    Prompt paksa inline pendek (hindari mode riset/artifact)."""
    prompt = (
        "Nilai video pendek AI/tech ini dari CAPTION-nya, skala INTEGER 1-5. "
        "Relatabilitas = seberapa banyak orang merasa 'ini aku banget'. "
        "Universalitas = dipahami masyarakat luas (5) vs niche sempit (1). "
        "Jawab HANYA satu baris JSON inline: {\"relatabilitas\":N,\"universalitas\":N}. "
        "JANGAN buat artikel/artifact, JANGAN mode riset. CAPTION: " + (desc or "")[:280]
    )
    try:
        p = subprocess.run(["python3", AI_WIKI, "--raw", "gemini", "--prompt", prompt],
                           text=True, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            return None, None, "gemini exit " + str(p.returncode)
        out = json.loads(p.stdout.strip() or "{}")
        ans = out.get("answer", "") if isinstance(out, dict) else str(out)
        m = re.search(r"\{[^{}]*relatabilitas[^{}]*\}", ans, re.I)
        if not m:
            return None, None, "format jawaban tak terbaca"
        d = json.loads(m.group(0))
        r = clamp15(d.get("relatabilitas")); u = clamp15(d.get("universalitas"))
        return r, u, None
    except subprocess.TimeoutExpired:
        return None, None, "gemini timeout"
    except Exception as e:
        return None, None, str(e)[:120]


def clamp15(v):
    try:
        return float(max(1, min(5, int(round(float(v))))))
    except (TypeError, ValueError):
        return None


# ---------- Tier-2: analyzer .50 (WIRED via pipeline enqueue + media.video_analysis) ----------
ENQUEUE = os.environ.get("ENQUEUE_PY", str(HERE / "../viral-pipeline/enqueue.py"))
ENQUEUE_ENABLED = True  # di-set main() (mati saat --dry-run/--no-enqueue)

HOOK_MAP = {"strong_hook": 5.0, "medium_hook": 3.5, "weak_hook": 2.0, "no_hook": 1.0, "none": 1.0}
EMO_NEUTRAL = {"neutral face", "unknown", "no face", ""}


def _fetch_ir(video_id: str):
    """Ambil IR (analysis jsonb) analyzer .50 utk video TikTok ini, atau None."""
    rows = db_json(
        "SELECT va.analysis FROM media.video_analysis va "
        "JOIN media.video_ingest vi ON vi.id = va.ingest_id "
        f"WHERE vi.platform = 'tiktok' AND vi.external_id = {q(video_id)} "
        "ORDER BY va.id DESC LIMIT 1")
    return rows[0]["analysis"] if rows else None


def map_ir_to_dims(a: dict) -> dict:
    """Petakan IR ViralAnalysis (.50) → 4 sub-skor 1..5. Ambang = titik kalibrasi (tunable)."""
    scenes = a.get("scene_analysis") or []
    dur = a.get("duration_sec") or 0
    # Hook = hook_strength SCENE PERTAMA (pembuka = 3 detik)
    s_hook = HOOK_MAP.get((scenes[0].get("hook_strength") or "").lower()) if scenes else None
    # Pacing = kepadatan cut (scene/detik) + motion rata-rata
    s_pacing = None
    if scenes and dur:
        p_cut = scale(len(scenes) / dur, 0.05, 0.5)          # 1 scene/20s .. 1 scene/2s
        p_mot = scale(sum(s.get("motion", 0) or 0 for s in scenes) / len(scenes), 0.5, 8.0)
        vals = [v for v in (p_cut, p_mot) if v is not None]
        s_pacing = round(sum(vals) / len(vals), 2) if vals else None
    # Re-watchability = makin pendek makin loopable (invert durasi)
    s_rewatch = scale(-dur, -60, -8) if dur else None        # <=8s=5 .. >=60s=1
    # Emosi = fraksi scene ber-emosi non-netral + tempo (bpm)
    s_emosi = None
    if scenes:
        frac = sum(1 for s in scenes if (s.get("emotion") or "").lower() not in EMO_NEUTRAL) / len(scenes)
        e_emo = scale(frac, 0.1, 0.8)
        e_bpm = scale(a.get("bpm"), 80, 160) if a.get("bpm") else None
        vals = [v for v in (e_emo, e_bpm) if v is not None]
        s_emosi = round(sum(vals) / len(vals), 2) if vals else None
    return {"s_hook": s_hook, "s_pacing": s_pacing, "s_rewatch": s_rewatch, "s_emosi": s_emosi}


def analyzer_ir(video_id: str, handle: str):
    """IR analyzer .50 → 4 dim. ASINKRON: kalau IR sudah ada di media.video_analysis
    → petakan+kembalikan; kalau belum → enqueue URL TikTok (analyzer proses saat drain
    .50 berikutnya, pola analyzer-pipeline-trigger.sh) → kembalikan None (pending).
    Run scorecard BERIKUTNYA (stlh drain) yang mengisi 4 dim ini."""
    ir = _fetch_ir(video_id)
    if ir:
        return map_ir_to_dims(ir)
    if ENQUEUE_ENABLED:
        url = f"https://www.tiktok.com/@{handle}/video/{video_id}"
        try:
            subprocess.run(["python3", ENQUEUE, "viral_video", url],
                           capture_output=True, text=True, timeout=30)  # idempoten (ON CONFLICT)
        except Exception:
            pass
    return None


# ---------- heuristik Feasibility ----------
def heuristik_feasibility(cand, s_share, cfg):
    th = cfg["thresholds"].get("duration_fast_s", {"lo": 15, "hi": 90})
    dur = cand.get("duration_s")
    # makin pendek makin cepat dibuat (skor tinggi) → invert skala durasi
    s_speed = None
    if dur is not None:
        s_speed = scale(-dur, -th["hi"], -th["lo"])
    # Biaya vs Hasil ≈ potensi hasil (share proxy) × kemudahan (speed)
    if s_share is not None and s_speed is not None:
        s_roi = round((s_share + s_speed) / 2, 2)
    else:
        s_roi = s_share or s_speed
    return s_speed, s_roi


# ---------- skor satu video ----------
def score_video(cand, handle_median_plays, cfg, tier2: bool, use_llm: bool):
    th = cfg["thresholds"]
    plays = cand["plays"]
    sr = rate(cand.get("saves"), plays)
    shr = rate(cand.get("shares"), plays)
    # G2 NilaiBerbagi (scraper): blend save-rate (utama) + share-rate
    s_share = None
    ns = scale(sr, *_lohi(th, "save_rate_pct", 0.1, 3.0))
    nh = scale(shr, *_lohi(th, "share_rate_pct", 0.1, 2.0))
    if ns is not None or nh is not None:
        vals = [v for v in (ns, nh) if v is not None]
        s_share = round(sum(vals) / len(vals), 2)
    # G3 TrendJacking (scraper): plays vs median akun
    s_trend = None
    if handle_median_plays:
        ratio = plays / handle_median_plays
        s_trend = scale(ratio, *_lohi(th, "trend_ratio", 0.5, 4.0))

    dims = {"s_share": s_share, "s_trend": s_trend}
    sources = {"s_share": "scraper", "s_trend": "scraper"}

    if tier2:
        ir = analyzer_ir(cand["video_id"], cand["handle"])
        for k in ("s_hook", "s_pacing", "s_rewatch", "s_emosi"):
            v = (ir or {}).get(k)
            dims[k] = v
            sources[k] = "analyzer" if v is not None else "pending"
        if use_llm:
            r, u, err = gemini_relate_universal(cand.get("description") or "")
            dims["s_relate"], dims["s_universal"] = r, u
            sources["s_relate"] = "gemini" if r is not None else "pending"
            sources["s_universal"] = "gemini" if u is not None else "pending"
        else:
            dims["s_relate"] = dims["s_universal"] = None
            sources["s_relate"] = sources["s_universal"] = "pending"
        s_speed, s_roi = heuristik_feasibility(cand, s_share, cfg)
        dims["s_speed"], dims["s_roi"] = s_speed, s_roi
        sources["s_speed"] = "heuristik" if s_speed is not None else "pending"
        sources["s_roi"] = "heuristik" if s_roi is not None else "pending"
    else:
        for k, _src in _all_dims():
            dims.setdefault(k, None)
            sources.setdefault(k, "pending" if k not in ("s_share", "s_trend") else sources.get(k))

    return finalize(dims, sources, cfg)


def _lohi(th, key, dlo, dhi):
    t = th.get(key, {})
    return t.get("lo", dlo), t.get("hi", dhi)


def _all_dims():
    for g, items in GROUPS.items():
        for dim, src in items:
            yield dim, src


def finalize(dims, sources, cfg):
    w = cfg["weights"]; z = cfg["zones"]
    gvals = {}
    for g, items in GROUPS.items():
        vs = [dims.get(dim) for dim, _ in items if dims.get(dim) is not None]
        gvals[g] = round(sum(vs) / len(vs), 3) if vs else None
    # total tertimbang; bobot dinormalisasi ulang atas grup yg ada nilainya
    num = sum(gvals[g] * w[g] for g in GROUPS if gvals[g] is not None)
    den = sum(w[g] for g in GROUPS if gvals[g] is not None)
    total = round(num / den, 3) if den else None
    complete = all(dims.get(dim) is not None for dim, _ in _all_dims())
    zone = None
    if total is not None:
        zone = "green" if total >= z["green"] else ("yellow" if total >= z["yellow"] else "red")
    return {**dims, "g1": gvals["g1"], "g2": gvals["g2"], "g3": gvals["g3"], "g4": gvals["g4"],
            "total": total, "zone": zone, "complete": complete, "sources": sources}


# ---------- main ----------
def main() -> int:
    ap = argparse.ArgumentParser(description="Viral Scorecard — lapisan keputusan")
    ap.add_argument("--run-id", default=None, help="batasi ke run scrape tertentu (default: semua video terbaru)")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--no-llm", action="store_true", help="lewati Gemini")
    ap.add_argument("--no-enqueue", action="store_true", help="jangan enqueue video ke analyzer .50")
    ap.add_argument("--dry-run", action="store_true", help="cetak saja, jangan tulis DB / enqueue")
    args = ap.parse_args()
    global ENQUEUE_ENABLED
    ENQUEUE_ENABLED = not (args.dry_run or args.no_enqueue)
    cfg = load_config()
    top_k = args.top_k or cfg["top_k"]
    score_run = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]

    cands = fetch_candidates(args.run_id)
    if not cands:
        print("tak ada kandidat video (jalankan scraper dulu).")
        return 0
    # median plays per handle (utk Trend Jacking)
    by_handle = {}
    for c in cands:
        by_handle.setdefault(c["handle"], []).append(c["plays"])
    med = {h: median(v) for h, v in by_handle.items()}

    # Tier-1 utk semua → ranking
    tier1 = [(c, score_video(c, med[c["handle"]], cfg, tier2=False, use_llm=False)) for c in cands]
    tier1.sort(key=lambda cs: (cs[1]["total"] or 0), reverse=True)
    top_ids = {c["video_id"] for c, _ in tier1[:top_k]}

    rows = []
    for c in cands:
        res = score_video(c, med[c["handle"]], cfg, tier2=(c["video_id"] in top_ids), use_llm=not args.no_llm)
        rows.append((c, res))
    rows.sort(key=lambda cr: (cr[1]["total"] or 0), reverse=True)

    print(f"{'total':>6} {'zone':>7} {'g1':>4} {'g2':>4} {'g3':>4} {'g4':>4}  {'✓':>1}  @handle  caption")
    for c, r in rows:
        z = {"green": "🟢", "yellow": "🟡", "red": "🔴", None: "·"}[r["zone"]]
        tot = f"{r['total']:.2f}" if r["total"] is not None else "  – "
        gg = lambda k: f"{r[k]:.1f}" if r[k] is not None else " – "
        print(f"{tot:>6} {z:>5} {gg('g1'):>4} {gg('g2'):>4} {gg('g3'):>4} {gg('g4'):>4}  "
              f"{'Y' if r['complete'] else 'p'}  @{c['handle']}  {(c.get('description') or '')[:38]}")

    if args.dry_run:
        print("\n[dry-run] tidak menulis DB.")
        return 0

    sql = []
    for c, r in rows:
        sql.append(
            "INSERT INTO trend.viral_score (run_id,video_id,s_hook,s_pacing,s_rewatch,"
            "s_emosi,s_relate,s_share,s_trend,s_universal,s_speed,s_roi,g1,g2,g3,g4,total,zone,complete,sources) "
            f"VALUES ({q(score_run)},{q(c['video_id'])},{q(r['s_hook'])},{q(r['s_pacing'])},{q(r['s_rewatch'])},"
            f"{q(r['s_emosi'])},{q(r['s_relate'])},{q(r['s_share'])},{q(r['s_trend'])},{q(r['s_universal'])},"
            f"{q(r['s_speed'])},{q(r['s_roi'])},{q(r['g1'])},{q(r['g2'])},{q(r['g3'])},{q(r['g4'])},"
            f"{q(r['total'])},{q(r['zone'])},{q(r['complete'])},{q(r['sources'])});")
    db_write("\n".join(sql))
    print(f"\nditulis {len(rows)} baris → trend.viral_score (run {score_run})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
