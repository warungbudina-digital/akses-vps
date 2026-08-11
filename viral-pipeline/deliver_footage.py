#!/usr/bin/env python3
"""deliver_footage.py — kirim klip dari footage-plan.json ke RN7 utk diimpor VN.

Baca <base>.footage-plan.json (dari footage_audit.py) -> tiap fase ber-klip (URUT) ->
stage bytes ke host ~/.android/ (bind-mount container tool-appium) -> `adb push` ke RN7
/sdcard/DCIM/VN-src/NN_<name>.mp4 (NN=urutan fase) -> MediaScanner rescan -> verifikasi
di disk + MediaStore. Klip muncul TERURUT di picker VN (grid Media & File App).

Sumber klip per fase (dari plan): lokal akses-vps (clip.source) atau gdrive (rclone cat).
Hasil = urutan klip siap impor -> lalu edit via repro-drive.sh (lihat segments_to_repro.py).

adb via container tool-appium ke RN7 (WireGuard 10.66.66.6). JANGAN `adb root`.
"""
import argparse, json, os, re, shutil, subprocess, sys

HOST_ANDROID = os.path.expanduser("~/.android")          # bind -> /home/appium/.android
CTN_ANDROID = "/home/appium/.android"
STAGE_SUB = "vnsrc"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sanitize(name):
    n = re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(name))
    return n if n.lower().endswith((".mp4", ".mov", ".mkv", ".m4v")) else n + ".mp4"


class RN7:
    def __init__(self, container, udid, dest):
        self.c, self.u, self.dest = container, udid, dest

    def adb(self, *args, **kw):
        return run(["docker", "exec", self.c, "adb", "-s", self.u, *args], **kw)

    def shell(self, cmd, **kw):
        return self.adb("shell", cmd, **kw)

    def preflight(self, clean=False):
        r = self.adb("get-state")
        if "device" not in r.stdout:
            return False, f"adb tak connect ke {self.u} ({r.stdout.strip()}{r.stderr.strip()})"
        self.shell(f"mkdir -p {self.dest}")
        if clean:
            # kosongkan folder + rescan -> album VN-src berisi TEPAT N klip saat ini
            # (import-clips.js pilih semua di album; hindari klip basi delivery lama)
            self.shell(f"rm -f {self.dest}/*.mp4")
            self.shell(f"content call --uri content://media/external/file "
                       f"--method scan_file --arg {self.dest}")
        return True, ("adb siap" + (" (folder dibersihkan)" if clean else ""))

    def push(self, host_path, remote_name):
        """host_path = file di ~/.android/vnsrc/ ; push dari path container.
        CATATAN: `adb push` menulis progres ke STDERR -> cek gabungan stdout+stderr."""
        ctn_path = host_path.replace(HOST_ANDROID, CTN_ANDROID, 1)
        remote = f"{self.dest}/{remote_name}"
        r = self.adb("push", ctn_path, remote)
        comb = (r.stdout + r.stderr)
        ok = r.returncode == 0 and ("pushed" in comb.lower() or "1 file" in comb.lower())
        tail = comb.strip().splitlines()[-1] if comb.strip() else ""
        return ok, remote, tail

    def scan(self, remote):
        # rescan MediaStore. Android 14 batasi broadcast MEDIA_SCANNER_SCAN_FILE -> pakai
        # rescan volume via MediaProvider (root). Fallback: file kebaca via File App/SAF.
        self.shell(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
                   f"-d file://{remote}")
        self.shell("content call --uri content://media/external/file "
                   f"--method scan_file --arg {remote}")

    def verify(self):
        ls = self.shell(f"ls -la {self.dest} 2>/dev/null").stdout
        mq = self.shell(
            "content query --uri content://media/external/video/media "
            "--projection _display_name:_data --where \"_data LIKE '%VN-src%'\"").stdout
        return ls, mq


def stage_local(source, staging):
    shutil.copy(source, staging)
    return os.path.getsize(staging)


def stage_gdrive(source, staging):
    with open(staging, "wb") as fh:
        p = subprocess.run(["rclone", "cat", source, "--timeout", "30s", "--retries", "3"],
                           stdout=fh, stderr=subprocess.PIPE)
    return os.path.getsize(staging) if p.returncode == 0 else -1


def main():
    ap = argparse.ArgumentParser(description="Kirim footage-plan.json ke RN7 utk VN")
    ap.add_argument("footage_plan", help="<base>.footage-plan.json")
    ap.add_argument("--udid", default="10.66.66.6:41575")
    ap.add_argument("--container", default="tool-appium-appium-1")
    ap.add_argument("--dest", default="/sdcard/DCIM/VN-src")
    ap.add_argument("--include", default="OK,WARN,FAIL",
                    help="verdikt yg dikirim (default semua ber-klip; EMPTY selalu skip)")
    ap.add_argument("--clips-dir", help="basis path kalau clip.source relatif/hilang")
    ap.add_argument("--no-scan", action="store_true")
    ap.add_argument("--clean", action="store_true",
                    help="kosongkan folder dest dulu (album VN-src = tepat N klip ini)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.footage_plan))
    phases = plan.get("phases", [])
    include = set(x.strip().upper() for x in a.include.split(","))
    dev = RN7(a.container, a.udid, a.dest)

    if not a.dry_run:
        ok, msg = dev.preflight(clean=a.clean)
        if not ok:
            log(f"GAGAL: {msg}")
            sys.exit(3)
        log(f"RN7 {a.udid}: {msg} · dest={a.dest}")

    stage_dir = os.path.join(HOST_ANDROID, STAGE_SUB)
    os.makedirs(stage_dir, exist_ok=True)
    manifest, n_ok, n_skip = [], 0, 0

    for e in phases:
        cl = e.get("clip")
        verdict = (e.get("audit") or {}).get("verdict", "EMPTY")
        if not cl or verdict == "EMPTY":
            n_skip += 1
            log(f"  fase {e['i']+1}: tak ada klip (skip)")
            continue
        if verdict not in include:
            n_skip += 1
            log(f"  fase {e['i']+1}: verdikt {verdict} tak di --include (skip)")
            continue
        src = cl.get("source")
        is_g = cl.get("is_gdrive")
        if not is_g and a.clips_dir and not os.path.isabs(src or ""):
            src = os.path.join(a.clips_dir, os.path.basename(cl["name"]))
        remote_name = f"{e['i']+1:02d}_{sanitize(cl['name'])}"
        rec = {"phase": e["i"] + 1, "remote": f"{a.dest}/{remote_name}",
               "src": src, "gdrive": bool(is_g), "verdict": verdict}
        if a.dry_run:
            log(f"  [dry] fase {e['i']+1} {verdict}: {src} -> {rec['remote']}")
            manifest.append(rec)
            continue

        staging = os.path.join(stage_dir, remote_name)
        try:
            sz = stage_gdrive(src, staging) if is_g else stage_local(src, staging)
            if sz <= 0:
                log(f"  fase {e['i']+1}: GAGAL ambil sumber ({src})")
                rec["status"] = "source_error"
                manifest.append(rec)
                continue
            pok, remote, tail = dev.push(staging, remote_name)
            if not pok:
                log(f"  fase {e['i']+1}: push GAGAL ({tail})")
                rec["status"] = "push_error"
                manifest.append(rec)
                continue
            if not a.no_scan:
                dev.scan(remote)
            rec["status"] = "delivered"
            rec["bytes"] = sz
            n_ok += 1
            log(f"  fase {e['i']+1} {verdict}: {os.path.basename(src)} -> {remote} ({sz//1024}KB)")
            manifest.append(rec)
        finally:
            if os.path.exists(staging):
                os.remove(staging)

    if not a.dry_run:
        ls, mq = dev.verify()
        n_media = len([l for l in mq.splitlines() if l.startswith("Row:")])
        log(f"=== TERKIRIM {n_ok} klip ({n_skip} skip) ke {a.dest} ===")
        log(f"  di disk RN7:\n" + "\n".join("    " + l for l in ls.splitlines() if ".mp4" in l))
        log(f"  MediaStore video terdaftar di VN-src: {n_media}"
            + ("" if n_media else " (belum — VN tetap bisa via File App/SAF)"))

    out = a.footage_plan.replace(".footage-plan.json", "") + ".delivery-manifest.json"
    json.dump({"udid": a.udid, "dest": a.dest, "delivered": n_ok,
               "clips": manifest}, open(out, "w"), ensure_ascii=False, indent=2)
    log(f"  manifest -> {out}")


if __name__ == "__main__":
    main()
