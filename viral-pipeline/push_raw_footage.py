#!/usr/bin/env python3
"""
push_raw_footage.py — kirim klip stok yg sudah diunduh (pexels_fetch.py /
pixabay_fetch.py) ke Gdrive sbg RAW FOOTAGE, siap diedit manual bebas (Jalur C,
lihat memori project_viral_analyzer.md "2026-08-29").

Baca satu/lebih `<base>.pexels-plan.json` / `<base>.pixabay-plan.json`
(TERBUKA utk keduanya sekaligus dlm satu job) -> tiap fase berstatus
downloaded/cached (punya local_path nyata di disk) -> `rclone copyto` ke
`gfootage:RAW-VIDEO/<job-id>/` -> tulis balik field `gdrive_path` ke plan
JSON yg sama (enrichment, pola sama footage_audit.py).

job-id = basename plan file dikupas suffix `.pexels-plan.json`/
`.pixabay-plan.json` (mis. `job-24.pexels-plan.json` -> job-id `job-24`,
cocok konvensi `reproductions/job-<id>/job-<id>.*` di orchestrator.py).

File LOKAL (~/pexels-cache, ~/pixabay-cache) SENGAJA TAK dihapus pasca-upload
-- itu cache dedup lintas-job (pexels_fetch/pixabay_fetch cek exists() dulu
sblm unduh ulang klip id yg sama).

stdlib + rclone (subprocess) — remote `gfootage:` (rclone.conf sudah ada,
lihat memori project_viral_analyzer.md).

Pemakaian:
  python3 push_raw_footage.py <plan.json> [<plan2.json> ...]
  [--remote gfootage:RAW-VIDEO/] [--dry-run]

Exit: 0 sukses (termasuk 0 klip valid) · 2 argumen · 3 error rclone.
"""
import argparse
import json
import os
import re
import subprocess
import sys

BASE_SUFFIXES = (".pexels-plan.json", ".pixabay-plan.json")


def log(*a):
    print("[push_raw_footage]", *a, file=sys.stderr)


def job_id_of(plan_path):
    name = os.path.basename(plan_path)
    for suf in BASE_SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)]
    # fallback: nama file tanpa ekstensi terakhir
    return re.sub(r"\.json$", "", name)


def rclone_copyto(src, dest, dry_run):
    cmd = ["rclone", "copyto", src, dest]
    if dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stderr or r.stdout).strip()


def main():
    ap = argparse.ArgumentParser(description="Push klip stok terunduh -> Gdrive RAW-VIDEO.")
    ap.add_argument("plans", nargs="+", help="satu/lebih <base>.pexels-plan.json / .pixabay-plan.json")
    ap.add_argument("--remote", default="gfootage:RAW-VIDEO/",
                    help="folder remote rclone (default gfootage:RAW-VIDEO/)")
    ap.add_argument("--dry-run", action="store_true", help="rclone --dry-run, plan JSON tak ditulis")
    a = ap.parse_args()

    total_ok = total_skip = total_err = 0

    for plan_path in a.plans:
        if not os.path.isfile(plan_path):
            log(f"GAGAL: plan tak ada: {plan_path}")
            return 2

        jid = job_id_of(plan_path)
        remote_dir = a.remote.rstrip("/") + "/" + jid + "/"
        plan = json.load(open(plan_path))
        phases = plan.get("phases", [])
        log(f"{os.path.basename(plan_path)}: job-id={jid} -> {remote_dir} ({len(phases)} fase)")

        changed = False
        for p in phases:
            status = p.get("status")
            local_path = p.get("local_path")
            if status not in ("downloaded", "cached") or not local_path:
                total_skip += 1
                continue
            if not os.path.isfile(local_path):
                log(f"  fase{p.get('i')}: SKIP, local_path hilang dr disk: {local_path}")
                total_skip += 1
                continue
            if p.get("gdrive_path") and not a.dry_run:
                log(f"  fase{p.get('i')}: sudah ter-upload sebelumnya ({p['gdrive_path']}), skip.")
                total_skip += 1
                continue

            fname = os.path.basename(local_path)
            dest = remote_dir + fname
            rc, msg = rclone_copyto(local_path, dest, a.dry_run)
            if rc != 0:
                total_err += 1
                log(f"  fase{p.get('i')}: ERROR rclone (rc={rc}): {msg[-300:]}")
                continue
            total_ok += 1
            sz = os.path.getsize(local_path)
            log(f"  fase{p.get('i')}: {fname} ({sz//1024}KB) -> {dest}")
            if not a.dry_run:
                p["gdrive_path"] = dest
                changed = True

        if changed:
            json.dump(plan, open(plan_path, "w"), ensure_ascii=False, indent=2)
            log(f"  plan diperbarui (gdrive_path ditulis): {plan_path}")

    log(f"SELESAI: {total_ok} klip ter-upload · {total_skip} dilewati · {total_err} error"
        + (" · DRY-RUN (rclone --dry-run, plan JSON tak diubah)" if a.dry_run else ""))
    return 3 if total_err and not total_ok else 0


if __name__ == "__main__":
    sys.exit(main())
