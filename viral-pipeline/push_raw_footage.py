#!/usr/bin/env python3
"""
push_raw_footage.py — kirim klip stok yg sudah diunduh (pexels_fetch.py /
pixabay_fetch.py) ke RN7 (adb push, via container tool-appium) sbg RAW
FOOTAGE, siap diedit manual bebas (Jalur C, lihat memori
project_viral_analyzer.md "2026-08-29").

(2026-10-31, revisi permintaan user) Target PINDAH dari Gdrive
gfootage:RAW-VIDEO/ (dipensiunkan, folder itu dihapus) ke RN7 lokal,
digabung ke folder yg sama dgn hasil download Seal (`/sdcard/Movies/Seal/`)
supaya VN-editor di RN7 punya SATU kolam footage mentah, bukan tercerai
antara Gdrive & device. adb dijalankan lewat container `tool-appium`
(pola sama vn_export_gdrive.sh/rn7-health-report.sh — adb host langsung
TERBUKTI tak jalan dari sini, lihat audit 31/10).

Baca satu/lebih `<base>.pexels-plan.json` / `<base>.pixabay-plan.json`
(TERBUKA utk keduanya sekaligus dlm satu job) -> tiap fase berstatus
downloaded/cached (punya local_path nyata di disk) -> `adb push` ke
`/sdcard/Movies/Seal/<job-id>_<fname>` (prefix job-id krn folder Seal FLAT,
bukan per-job spt RAW-VIDEO dulu -- cegah filename kolisi lintas job) ->
tulis balik field `rn7_path` ke plan JSON yg sama (dulu `gdrive_path`,
berganti nama krn target bukan lagi Gdrive -- enrichment, pola sama
footage_audit.py).

job-id = basename plan file dikupas suffix `.pexels-plan.json`/
`.pixabay-plan.json` (mis. `job-24.pexels-plan.json` -> job-id `job-24`,
cocok konvensi `reproductions/job-<id>/job-<id>.*` di orchestrator.py).

File LOKAL (~/pexels-cache, ~/pixabay-cache) SENGAJA TAK dihapus pasca-push
-- itu cache dedup lintas-job (pexels_fetch/pixabay_fetch cek exists() dulu
sblm unduh ulang klip id yg sama).

stdlib + adb (subprocess, via `docker exec`) -- RN7 offline (Doze/tak
dicas) = gagal SENYAP per-klip (exit 0 total kalau semua gagal krn device
tak ada, BUKAN exit 3 -- beda dari dulu krn RN7 drop koneksi jauh lebih
sering drpd Gdrive, jangan sampai run-drain.sh dianggap error tiap device
kebetulan tidur).

Pemakaian:
  python3 push_raw_footage.py <plan.json> [<plan2.json> ...]
  [--target /sdcard/Movies/Seal/] [--rn7-ip 10.66.66.6] [--container tool-appium-appium-1] [--dry-run]

Exit: 0 sukses/device-offline (best-effort) · 2 argumen.
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


def adb(container, args, timeout=60):
    """TAK PERNAH raise (pola sh_safe() di orchestrator.py) -- RN7 sering
    Doze/tak dicas, docker exec ke adb bisa hang lama MELEBIHI timeout
    (bukan cuma gagal cepat), jadi TimeoutExpired/OSError WAJIB ditangkap
    di sini, bukan di pemanggil -- celah nyata ditemukan 31/10: job-7/8
    crash traceback mentah persis krn ini belum ditangkap."""
    try:
        r = subprocess.run(["docker", "exec", container, "adb"] + args,
                            capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return 1, f"timeout {timeout}s"
    except Exception as e:
        return 1, repr(e)[:200]


def resolve_udid(container, rn7_ip):
    """Pola sama vn_export_gdrive.sh: connect dulu (idempoten kalau sudah),
    baru cari UDID persis via `adb devices` (port adb-over-WG bisa beda-beda,
    jangan asumsikan :5555 tetap -- walau skrg per rn7-health-report.sh
    biasanya permanen di situ)."""
    adb(container, ["connect", f"{rn7_ip}:5555"], timeout=15)
    rc, out = adb(container, ["devices"], timeout=15)
    if rc != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0].startswith(rn7_ip) and len(parts) > 1 and parts[1] == "device":
            return parts[0]
    return None


def adb_push(container, udid, local, remote, dry_run, timeout=300):
    if dry_run:
        return 0, f"(dry-run) {local} -> {remote}"
    try:
        r = subprocess.run(["docker", "exec", container, "adb", "-s", udid, "push", local, remote],
                            capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stderr or r.stdout).strip()
    except subprocess.TimeoutExpired:
        return 1, f"timeout {timeout}s"
    except Exception as e:
        return 1, repr(e)[:200]


def main():
    ap = argparse.ArgumentParser(description="Push klip stok terunduh -> RN7 (gabung folder Seal).")
    ap.add_argument("plans", nargs="+", help="satu/lebih <base>.pexels-plan.json / .pixabay-plan.json")
    ap.add_argument("--target", default="/sdcard/Movies/Seal/",
                    help="folder di RN7 (default /sdcard/Movies/Seal/, gabung dgn hasil Seal)")
    ap.add_argument("--rn7-ip", default="10.66.66.6")
    ap.add_argument("--container", default="tool-appium-appium-1")
    ap.add_argument("--dry-run", action="store_true", help="tak push sungguhan, plan JSON tak ditulis")
    a = ap.parse_args()

    udid = None if a.dry_run else resolve_udid(a.container, a.rn7_ip)
    if not a.dry_run and not udid:
        log(f"RN7 ({a.rn7_ip}) tak terjangkau adb -- device kemungkinan Doze/tak dicas. "
            "Dilewati semua (best-effort, bukan error).")
        return 0

    total_ok = total_skip = total_err = 0

    for plan_path in a.plans:
        if not os.path.isfile(plan_path):
            log(f"GAGAL: plan tak ada: {plan_path}")
            return 2

        jid = job_id_of(plan_path)
        plan = json.load(open(plan_path))
        phases = plan.get("phases", [])
        log(f"{os.path.basename(plan_path)}: job-id={jid} -> {a.target} ({len(phases)} fase)")

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
            if p.get("rn7_path") and not a.dry_run:
                log(f"  fase{p.get('i')}: sudah ter-push sebelumnya ({p['rn7_path']}), skip.")
                total_skip += 1
                continue

            fname = f"{jid}_{os.path.basename(local_path)}"
            dest = a.target.rstrip("/") + "/" + fname
            rc, msg = adb_push(a.container, udid, local_path, dest, a.dry_run)
            if rc != 0:
                total_err += 1
                log(f"  fase{p.get('i')}: ERROR adb push (rc={rc}): {msg[-300:]}")
                continue
            total_ok += 1
            sz = os.path.getsize(local_path)
            log(f"  fase{p.get('i')}: {fname} ({sz//1024}KB) -> {dest}")
            if not a.dry_run:
                p["rn7_path"] = dest
                changed = True

        if changed:
            json.dump(plan, open(plan_path, "w"), ensure_ascii=False, indent=2)
            log(f"  plan diperbarui (rn7_path ditulis): {plan_path}")

    log(f"SELESAI: {total_ok} klip ter-push · {total_skip} dilewati · {total_err} error"
        + (" · DRY-RUN (plan JSON tak diubah)" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
