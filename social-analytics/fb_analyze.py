#!/usr/bin/env python3
"""
fb_analyze.py -- Analisa akun Facebook (Insight + Galeri Konten) via browser
laptop SUARAHATI yang sudah login persisten, TANPA API resmi Meta.

KENAPA LEWAT BROWSER, BUKAN API:
  - Facebook Graph API resmi butuh App Review + Page Access Token per-akun,
    proses berat utk sekadar "intip insight". User SUDAH menyimpan akun
    (Facebook/IG/TikTok/YouTube) login persisten di browser laptop SUARAHATI
    -- SOP: [[feedback_social_login_use_laptop_browser]] di memori Claude.
  - Skrip ini reuse infrastruktur CDP yg SUDAH ADA di laptop (dipakai jg utk
    bootstrap Cloud Shell): Chrome jalan dgn --remote-debugging-port=9222,
    dikontrol dari HUB via SSH (host alias `ltap-mini`) + helper Python kecil
    di C:\\chrome-cdp\\ (cdp-eval.py / cdp-click-text.py / cdp-screenshot.py).

DESAIN "FIXED & OFFLINE" (permintaan user 2026-08-25):
  - TIDAK ada langkah yg butuh reasoning model besar -- semua navigasi pakai
    klik-berdasar-TEKS (cari elemen yg innerText-nya PERSIS cocok), bukan
    koordinat piksel tetap yg gampang rusak kalau layout FB berubah.
  - Output SELALU JSON terstruktur ke stdout (gampang dikonsumsi n8n Execute
    Command node / model AI kecil / dibaca manusia) + field "raw_text_dump"
    sbg fallback lossless kalau parser structured-nya suatu saat meleset.
  - Satu file, satu command, exit-code jelas (0=sukses, != 0=gagal) -- tak
    perlu instalasi tambahan di HUB (cuma python3 + ssh, sudah ada).

CARA PAKAI:
  python3 fb_analyze.py --account "Go Go Bud" [--profile "Profile 28"] [--keep-tab]

  --account   : nama PERSIS yg muncul di pemilih-akun Facebook (klik ikon
                profil kanan-atas -> daftar profil). WAJIB.
  --profile   : direktori profil Chrome laptop tempat akun itu login
                (lihat daftar via list-profiles.ps1 di C:\\chrome-cdp\\, atau
                cek Local State Chrome). Default "Profile 28" (Budayana,
                akun yg sejauh ini terverifikasi py akses ke Go Go Bud).
  --keep-tab  : jangan tutup tab Chrome setelah selesai (default: ditutup,
                supaya tak menumpuk tab tiap kali skrip dipanggil berulang
                mis. dari n8n cron).

CARA PAKAI DARI n8n (gogobuda, `.61`):
  n8n TAK BISA SSH langsung ke laptop (beda mesin, beda kredensial). Panggil
  skrip ini via SSH DARI node "Execute Command" n8n ke HUB (yg sudah py akses
  `ssh ltap-mini` terpasang), pola persis skrip deploy lain di proyek ini:
    ssh -i <admin-key> warungbudina@10.66.66.1 \\
      "python3 ~/akses-vps/social-analytics/fb_analyze.py --account 'Go Go Bud'"
  (butuh admin-key n8n bisa reach hub -- BELUM diset, lihat catatan di README
  folder ini utk langkah lanjutan kalau mau diotomasi penuh dari n8n.)

BATASAN DIKETAHUI (baca sebelum percaya buta ke outputnya):
  - Ini SCRAPING UI, bukan API resmi -- kalau Facebook ubah tampilan Dasbor
    Profesional, parser "posts" bisa meleset (walau raw_text_dump tetap
    lossless sbg fallback).
  - Assume akun target SUDAH terdaftar sbg salah satu "profil" yg bisa
    dipilih dari pemilih-akun (Settings -> ikon profil kanan atas) di profil
    Chrome yg dipakai -- BUKAN di-search dari halaman publik (itu selalu
    kena login-wall, sudah diuji 2026-08-25).
  - Laptop WAJIB nyala + Chrome+CDP watcher (`ensure-chrome-cdp` task) hidup.
"""
import argparse
import json
import subprocess
import sys
import time
import re
import shlex
from datetime import datetime, timezone

SSH_HOST = "ltap-mini"
# (2026-08-25) DUA bentuk path sengaja dipisah -- pelajaran pahit sesi ini:
# `subprocess.run(cmd, shell=True)` di Linux lewat /bin/sh, dan backslash
# TAK terkutip di sana ikut ditelan sbg escape char (\c -> c), beda dari
# saat path ini cuma dipakai LANGSUNG di command line bash interaktif.
# REMOTE_DIR_FS (forward-slash) -> WAJIB dipakai di setiap string command
# shell (scp/ssh/powershell -Command via run()/ssh() Python ini).
# REMOTE_DIR (backslash asli) -> HANYA utk isi *konten* skrip PowerShell/XML
# yg nanti dieksekusi Windows sendiri (backslash valid & perlu di sana).
REMOTE_DIR = r"C:\chrome-cdp"
REMOTE_DIR_FS = "C:/chrome-cdp"
LAUNCH_PARAMS_REMOTE = REMOTE_DIR + r"\launch-params.json"
LAUNCH_PARAMS_REMOTE_FS = REMOTE_DIR_FS + "/launch-params.json"
GENERIC_TASK_NAME = "open-profile-generic"

# --- header kolom tabel "Galeri Konten" (urutan TETAP di Dasbor Profesional
# bahasa Indonesia, per pengamatan langsung 2026-08-25). Kalau FB ubah urutan
# ini, cuma bagian parse_posts() yg perlu disesuaikan -- ekstraksi mentahnya
# tetap aman.
POST_METRIC_KEYS = [
    "views", "reach", "engagement", "revenue", "net_followers",
    "impressions", "comments", "distribution_multiplier",
    "watch_time", "avg_watch_time", "views_3s", "views_1min",
]
STATUS_MARKERS = ("Diterbitkan", "Terjadwal", "Draf", "Di-crossposting")

# --- Isi helper kecil di laptop (C:\chrome-cdp\), di-deploy otomatis kalau
# belum ada (lihat ensure_generic_launcher()) -- supaya file INI SATU-SATUNYA
# yg perlu dibawa/dicommit, tak diam-diam bergantung file scratch sesi lain.
HELPER_CDP_EVAL = r"""#!/usr/bin/env python3
import sys, json, time
from websocket import create_connection

tid = sys.argv[1]
expr = sys.argv[2]
outfile = sys.argv[3] if len(sys.argv) > 3 else None
ws = create_connection("ws://127.0.0.1:9222/devtools/page/%s" % tid, timeout=20, max_size=None)

def send(method, params=None):
    mid = int(time.time() * 1000) % 100000
    msg = {"id": mid, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    for _ in range(200):
        raw = ws.recv()
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if r.get("id") == mid:
            return r
    raise SystemExit("no matching response")

r = send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
out = json.dumps(r.get("result", {}).get("result", {}).get("value"), ensure_ascii=False, indent=2)
if outfile:
    with open(outfile, "wb") as f:
        f.write(out.encode("utf-8"))
    print("written %d bytes to %s" % (len(out.encode("utf-8")), outfile))
else:
    sys.stdout.buffer.write(out.encode("utf-8"))
ws.close()
"""

HELPER_CDP_CLICK_TEXT = r"""#!/usr/bin/env python3
# Klik elemen berdasarkan TEKS-nya (exact match innerText) -- jauh lebih
# tahan thd perubahan layout drpd hardcode pixel x,y.
import sys, json, time
from websocket import create_connection

tid = sys.argv[1]
needle = sys.argv[2]

ws = create_connection("ws://127.0.0.1:9222/devtools/page/%s" % tid, timeout=20, max_size=None)

def send(method, params=None):
    mid = int(time.time() * 1000) % 100000
    msg = {"id": mid, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    for _ in range(200):
        raw = ws.recv()
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if r.get("id") == mid:
            return r
    raise SystemExit("no matching response")

js = ("(function(needle){"
      # (2026-08-25) FB SPA sering punya >1 elemen dgn teks PERSIS sama
      # (mis. label kartu angka "Tayangan" DI LUAR item menu sidebar
      # "Tayangan" -- keduanya innerText persis "Tayangan"). Klik yg
      # kena kartu label (bukan navigasi) diam2 gagal pindah halaman.
      # Fix: PRIORITASKAN kandidat yg py ancestor <a>/role=link/
      # role=button dlm 4 level ke atas (brati genuinely klik-abel utk
      # navigasi), baru fallback ke area terkecil kalau tak ada yg begitu.
      "function isNavish(el){"
      "  var n = el; var hops = 0;"
      "  while (n && hops < 4) {"
      "    if (n.tagName === 'A') return true;"
      "    var role = n.getAttribute && n.getAttribute('role');"
      "    if (role === 'link' || role === 'button' || role === 'menuitem') return true;"
      "    n = n.parentElement; hops++;"
      "  }"
      "  return false;"
      "}"
      "var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);"
      "var candidates = [];"
      "var node;"
      "while (node = walker.nextNode()) {"
      "  var txt = (node.innerText || '').trim();"
      "  if (txt === needle && node.children.length <= 2) {"
      "    var r = node.getBoundingClientRect();"
      "    if (r.width > 0 && r.height > 0) candidates.push({el: node, area: r.width*r.height, rect: r, nav: isNavish(node)});"
      "  }"
      "}"
      "if (!candidates.length) return JSON.stringify({found: false});"
      "candidates.sort(function(a,b){"
      "  if (a.nav !== b.nav) return a.nav ? -1 : 1;"
      "  return a.area - b.area;"
      "});"
      "var best = candidates[0].rect;"
      "return JSON.stringify({found: true, x: best.x + best.width/2, y: best.y + best.height/2, count: candidates.length, nav: candidates[0].nav});"
      "})(%s)") % json.dumps(needle)

r = send("Runtime.evaluate", {"expression": js, "returnByValue": True})
val = r.get("result", {}).get("result", {}).get("value")
print(val)
data = json.loads(val)
if data.get("found"):
    x, y = data["x"], data["y"]
    for tp in ("mousePressed", "mouseReleased"):
        send("Input.dispatchMouseEvent", {"type": tp, "x": x, "y": y, "button": "left", "clickCount": 1})
    print("clicked (%.0f, %.0f)" % (x, y))
ws.close()
"""

HELPER_CDP_CLICK_ARIA = r'''#!/usr/bin/env python3
# Klik elemen berdasar aria-label (exact match) -- utk tombol ikon tanpa
# teks visible (mis. avatar profil). Lebih stabil drpd koordinat piksel.
import sys, json, time
from websocket import create_connection

tid = sys.argv[1]
needle = sys.argv[2]

ws = create_connection("ws://127.0.0.1:9222/devtools/page/%s" % tid, timeout=20, max_size=None)

def send(method, params=None):
    mid = int(time.time() * 1000) % 100000
    msg = {"id": mid, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    for _ in range(200):
        raw = ws.recv()
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if r.get("id") == mid:
            return r
    raise SystemExit("no matching response")

js = """
(function(needle){
  var els = Array.from(document.querySelectorAll('[aria-label="' + needle + '"]'));
  els = els.filter(function(e){var r=e.getBoundingClientRect();return r.width>0 && r.height>0;});
  if (!els.length) return JSON.stringify({found:false});
  var r = els[0].getBoundingClientRect();
  return JSON.stringify({found:true, x:r.x+r.width/2, y:r.y+r.height/2, count:els.length});
})(%s)
""" % json.dumps(needle)

r = send("Runtime.evaluate", {"expression": js, "returnByValue": True})
val = r.get("result", {}).get("result", {}).get("value")
print(val)
data = json.loads(val)
if data.get("found"):
    x, y = data["x"], data["y"]
    for tp in ("mousePressed", "mouseReleased"):
        send("Input.dispatchMouseEvent", {"type": tp, "x": x, "y": y, "button": "left", "clickCount": 1})
    print("clicked (%.0f, %.0f)" % (x, y))
ws.close()
'''

HELPER_LIST_TABS = """$tabs = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/list"
foreach ($t in $tabs) {
    if ($t.type -eq "page") {
        Write-Output ("[" + $t.id + "] TITLE=" + $t.title + " URL=" + $t.url)
    }
}
"""

HELPER_WRITE_PARAMS = r"""#!/usr/bin/env python3
import sys, json
profile = sys.argv[1]
url = sys.argv[2]
outpath = sys.argv[3]
with open(outpath, "w", encoding="utf-8") as f:
    json.dump({"profile": profile, "url": url}, f)
print("written")
"""


def run(cmd, timeout=60):
    """Jalankan command shell lokal (di HUB), return (rc, stdout, stderr)."""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def ssh(remote_cmd, timeout=60):
    full = "ssh -o ConnectTimeout=8 %s %s" % (SSH_HOST, shlex.quote(remote_cmd))
    return run(full, timeout=timeout)


def ensure_generic_launcher():
    """Pasang launcher generik + scheduled task InteractiveToken di laptop,
    KALAU belum ada (idempoten, aman dipanggil berkali-kali). Ini yg bikin
    skrip reusable utk akun/profile Chrome APAPUN, tak perlu bikin scheduled
    task baru tiap akun baru (beda dari pendekatan one-off sesi 25/8 awal)."""
    ps1_content = (
        '$p = Get-Content "%s" -Raw | ConvertFrom-Json\r\n'
        'Start-Process "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
        '-ArgumentList (\'--profile-directory="\' + $p.profile + \'"\'), $p.url\r\n'
    ) % LAUNCH_PARAMS_REMOTE
    xml_content = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>SUARAHATI\\warungbudina</Author>
    <Description>Launcher generik: buka Chrome profil+URL apa pun dari launch-params.json, di sesi interaktif user. Dipakai fb_analyze.py dkk (jangan hapus).</Description>
  </RegistrationInfo>
  <Triggers />
  <Principals>
    <Principal id="Author">
      <UserId>SUARAHATI\\warungbudina</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "%s\\open-profile-generic.ps1"</Arguments>
    </Exec>
  </Actions>
</Task>
""" % REMOTE_DIR

    # 0. helper Python kecil (cdp-eval.py dkk) + list-tabs-full.ps1 WAJIB
    #    ada di laptop -- deploy kalau belum (bikin skrip ini genuinely
    #    mandiri, tak diam-diam bergantung file sisa testing manual sesi
    #    perancangan 2026-08-25).
    helpers = {
        "cdp-eval.py": HELPER_CDP_EVAL,
        "cdp-click-text.py": HELPER_CDP_CLICK_TEXT,
        "cdp-click-aria.py": HELPER_CDP_CLICK_ARIA,
        "list-tabs-full.ps1": HELPER_LIST_TABS,
        "write-launch-params.py": HELPER_WRITE_PARAMS,
    }
    import tempfile, os
    for fname, content in helpers.items():
        # Test-Path return code SELALU 0 (yg penting isi stdout True/False)
        _, out2, _ = ssh("Test-Path %s/%s" % (REMOTE_DIR_FS, fname))
        if out2.strip() == "True":
            continue
        print("[setup] helper '%s' belum ada, deploy..." % fname, file=sys.stderr)
        with tempfile.NamedTemporaryFile("w", suffix=os.path.splitext(fname)[1], delete=False, newline="") as f:
            f.write(content)
            localf = f.name
        rc3 = run("scp -o ConnectTimeout=8 %s %s:%s/%s" % (localf, SSH_HOST, REMOTE_DIR_FS, fname))
        os.unlink(localf)
        if rc3[0] != 0:
            raise RuntimeError("gagal deploy helper %s: %s" % (fname, rc3[2]))

    rc, out, _ = ssh("schtasks /query /tn %s" % GENERIC_TASK_NAME)
    if rc == 0:
        return  # sudah terpasang

    print("[setup] task '%s' belum ada, memasang..." % GENERIC_TASK_NAME, file=sys.stderr)
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, newline="") as f:
        f.write(ps1_content)
        local_ps1 = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, newline="") as f:
        f.write(xml_content)
        local_xml = f.name
    # PENTING: scp mentah (bukan lewat ssh() yg shlex.quote-protected) --
    # WAJIB forward-slash (REMOTE_DIR_FS), backslash di sini akan ketelan
    # /bin/sh krn tak terkutip (\c -> c). Lihat catatan di deklarasi var.
    r1 = run("scp -o ConnectTimeout=8 %s %s:%s/open-profile-generic.ps1" % (local_ps1, SSH_HOST, REMOTE_DIR_FS))
    r2 = run("scp -o ConnectTimeout=8 %s %s:%s/open-profile-generic.xml" % (local_xml, SSH_HOST, REMOTE_DIR_FS))
    os.unlink(local_ps1)
    os.unlink(local_xml)
    if r1[0] != 0 or r2[0] != 0:
        raise RuntimeError("gagal deploy launcher generik: %s / %s" % (r1[2], r2[2]))
    rc, out, err = ssh(r'schtasks /create /tn %s /xml %s\open-profile-generic.xml /f' % (GENERIC_TASK_NAME, REMOTE_DIR))
    if rc != 0:
        raise RuntimeError("gagal register scheduled task: %s" % err)


def open_profile_tab(chrome_profile, url):
    """Tulis launch-params.json (via helper file write-launch-params.py --
    BUKAN inline `python -c`, yg rawan rusak lintas quoting bash->ssh->cmd)
    + trigger scheduled task generik, tunggu tab baru muncul di /json/list,
    return target id-nya."""
    write_cmd = "cd %s; python write-launch-params.py %s %s %s" % (
        REMOTE_DIR, shlex.quote(chrome_profile), shlex.quote(url), LAUNCH_PARAMS_REMOTE)
    rc, out, err = ssh(write_cmd)
    if rc != 0:
        raise RuntimeError("gagal tulis launch-params.json: %s" % err)

    before_ids = set(list_tab_ids())
    ssh("schtasks /run /tn %s" % GENERIC_TASK_NAME)

    for _ in range(30):
        time.sleep(2)
        after_ids = set(list_tab_ids())
        new_ids = after_ids - before_ids
        if new_ids:
            return sorted(new_ids)[0]
    raise RuntimeError("tab baru tak muncul dlm 60 detik -- cek laptop nyala & ensure-chrome-cdp hidup")


def list_tab_ids():
    """Pakai file .ps1 terpisah (list-tabs-full.ps1, sudah di-deploy manual
    ke laptop) -- BUKAN inline `-Command` bertingkat, yg TERBUKTI rapuh
    (nested-quote bash->ssh->powershell rusak berkali-kali sesi ini)."""
    rc, out, _ = ssh(r'powershell -NoProfile -ExecutionPolicy Bypass -File %s\list-tabs-full.ps1' % REMOTE_DIR)
    if rc != 0:
        return []
    ids = []
    for line in out.splitlines():
        m = re.match(r"\[([0-9A-Fa-f]+)\]", line.strip())
        if m:
            ids.append(m.group(1))
    return ids


def _click_with_retry(cmd_fmt, tid, needle, tries=4, wait=2.5):
    """FB adalah SPA berat -- elemen kadang belum ke-render sesaat pasca
    navigasi/klik sebelumnya, walau tab technically 'loaded'. Retry pendek
    di sini jauh lebih robust drpd cuma naikkan satu sleep() tetap di
    main() (yg mustahil pas utk semua kecepatan render)."""
    last_out = ""
    for attempt in range(tries):
        rc, out, err = ssh(cmd_fmt % (REMOTE_DIR, tid, shlex.quote(needle)))
        last_out = out
        if rc == 0 and '"found":true' in out.replace(" ", ""):
            return True
        time.sleep(wait)
    return False


def cdp_click_text(tid, text, tries=4):
    """Klik elemen berdasar innerText EXACT -- jauh lebih tahan thd
    perubahan layout drpd koordinat piksel tetap. tries=1 utk klik yg
    SEKALI-JALAN/navigasional (mis. pemilih-akun) -- retry internal disini
    bisa BAHAYA kalau klik pertama sbnrnya sukses tapi deteksinya telat:
    retry ke-2 bisa ke-dispatch di KONTEKS HALAMAN BARU yg sudah berubah,
    mengacaukan navigasi yg sebenarnya sudah benar (pelajaran pahit sesi
    perancangan 2026-08-25)."""
    return _click_with_retry('cd %s; python cdp-click-text.py %s %s', tid, text, tries=tries)


def cdp_click_aria(tid, label, tries=4):
    """Klik elemen berdasar aria-label EXACT (utk tombol ikon tanpa teks,
    mis. avatar 'Profil Anda') -- lebih stabil drpd koordinat piksel tetap.
    tries=1 utk klik navigasional sekali-jalan (lihat catatan cdp_click_text)."""
    return _click_with_retry('cd %s; python cdp-click-aria.py %s %s', tid, label, tries=tries)


def cdp_eval_text(tid, js_expr):
    """Evaluate expression yg return string, ambil via file sementara (utf-8
    aman, hindari mangling encoding lintas ssh/cmd -- scp TAK support '-'
    sbg stdout, jadi selalu lewat file lokal sementara)."""
    import tempfile, os
    remote_out = REMOTE_DIR + r"\_tmp_eval_out.txt"
    rc, out, err = ssh('cd %s; python cdp-eval.py %s %s %s' % (
        REMOTE_DIR, tid, shlex.quote(js_expr), remote_out))
    if rc != 0:
        raise RuntimeError("eval gagal: %s" % err)
    fd, localf = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    rc, _, err = run("scp -o ConnectTimeout=8 '%s:%s' %s" % (
        SSH_HOST, remote_out.replace("\\", "/"), localf))
    if rc != 0:
        raise RuntimeError("gagal tarik hasil eval: %s" % err)
    with open(localf, "r", encoding="utf-8") as f:
        content = f.read()
    os.unlink(localf)
    try:
        return json.loads(content)
    except Exception:
        return content


def wait_for_text(tid, marker, timeout_s=12, interval=1.5):
    """Poll innerText sampai `marker` genuinely muncul (bukan cuma tebak
    sleep() tetap -- FB SPA render-nya VARIABEL, kadang <1s kadang >5s
    tergantung beban. Ini akar masalah "kadang capture kosong" yg TERBUKTI
    kejadian berulang selama perancangan 2026-08-25). Return teks final yg
    ditangkap (baik ketemu marker maupun timeout -- selalu return APA
    ADANYA, caller yg putuskan apakah itu cukup)."""
    deadline = time.time() + timeout_s
    text = ""
    while time.time() < deadline:
        text = cdp_eval_text(tid, "document.body.innerText")
        if isinstance(text, str) and marker in text:
            return text
        time.sleep(interval)
    return text  # timeout -- tetap kembalikan hasil terakhir apa adanya


def close_tab(tid):
    # (2026-08-25) HINDARI inline -Command nested-quote (rapuh, TERBUKTI
    # gagal senyap sesi ini) -- bare command langsung ke shell PowerShell
    # remote sudah cukup (server SSH laptop default-nya PowerShell).
    ssh('Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/close/%s"' % tid)


def parse_posts(raw_text):
    """Parser best-effort tabel 'Galeri Konten'. Rapuh thd perubahan UI FB
    scr desain (lihat docstring modul) -- makanya raw_text SELALU disimpan
    utuh di output juga."""
    lines = [l for l in raw_text.split("\n")]
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "Tayangan 1 menit")
    except StopIteration:
        return []
    body = lines[start + 1:]

    posts = []
    i = 0
    while i < len(body):
        line = body[i].strip()
        if not line:
            i += 1
            continue
        # cari marker status dlm beberapa baris ke depan (caption bisa >1 baris)
        status_idx = None
        for j in range(i, min(i + 6, len(body))):
            if any(body[j].strip().startswith(m) for m in STATUS_MARKERS):
                status_idx = j
                break
        if status_idx is None:
            i += 1
            continue
        caption = " ".join(x.strip() for x in body[i:status_idx] if x.strip())
        status_line = body[status_idx].strip()
        date_line = body[status_idx + 1].strip() if status_idx + 1 < len(body) else ""
        metrics_start = status_idx + 2
        metrics = body[metrics_start: metrics_start + len(POST_METRIC_KEYS)]
        post = {"caption": caption, "status": status_line.rstrip("• ").strip(), "published_at": date_line}
        for key, val in zip(POST_METRIC_KEYS, metrics):
            post[key] = val.strip()
        posts.append(post)
        i = metrics_start + len(POST_METRIC_KEYS)
    return posts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", required=True, help='nama PERSIS di pemilih-akun FB, mis. "Go Go Bud"')
    ap.add_argument("--profile", default="Profile 28", help='direktori profil Chrome (default: Profile 28 / Budayana)')
    ap.add_argument("--keep-tab", action="store_true", help="jangan tutup tab setelah selesai")
    ap.add_argument("--days", default="28 hari terakhir", help="label rentang waktu insight (informational saja, FB pakai default periode terakhir)")
    args = ap.parse_args()

    result = {
        "account_requested": args.account,
        "chrome_profile": args.profile,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "error": None,
    }

    tid = None
    try:
        ensure_generic_launcher()

        tid = open_profile_tab(args.profile, "https://www.facebook.com/")
        time.sleep(2)

        # 1. buka pemilih-akun (avatar kanan-atas, aria-label "Profil Anda"
        #    -- ditemukan via inspeksi DOM langsung 2026-08-25, lebih stabil
        #    drpd koordinat piksel tetap) lalu klik nama akun target.
        #    PENTING (pelajaran pahit perancangan 2026-08-25): return value
        #    fungsi klik ITU SENDIRI tak selalu andal jadi sinyal sukses --
        #    pernah kejadian klik BENERAN berhasil (feed pindah akun) tapi
        #    fungsi lapor gagal (kemungkinan round-trip SSH sempat lambat).
        #    Makanya di sini klik dianggap CUMA USAHA TERBAIK; validitas
        #    SEBENARNYA diverifikasi lewat wait_for_text("pengikut") di
        #    bawah -- itu baca STATE HALAMAN NYATA, bukan return value klik.
        #    CATATAN (perancangan 2026-08-25): klik avatar+nama akun ini
        #    memindah KONTEKS akun (terverifikasi via composer "Apa yang
        #    Anda pikirkan, <Nama>?"), tapi TAK SELALU mendarat persis di
        #    halaman profil sendiri ("N pengikut" cuma nampak di sana, tak
        #    ada di Beranda/feed) -- perilaku SPA FB tak konsisten soal ini,
        #    beberapa kali percobaan menembak-nembak (double-click-cycle dkk)
        #    JUSTRU memperburuk (bikin langkah SETELAHNYA ikut gagal krn
        #    kelamaan/kena state aneh). Versi PALING ANDAL scr empiris:
        #    SATU kali klik avatar+akun, retry di dalam fungsi klik itu
        #    sendiri (tries default) kalau tak ketemu elemen, LALU LANJUT
        #    apa pun hasilnya -- followers_total best-effort (sering null,
        #    field lain TAK bergantung ke ini).
        cdp_click_aria(tid, "Profil Anda")
        time.sleep(1.5)
        cdp_click_text(tid, args.account)
        probe = wait_for_text(tid, "pengikut", timeout_s=8)
        got_it = "pengikut" in probe
        # (2026-08-25) SENGAJA TAK di-raise kalau got_it False -- follower
        # count ("pengikut") itu SATU field best-effort, BUKAN syarat mutlak
        # utk lanjut. Terbukti empiris di sesi perancangan: proses berikutnya
        # (klik "Dasbor" -> Insight -> Galeri Konten) TETAP bisa berhasil
        # walau step ini gagal mendarat tepat di halaman profil (kadang
        # nyangkut di Beranda/feed) -- drpd gagalkan SELURUH run demi 1
        # field, cukup catat null utk followers_total & tetap lanjut.
        if not got_it:
            print('[warn] gagal pastikan halaman profil (utk follower count) '
                  '-- lanjut tanpa itu, field lain biasanya tetap berhasil',
                  file=sys.stderr)

        # 2b. innerText halaman profil (dari `probe` di atas, best-effort --
        #     sumber PALING andal utk follower count, "N pengikut" nampak
        #     langsung di header profil, drpd navigasi sidebar "Pemirsa" yg
        #     TERBUKTI ambigu/>1 elemen bernama sama di FB).
        sections = {"profile_raw": probe}

        # 3. masuk Dasbor Profesional -- halaman BERANDA-nya SENDIRI sudah
        #    menampilkan Tayangan+Interaksi+Pengikut-bersih SEKALIGUS dlm 1
        #    widget "Insight" ringkas, jadi TAK PERLU lagi klik ke sub-menu
        #    "Tayangan"/"Interaksi"/"Pemirsa" terpisah (sub-menu itu punya
        #    label yg AMBIGU/duplikat di sidebar FB -- percobaan awal
        #    perancangan skrip ini kena nyasar ke halaman "Pengelola
        #    komentar" krn keduanya sama2 innerText "Interaksi").
        cdp_click_text(tid, "Dasbor")
        overview_raw = wait_for_text(tid, "Tayangan")
        if "Tayangan" not in overview_raw:
            cdp_click_text(tid, "Dasbor")  # 1x retry, sama pola Galeri Konten
            overview_raw = wait_for_text(tid, "Tayangan")
        sections["overview_raw"] = overview_raw

        # 4. Isi (Galeri Konten) -- data per-postingan, paling berguna utk
        #    "ide konten" (lihat post mana yg performanya bagus). "Isi" itu
        #    header collapsible -- sub-item "Galeri Konten" baru klik-abel
        #    SETELAH expand-nya genuinely selesai render, jadi tunggu dulu
        #    sblm coba klik (sama akar masalah timing spt langkah lain).
        cdp_click_text(tid, "Isi")
        wait_for_text(tid, "Galeri Konten", timeout_s=8)
        cdp_click_text(tid, "Galeri Konten")
        content_raw = wait_for_text(tid, "Pratinjau")
        if "Pratinjau" not in content_raw:
            # satu percobaan ulang -- kadang expand "Isi" perlu diklik ulang
            # kalau attempt pertama kena race (menu sempat collapse lagi).
            cdp_click_text(tid, "Isi")
            wait_for_text(tid, "Galeri Konten", timeout_s=8)
            cdp_click_text(tid, "Galeri Konten")
            content_raw = wait_for_text(tid, "Pratinjau")
        sections["content_raw"] = content_raw

        def grab_number_before_label(label, text):
            """Pola nyata di Dasbor FB: NOMOR \\n PERSEN% \\n LABEL (nomor
            & persen mendahului label-nya, bukan sesudah)."""
            lines = [l.strip() for l in text.split("\n")]
            for i, l in enumerate(lines):
                if l == label and i >= 2:
                    pct_line = lines[i - 1].lstrip("﻿​").strip()
                    num_line = lines[i - 2].strip()
                    if re.match(r"^[\d.,]+$", num_line):
                        return num_line, (pct_line or None)
            return None, None

        def grab_follower_count(text):
            m = re.search(r"([\d.,]+)\s*pengikut\b", text)
            return m.group(1) if m else None

        # (2026-08-25) klik akun kadang mendarat di Beranda/feed, bukan
        # halaman profil sendiri (perilaku FB tak konsisten, blm ketemu
        # cara paksa navigasi yg andal) -- fallback CARI DI SEMUA bagian
        # teks yg sudah tertangkap, bukan cuma profile_raw. Biaya nol
        # (tak nambah request), kadang tertangkap krn "N pengikut" bisa
        # nongol di sidebar/tempat lain jg.
        followers = None
        for _sect in (sections.get("profile_raw", ""), sections.get("overview_raw", ""), sections.get("content_raw", "")):
            followers = grab_follower_count(_sect)
            if followers:
                break
        views, views_growth = grab_number_before_label("Tayangan", sections["overview_raw"])
        engagement, engagement_growth = grab_number_before_label("Interaksi", sections["overview_raw"])
        net_followers, net_followers_growth = grab_number_before_label("Pengikut bersih", sections["overview_raw"])

        result["insight"] = {
            "followers_total": followers,
            "views_total": views,
            "views_growth": views_growth,
            "engagement_total": engagement,
            "engagement_growth": engagement_growth,
            "net_followers_period": net_followers,
            "net_followers_growth": net_followers_growth,
        }
        result["posts"] = parse_posts(content_raw)
        result["raw_text_dump"] = sections
        result["ok"] = True

    except Exception as e:
        result["error"] = str(e)
    finally:
        # WAJIB tutup tab meski GAGAL -- kalau tidak, tiap percobaan gagal
        # numpuk tab Chrome baru (terbukti nyata sesi perancangan 2026-08-25:
        # 9 tab nyangkut dari retry berturut2, laptop makin lambat & bikin
        # percobaan BERIKUTNYA makin sering gagal juga -- efek bola salju).
        if tid and not args.keep_tab:
            try:
                close_tab(tid)
            except Exception:
                pass

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
