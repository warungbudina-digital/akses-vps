#!/usr/bin/env python3
"""ir_to_vn.py — PENERJEMAH IR (viral_analyzer) -> cetak-biru reproduksi VN editor.

Ambil hasil analisa (ViralAnalysis IR) lalu petakan ke "pemahaman yang bisa
dibangun ulang" oleh VN editor di Infinix. Target = FIDELITY STRUKTURAL
(rasio/durasi/ritme-cut/beat/caption/hook), BUKAN pixel-identik.

Output (3 berkas + ringkasan ke stdout):
  <out>.srt              — caption siap IMPOR ke VN (flAddAddSubtitlesFormSRT)
  <out>.vn-blueprint.json — rencana terstruktur (machine-readable)
  <out>.vn-recipe.md     — langkah build VN + storyboard fase (human-readable)

Pakai:  ir_to_vn.py <ir.json> [--out DIR/basename] [--min-phase-sec 6]
"""
import json, sys, os, argparse
from collections import Counter

def fmt_ts(t):  # detik -> SRT "HH:MM:SS,mmm"
    if t < 0: t = 0
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def dur_of(s):
    return s.get("duration") or max(0.0, (s.get("end", 0) or 0) - (s.get("start", 0) or 0))

def top(counter, n=6):
    return dict(Counter(x for x in counter if x is not None).most_common(n))

def ratio_from_ir(d):
    """Rasio dari meta IR. Sejak analyzer commit de9f18a: aspect_ratio/width/height
    ada di TOP-LEVEL IR. IR lama (cuma `video` string) -> TAK DIKETAHUI. (label, tahu?)."""
    ar = d.get("aspect_ratio")
    w, h = d.get("width"), d.get("height")
    if ar:
        return (f"{ar} ({w}x{h})" if w and h else ar), True
    if w and h:
        r = w / h
        lab = "9:16" if r < 0.85 else "1:1" if r < 1.15 else "16:9"
        return f"{lab} ({w}x{h})", True
    return "TAK DIKETAHUI (IR lama tak simpan resolusi)", False

def build_srt(segs):
    out = []
    for i, s in enumerate(segs, 1):
        txt = (s.get("text") or "").strip()
        if not txt: continue
        out.append(f"{i}\n{fmt_ts(s.get('start',0))} --> {fmt_ts(s.get('end',0))}\n{txt}\n")
    return "\n".join(out)

def phases(scenes, min_phase_sec):
    """Kelompokkan scene beruntun ber-semantic sama jadi FASE (storyboard).
    Fase pendek digabung ke tetangga supaya jumlahnya manusiawi."""
    raw = []
    for s in scenes:
        sem = s.get("semantic") or "unknown"
        if raw and raw[-1]["semantic"] == sem:
            raw[-1]["scenes"].append(s)
        else:
            raw.append({"semantic": sem, "scenes": [s]})
    # gabung fase < min_phase_sec ke fase sebelumnya
    merged = []
    for ph in raw:
        d = sum(dur_of(s) for s in ph["scenes"])
        if merged and d < min_phase_sec:
            merged[-1]["scenes"].extend(ph["scenes"])
        else:
            merged.append(ph)
    res = []
    for ph in merged:
        sc = ph["scenes"]
        d = sum(dur_of(s) for s in sc)
        res.append({
            "start": round(sc[0].get("start", 0), 2),
            "end":   round(sc[-1].get("end", 0), 2),
            "dur_sec": round(d, 2),
            "n_cuts": len(sc),
            "avg_cut_sec": round(d / len(sc), 2),
            "semantic": Counter(s.get("semantic") for s in sc).most_common(1)[0][0],
            "emotion":  Counter(s.get("emotion")  for s in sc).most_common(1)[0][0],
            "camera":   top((s.get("camera_movement") for s in sc), 3),
            "beat_sync_ratio": round(sum(1 for s in sc if s.get("beat_sync")) / len(sc), 2),
        })
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ir"); ap.add_argument("--out"); ap.add_argument("--min-phase-sec", type=float, default=6.0)
    a = ap.parse_args()
    d = json.load(open(a.ir))
    base = a.out or os.path.splitext(a.ir)[0]

    scenes = d.get("scene_analysis") or []
    segs   = d.get("subtitle_segments") or []
    durs   = [dur_of(s) for s in scenes]
    total  = sum(durs)
    ratio_lab, ratio_known = ratio_from_ir(d)
    n_fade = sum(1 for s in scenes if s.get("transition") == "fade")
    n_cut  = sum(1 for s in scenes if s.get("transition") == "cut")
    beat_on = sum(1 for s in scenes if s.get("beat_sync"))
    strong = [round(s.get("start", 0), 1) for s in scenes if s.get("hook_strength") == "strong_hook"]
    med = sorted(durs)[len(durs)//2] if durs else 0
    ss = d.get("subtitle_style") or {}
    ph = phases(scenes, a.min_phase_sec)
    # titik-cut = batas antar-scene (start scene ke-2 dst) = tempat split di VN
    cut_points = [round(s.get("start", 0), 2) for s in scenes if (s.get("start", 0) or 0) > 0.05]
    # momen zoom (analyzer >=734c838 pisah zoom_in/zoom_out; IR lama = "zoom" tanpa arah)
    zoom_moments = [{"t": round(s.get("start", 0), 2),
                     "dir": s.get("camera_movement"),
                     "vn": {"zoom_in": "Perbesar", "zoom_out": "Perkecil"}.get(s.get("camera_movement"), "Perbesar/Perkecil?")}
                    for s in scenes if s.get("camera_movement") in ("zoom_in", "zoom_out", "zoom")]

    bp = {
        "source": {"bpm": d.get("bpm"), "total_sec": round(total, 2),
                   "aspect_ratio": ratio_lab, "aspect_ratio_known": ratio_known},
        "format": {"orientation_hint": ratio_lab, "duration_sec": round(total, 2),
                   "duration_mmss": f"{int(total//60)}:{int(total%60):02d}", "long_form": total > 90},
        "pacing": {"n_scenes": len(scenes), "cuts": n_cut, "fades": n_fade,
                   "median_cut_sec": round(med, 2), "min_cut_sec": round(min(durs), 2) if durs else 0,
                   "max_cut_sec": round(max(durs), 2) if durs else 0,
                   "style": "jump-cut cepat" if med < 3.5 else "cut sedang",
                   "cut_points_sec": cut_points},
        "camera": top((s.get("camera_movement") for s in scenes)),
        "zoom_moments": zoom_moments,
        "beat":  {"bpm": d.get("bpm"), "on_beat_ratio": round(beat_on/len(scenes), 2) if scenes else 0},
        "captions": {"n_segments": len(segs), "words_avg": ss.get("word_count_avg"),
                     "speed": ss.get("speed"), "srt_file": base + ".srt",
                     "total_chars": sum(len(s.get("text","")) for s in segs)},
        "hook": {"opening_semantic": scenes[0].get("semantic") if scenes else None,
                 "opening_dur_sec": round(durs[0], 2) if durs else None,
                 "strong_hook_count": len(strong), "strong_hook_timestamps": strong[:20]},
        "clip_semantics": top((s.get("semantic") for s in scenes), 8),
        "emotion_signal_noisy": top((s.get("emotion") for s in scenes)),
        "phases": ph,
    }

    # tulis SRT + blueprint json + cutlist (satu timestamp/baris, utk otomasi split VN)
    open(base + ".srt", "w").write(build_srt(segs))
    json.dump(bp, open(base + ".vn-blueprint.json", "w"), ensure_ascii=False, indent=2)
    open(base + ".cutlist.txt", "w").write("\n".join(f"{t:.2f}" for t in cut_points) + "\n")

    # recipe markdown (langkah VN + storyboard)
    r = []
    r.append(f"# Cetak-biru reproduksi VN — {os.path.basename(a.ir)}\n")
    r.append(f"Target: **fidelity struktural** (kerangka), bukan pixel-identik. "
             f"Durasi {bp['format']['duration_mmss']} ({bp['format']['duration_sec']}s), "
             f"{'LONG-FORM' if bp['format']['long_form'] else 'short-form'}.\n")
    r.append("## Langkah build di VN (Infinix)\n")
    r.append(f"1. **Rasio** (`llFrameType`): {ratio_lab}."
             + ("" if ratio_known else " ⚠️ IR tak simpan resolusi — konfirmasi dari sumber; default reel = 9:16.") + "\n")
    r.append(f"2. **Impor footage** lalu potong (`editor_toolbar_split`) mengikuti ritme "
             f"**{bp['pacing']['style']}** (median {bp['pacing']['median_cut_sec']}s/cut, "
             f"{bp['pacing']['cuts']} cut + {bp['pacing']['fades']} fade). Jump-cut = buang jeda antar kalimat. "
             f"**Titik-cut presisi ({len(cut_points)}) di `{os.path.basename(base)}.cutlist.txt`** (satu detik/baris) "
             f"— split di tiap timestamp; tiap fase punya kepadatan cut sendiri (lihat storyboard).\n")
    r.append(f"3. **Caption**: impor `{os.path.basename(base)}.srt` via `flAddAddSubtitlesFormSRT` "
             f"({bp['captions']['n_segments']} segmen, ~{bp['captions']['words_avg']} kata, {bp['captions']['speed']}). "
             f"Caption menerus = alat retensi utama video ini.\n")
    r.append(f"4. **Musik + beat**: bpm **{bp['beat']['bpm']}**, {int(bp['beat']['on_beat_ratio']*100)}% cut on-beat "
             f"→ tambah musik lalu beat-sync (`UseMusicDetailActivity`→Ketukan, atau AutoCut).\n")
    nzi = sum(1 for z in zoom_moments if z['dir'] == 'zoom_in')
    nzo = sum(1 for z in zoom_moments if z['dir'] == 'zoom_out')
    nzq = sum(1 for z in zoom_moments if z['dir'] == 'zoom')  # IR lama, arah tak diketahui
    zline = (f"5. **Dinamika kamera** {json.dumps(bp['camera'], ensure_ascii=False)}. "
             f"**Zoom: {len(zoom_moments)} momen** ({nzi} in→`Perbesar`, {nzo} out→`Perkecil`"
             + (f", {nzq} arah-tak-diketahui (IR lama)" if nzq else "") + "). "
             f"Terapkan `editor_toolbar_clipZoom` per arah di timestamp momen (lihat `zoom_moments` di blueprint).")
    if zoom_moments:
        zline += " Momen: " + ", ".join(f"{z['t']}s→{z['vn']}" for z in zoom_moments[:12])
        if len(zoom_moments) > 12: zline += " …"
    r.append(zline + "\n")
    r.append(f"6. **Hook** (3 detik pertama menentukan): buka dengan **{bp['hook']['opening_semantic']}** "
             f"({bp['hook']['opening_dur_sec']}s). {bp['hook']['strong_hook_count']} momen 'strong hook' di "
             f"detik: {bp['hook']['strong_hook_timestamps'][:10]} — jadikan titik tekanan/emphasis.\n")
    r.append("\n## Storyboard fase (234 scene → fase yang bisa diikuti)\n")
    r.append("| # | mulai | durasi | cut | rata cut | jenis konten | emosi(CLIP,noisy) | kamera |\n|---|---|---|---|---|---|---|---|")
    for i, p in enumerate(ph, 1):
        r.append(f"| {i} | {p['start']}s | {p['dur_sec']}s | {p['n_cuts']} | {p['avg_cut_sec']}s | "
                 f"{p['semantic']} | {p['emotion']} | {'/'.join(p['camera'].keys())} |")
    r.append(f"\n_{len(ph)} fase. Sinyal semantic/emotion dari CLIP zero-shot = ARAH, bukan kebenaran mutlak._\n")
    open(base + ".vn-recipe.md", "w").write("\n".join(r))

    # ringkasan stdout
    print(f"IR: {os.path.basename(a.ir)}  |  durasi {bp['format']['duration_mmss']}  |  rasio {ratio_lab}")
    print(f"pacing: {bp['pacing']['n_scenes']} scene, {bp['pacing']['cuts']} cut/{bp['pacing']['fades']} fade, "
          f"median {bp['pacing']['median_cut_sec']}s ({bp['pacing']['style']})")
    print(f"beat: bpm {bp['beat']['bpm']}, {int(bp['beat']['on_beat_ratio']*100)}% on-beat")
    print(f"caption: {bp['captions']['n_segments']} segmen -> {base}.srt")
    print(f"hook: buka '{bp['hook']['opening_semantic']}', {bp['hook']['strong_hook_count']} strong-hook")
    print(f"fase storyboard: {len(ph)}")
    print(f"tulis: {base}.srt , {base}.vn-blueprint.json , {base}.vn-recipe.md")

if __name__ == "__main__":
    main()
