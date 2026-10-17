#!/usr/bin/env python3
"""orchestrator.py — pipeline video viral ON-DEMAND (jalan di akses-vps).

Kuras antrean `media.video_ingest` (DB-VPS). Per job:
  claim (FOR UPDATE SKIP LOCKED) -> download di DB-VPS (yt-dlp, cookies per platform)
  -> stream video DB-VPS->.50 via pipe (TAK mendarat di disk akses-vps)
  -> POST /analyze di .50 -> tulis media.video_analysis (+category, JSON dollar-quote)
  -> status 'analyzed' -> [best-effort: reproduksi VN + footage stok + RAW
  footage Gdrive, lihat split_and_push_raw()] -> hapus video 2 sisi.
Gagal di langkah mana pun -> status 'pending' (retry) / 'dead' (habis) + last_error.

(2026-10-17) Sejak job 'analyzed': video sumber (TANPA audio) + audio-only +
1 thumbnail ditarik balik DB-VPS->hub & di-push ke Gdrive gfootage:
raw-video-footage/ · raw-audio-footage/ · raw-thumbnail/ (nama file = judul
asli + URL lengkap) -- lihat split_and_push_raw(). Ini kolam bahan MENTAH
hasil analisa, BEDA dari gfootage:RAW-VIDEO/ (stok Pexels/Pixabay, Jalur C)
dan gfootage:VN-exports/ (hasil edit SIAP-PUBLISH, dipakai premiere_pipeline.py).

Prasyarat runtime: user aktifkan .50 + analyzer healthy (bring-up-analyzer.sh);
DB-VPS reachable; cookies+yt-dlp+deno di DB-VPS ~/viral-pipeline/.
Env: MAX_JOBS=N (0=kuras semua, default 0).
"""
import subprocess, json, sys, os, shlex, re

DBVPS       = "db-vps"                    # host alias ssh (akses-vps -> DB-VPS)
C50_SOCK    = "/tmp/c50.sock"
C50         = "warungbudina@10.66.66.50"
DBVPS_TOOLS = "~/viral-pipeline"          # yt-dlp, deno, {yt,fb,ig}-cookies.txt
DBVPS_WORK  = "~/viral-pipeline/work"
C50_INPUT   = "~/tool-analisa-video/data/input"
ANALYZER    = "http://127.0.0.1:9021"
COOKIES     = {"youtube":"yt-cookies.txt", "facebook":"fb-cookies.txt", "instagram":"ig-cookies.txt"}
MAX_JOBS    = int(os.getenv("MAX_JOBS", "0"))
ANALYZE_TIMEOUT = int(os.getenv("ANALYZE_TIMEOUT", "1200"))  # detik; whisper CPU (V2) utk video panjang bisa >5mnt
# (2026-08-28) opsi 3 permintaan user: sambungkan ir_to_vn.py ke drain
# otomatis, supaya tiap analisa SEKALIAN hasilkan cetak-biru reproduksi VN
# (termasuk .story-script.md, WAJIB per SOP lama -- lihat memori
# feedback_ir_to_vn_story_script) TANPA langkah manual lagi.
IR_TO_VN    = os.path.expanduser("~/viral-pipeline/ir_to_vn.py")   # jalan LOKAL di akses-vps
REPRO_DIR   = os.path.expanduser("~/viral-pipeline/reproductions")  # <dir>/job-<id>/job-<id>.*
# (2026-08-29) Jalur C permintaan user: sekalian sumber-kan footage stok
# MENTAH (Pexels+Pixabay, per babak) & kirim ke Gdrive raw -- bahan siap
# diedit manual bebas (BEDA dari build_reproduction() di atas, yg bikin
# cetak-biru edit OTOMATIS/VN-HP). Lihat memori project_viral_analyzer.md.
PEXELS_FETCH     = os.path.expanduser("~/viral-pipeline/pexels_fetch.py")
PIXABAY_FETCH    = os.path.expanduser("~/viral-pipeline/pixabay_fetch.py")
PUSH_RAW_FOOTAGE = os.path.expanduser("~/viral-pipeline/push_raw_footage.py")
FOOTAGE_TIMEOUT  = int(os.getenv("FOOTAGE_TIMEOUT", "600"))  # detik/skrip; jaringan-bound (unduh+upload)
# (2026-08-28) celah #3 audit otomatisasi: job yg gagal permanen ('dead' stlh
# max_attempts habis) dulu diam total di DB, tak ada yg tahu kecuali cek
# manual -- beda dgn wake-orchestrator.sh yg SELALU notify Telegram. Fix:
# reuse helper yg sama (send-telegram.sh, no-op anggun kalau kredensial
# belum diisi -- lihat isi skrip itu).
TELEGRAM_SCRIPT = os.path.expanduser("~/akses-vps/backup/send-telegram.sh")
# (2026-10-17) permintaan user: simpan bahan MENTAH sumber Tier-2 (video TANPA
# audio + audio-only + 1 thumbnail) ke Gdrive gfootage: -- TIGA folder BARU,
# TERPISAH dari RAW-VIDEO (stok Pexels/Pixabay, Jalur C lama) dan VN-exports
# (hasil edit SIAP-PUBLISH) -- supaya "bahan mentah hasil analisa" tak
# tercampur dgn "video siap publish". Proses jalan LOKAL di hub (bukan
# DB-VPS/.50 -- keduanya nol ffmpeg+kredensial gfootage, lihat audit 17/10),
# pola sama persis fetch_and_push_footage() (tarik->proses->push->best-effort).
GFOOTAGE = {"video": "gfootage:raw-video-footage/", "audio": "gfootage:raw-audio-footage/",
            "thumb": "gfootage:raw-thumbnail/"}
RAW_WORKDIR = os.path.expanduser("~/viral-pipeline/raw-work")
RAW_MIN_DISK_MB = 500  # lindungi disk hub (pernah 93% penuh, lihat social-trend-cron.sh)

def sh(args, inp=None, timeout=None):
    return subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)

def sh_safe(args, timeout=None):
    """sh() tapi TAK PERNAH raise (TimeoutExpired dkk ditangkap) -- dipakai
    langkah best-effort PASCA-job-sukses (build_reproduction, fetch_and_push_
    footage). Tanpa ini, subprocess.run(timeout=...) yg raise TimeoutExpired
    lolos ke except umum di main() -> fail_job() keliru menimpa status job
    yg SEBENARNYA sudah 'analyzed' -- celah yg ditemukan 2026-08-29 saat
    nambah langkah footage baru, sekalian difix di build_reproduction()."""
    try:
        return sh(args, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(args, -1, "", f"exception: {e!r}")

def ssh_db(cmd, timeout=None):
    return sh(["ssh", DBVPS, cmd], timeout=timeout)

def ssh_c50(cmd, timeout=None):
    return sh(["ssh", "-o", f"ControlPath={C50_SOCK}", "-p", "22", C50, cmd], timeout=timeout)

def psql(sql, timeout=30):
    return ssh_db(f"sudo -n -u postgres psql -d scraper -tAF'|' -v ON_ERROR_STOP=1 -c {shlex.quote(sql)}", timeout=timeout)

def log(*a):
    print("[orch]", *a, flush=True)

def notify(msg):
    # best-effort, TAK PERNAH boleh gagalkan drain kalau Telegram/jaringan
    # bermasalah -- notifikasi ini pelengkap, bukan jalur kritis pipeline.
    # Hasil TETAP dilog (bukan cuma diam) supaya kegagalan kirim (mis.
    # kredensial belum diisi / API error) ketahuan dari log, bukan asumsi
    # "pasti terkirim" begitu saja.
    try:
        r = sh([TELEGRAM_SCRIPT, msg], timeout=15)
        if r.returncode == 0:
            log("  notify Telegram terkirim.")
        else:
            log("  (notify Telegram gagal, rc=%s):" % r.returncode, (r.stderr or r.stdout or "").strip()[:150])
    except Exception as e:
        log("  (notify Telegram gagal, exception):", repr(e)[:150])

def preflight():
    r = ssh_c50(f"curl -sf {ANALYZER}/healthz", timeout=20)
    if r.returncode != 0 or '"ok":true' not in r.stdout:
        log("ABORT: analyzer .50 tak healthy. Aktifkan .50 + jalankan bring-up-analyzer.sh dulu.")
        log("  ", (r.stdout or r.stderr).strip()[:200]); sys.exit(1)
    log("analyzer .50 healthy:", r.stdout.strip())
    r = psql("select 1")
    if r.returncode != 0 or r.stdout.strip() != "1":
        log("ABORT: DB-VPS tak terjangkau:", r.stderr.strip()[:200]); sys.exit(1)
    r = ssh_db(f"cd {DBVPS_TOOLS} && ls yt-dlp deno yt-cookies.txt fb-cookies.txt ig-cookies.txt >/dev/null 2>&1 && echo ok || echo MISSING")
    if r.stdout.strip() != "ok":
        log("ABORT: tools/cookies DB-VPS tak lengkap di", DBVPS_TOOLS); sys.exit(1)
    log("DB-VPS + tools OK.")

CLAIM_SQL = ("UPDATE media.video_ingest SET status='processing', claimed_at=now(), "
             "attempts=attempts+1, updated_at=now() WHERE id = ("
             "SELECT id FROM media.video_ingest WHERE status='pending' AND attempts < max_attempts "
             "ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1) "
             "RETURNING json_build_object('id',id,'category',category,"
             "'platform',coalesce(platform,''),'url',source_url)::text;")

def claim():
    r = psql(CLAIM_SQL)
    if r.returncode != 0:
        log("claim error:", r.stderr.strip()[:200]); return None
    for ln in r.stdout.splitlines():          # lewati tag perintah psql spt "UPDATE 0"
        ln = ln.strip()
        if ln.startswith("{"):                # baris job = JSON object (aman escaping)
            j = json.loads(ln)
            return {"id": int(j["id"]), "category": j["category"],
                    "platform": j["platform"], "url": j["url"]}
    return None

def fail_job(job, err):
    jid = job["id"]
    e = err.replace("'", "''")[:1000]
    # RETURNING status -> tahu di request YANG SAMA apakah job ini baru saja
    # mati permanen (dead) atau masih akan di-retry (pending), tanpa query
    # tambahan.
    r = psql("UPDATE media.video_ingest SET status = CASE WHEN attempts >= max_attempts THEN 'dead' "
             f"ELSE 'pending' END, last_error='{e}', updated_at=now() WHERE id={jid} RETURNING status;")
    # (2026-08-28) ketahuan live-test: stdout psql BUKAN cuma nilai RETURNING
    # ("dead"/"pending") -- ada baris tag perintah menyusul ("UPDATE 1"), jadi
    # 'pending\nUPDATE 1\n'. .strip() polos TAK PERNAH match persis "dead" --
    # notify() akibatnya tak pernah terpicu (bug diam, ketahuan krn ada log
    # eksplisit di notify() sendiri, bukan krn ada error). Ambil baris
    # PERTAMA saja, pola sama spt claim() yg sudah lama tahu soal ini.
    lines = (r.stdout or "").strip().splitlines()
    status = lines[0].strip() if lines else ""
    if status == "dead":
        notify(f"⚠️ viral-pipeline: job #{jid} MATI PERMANEN (habis retry) -- "
               f"{job.get('platform','?')}/{job.get('category','?')} {job.get('url','')[:200]}\n"
               f"Error terakhir: {err[:300]}")

def download(job):
    cookie = COOKIES.get(job["platform"])
    if not cookie:
        return None, f"platform tak didukung: {job['platform']}"
    jid, url = job["id"], job["url"]
    # --write-info-json (2026-10-17): sidecar job-<id>.info.json berisi 'title'
    # asli -- dipakai nama file raw-footage Gdrive (fetch_title()). Filter file
    # hasil WAJIB buang .info.json juga (bukan cuma .log), krn urut alfabet
    # ".info.json" < ".mp4" -- tanpa itu `head -1` salah ambil sidecar JSON,
    # bukan video, sbg "path video".
    cmd = (f"cd {DBVPS_TOOLS} && mkdir -p work && rm -f work/job-{jid}.* && "
           f'PATH="$PWD:$PATH" ./yt-dlp --cookies {cookie} --no-playlist --write-info-json '
           f"-o 'work/job-{jid}.%(ext)s' {shlex.quote(url)} >work/job-{jid}.log 2>&1 && "
           f"ls work/job-{jid}.* | grep -v '\\.log$' | grep -v '\\.info\\.json$' | head -1")
    r = ssh_db(cmd, timeout=600)
    if r.returncode != 0 or not r.stdout.strip():
        tail = ssh_db(f"tail -3 {DBVPS_WORK}/job-{jid}.log 2>/dev/null").stdout.strip()
        return None, f"download gagal: {tail[:400]}"
    return r.stdout.strip().splitlines()[-1], None   # path relatif (work/job-<id>.ext)


def fetch_title(job, dbvps_relpath):
    """Judul asli video (sidecar .info.json yg ditulis yt-dlp di download()) --
    utk nama file raw-footage Gdrive. Best-effort PENUH: gagal baca/parse ->
    string kosong (safe_name() punya fallback 'untitled'), TAK PERNAH
    menggagalkan job -- judul cuma kosmetik nama file, bukan data kritis."""
    info_path = re.sub(r"\.[^.]+$", ".info.json", dbvps_relpath)
    try:
        r = ssh_db(f"cd {DBVPS_TOOLS} && cat {shlex.quote(info_path)} 2>/dev/null", timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout).get("title") or ""
    except Exception:
        pass
    return ""

def stream_to_c50(job, dbvps_relpath):
    jid = job["id"]
    ext = dbvps_relpath.rsplit(".", 1)[-1]
    dest = f"{C50_INPUT}/job-{jid}.{ext}"
    # cd dulu (tilde tanpa kutip -> expand), lalu cat path relatif (aman dikutip)
    p1 = subprocess.Popen(["ssh", DBVPS, f"cd {DBVPS_TOOLS} && cat {shlex.quote(dbvps_relpath)}"], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["ssh", "-o", f"ControlPath={C50_SOCK}", "-p", "22", C50,
                           f"mkdir -p {C50_INPUT} && cat > {dest}"], stdin=p1.stdout)
    p1.stdout.close(); p2.communicate(); p1.wait()
    if p1.returncode != 0 or p2.returncode != 0:
        return None, "stream DB-VPS->.50 gagal"
    return f"/data/input/job-{jid}.{ext}", None       # path DI DALAM container analyzer

def analyze(container_path):
    payload = json.dumps({"video_path": container_path})
    cmd = (f"curl -s --max-time {ANALYZE_TIMEOUT} -X POST {ANALYZER}/analyze "
           f"-H 'Content-Type: application/json' -d {shlex.quote(payload)}")
    r = ssh_c50(cmd, timeout=ANALYZE_TIMEOUT + 60)
    if r.returncode != 0:
        return None, f"curl analyze gagal (rc={r.returncode}): {(r.stderr or r.stdout).strip()[:200]}"
    try:
        data = json.loads(r.stdout)
    except Exception:
        return None, f"respons bukan JSON: {r.stdout[:200]}"
    if "analysis" not in data or data.get("status") not in ("ok", "deterministic_only"):
        return None, f"analisa gagal: {json.dumps(data)[:300]}"
    return data, None

def write_result(job, data):
    jid = job["id"]
    ver = str(data.get("analyzer_version", "0.1.0")).replace("'", "''")[:32]
    aj  = json.dumps(data["analysis"], separators=(",", ":"))   # minified, satu baris
    sql = (
        "INSERT INTO media.video_analysis (ingest_id, category, platform, source_url, analyzer_ver, analysis)\n"
        f"SELECT id, category, platform, source_url, '{ver}', $vaj${aj}$vaj$::jsonb\n"
        f"FROM media.video_ingest WHERE id={jid};\n"
        f"UPDATE media.video_ingest SET status='analyzed', analyzed_at=now(), updated_at=now() WHERE id={jid};\n"
    )
    subprocess.run(["ssh", DBVPS, f"cat > /tmp/vaj-{jid}.sql"], input=sql, text=True)
    r = ssh_db(f"sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -f /tmp/vaj-{jid}.sql; rc=$?; rm -f /tmp/vaj-{jid}.sql; exit $rc", timeout=30)
    if r.returncode != 0:
        return f"tulis hasil gagal: {r.stderr.strip()[:300]}"
    return None

def build_reproduction(job, analysis):
    """Panggil ir_to_vn.py LOKAL (akses-vps) supaya tiap job SEKALIAN
    hasilkan cetak-biru reproduksi VN (.srt/.vn-blueprint.json/.cutlist.txt/
    .vn-recipe.md/.segments.json/.story-script.md) -- bukan cuma tersimpan
    di DB. Best-effort: job SUDAH 'analyzed' di DB sebelum fungsi ini
    dipanggil (lihat main()) -- kalau ir_to_vn.py gagal (mis. IR versi lama
    kurang field), itu TAK BOLEH menggagalkan job yg sudah sukses, cuma
    log peringatan & job kehilangan bonus reproduksi kali ini saja."""
    jid = job["id"]
    outdir = os.path.join(REPRO_DIR, f"job-{jid}")
    base = os.path.join(outdir, f"job-{jid}")
    try:
        os.makedirs(outdir, exist_ok=True)
        with open(base + ".ir.json", "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"  (build_reproduction: gagal tulis IR lokal, dilewati):", repr(e)[:150])
        return None
    r = sh_safe(["python3", IR_TO_VN, base + ".ir.json", "--out", base], timeout=60)
    if r.returncode != 0:
        log(f"  (ir_to_vn.py gagal utk job {jid}, analisa TETAP tersimpan di DB, cuma bonus reproduksi dilewati):",
            (r.stderr or r.stdout or "").strip()[:250])
        return None
    log(f"  reproduksi VN (story-script + blueprint) tersimpan: {outdir}/")
    return outdir

def _last_line(r):
    lines = [ln.strip() for ln in (r.stderr or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""

def fetch_and_push_footage(job, outdir):
    """(2026-08-29, Jalur C permintaan user "otomatis") Sekalian sumber-kan
    footage stok MENTAH per babak (Pexels + Pixabay, dua provider = lebih
    banyak kandidat klip per babak) & kirim ke Gdrive gfootage:RAW-VIDEO/
    job-<id>/ -- bahan baku siap diedit manual bebas oleh user sendiri
    (dipandu editor.obc-crypto.com/.story-script.md), BEDA dari
    build_reproduction() (itu bikin cetak-biru utk edit OTOMATIS/VN-HP).
    Best-effort PENUH sama spt build_reproduction(): job SUDAH 'analyzed' di
    DB sebelum dipanggil, kegagalan di sini TAK PERNAH menggagalkan job."""
    jid = job["id"]
    base = os.path.join(outdir, f"job-{jid}")
    blueprint = base + ".vn-blueprint.json"
    if not os.path.isfile(blueprint):
        log(f"  (footage: {os.path.basename(blueprint)} tak ada, dilewati)")
        return

    plans = []
    for name, script in (("pexels", PEXELS_FETCH), ("pixabay", PIXABAY_FETCH)):
        r = sh_safe(["python3", script, blueprint], timeout=FOOTAGE_TIMEOUT)
        plan_path = f"{base}.{name}-plan.json"
        if r.returncode == 0 and os.path.isfile(plan_path):
            plans.append(plan_path)
            log(f"  footage {name}: {_last_line(r)[:150]}")
        else:
            log(f"  (footage {name}: gagal/skip, rc={r.returncode}):",
                (_last_line(r) or r.stdout or "")[-200:])

    if not plans:
        log("  (footage: tak ada plan yg berhasil, push ke Gdrive dilewati)")
        return

    r = sh_safe(["python3", PUSH_RAW_FOOTAGE] + plans, timeout=FOOTAGE_TIMEOUT)
    if r.returncode != 0:
        log("  (footage: push_raw_footage.py gagal, klip TETAP lokal di hub, tak sampai Gdrive):",
            (_last_line(r) or r.stdout or "")[-200:])
    else:
        log(f"  footage -> gfootage:RAW-VIDEO/job-{jid}/ :", _last_line(r)[:150])

def disk_avail_mb(path="/"):
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize // (1024 * 1024)
    except Exception:
        return 0


def safe_name(title, url):
    """'<judul> [<url-lengkap>]' jadi SATU nama file flat. URL mentah punya
    '/' yg akan disalahartikan rclone sbg pemisah folder kalau tak disanitasi
    -- diganti '_'. Judul dibersihkan dr karakter terlarang filesystem supaya
    aman kalau nanti disalin keluar Gdrive (mis. backup ke SSD lokal)."""
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", (title or "")).strip()
    t = re.sub(r"\s+", " ", t)[:120] or "untitled"
    u = re.sub(r"^https?://", "", url or "").rstrip("/")
    u = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", u)[:150]
    return f"{t} [{u}]"


def pull_from_dbvps(remote_relpath, local_path, timeout=300):
    """Tarik SATU file biner DB-VPS -> hub (beda dr stream_to_c50 yg pipe ke
    .50): sengaja mendarat di disk hub sebentar krn ffmpeg+rclone+kredensial
    gfootage: cuma ada di sini (lihat audit 17/10 -- DB-VPS/.50 nol keduanya)."""
    try:
        with open(local_path, "wb") as f:
            r = subprocess.run(["ssh", DBVPS, f"cd {DBVPS_TOOLS} && cat {shlex.quote(remote_relpath)}"],
                               stdout=f, stderr=subprocess.PIPE, timeout=timeout)
        return r.returncode == 0, (r.stderr or b"").decode(errors="replace").strip()[:300]
    except Exception as e:
        return False, repr(e)[:300]


def ffmpeg_run(args, timeout=180):
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stderr or "").strip()[:300]
    except Exception as e:
        return False, repr(e)[:300]


def rclone_push(local_path, remote_dir, remote_name, timeout=180):
    try:
        r = subprocess.run(["rclone", "copyto", local_path, remote_dir + remote_name],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stderr or r.stdout).strip()[:300]
    except Exception as e:
        return False, repr(e)[:300]


def split_and_push_raw(job, dbvps_relpath, title):
    """(2026-10-17, permintaan user) video TANPA audio (-c:v copy, nol re-
    encode -- 'raw' = codec asli dipertahankan) -> MKV, audio-only (-c:a copy)
    -> MKA (kontainer Matroska dipilih krn fleksibel: nampung codec apa pun
    [h264/vp9/aac/opus/...] tanpa transcode, beda dr memaksa .mp4/.m4a yg bisa
    gagal mux utk source tertentu), + 1 thumbnail representatif (filter
    `thumbnail`, bukan frame fixed -- hindari frame hitam/transisi) -> JPG.
    Nama file SAMA utk ketiganya: '<judul> [<url>].<ext>' (permintaan user).
    Best-effort PENUH (pola sama build_reproduction()/fetch_and_push_footage()):
    job SUDAH 'analyzed' sebelum dipanggil, kegagalan di SINI (ffmpeg/rclone/
    disk penuh/exception apa pun) TAK PERNAH menggagalkan job -- fungsi ini
    TAK PERNAH raise ke pemanggil."""
    jid = job["id"]
    # didefinisikan DULUAN (bukan di tengah try) supaya finally selalu punya
    # 4 nama path yg konsisten utk dibersihkan, apa pun titik return/exception
    # di bawah -- tanpa ini, cleanup jadi rawan NameError/path salah.
    ext = os.path.splitext(dbvps_relpath)[1] or ".mp4"
    src = os.path.join(RAW_WORKDIR, f"job-{jid}{ext}")
    out_v = os.path.join(RAW_WORKDIR, f"job-{jid}.video.mkv")
    out_a = os.path.join(RAW_WORKDIR, f"job-{jid}.audio.mka")
    out_t = os.path.join(RAW_WORKDIR, f"job-{jid}.thumb.jpg")
    try:
        if disk_avail_mb() < RAW_MIN_DISK_MB:
            log(f"  (raw-footage: disk hub <{RAW_MIN_DISK_MB}MB, dilewati)")
            return
        os.makedirs(RAW_WORKDIR, exist_ok=True)
        name = safe_name(title, job.get("url"))

        ok, err = pull_from_dbvps(dbvps_relpath, src)
        if not ok:
            log("  (raw-footage: tarik file dr DB-VPS gagal):", err)
            return

        pushed = []
        for key, args, out, remote_ext in (
            ("video", ["-i", src, "-an", "-c:v", "copy", out_v], out_v, ".mkv"),
            ("audio", ["-i", src, "-vn", "-c:a", "copy", out_a], out_a, ".mka"),
            ("thumb", ["-i", src, "-vf", "thumbnail", "-frames:v", "1", out_t], out_t, ".jpg"),
        ):
            ok, err = ffmpeg_run(args)
            if not ok:
                log(f"  (raw-footage: ffmpeg {key} gagal):", err)
                continue
            ok, err = rclone_push(out, GFOOTAGE[key], name + remote_ext)
            if ok:
                pushed.append(key)
            else:
                log(f"  (raw-footage: push {key} gagal):", err)

        log(f"  raw-footage: {len(pushed)}/3 ter-upload ({','.join(pushed) or '-'}) -> gfootage: \"{name}\"")
    except Exception as e:
        log("  (raw-footage: exception, dilewati):", repr(e)[:200])
    finally:
        for p in (src, out_v, out_a, out_t):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            except Exception as e:
                log(f"  (raw-footage: gagal hapus temp {p}):", repr(e)[:100])


def cleanup(jid):
    ssh_db(f"rm -f {DBVPS_WORK}/job-{jid}.*")
    ssh_c50(f"rm -f {C50_INPUT}/job-{jid}.*")

def main():
    preflight()
    done = ok = fail = 0
    while not (MAX_JOBS and done >= MAX_JOBS):
        job = claim()
        if not job:
            log("antrean habis." if done else "antrean kosong."); break
        done += 1
        log(f"[job {job['id']}] {job['platform']}/{job['category']} {job['url'][:60]}")
        try:
            relpath, err = download(job)
            if err:
                log("  x download:", err); fail_job(job, err); fail += 1; continue
            log("  downloaded:", relpath)
            title = fetch_title(job, relpath)   # best-effort, boleh kosong ("")
            cpath, err = stream_to_c50(job, relpath)
            if err:
                log("  x stream:", err); fail_job(job, err); cleanup(job["id"]); fail += 1; continue
            data, err = analyze(cpath)
            if err:
                log("  x analyze:", err); fail_job(job, err); cleanup(job["id"]); fail += 1; continue
            werr = write_result(job, data)
            if werr:
                log("  x write:", werr); fail_job(job, werr); cleanup(job["id"]); fail += 1; continue
            outdir = build_reproduction(job, data["analysis"])   # best-effort, tak pernah gagalkan job
            if outdir:
                fetch_and_push_footage(job, outdir)              # best-effort, tak pernah gagalkan job
            split_and_push_raw(job, relpath, title)              # best-effort, tak pernah gagalkan job
            cleanup(job["id"])
            ok += 1
            sc = len(data["analysis"].get("scene_analysis", []))
            log(f"  OK: status={data['status']} scenes={sc} bpm={data['analysis'].get('bpm')}")
        except Exception as e:
            # TimeoutExpired dll TAK boleh crash seluruh drain + menyangkutkan job di 'processing'
            log("  x exception:", repr(e)[:200]); fail_job(job, f"exception: {e}"[:800]); cleanup(job["id"]); fail += 1; continue
    log(f"SELESAI: {ok} sukses, {fail} gagal, {done} diproses.")

if __name__ == "__main__":
    main()
