#!/usr/bin/env python3
"""ir_to_vn.py — PENERJEMAH IR (viral_analyzer) -> cetak-biru reproduksi VN editor.

Ambil hasil analisa (ViralAnalysis IR) lalu petakan ke "pemahaman yang bisa
dibangun ulang" oleh VN editor di Infinix. Target = FIDELITY STRUKTURAL
(rasio/durasi/ritme-cut/beat/caption/hook), BUKAN pixel-identik.

Output (4 berkas + ringkasan ke stdout):
  <out>.srt               — caption siap IMPOR ke VN (flAddAddSubtitlesFormSRT)
  <out>.vn-blueprint.json  — rencana terstruktur (machine-readable)
  <out>.vn-recipe.md      — langkah build VN + storyboard fase (human-readable)
  <out>.story-script.md   — alur cerita babak-per-babak (bahasa naratif) + arahan
                             "apa yang harus direkam" per babak, buat kreator/model
                             AI kreatif menulis naskah rekam-ulang yang match pesan
                             video sumber. DIHASILKAN OTOMATIS TIAP ANALISA VIDEO.

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

CAMERA_DESC = {
    "static":    "kamera diam (tripod/statis), framing stabil",
    "pan":       "kamera bergerak menyamping (pan) mengikuti aksi",
    "shake":     "kamera goyang/handheld — kesan mentah dan energik",
    "fast_move": "kamera bergerak cepat — energi tinggi, mengejar aksi",
    "zoom_in":   "kamera zoom IN (mendekat) — menekankan detail/emosi",
    "zoom_out":  "kamera zoom OUT (menjauh) — membuka konteks",
    "zoom":      "kamera zoom (arah tak spesifik di IR lama)",
}

def _camera_desc(cams):
    if not cams:
        return "tidak ada gerakan kamera dominan terdeteksi"
    return "; ".join(f"{CAMERA_DESC.get(c, c)} ({n}x)" for c, n in cams.items())

def _lighting_desc(bl, cl, tl):
    parts = []
    if bl == "dark": parts.append("pencahayaan REDUP/gelap")
    elif bl == "bright": parts.append("pencahayaan TERANG/high-key")
    elif bl: parts.append("pencahayaan normal")
    if cl == "low": parts.append("kontras rendah (flat/lembut)")
    elif cl == "high": parts.append("kontras tinggi (tegas/dramatis)")
    if tl == "warm": parts.append("nuansa warna HANGAT (oranye/kuning)")
    elif tl == "cool": parts.append("nuansa warna DINGIN (biru)")
    return ", ".join(parts) if parts else "tidak ada data pencahayaan"

def _subs_in_range(segs, t0, t1):
    return [s.get("text", "").strip() for s in segs
            if s.get("text", "").strip() and (s.get("start", 0) or 0) < t1 and (s.get("end", 0) or 0) > t0]

def _framing_desc(scenes_in_phase):
    has_face = any((s.get("framing") or {}).get("faces") for s in scenes_in_phase)
    positions = top(((s.get("framing") or {}).get("speaker_position") for s in scenes_in_phase), 2)
    if has_face:
        pos = "/".join(positions.keys()) if positions and next(iter(positions)) != "unknown" else "tidak spesifik"
        return f"ADA wajah/orang di frame (posisi: {pos}) → rekam gaya talking-head/wajah menghadap kamera"
    return "TIDAK ada wajah terdeteksi → shot objek/teks/B-roll, bukan talking-head"

def _shot_direction(is_hook, is_penutup, p, scenes_in_phase, bl):
    has_face = any((s.get("framing") or {}).get("faces") for s in scenes_in_phase)
    parts = []
    if is_hook:
        parts.append("buat 1-3 detik pertama SANGAT jelas & langsung nyantol (mengejutkan/relate) — ini penentu penonton lanjut nonton atau scroll")
    if is_penutup:
        parts.append("pastikan pesan/ajakan mendarat jelas di sini — ini yang paling diingat penonton setelah video selesai")
    if has_face:
        parts.append("posisikan wajah/tubuh presenter menghadap kamera, ekspresi harus cocok mood babak ini")
    else:
        parts.append("ambil footage objek/teks/aksi (B-roll) sesuai tema babak, tanpa perlu wajah di kamera")
    if p["n_cuts"] > 1 and p["avg_cut_sec"] < 2.5:
        parts.append(f"siapkan minimal {p['n_cuts']} klip pendek terpisah (~{p['avg_cut_sec']}s/klip) untuk di-jump-cut, jangan 1 take panjang")
    else:
        parts.append(f"1 take ~{p['dur_sec']}s cukup, tidak perlu banyak potongan")
    if bl == "dark":
        parts.append("syuting di lokasi/waktu minim cahaya, atau turunkan exposure saat editing")
    elif bl == "bright":
        parts.append("syuting di tempat terang/siang hari")
    return "; ".join(parts) + "."

def _core_message(bp, ph, segs):
    all_text = " ".join(s.get("text", "") for s in segs if s.get("text", "").strip())
    cta_words = ["komen", "follow", "like", "share", "subscribe", "dm", "save",
                 "bagikan", "klik", "link di bio", "tonton sampai habis"]
    has_cta = any(w in all_text.lower() for w in cta_words)
    lines = []
    if all_text.strip():
        lines.append(f'Narasi suara yang tertangkap: "{all_text.strip()}"')
    else:
        lines.append("Tidak ada narasi suara yang tertangkap — pesan kemungkinan besar disampaikan lewat "
                      "TEKS DI LAYAR (on-screen text), bukan suara. Pastikan naskah rekam-ulang menuliskan "
                      "teks overlay yang jelas per babak, jangan andalkan dialog.")
    if has_cta:
        lines.append("Terdeteksi pola AJAKAN AKSI (CTA) dalam narasi — pastikan versi rekam ulang punya CTA "
                      "setara (komen kata kunci / follow / tonton sampai akhir) supaya efek engagement ikut "
                      "ter-reproduksi, bukan cuma visualnya.")
    hook_lab = bp["hook"]["opening_semantic"] or "tidak diketahui"
    lines.append(f"Struktur keseluruhan: buka dengan **{hook_lab}** dalam {bp['hook']['opening_dur_sec']}s "
                 f"pertama, lalu {len(ph)} babak mengalir dengan ritme **{bp['pacing']['style']}**, "
                 f"ditutup di babak bertema **{ph[-1]['semantic'] if ph else hook_lab}**. Reproduksi yang "
                 f"benar bukan cuma meniru visualnya, tapi menjaga URUTAN dan RITME transisi antar-babak ini.")
    return "\n\n".join(lines)

def build_story_script(scenes, segs, ph, bp, base):
    """Alur cerita babak-per-babak (naratif, bukan tabel teknis) supaya kreator/model
    AI kreatif bisa membayangkan visualnya dan menulis naskah rekam-ulang yang match
    dengan pesan video sumber. Dipanggil OTOMATIS tiap analisa (bukan on-request)."""
    r = []
    r.append(f"# Alur Cerita & Panduan Rekam — {os.path.basename(base)}\n")
    r.append(f"> Dibaca oleh **kreator/model AI kreatif** untuk membayangkan visual & menulis naskah rekam "
             f"ulang. Durasi total {bp['format']['duration_mmss']} ({bp['format']['duration_sec']}s), "
             f"rasio {bp['source']['aspect_ratio']}.\n")
    opening_sem = bp["hook"]["opening_semantic"] or "tidak diketahui"
    on_beat_txt = (f"selaras irama musik ({int(bp['beat']['on_beat_ratio']*100)}% on-beat)"
                   if bp["beat"]["on_beat_ratio"] else "tanpa data selaras-beat")
    r.append(f"**Premis 1-kalimat:** video ini membuka dengan *{opening_sem}* lalu bergerak lewat "
             f"{len(ph)} babak visual sebelum berakhir di *{ph[-1]['semantic'] if ph else opening_sem}*, "
             f"disokong {bp['pacing']['cuts']} potongan ({bp['pacing']['style']}), {on_beat_txt}.\n")

    r.append("## Alur cerita, langkah demi langkah\n")
    n = len(ph)
    for i, p in enumerate(ph):
        scenes_in_phase = [s for s in scenes if p["start"] <= (s.get("start", 0) or 0) <= p["end"]] or scenes
        is_hook = (n == 1) or (i == 0)
        is_penutup = (n == 1) or (i == n - 1)
        if n == 1:
            label = "HOOK + ISI + PENUTUP (video super pendek, satu napas)"
        elif i == 0:
            label = "HOOK (pembuka — menentukan apakah penonton lanjut nonton)"
        elif i == n - 1:
            label = "PENUTUP / PAYOFF-CTA (pesan mendarat / ajakan aksi)"
        else:
            label = f"ISI / BUILD-UP {i}"

        strong_here = [t for t in bp["hook"]["strong_hook_timestamps"] if p["start"] <= t <= p["end"]]
        lg = [s.get("lighting") for s in scenes_in_phase if s.get("lighting")]
        bl = next(iter(top((l.get("brightness_label") for l in lg), 1)), None)
        cl = next(iter(top((l.get("contrast_label") for l in lg), 1)), None)
        tl = next(iter(top((l.get("temperature_label") for l in lg), 1)), None)
        subs = _subs_in_range(segs, p["start"], p["end"])
        sub_txt = " / ".join(f'"{t}"' for t in subs) if subs else \
            "_(tidak ada narasi suara terdeteksi di sini — kemungkinan pesan lewat teks-di-layar)_"

        r.append(f"### Babak {i+1} — {label}\n")
        r.append(f"**Waktu:** {p['start']}s – {p['end']}s ({p['dur_sec']}s, {p['n_cuts']} potongan)\n")
        r.append(f"**Apa yang terlihat di layar:** adegan bertipe **{p['semantic']}**, nuansa emosi "
                 f"**{p['emotion']}** (sinyal AI, arah bukan pasti), {_camera_desc(p['camera'])}.\n")
        r.append(f"**Kondisi cahaya:** {_lighting_desc(bl, cl, tl)}.\n")
        r.append(f"**Framing:** {_framing_desc(scenes_in_phase)}.\n")
        r.append(f"**Teks/dialog di segmen ini:** {sub_txt}\n")
        if strong_here:
            r.append(f"**⚡ Titik hook kuat** di detik {strong_here} — momen yang PALING menahan perhatian, "
                     f"jangan lewatkan saat rekam ulang (ekspresi/aksi harus tegas di sini).\n")
        r.append(f"**Yang harus kamu REKAM di babak ini:** "
                 f"{_shot_direction(is_hook, is_penutup, p, scenes_in_phase, bl)}\n")

    r.append("## Pesan inti yang harus tersampaikan ke penonton\n")
    r.append(_core_message(bp, ph, segs) + "\n")

    r.append("## Checklist rekam cepat\n")
    for i, p in enumerate(ph):
        cam_short = _camera_desc(p["camera"]).split(";")[0]
        r.append(f"- [ ] Babak {i+1} ({p['dur_sec']}s): {p['semantic']} — {cam_short}")
    r.append("")
    return "\n".join(r)

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
    # pencahayaan (analyzer >=d769792; IR lama tak punya field `lighting`)
    lit = [s.get("lighting") for s in scenes if s.get("lighting")]
    lighting_summary = {}
    if lit:
        avg = lambda k: round(sum(l.get(k, 0) for l in lit) / len(lit), 3)
        lighting_summary = {
            "avg_brightness": avg("brightness"), "avg_contrast": avg("contrast"),
            "avg_warmth": avg("warmth"), "avg_saturation": avg("saturation"),
            "brightness": top((l.get("brightness_label") for l in lit), 3),
            "contrast": top((l.get("contrast_label") for l in lit), 3),
            "temperature": top((l.get("temperature_label") for l in lit), 3),
        }

    # RENCANA PER-SEGMEN — wiring tiap scene ke aksi VN (zoom clipZoom + Adjust pencahayaan).
    # Dikonsumsi orchestrator vn_reproduce.py (segmen VN = scene IR, syarat: footage sama).
    def _adjust_from_lighting(lg):
        acts = []
        if not lg:
            return acts
        bl, cl, tl = lg.get("brightness_label"), lg.get("contrast_label"), lg.get("temperature_label")
        if bl == "dark":    acts.append({"param": "KECERAHAN", "dir": "naik"})
        elif bl == "bright": acts.append({"param": "KECERAHAN", "dir": "turun"})
        if cl == "low":     acts.append({"param": "KONTRAS", "dir": "naik"})
        elif cl == "high":  acts.append({"param": "KONTRAS", "dir": "turun"})
        if tl == "warm":    acts.append({"param": "SUHU", "dir": "hangat"})
        elif tl == "cool":  acts.append({"param": "SUHU", "dir": "dingin"})
        return acts
    segments = []
    for idx, s in enumerate(scenes):
        cm = s.get("camera_movement")
        zoom = None
        if cm in ("zoom_in", "zoom_out"):
            zoom = {"dir": cm, "vn": {"zoom_in": "Perbesar", "zoom_out": "Perkecil"}[cm]}
        elif cm == "zoom":
            zoom = {"dir": "zoom", "vn": "Perbesar/Perkecil?"}  # IR lama, arah tak diketahui
        segments.append({
            "i": idx, "start": round(s.get("start", 0), 2), "end": round(s.get("end", 0), 2),
            "dur": round(s.get("duration", 0), 2),
            "zoom": zoom, "adjust": _adjust_from_lighting(s.get("lighting")),
        })
    n_seg_zoom = sum(1 for x in segments if x["zoom"])
    n_seg_adj = sum(1 for x in segments if x["adjust"])

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
        "lighting": lighting_summary,
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
        "segments": segments,
    }

    # tulis SRT + blueprint json + cutlist (satu timestamp/baris, utk otomasi split VN)
    open(base + ".srt", "w").write(build_srt(segs))
    json.dump(bp, open(base + ".vn-blueprint.json", "w"), ensure_ascii=False, indent=2)
    open(base + ".cutlist.txt", "w").write("\n".join(f"{t:.2f}" for t in cut_points) + "\n")
    # rencana per-segmen utk orchestrator vn_reproduce.py
    json.dump({"segments": segments, "aspect_ratio": ratio_lab}, open(base + ".segments.json", "w"),
              ensure_ascii=False, indent=1)

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
    if lighting_summary:
        ls = lighting_summary
        bl = next(iter(ls["brightness"]), "normal"); cl = next(iter(ls["contrast"]), "normal"); tl = next(iter(ls["temperature"]), "neutral")
        adj = []
        if bl == "dark":   adj.append("naikkan **Kecerahan/Eksposur**")
        elif bl == "bright": adj.append("turunkan **Kecerahan/Eksposur**")
        if cl == "low":    adj.append("naikkan **Kontras**")
        elif cl == "high": adj.append("turunkan **Kontras**")
        if tl == "warm":   adj.append("geser **Suhu** ke hangat")
        elif tl == "cool": adj.append("geser **Suhu** ke dingin")
        adj_txt = ("; ".join(adj) or "biarkan (sudah netral/normal)")
        r.append(f"6. **Pencahayaan** (dominan: {bl}/{cl}/{tl}; rata brightness {ls['avg_brightness']}, "
                 f"contrast {ls['avg_contrast']}, warmth {ls['avg_warmth']}) → VN **Adjust** ("
                 f"`editor_toolbar_filter`→Sesuaikan): {adj_txt}. Terapkan per-klip untuk scene yang menyimpang.\n")
    else:
        r.append("6. **Pencahayaan**: IR ini belum punya data pencahayaan (analyzer lama) — re-analisa untuk dapat panduan Adjust.\n")
    r.append(f"7. **Hook** (3 detik pertama menentukan): buka dengan **{bp['hook']['opening_semantic']}** "
             f"({bp['hook']['opening_dur_sec']}s). {bp['hook']['strong_hook_count']} momen 'strong hook' di "
             f"detik: {bp['hook']['strong_hook_timestamps'][:10]} — jadikan titik tekanan/emphasis.\n")
    r.append(f"\n## Storyboard fase ({len(scenes)} scene → fase yang bisa diikuti)\n")
    r.append("| # | mulai | durasi | cut | rata cut | jenis konten | emosi(CLIP,noisy) | kamera |\n|---|---|---|---|---|---|---|---|")
    for i, p in enumerate(ph, 1):
        r.append(f"| {i} | {p['start']}s | {p['dur_sec']}s | {p['n_cuts']} | {p['avg_cut_sec']}s | "
                 f"{p['semantic']} | {p['emotion']} | {'/'.join(p['camera'].keys())} |")
    r.append(f"\n_{len(ph)} fase. Sinyal semantic/emotion dari CLIP zero-shot = ARAH, bukan kebenaran mutlak._\n")
    open(base + ".vn-recipe.md", "w").write("\n".join(r))

    # alur cerita naratif (OTOMATIS tiap analisa — lihat build_story_script)
    story = build_story_script(scenes, segs, ph, bp, base)
    open(base + ".story-script.md", "w").write(story)

    # ringkasan stdout
    print(f"IR: {os.path.basename(a.ir)}  |  durasi {bp['format']['duration_mmss']}  |  rasio {ratio_lab}")
    print(f"pacing: {bp['pacing']['n_scenes']} scene, {bp['pacing']['cuts']} cut/{bp['pacing']['fades']} fade, "
          f"median {bp['pacing']['median_cut_sec']}s ({bp['pacing']['style']})")
    print(f"beat: bpm {bp['beat']['bpm']}, {int(bp['beat']['on_beat_ratio']*100)}% on-beat")
    print(f"caption: {bp['captions']['n_segments']} segmen -> {base}.srt")
    print(f"hook: buka '{bp['hook']['opening_semantic']}', {bp['hook']['strong_hook_count']} strong-hook")
    print(f"fase storyboard: {len(ph)}")
    print(f"tulis: {base}.srt , {base}.vn-blueprint.json , {base}.vn-recipe.md , {base}.story-script.md")

if __name__ == "__main__":
    main()
