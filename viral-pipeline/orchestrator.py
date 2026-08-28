#!/usr/bin/env python3
"""orchestrator.py — pipeline video viral ON-DEMAND (jalan di akses-vps).

Kuras antrean `media.video_ingest` (DB-VPS). Per job:
  claim (FOR UPDATE SKIP LOCKED) -> download di DB-VPS (yt-dlp, cookies per platform)
  -> stream video DB-VPS->.50 via pipe (TAK mendarat di disk akses-vps)
  -> POST /analyze di .50 -> tulis media.video_analysis (+category, JSON dollar-quote)
  -> status 'analyzed' -> hapus video 2 sisi.
Gagal di langkah mana pun -> status 'pending' (retry) / 'dead' (habis) + last_error.

Prasyarat runtime: user aktifkan .50 + analyzer healthy (bring-up-analyzer.sh);
DB-VPS reachable; cookies+yt-dlp+deno di DB-VPS ~/viral-pipeline/.
Env: MAX_JOBS=N (0=kuras semua, default 0).
"""
import subprocess, json, sys, os, shlex

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
# (2026-08-28) celah #3 audit otomatisasi: job yg gagal permanen ('dead' stlh
# max_attempts habis) dulu diam total di DB, tak ada yg tahu kecuali cek
# manual -- beda dgn wake-orchestrator.sh yg SELALU notify Telegram. Fix:
# reuse helper yg sama (send-telegram.sh, no-op anggun kalau kredensial
# belum diisi -- lihat isi skrip itu).
TELEGRAM_SCRIPT = os.path.expanduser("~/akses-vps/backup/send-telegram.sh")

def sh(args, inp=None, timeout=None):
    return subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)

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
    cmd = (f"cd {DBVPS_TOOLS} && mkdir -p work && rm -f work/job-{jid}.* && "
           f'PATH="$PWD:$PATH" ./yt-dlp --cookies {cookie} --no-playlist '
           f"-o 'work/job-{jid}.%(ext)s' {shlex.quote(url)} >work/job-{jid}.log 2>&1 && "
           f"ls work/job-{jid}.* | grep -v '\\.log$' | head -1")
    r = ssh_db(cmd, timeout=600)
    if r.returncode != 0 or not r.stdout.strip():
        tail = ssh_db(f"tail -3 {DBVPS_WORK}/job-{jid}.log 2>/dev/null").stdout.strip()
        return None, f"download gagal: {tail[:400]}"
    return r.stdout.strip().splitlines()[-1], None   # path relatif (work/job-<id>.ext)

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
            cpath, err = stream_to_c50(job, relpath)
            if err:
                log("  x stream:", err); fail_job(job, err); cleanup(job["id"]); fail += 1; continue
            data, err = analyze(cpath)
            if err:
                log("  x analyze:", err); fail_job(job, err); cleanup(job["id"]); fail += 1; continue
            werr = write_result(job, data)
            if werr:
                log("  x write:", werr); fail_job(job, werr); cleanup(job["id"]); fail += 1; continue
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
