#!/usr/bin/env python3
import argparse, json, os, re, subprocess, sys, time, urllib.request

PORT = 9222
CHROME_CDP_DIR = r"C:\chrome-cdp"
LOG = os.path.join(CHROME_CDP_DIR, "open-cs.log")
DESKTOP = os.path.join(os.environ["USERPROFILE"], "Desktop")
SCLOUDSHELL = r"D:\scloudshell"

PROFILES = [
    {"name": "yuni",            "shortcut": os.path.join(DESKTOP, "Cloud Shell - yuni.lnk"),
     "bootstrap": os.path.join(SCLOUDSHELL, "warungbudina-bootstraps.sh")},
    {"name": "balibruntattour", "shortcut": os.path.join(DESKTOP, "Cloud Shell - balibruntat.lnk"),
     "bootstrap": os.path.join(SCLOUDSHELL, "balibruntattour-bootstraps.sh")},
    {"name": "gogobuda",        "shortcut": os.path.join(DESKTOP, "Cloud Shell - gogobuda.lnk"),
     "bootstrap": os.path.join(SCLOUDSHELL, "gogobuda-bootstraps.sh")},
    # ⛔ 2026-10-15 (permintaan user): profil "ogis" DIDEKOMISIONING PENUH
    # (dulu 2026-08-31 cuma dinonaktifkan sementara karena laptop 2 core/
    # 1,4 GHz kewalahan 4 tab Cloud Shell sekaligus -- itu sudah tak berlaku,
    # ini keputusan final). Task Windows open-cs-ogis sudah dihapus, bootstrap
    # D:\scloudshell\ogis-bootstraps.sh di-archive (.decommissioned-20261015,
    # WG privkey-nya sudah tak berguna krn peer 10.66.66.8 dihapus dari hub),
    # ogis-vault/ + deploy_ogis() dihapus dari repo akses-vps (commit 77e225b).
    # Tak ada lagi "cara mengaktifkan lagi" -- harus dibangun ulang dari nol
    # kalau node ini diperlukan lagi ke depan.
]
PROFILE_NAMES = [p["name"] for p in PROFILES]

# (2026-10-28 fix) akun Cloud Shell per profil -- dipakai find_existing_tab()
# utk mengenali tab LAMA yg sudah live & siap pakai, lih. catatan di sana.
EXPECTED_ACCOUNT = {
    "yuni": "warungbudina",
    "balibruntattour": "balibruntattour",
    "gogobuda": "gogobuda65",
}

STAGGER_SECS = 18
READY_TIMEOUT = 180
READY_POLL = 5
# (2026-08-31) batas tunggu tab baru muncul di CDP setelah shortcut diklik.
OPEN_TIMEOUT = 60
# (2026-08-31 fix #2) batas tunggu CDP siap SETELAH ensure-chrome-cdp.ps1
# dipanggil. Chrome cold-start di AMD E1-2500 terukur ~60 detik sampai benar2
# melayani /json (port listening jauh lebih dulu) -- beri margin lebar.
RECOVER_WAIT = 150


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "%s  %s" % (ts, msg)
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def shell_target_ids():
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=5) as r:
            data = json.load(r)
    except Exception:
        return set()
    return {t["id"] for t in data if t.get("type") == "page" and "shell.cloud.google" in t.get("url", "")}


def cdp_alive():
    """True kalau port CDP 9222 benar2 menjawab. SENGAJA dipisah dari
    shell_target_ids(): fungsi itu menelan SEMUA exception jadi set()
    kosong, sehingga "Chrome mati" TAK BISA dibedakan dari "belum ada tab
    Cloud Shell" -- persis lubang yg bikin insiden 2026-08-31."""
    # (2026-08-31 fix #2) timeout 5s TERBUKTI terlalu galak: probe ini HTTP
    # penuh, jauh lebih berat drpd `Test-CDP` di ensure-chrome-cdp.ps1 yg cuma
    # TCP-connect. Saat Chrome baru cold-start di AMD E1-2500, port 9222 SUDAH
    # listening tapi endpoint /json belum sanggup menjawab -> probe gagal
    # padahal Chrome sedang naik dgn baik.
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=8):
            return True
    except Exception:
        return False


def ensure_chrome_cdp(label=""):
    """Pastikan Chrome+CDP hidup SEBELUM shortcut profil diluncurkan.

    (2026-08-31 fix, insiden Wake1) Chrome 109 (versi terakhir yg jalan di
    Win 8.1 ini, tak bisa di-update) CRASH 4x dlm 41 menit pagi itu --
    dikonfirmasi 4 crashpad dump (06:02:34/06:19:19/06:30:24/06:43:15).
    Crash 06:19 membunuh SATU proses Chrome yg dipakai BERSAMA semua profil
    -> sesi balibruntattour+gogobuda yg sudah sehat ikut mati, dan 3
    percobaan yuni berikutnya semua tumbang di "tab baru tak terdeteksi
    dlm 20s" karena menembak ke browser yg memang sudah tak ada.

    Kita TAK bisa memperbaiki Chrome-nya (tak ada versi lebih baru utk
    Win 8.1), jadi yg diperbaiki adalah KETAHANANNYA: sebelum menyentuh
    shortcut apa pun, panggil SOP pemulihan resmi ensure-chrome-cdp.ps1
    (terbukti pulih <10 detik, lihat catatan 2026-08-29). Dgn ini tiap
    retry wake-orchestrator jadi benar2 "percobaan baru", bukan mengulang
    tembakan ke ruang hampa selama 33 menit."""
    if cdp_alive():
        return True
    log("%sCDP 9222 mati -> jalankan SOP pemulihan ensure-chrome-cdp.ps1..." % label)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             os.path.join(CHROME_CDP_DIR, "ensure-chrome-cdp.ps1")],
            capture_output=True, text=True, timeout=120)
    except Exception as e:
        log("%sWARN: ensure-chrome-cdp.ps1 gagal dipanggil: %s" % (label, e))
    # (2026-08-31 fix #2, ketahuan dari live-test siang ini) 40s TERLALU PENDEK
    # & bikin kesimpulan SALAH. Bukti: ensure-chrome-cdp.ps1 lapor "RECOVERED"
    # 11:56:47 (TCP connect), tapi kode ini vonis "CDP tetap mati" 11:57:29 --
    # padahal proses Chrome MASIH bermunculan sampai 11:57:43. Jadi Chrome
    # sedang naik normal, cuma butuh ~60 detik penuh utk siap melayani /json
    # di laptop ini. Anggaran dinaikkan ke RECOVER_WAIT (150s) supaya tak lagi
    # menyerah di tengah startup yg sebenarnya sehat; loop tetap keluar SEGERA
    # begitu CDP menjawab (kasus normal beberapa detik), jadi ini murni
    # menambah kesabaran, bukan menambah waktu tunggu.
    deadline = time.time() + RECOVER_WAIT
    while time.time() < deadline:
        if cdp_alive():
            log("%sCDP pulih (%.0fs)." % (label, time.time() - (deadline - RECOVER_WAIT)))
            # Chrome baru bangun masih sibuk render window pertama di CPU
            # lemah ini -- kasih napas sebelum shortcut profil ditembakkan.
            time.sleep(5.0)
            return True
        time.sleep(3)
    log("%sERROR: CDP tetap mati setelah ensure-chrome-cdp + tunggu %ss." % (label, RECOVER_WAIT))
    return False


def run_tool(script, *args, timeout=60):
    cmd = [sys.executable, os.path.join(CHROME_CDP_DIR, script)] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.returncode, (r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return (-1, "TIMEOUT")


def find_existing_tab(name):
    """(2026-10-28 fix, insiden pasca-outage-listrik 27/10) Cek dulu apakah
    profil ini SUDAH punya tab Cloud Shell live sisa percobaan sebelumnya,
    sebelum menembak shortcut.

    Akar masalah yg diperbaiki: shell_target_ids() global (semua profil
    campur jadi satu set, CDP 9222 melayani SEMUA window Chrome). Kalau tab
    utk profil INI sudah terbuka (mis. attempt sebelumnya macet di tengah
    bootstrap), klik shortcut lagi di laptop Windows ini cuma FOKUS ke window
    yg sudah ada -- TAK membuka tab baru -- jadi diff before/after di
    open_profile() selalu kosong & divonis salah "tab baru tak terdeteksi"
    (reproduksi live 2026-10-28: balibruntattour SKIP total, bootstrap tak
    pernah dicoba, padahal tab-nya sendiri live & siap pakai). Reused: tab
    lama kalau memang authentic (akun cocok) & responsif -- JAUH lebih murah
    drpd buang tab yg justru sudah dalam kondisi terbaik (siap diketik)."""
    for tid in shell_target_ids():
        rc, out = run_tool("cshell.py", "scrape", tid, "10", timeout=20)
        if rc != 0:
            continue
        m = re.search(r"([A-Za-z0-9._%+-]+)@cloudshell", out)
        if m and m.group(1) == EXPECTED_ACCOUNT.get(name):
            return tid
    return None


def open_profile(p):
    if not os.path.exists(p["shortcut"]):
        log("[%s] ERROR shortcut tak ditemukan: %s" % (p["name"], p["shortcut"]))
        return None
    # (2026-08-31 fix) Prasyarat MUTLAK: browser hidup dulu, baru shortcut.
    if not ensure_chrome_cdp("[%s] " % p["name"]):
        log("[%s] SKIP: browser tak bisa dihidupkan (bukan soal profil ini)." % p["name"])
        return None
    existing = find_existing_tab(p["name"])
    if existing:
        log("[%s] tab lama SUDAH live (id=%s) -- pakai ulang, skip klik shortcut." %
            (p["name"], existing))
        return existing
    before = shell_target_ids()
    os.startfile(p["shortcut"])
    log("[%s] shortcut diluncurkan, menunggu tab baru..." % p["name"])
    # (2026-08-31 fix) 20s TERBUKTI terlalu mepet: kalau Chrome baru
    # cold-start (mis. barusan dipulihkan di atas), window pertama + halaman
    # shell.cloud.google.com di AMD E1-2500 bisa lewat 20 detik. Dinaikkan ke
    # OPEN_TIMEOUT; loop tetap keluar SEGERA begitu tab muncul (kasus normal
    # ~2 detik), jadi ini murni menambah toleransi, bukan menambah tunggu.
    deadline = time.time() + OPEN_TIMEOUT
    new_id = None
    while time.time() < deadline:
        time.sleep(1.5)
        # Kalau CDP hilang DI TENGAH tunggu, itu Chrome crash lagi -- laporkan
        # apa adanya, jangan disamarkan jadi "tab tak terdeteksi" (diagnosa
        # yg menyesatkan selama insiden 31/8).
        if not cdp_alive():
            log("[%s] ERROR: CDP hilang saat menunggu tab -- Chrome crash lagi." % p["name"])
            return None
        diff = shell_target_ids() - before
        if diff:
            new_id = sorted(diff)[0]
            break
    if new_id:
        log("[%s] tab id=%s" % (p["name"], new_id))
    else:
        log("[%s] WARN: tab baru tak terdeteksi dlm %ss (mungkin numpang tab lama)"
            % (p["name"], OPEN_TIMEOUT))
    return new_id


def wait_ready(name, tid):
    deadline = time.time() + READY_TIMEOUT
    while time.time() < deadline:
        rc, out = run_tool("cshell.py", "scrape", tid, "15", timeout=20)
        if rc == 0 and "@cloudshell" in out:
            log("[%s] prompt siap." % name)
            return True
        # (2026-08-31 fix #3) Chrome bisa CRASH di tengah penantian ini. Dulu
        # tak dicek sama sekali -> browser mati ditunggui sampai 180s habis lalu
        # dilaporkan "prompt TAK siap", diagnosa yg MENYESATKAN (menyiratkan
        # Cloud Shell/Google yg lambat, padahal browsernya yg tumbang).
        # Terjadi persis begitu 2026-08-31 12:11:57-12:15:02: tab yuni terbuka
        # normal, Chrome mati 12:13:28, sisa waktu terbuang menunggui mayat.
        # Keluar SEGERA & sebut sebab sebenarnya; retry di wake-orchestrator
        # akan memanggil ensure_chrome_cdp() dan mulai dari browser bersih.
        if not cdp_alive():
            log("[%s] ERROR: CDP hilang saat menunggu prompt -- Chrome crash "
                "(BUKAN 'prompt tak siap')." % name)
            return False
        time.sleep(READY_POLL)
    log("[%s] WARN: prompt TAK siap dlm %ss (auth/VM mungkin masih proses)." % (name, READY_TIMEOUT))
    return False


def bootstrap(p, tid):
    if not os.path.exists(p["bootstrap"]):
        log("[%s] ERROR bootstrap file tak ada: %s" % (p["name"], p["bootstrap"]))
        return False
    # (2026-08-28 fix #2, temuan user via pengamatan LANGSUNG di laptop) --
    # "prompt siap" (wait_ready, deteksi teks "@cloudshell") TAK BERARTI
    # halaman benar2 selesai settle -- page masih bisa geser layout/kursor
    # sesaat sesudahnya. Ketik TERLALU CEPAT pasca-load = kursor "berpindah"
    # & ketikan nyasar. Kasih jeda dulu sblm menyentuh apa pun.
    time.sleep(2.5)
    # (2026-08-28 fix, temuan user) Cloud Shell default buka mode "Editor"
    # (split: panel Editor gede + Terminal cuma sisa ~seperempat layar) --
    # BEDA dari kebiasaan manual user yg SELALU pakai mode full-terminal
    # (blank hitam penuh). Diduga kuat kontributor silent-drop/typing-gagal
    # (area terminal kecil -> render/klik-koordinat kurang stabil di CPU
    # lemah). Tutup Editor SEBELUM upload+ketik apa pun -- tombol toggle,
    # aman diklik walau kadang sudah tertutup (op_click "NONE" kalau label
    # "Tutup Editor" tak ketemu, mis. krn sudah "Buka Editor").
    # (2026-08-29 fix, temuan investigasi "yuni tak dapat full-terminal") --
    # op_click() SEKALI tembak, tanpa retry sendiri (beda dr op_run yg sudah
    # 3x). Terbukti live: kalau tab masih sibuk render (mis. profil TERAKHIR
    # diproses, 2 tab lain sudah nge-flood ping keepalive -> CPU lemah makin
    # kewalahan) atau ada popup baru Google yg tak terduga (mis. "Try Google
    # Cloud Data Agent Kit"), evaluate JS-nya bisa macet & kena hard-kill
    # timeout=15 di run_tool -- rc=-1 TIMEOUT, panel Editor TAK PERNAH
    # tertutup, sisa proses (upload/ketik) tetap jalan tapi di terminal
    # kecil (scrape sering ketinggalan echo -> false "STATUS TAK PASTI").
    # Retry maks 3x, jeda 3s antar percobaan biar tab sempat settle.
    for attempt in range(1, 4):
        rc, out = run_tool("cshell.py", "click", tid, "Tutup Editor", timeout=15)
        log("[%s] tutup panel Editor (full-terminal) percobaan %d/3: rc=%s %s" %
            (p["name"], attempt, rc, out.strip()[:80]))
        if rc == 0:
            break
        if attempt < 3:
            time.sleep(3.0)
    # (fix #2) jeda lebih panjang pasca klik ini -- ini LAYOUT SHIFT BESAR
    # (panel Editor unmount, Terminal resize ke full-screen), butuh waktu
    # settle sblm koordinat klik terminal berikutnya (click_terminal() di
    # cshell.py) bisa dipercaya akurat.
    time.sleep(2.5)
    rc, out = run_tool("upload.py", tid, p["bootstrap"], timeout=30)
    log("[%s] upload rc=%s: %s" % (p["name"], rc, out.strip()[:200]))
    if rc != 0 or "NO_FILE_INPUT" in out:
        log("[%s] ERROR upload gagal, batal bootstrap." % p["name"])
        return False
    time.sleep(2.5)
    # (2026-08-28 fix) popup "N item telah ditransfer" muncul pasca-upload &
    # bisa curi fokus/menutupi terminal -- tutup dulu sblm ngetik. Label
    # "Tutup" AMAN unik dipakai di titik ini krn Editor sudah tertutup di
    # atas (kalau editor masih ada, "Tutup Editor"/"Tutup Terminal" JUGA
    # match "Tutup"? -- TIDAK, regex op_click pakai anchor ^$ exact match,
    # jadi "Tutup" tak pernah nyasar ke "Tutup Editor").
    rc, out = run_tool("cshell.py", "click", tid, "Tutup", timeout=15)
    log("[%s] tutup popup transfer: rc=%s %s" % (p["name"], rc, out.strip()[:80]))
    # (fix #2) jeda settle pasca popup ditutup SEBELUM klik-kursor+ketik
    # (dilakukan cshell.py run -> type_cmd() -> click_terminal()+ctrlu()).
    # Ini PERSIS urutan yg diminta user: pause -> pastikan full-terminal ->
    # klik kursor terminal -> baru ketik (bukan ketik langsung stlh upload).
    time.sleep(2.0)
    fname = os.path.basename(p["bootstrap"])
    cmd = "chmod +x %s && sudo bash %s" % (fname, fname)
    # (2026-08-27 fix) Timeout lama 40s TERBUKTI mepet/kurang: op_run() cshell.py
    # tidur "wait" detik (20s) SEBELUM cek hasil, dan bisa retry SEKALI (fix
    # 25/8) -> attempt tunggal saja (ketik command 70-85 karakter @ 2 event
    # CDP/karakter di laptop AMD E1-2500 yg sering CPU-bound + overhead
    # front/focus/esc/klik-terminal) sudah mepet ke 35-40 detik; kalau attempt
    # ke-2 sempat terpicu (marker belum ke-echo di attempt-1), total mudah
    # 41-46 detik -> lewat timeout=40 lama -> proses dibunuh paksa, TIMEOUT
    # palsu walau command sebenarnya sedang/sudah jalan di VM. Dikonfirmasi
    # reproduksi live 2026-08-27 (yuni & balibruntattour, gejala identik pas
    # di detik ke-42). Naikkan ke 90s: aman menampung 2x(20s tidur)+ketik+
    # overhead dengan margin, tanpa mengubah wait="20" (masih perlu utk kasih
    # waktu command benar2 selesai jalan sebelum discrape).
    #
    # (2026-08-28 fix) 2 attempt TERBUKTI kadang tak cukup (reproduksi live:
    # balibruntattour attempt 1 & 2 SAMA-SAMA gagal ter-echo, WG tunnel tak
    # pernah naik walau exit rc=0 "selesai" dilaporkan) -> cshell.py op_run()
    # dinaikkan jadi 3 attempt. Timeout di sini ikut dinaikkan 90->130s supaya
    # attempt ke-3 tak kepotong paksa (~3x(20s tidur)+ketik+overhead, margin).
    rc, out = run_tool("cshell.py", "run", tid, cmd, "20", timeout=130)
    tail = out.strip()[-600:]
    log("[%s] bootstrap run rc=%s:\n%s" % (p["name"], rc, tail))
    ok = ("SSH ACCESS READY" in out) or ("watchdog aktif" in out) or ("DONE" in out)
    log("[%s] bootstrap %s." % (p["name"], "SUKSES" if ok else "STATUS TAK PASTI (cek log/scrape manual)"))
    return ok


def process_one(p):
    """Buka + bootstrap SATU profil. Dipakai baik mode single-profile maupun
    mode legacy all-3 (dipanggil per-item setelah tab-nya sendiri terbuka)."""
    tid = open_profile(p)
    if not tid:
        log("[%s] SKIP bootstrap (tab id tak diketahui)." % p["name"])
        return False
    if wait_ready(p["name"], tid):
        return bootstrap(p, tid)
    log("[%s] SKIP bootstrap (prompt tak siap)." % p["name"])
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Buka + bootstrap tab Cloud Shell (WG+SSH admin doang, TANPA "
                     "git-clone/deploy - itu urusan hub).")
    ap.add_argument("--profile", choices=PROFILE_NAMES, default=None,
                     help="Kalau diisi: proses SATU profil ini saja, dipicu HUB "
                          "satu-per-satu (alur bertahap wake-orchestrator.sh). "
                          "Kalau kosong: mode lama, proses SEMUA profil sekaligus "
                          "(staggered) - dipertahankan utk pakai manual/darurat "
                          "saja, BUKAN alur otomatis harian lagi.")
    args = ap.parse_args()

    if args.profile:
        p = next(x for x in PROFILES if x["name"] == args.profile)
        log("=== open-and-bootstrap-cs: mulai (single-profile: %s) ===" % args.profile)
        ok = process_one(p)
        log("=== open-and-bootstrap-cs: selesai (single-profile %s, bootstrap=%s) ===" %
            (args.profile, "ok" if ok else "tak-pasti/gagal"))
        # Exit code cuma indikasi kasar (lihat catatan bootstrap()) - hub TETAP
        # wajib verifikasi independen via WG handshake, bukan percaya exit code ini.
        sys.exit(0 if ok else 1)

    # ---- mode lama: SEMUA profil, staggered (manual/darurat, bukan auto harian) ----
    log("=== open-and-bootstrap-cs: mulai (mode all-3-staggered, LEGACY/manual) ===")
    ids = {}
    for i, p in enumerate(PROFILES):
        ids[p["name"]] = open_profile(p)
        if i < len(PROFILES) - 1:
            time.sleep(STAGGER_SECS)
    log("Semua shortcut diluncurkan. Lanjut bootstrap sekuensial per-profil (hemat CPU, hindari resource-starvation)...")
    for p in PROFILES:
        tid = ids.get(p["name"])
        if not tid:
            log("[%s] SKIP bootstrap (tab id tak diketahui)." % p["name"])
            continue
        if wait_ready(p["name"], tid):
            bootstrap(p, tid)
        else:
            log("[%s] SKIP bootstrap (prompt tak siap)." % p["name"])
    log("=== open-and-bootstrap-cs: selesai (mode legacy) ===")


if __name__ == "__main__":
    main()
