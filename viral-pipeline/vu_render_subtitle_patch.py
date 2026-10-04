#!/usr/bin/env python3
# Patch idempoten: render.py honor EDL "subtitle_style" (override SUB_FORCE_STYLE).
import sys
p = sys.argv[1]
src = open(p).read()
if "edl.get(\"subtitle_style\")" in src:
    print("sudah dipatch"); sys.exit(0)
anchor = "edl = json.loads(edl_path.read_text())"
if anchor not in src:
    print("ANCHOR TAK DITEMUKAN"); sys.exit(2)
ins = (anchor + "\n"
       "    global SUB_FORCE_STYLE\n"
       "    if isinstance(edl.get(\"subtitle_style\"), str) and edl[\"subtitle_style\"].strip():\n"
       "        SUB_FORCE_STYLE = edl[\"subtitle_style\"].strip()")
src = src.replace(anchor, ins, 1)
open(p, "w").write(src)
print("patched OK")
