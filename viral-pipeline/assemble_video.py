#!/usr/bin/env python3
"""
assemble_video.py — perakit Jalur A (headless): rencana Pexels + SRT -> MP4 9:16.

Baca <base>.pexels-plan.json (dari pexels_fetch.py) + SRT (caption dari
ir_to_vn.py), lalu rakit video final via ffmpeg TANPA syuting:
  tiap fase -> ambil klip stok, potong ke durasi fase, scale+crop ke 1080x1920,
  concat berurutan (= durasi & ritme sumber), burn-in caption SRT.
Audio: --music (di-loop+dipotong ke panjang video) atau diam (Pexels tak sedia
audio -> gap musik disengaja, isi dari sumber royalti-bebas terpisah).

Path-PORTABLE: klip diresolusi `--clips-dir/<basename(local_path)>` supaya bisa
jalan di node/kontainer mana pun (mis. di dalam container analyzer .50 yg punya
ffmpeg 7.x + libass). Butuh ffmpeg ber-libass (filter `subtitles`).

Pemakaian (contoh, di dalam container ber-ffmpeg dgn /work ter-mount):
  python3 assemble_video.py /work/base.pexels-plan.json \
    --srt /work/base.srt --clips-dir /work --out /work/final.mp4 [--music /work/bg.mp3]

Exit: 0 sukses · 2 argumen · 3 tak ada klip layak · 4 ffmpeg gagal.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

W_DEF, H_DEF, FPS_DEF = 1080, 1920, 30
USABLE = ("downloaded", "cached", "planned")


def log(*a):
    print("[assemble]", *a, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Rakit rencana Pexels + SRT -> MP4 9:16 (ffmpeg).")
    ap.add_argument("plan", help="path <base>.pexels-plan.json")
    ap.add_argument("--srt", help="path SRT caption (default: srt_file dari plan)")
    ap.add_argument("--clips-dir", required=True, help="direktori berisi klip (resolve by basename)")
    ap.add_argument("--out", required=True, help="path MP4 output")
    ap.add_argument("--music", help="audio latar (di-loop + dipotong ke panjang video)")
    ap.add_argument("--width", type=int, default=W_DEF)
    ap.add_argument("--height", type=int, default=H_DEF)
    ap.add_argument("--fps", type=int, default=FPS_DEF)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--no-subs", action="store_true", help="lewati burn-in caption")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="binary ffmpeg (default: ffmpeg di PATH)")
    ap.add_argument("--print-cmd", action="store_true", help="cetak perintah ffmpeg lalu jalankan")
    a = ap.parse_args()

    if not os.path.isfile(a.plan):
        log(f"GAGAL: plan tak ada: {a.plan}")
        return 2
    plan = json.load(open(a.plan))
    W, H, FPS = a.width, a.height, a.fps

    # fase layak = punya klip; resolve path portable via basename
    usable = []
    for ph in plan.get("phases", []):
        if ph.get("status") not in USABLE or not ph.get("local_path"):
            log(f"  lewati fase{ph.get('i')} (status={ph.get('status')})")
            continue
        clip = os.path.join(a.clips_dir, os.path.basename(ph["local_path"]))
        if not os.path.isfile(clip):
            log(f"  lewati fase{ph.get('i')}: klip tak ada di clips-dir: {clip}")
            continue
        dur = float(ph.get("dur_sec") or 0)
        if dur <= 0:
            log(f"  lewati fase{ph.get('i')}: durasi 0")
            continue
        usable.append((clip, dur))

    if not usable:
        log("GAGAL: tak ada fase dgn klip layak.")
        return 3
    total = round(sum(d for _, d in usable), 3)
    log(f"{len(usable)} fase · total {total}s · {W}x{H}@{FPS} · out={a.out}")

    # ── susun filter_complex ──────────────────────────────────────────────
    inputs = []
    filt = []
    vlabels = []
    for idx, (clip, dur) in enumerate(usable):
        inputs += ["-i", clip]
        filt.append(
            f"[{idx}:v]trim=0:{dur:.3f},setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[v{idx}]"
        )
        vlabels.append(f"[v{idx}]")
    filt.append("".join(vlabels) + f"concat=n={len(usable)}:v=1:a=0[vcat]")

    # caption: salin SRT ke nama sederhana di clips-dir (hindari escaping path)
    vout = "vcat"
    srt = a.srt or plan.get("srt_file")
    if srt and not a.no_subs:
        srt = os.path.join(a.clips_dir, os.path.basename(srt)) if not os.path.isfile(srt) else srt
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

    # ── audio: music (loop+potong) atau diam ──────────────────────────────
    if a.music and os.path.isfile(a.music):
        inputs += ["-stream_loop", "-1", "-i", a.music]
        amap = f"{len(usable)}:a"
        log(f"  audio: musik {os.path.basename(a.music)} (loop)")
    else:
        if a.music:
            log(f"  musik tak ada ({a.music}) -> audio diam")
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = f"{len(usable)}:a"
        log("  audio: diam (anullsrc)")

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
    log(f"SELESAI: {a.out} ({sz//1024}KB, ~{total}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
