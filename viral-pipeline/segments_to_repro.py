#!/usr/bin/env python3
"""segments_to_repro.py — konversi ir_to_vn `.segments.json` -> plan repro-drive.sh.

Celah yg ditutup: repro-drive.sh (tool-appium) mengonsumsi plan
  [{"t":detik_midpoint, "zoom":"in"|"out"|null, "adj":{"type":..,"dir":..}|null}, ...]
sedangkan ir_to_vn menghasilkan `.segments.json`
  {"segments":[{i,start,end,dur,zoom:{dir:"zoom_in"..,vn},adjust:[{param:"KECERAHAN"..,dir:"naik"..}]}], "aspect_ratio"}
Skrip ini menerjemahkan yg pertama dari yg kedua.

Batasan repro-segments.js (profil RN7 §25): adj type = BRIGHTNESS/CONTRAST/EXPOSURE/
SATURATION saja. **SUHU/temperature (ir_to_vn) TAK didukung -> di-drop + dicatat.**
Segmen tanpa op (zoom & adjust kosong) dilewati. Adjust ganda -> elemen t-sama tambahan.
"""
import argparse, json, sys

PARAM_MAP = {"KECERAHAN": "BRIGHTNESS", "KONTRAS": "CONTRAST",
             "PAPARAN": "EXPOSURE", "EKSPOSUR": "EXPOSURE", "KEJENUHAN": "SATURATION"}
DIR_MAP = {"naik": "up", "turun": "down"}
ZOOM_MAP = {"zoom_in": "in", "zoom_out": "out"}


def convert(seg):
    t = round(((seg.get("start", 0) or 0) + (seg.get("end", 0) or 0)) / 2, 2)
    zoom = ZOOM_MAP.get((seg.get("zoom") or {}).get("dir"))
    ops, dropped = [], []
    for a in (seg.get("adjust") or []):
        typ, d = PARAM_MAP.get(a.get("param")), DIR_MAP.get(a.get("dir"))
        (ops if (typ and d) else dropped).append({"type": typ, "dir": d} if typ and d else a)
    return t, zoom, ops, dropped


def main():
    ap = argparse.ArgumentParser(description="segments.json -> plan repro-drive.sh")
    ap.add_argument("segments_json")
    ap.add_argument("--out", help="default: <base>.repro-plan.json")
    a = ap.parse_args()
    d = json.load(open(a.segments_json))
    segs = d.get("segments", d if isinstance(d, list) else [])
    plan, n_drop, n_skip = [], 0, 0
    for s in segs:
        t, zoom, ops, dropped = convert(s)
        n_drop += len(dropped)
        if not zoom and not ops:
            n_skip += 1
            continue
        plan.append({"t": t, "zoom": zoom, "adj": ops[0] if ops else None})
        for extra in ops[1:]:
            plan.append({"t": t, "zoom": None, "adj": extra})
    out = a.out or (a.segments_json.replace(".segments.json", "") + ".repro-plan.json")
    json.dump(plan, open(out, "w"), ensure_ascii=False, indent=2)
    print(f"{len(plan)} elemen repro dari {len(segs)} segmen "
          f"({n_skip} tanpa-op dilewati, {n_drop} adjust di-drop=SUHU/tak-didukung) -> {out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
