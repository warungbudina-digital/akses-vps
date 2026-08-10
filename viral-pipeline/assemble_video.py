#!/usr/bin/env python3
"""
assemble_video.py — perakit Jalur A (headless): rencana Pexels + SRT -> MP4 9:16.

Baca <base>.pexels-plan.json (dari pexels_fetch.py) + SRT (caption ir_to_vn.py),
rakit video final via ffmpeg TANPA syuting:
  - MODE FASE (default): tiap fase -> 1 klip stok, ditampilkan selama durasi fase.
  - MODE BEAT-CUT (--beat-cut): footage dipotong mengikuti GRID BEAT (60/bpm *
    beats-per-cut). Tiap potongan lompat ke bagian klip berbeda (non-kontinu) ->
    jump-cut ON-BEAT yang energik. Footage tetap ikut fase (koherensi naratif);
    ganti fase = ganti klip.
Semua klip di-scale+crop 1080x1920 lalu concat, caption SRT di-burn (libass).

SLOT MUSIK (--music FILE): audio latar di-loop + dipotong ke panjang video +
volume (--music-vol) + fade in/out (--audio-fade). Tanpa --music = audio diam.
SFX (--transition-sfx FILE): one-shot (whoosh dll) di-mix di tiap batas fase
(atau tiap potongan beat-cut via --sfx-every-cut). SUMBER SFX/musik = Pixabay
tapi Pixabay TAK punya API audio -> unduh file manual dari situsnya ke folder,
lalu tunjuk lewat flag ini (gratis, tanpa atribusi per lisensi Pixabay).

⚠️ BEAT-CUT pakai **bpm SUMBER** (dari plan/analisa) sbg grid, BUKAN deteksi beat
file musik (ffmpeg tak bisa). Kalau musik beda tempo, set --bpm agar cut selaras
musik (atau biarkan cut ikut ritme sumber & musik jadi latar saja).

Path-PORTABLE: klip diresolusi `--clips-dir/<basename>` -> jalan di node/kontainer
mana pun ber-ffmpeg+libass (mis. di dalam container analyzer .50).

Pemakaian:
  python3 assemble_video.py /work/base.pexels-plan.json --srt /work/base.srt \
    --clips-dir /work --out /work/final.mp4 [--beat-cut --beats-per-cut 2] \
    [--music /work/bg.mp3 --music-vol 0.8 --audio-fade 0.8] [--bpm 120]

Exit: 0 sukses · 2 argumen · 3 tak ada klip layak · 4 ffmpeg gagal · 5 terlalu banyak potongan.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

W_DEF, H_DEF, FPS_DEF = 1080, 1920, 30
USABLE = ("downloaded", "cached", "planned")
MAX_SEGMENTS = 220  # rem: hindari ledakan input ffmpeg (beat-cut utk reel pendek)


def log(*a):
    print("[assemble]", *a, file=sys.stderr)


def build_segments(phases, beat_cut, bpm, beats_per_cut):
    """phases: list dict {clip, dur, clip_dur}. Balikkan list segmen
    {clip, src_in, dur}. Mode fase = 1 segmen/fase; beat-cut = grid beat."""
    segs = []
    if not beat_cut:
        for p in phases:
            segs.append({"clip": p["clip"], "src_in": 0.0, "dur": p["dur"]})
        return segs

    seg_len = (60.0 / bpm) * beats_per_cut  # detik per potongan
    for p in phases:
        clip_dur = p.get("clip_dur") or 0.0
        remaining = p["dur"]
        j = 0
        while remaining > 0.05:
            this_len = min(seg_len, remaining)
            # in-point non-kontinu -> tiap beat tampilkan bagian klip berbeda
            max_in = max(0.0, clip_dur - this_len)
            if max_in > 0.1:
                stride = max(this_len * 1.7, clip_dur / 6.0)
                src_in = round((j * stride) % max_in, 3)
            else:
                src_in = 0.0  # klip terlalu pendek utk melompat
            segs.append({"clip": p["clip"], "src_in": src_in, "dur": round(this_len, 3)})
            remaining -= this_len
            j += 1
    return segs


def main():
    ap = argparse.ArgumentParser(description="Rakit rencana Pexels + SRT -> MP4 9:16 (ffmpeg).")
    ap.add_argument("plan", help="path <base>.pexels-plan.json")
    ap.add_argument("--srt", help="path SRT caption (default: srt_file dari plan)")
    ap.add_argument("--clips-dir", required=True, help="direktori klip (resolve by basename)")
    ap.add_argument("--out", required=True, help="path MP4 output")
    # beat-cut
    ap.add_argument("--beat-cut", action="store_true", help="potong footage mengikuti grid beat")
    ap.add_argument("--bpm", type=float, help="override bpm grid (default: bpm dari plan)")
    ap.add_argument("--beats-per-cut", type=float, default=2.0,
                    help="panjang tiap potongan dalam beat (default 2 = ~1s @120bpm)")
    ap.add_argument("--detect-music-bpm", action="store_true",
                    help="deteksi bpm dari --music via librosa (butuh librosa, mis. container analyzer) "
                         "-> grid beat selaras BEAT MUSIK, bukan bpm sumber")
    # musik
    ap.add_argument("--music", help="audio latar (loop + potong ke panjang video)")
    ap.add_argument("--music-vol", type=float, default=1.0, help="volume musik (default 1.0)")
    ap.add_argument("--audio-fade", type=float, default=0.8, help="fade in/out audio detik (default 0.8)")
    # SFX (sumber = Pixabay, unduh manual — Pixabay TAK punya API audio)
    ap.add_argument("--transition-sfx", help="file SFX (whoosh dll, dari Pixabay) di tiap potongan")
    ap.add_argument("--sfx-vol", type=float, default=0.8, help="volume SFX (default 0.8)")
    ap.add_argument("--sfx-every-cut", action="store_true",
                    help="taruh SFX di TIAP potongan beat-cut (default: hanya batas fase)")
    # video
    ap.add_argument("--width", type=int, default=W_DEF)
    ap.add_argument("--height", type=int, default=H_DEF)
    ap.add_argument("--fps", type=int, default=FPS_DEF)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--no-subs", action="store_true", help="lewati burn-in caption")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--print-cmd", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.plan):
        log(f"GAGAL: plan tak ada: {a.plan}")
        return 2
    plan = json.load(open(a.plan))
    W, H, FPS = a.width, a.height, a.fps

    # fase layak = punya klip; resolve path portable via basename
    phases = []
    for ph in plan.get("phases", []):
        if ph.get("status") not in USABLE or not ph.get("local_path"):
            log(f"  lewati fase{ph.get('i')} (status={ph.get('status')})")
            continue
        clip = os.path.join(a.clips_dir, os.path.basename(ph["local_path"]))
        if not os.path.isfile(clip):
            log(f"  lewati fase{ph.get('i')}: klip tak ada: {clip}")
            continue
        dur = float(ph.get("dur_sec") or 0)
        if dur <= 0:
            continue
        phases.append({"clip": clip, "dur": dur, "clip_dur": float(ph.get("clip_dur") or 0)})

    if not phases:
        log("GAGAL: tak ada fase dgn klip layak.")
        return 3

    bpm = a.bpm or plan.get("bpm") or 120.0
    # auto-deteksi bpm dari file musik (librosa) -> grid selaras beat musik nyata
    if a.detect_music_bpm and a.music and os.path.isfile(a.music):
        try:
            import librosa  # hanya saat diminta -> skrip tetap portable tanpa flag ini
            y, sr = librosa.load(a.music, mono=True)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            det = float(tempo if getattr(tempo, "ndim", 0) == 0 else tempo[0])
            if 40.0 <= det <= 300.0:
                log(f"  bpm musik terdeteksi (librosa): {det:.1f} (override grid; sumber={bpm})")
                bpm = det
            else:
                log(f"  bpm terdeteksi {det:.1f} di luar 40-300 -> abaikan, pakai {bpm}")
        except Exception as e:
            log(f"  deteksi bpm gagal ({e}) -> pakai bpm={bpm}")
    elif a.detect_music_bpm:
        log("  --detect-music-bpm diabaikan (tak ada --music)")

    segs = build_segments(phases, a.beat_cut, bpm, a.beats_per_cut)
    total = round(sum(s["dur"] for s in segs), 3)
    if len(segs) > MAX_SEGMENTS:
        log(f"GAGAL: {len(segs)} potongan > {MAX_SEGMENTS} (beat-cut utk reel pendek). "
            f"Naikkan --beats-per-cut atau pakai mode fase.")
        return 5
    mode = f"beat-cut bpm={bpm:.1f} x{a.beats_per_cut}beat" if a.beat_cut else "fase"
    log(f"mode={mode} · {len(phases)} fase -> {len(segs)} potongan · total {total}s · "
        f"{W}x{H}@{FPS} · out={a.out}")

    # ── filter_complex: 1 input per potongan (sederhana; aman utk reel pendek) ──
    inputs = []
    filt = []
    vlabels = []
    for idx, s in enumerate(segs):
        inputs += ["-i", s["clip"]]
        filt.append(
            f"[{idx}:v]trim=start={s['src_in']:.3f}:duration={s['dur']:.3f},"
            f"setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[v{idx}]"
        )
        vlabels.append(f"[v{idx}]")
    filt.append("".join(vlabels) + f"concat=n={len(segs)}:v=1:a=0[vcat]")

    # caption
    vout = "vcat"
    srt = a.srt or plan.get("srt_file")
    if srt and not a.no_subs:
        if not os.path.isfile(srt):
            srt = os.path.join(a.clips_dir, os.path.basename(srt))
        if os.path.isfile(srt):
            subs_path = os.path.join(a.clips_dir, "_subs.srt")
            if os.path.abspath(srt) != os.path.abspath(subs_path):
                shutil.copyfile(srt, subs_path)
            style = "Fontsize=16,Outline=2,Shadow=1,Alignment=2,MarginV=90,BorderStyle=1"
            filt.append(f"[vcat]subtitles={subs_path}:force_style='{style}'[vout]")
            vout = "vout"
        else:
            log(f"  caption dilewati: SRT tak ada ({srt})")
    else:
        log("  caption dilewati (--no-subs / plan tanpa srt)")

    # ── audio: base (musik loop+vol+fade / diam) + SFX Pixabay (mix) ───────
    # Pixabay TAK punya API audio -> file SFX/musik diunduh manual dari situs.
    AFMT = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    fade = max(0.0, min(a.audio_fade, total / 2.0))
    base_idx = len(segs)
    if a.music and os.path.isfile(a.music):
        inputs += ["-stream_loop", "-1", "-i", a.music]
        af = f"[{base_idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={a.music_vol}"
        if fade > 0.01:
            af += (f",afade=t=in:st=0:d={fade:.3f},"
                   f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade:.3f}")
        af += f",{AFMT}[abase]"
        filt.append(af)
        log(f"  musik: {os.path.basename(a.music)} (loop, vol={a.music_vol}, fade={fade:.2f}s)")
    else:
        if a.music:
            log(f"  musik tak ada ({a.music}) -> latar diam")
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filt.append(f"[{base_idx}:a]{AFMT}[abase]")
        log("  musik: diam (anullsrc)")

    amap = "[abase]"
    if a.transition_sfx and os.path.isfile(a.transition_sfx):
        src = segs if a.sfx_every_cut else phases
        acc, sfx_times = 0.0, []
        for x in src[:-1]:
            acc += x["dur"]
            sfx_times.append(round(acc, 3))
        sfx_times = [t for t in sfx_times if 0.05 < t < total - 0.05][:60]
        labels = ["[abase]"]
        for j, t in enumerate(sfx_times):
            inputs += ["-i", a.transition_sfx]
            ms = int(t * 1000)
            filt.append(f"[{base_idx + 1 + j}:a]adelay={ms}|{ms},volume={a.sfx_vol},{AFMT}[sfx{j}]")
            labels.append(f"[sfx{j}]")
        if sfx_times:
            filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:"
                        f"dropout_transition=0[aout]")
            amap = "[aout]"
            log(f"  SFX: {os.path.basename(a.transition_sfx)} x{len(sfx_times)} "
                f"({'tiap potongan' if a.sfx_every_cut else 'batas fase'}, vol={a.sfx_vol})")
    elif a.transition_sfx:
        log(f"  SFX tak ada ({a.transition_sfx}) -> dilewati")

    cmd = [a.ffmpeg, "-y", *inputs,
           "-filter_complex", ";".join(filt),
           "-map", f"[{vout}]", "-map", amap,
           "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
           "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "128k", "-shortest",
           "-movflags", "+faststart", a.out]

    if a.print_cmd:
        log("CMD:", " ".join(cmd))
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        log("!!! ffmpeg GAGAL:")
        sys.stderr.write("\n".join(r.stderr.strip().splitlines()[-15:]) + "\n")
        return 4
    sz = os.path.getsize(a.out) if os.path.isfile(a.out) else 0
    log(f"SELESAI: {a.out} ({sz//1024}KB, ~{total}s, {len(segs)} potongan)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
