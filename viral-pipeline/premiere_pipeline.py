#!/usr/bin/env python3
"""
premiere_pipeline.py — tutup 2 celah manual pipeline publish Go Go Bud
(lihat memory project_medsos_agent.md, entri 2026-10-14 "PETA LENGKAP"):
  1. Gdrive VN-exports/ -> ig-media/ (copy file, dulu scp/cp manual)
  2. ig-media/ -> update field workflow n8n -> fire webhook (dulu PUT
     manual tiap video baru)

ALUR: scan (cron, aman/tanpa publish) -> stage ke ig-media/ + notifikasi
Telegram -> approve MANUAL (user/Claude kasih caption + --go) -> publish
nyata ke IG Reel + FB Reel.

KELUAR LINGKUP SENGAJA -- IG Carousel: workflow itu butuh SET aset
terkurasi (1 video + beberapa slide gambar + caption per-post), bukan 1
video auto-detect -- strukturnya tak cocok model trigger "video baru ->
auto" yang sama persis. Tetap manual seperti sebelumnya (PUT mediaUrls
sendiri kalau perlu).

Caption SENGAJA TIDAK di-auto-generate -- kualitas editorial perlu
manusia, wajib disuplai saat approve (bukan placeholder generik).

Subcommand:
  scan                        - cron entrypoint: deteksi+stage+notify
  list                        - tampilkan status semua entri state
  approve <name> <caption>    - update 2 workflow n8n + fire webhook
                                 (DRY-RUN default, --go utk eksekusi nyata)
  skip <name>                 - tandai dilewati (tak dinotif ulang)

Reuse FAKTA TERVERIFIKASI (jangan tebak ulang):
  - Field 'Konfigurasi'.videoUrl (IG Reel) & .caption/.fileSize/.videoState
    (FB Reel) -- struktur node 'set', assignments[] {name,value}.
  - Node 'Gdrive: download video' (FB Reel) BUKAN gdriveFileId beneran --
    itu httpRequest node, url-nya HARDCODE ke media.obc-crypto.com/<file>,
    field gdriveFileId di Konfigurasi VESTIGIAL/tak dipakai jalur asli.
  - PUT /api/v1/workflows/{id} body HARUS cuma {name,nodes,connections,
    settings} (buang active/id/tags, atau API menolak).
  - activate/deactivate workflow TIDAK disentuh skrip ini (tetap gated,
    user jalankan via ! sekali di awal kalau belum aktif).
"""
import argparse, json, os, subprocess, sys, time
import urllib.request, urllib.error

HOME = os.path.expanduser("~")
STATE_DIR = f"{HOME}/.config/premiere-pipeline"
STATE_FILE = f"{STATE_DIR}/state.json"
REMOTE = "gfootage:VN-exports/"
IGMEDIA_DIR = f"{HOME}/akses-vps/nginx/dashboards/ig-media"
MEDIA_BASE = "https://media.obc-crypto.com"
TELEGRAM_SH = f"{HOME}/akses-vps/backup/send-telegram.sh"

N8N_BASE = "http://10.122.31.254:5678"
N8N_APIKEY_FILE = f"{HOME}/.config/n8n-gogobuda/api-key.json"
IG_REEL_WF, IG_REEL_HOOK = "h4YUhSXfOMNrO6qc", "ig-reel-run"
FB_REEL_WF, FB_REEL_HOOK = "dzpcInyH7wgRAuOO", "fb-reel-run"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def load_state():
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(d):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def rclone_lsjson(remote):
    # (2026-10-16 fix) gfootage: pakai shared/retiring Google Drive client_id
    # rclone -> sering kena RATE_LIMIT_EXCEEDED dari Google, dan pacer rclone
    # otomatis backoff-retry (terukur 16-18s sekali kena) SEBELUM akhirnya
    # berhasil sendiri. timeout=30 lama TERBUKTI motong di tengah retry itu
    # (2x berturut gagal saat cron, padahal re-run manual < 1 menit kemudian
    # selalu sukses) -> dinaikkan ke 90s (margin di atas backoff terukur,
    # TANPA bikin scan jadi sungguhan macet lama krn kasus normal tetap <2s).
    # Exception DITANGKAP di sini (bukan dibiarkan traceback) krn ini kondisi
    # TRANSIENT yg akan sembuh sendiri di tick cron berikutnya (*/15menit) --
    # bukan error yg perlu menghentikan proses/menumpuk traceback di log.
    try:
        r = subprocess.run(["rclone", "lsjson", remote], capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        log("rclone lsjson TIMEOUT 90s (kemungkinan rate-limit Google Drive shared client_id) -- lewati, coba lagi tick berikutnya.")
        return []
    if r.returncode != 0:
        log(f"rclone lsjson GAGAL: {r.stderr.strip()[:200]}")
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        log(f"rclone lsjson output tak valid JSON: {r.stdout[:200]}")
        return []


def telegram(msg):
    try:
        subprocess.run([TELEGRAM_SH, msg], timeout=20, capture_output=True)
    except Exception as e:
        log(f"WARN telegram gagal: {e}")


def n8n_apikey():
    with open(N8N_APIKEY_FILE) as f:
        return json.load(f)["apiKey"]


def n8n_get(wf):
    req = urllib.request.Request(f"{N8N_BASE}/api/v1/workflows/{wf}",
                                  headers={"X-N8N-API-KEY": n8n_apikey()})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def n8n_put(wf, data):
    body = json.dumps({
        "name": data["name"], "nodes": data["nodes"],
        "connections": data["connections"], "settings": data.get("settings", {}),
    }).encode()
    req = urllib.request.Request(f"{N8N_BASE}/api/v1/workflows/{wf}", data=body, method="PUT",
                                  headers={"X-N8N-API-KEY": n8n_apikey(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def n8n_fire(path):
    req = urllib.request.Request(f"{N8N_BASE}/webhook/{path}", data=b"{}", method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return -1, str(e)


def set_assignment(wf_json, node_name, field, value):
    for n in wf_json["nodes"]:
        if n["name"] == node_name:
            for a in n["parameters"]["assignments"]["assignments"]:
                if a["name"] == field:
                    a["value"] = value
                    return True
    return False


def set_param(wf_json, node_name, param_key, value):
    for n in wf_json["nodes"]:
        if n["name"] == node_name:
            n["parameters"][param_key] = value
            return True
    return False


# ---------------------------------------------------------------------
def cmd_scan(args):
    state = load_state()
    files = [f for f in rclone_lsjson(REMOTE) if not f.get("IsDir") and f["Name"].lower().endswith((".mp4", ".mov"))]
    new = [f for f in files if f["Name"] not in state]
    if not new:
        log("tak ada video baru.")
        return 0
    for f in new:
        name = f["Name"]
        log(f"video baru: {name} ({f['Size']} bytes)")
        local_tmp = f"/tmp/premiere-stage-{name}"
        r = subprocess.run(["rclone", "copyto", f"{REMOTE}{name}", local_tmp],
                            capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            log(f"  GAGAL copy dari Gdrive: {r.stderr.strip()[:200]}")
            continue
        os.makedirs(IGMEDIA_DIR, exist_ok=True)
        dest = f"{IGMEDIA_DIR}/{name}"
        os.replace(local_tmp, dest)
        media_url = f"{MEDIA_BASE}/{name}"
        state[name] = {
            "status": "staged", "media_url": media_url, "size": f["Size"],
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        save_state(state)
        telegram(
            "\U0001F3AC Video baru ter-stage utk publish Go Go Bud:\n"
            f"{name}\n{media_url}\n\n"
            "Siapkan caption lalu jalankan (via Claude/terminal):\n"
            f'premiere_pipeline.py approve "{name}" "<caption>" --go\n\n'
            "(IG Carousel TIDAK termasuk -- tetap manual, butuh beberapa aset per-post.)"
        )
        log(f"  staged -> {media_url}, notifikasi Telegram terkirim.")
    return 0


def cmd_list(args):
    state = load_state()
    if not state:
        print("(kosong)")
        return 0
    for name, e in sorted(state.items(), key=lambda kv: kv[1].get("staged_at", "")):
        print(f"{e.get('status', '?'):10} {name:40} {e.get('media_url', '')}")
    return 0


def cmd_skip(args):
    state = load_state()
    if args.name not in state:
        print(f"'{args.name}' tak ada di state.")
        return 1
    state[args.name]["status"] = "skipped"
    save_state(state)
    print(f"'{args.name}' ditandai skipped.")
    return 0


def cmd_approve(args):
    state = load_state()
    entry = state.get(args.name)
    if not entry:
        print(f"'{args.name}' tak ditemukan di state (jalankan 'scan' dulu, atau cek 'list').")
        return 1
    media_url = entry["media_url"]
    size = entry["size"]
    caption = args.caption

    print(f"=== Rencana publish '{args.name}' ===")
    print(f"  media_url : {media_url}")
    print(f"  fileSize  : {size}")
    print(f"  caption   : {caption[:80]}{'...' if len(caption) > 80 else ''}")
    print(f"  target    : IG Reel ({IG_REEL_HOOK}) + FB Reel ({FB_REEL_HOOK})")
    if not args.go:
        print("\n[DRY-RUN] Tak ada yang diubah/dipublish. Tambahkan --go utk eksekusi nyata.")
        return 0

    wf = n8n_get(IG_REEL_WF)
    set_assignment(wf, "Konfigurasi", "videoUrl", media_url)
    set_assignment(wf, "Konfigurasi", "caption", caption)
    n8n_put(IG_REEL_WF, wf)
    print("IG Reel: Konfigurasi di-update.")

    wf2 = n8n_get(FB_REEL_WF)
    set_assignment(wf2, "Konfigurasi", "caption", caption)
    set_assignment(wf2, "Konfigurasi", "fileSize", size)
    set_assignment(wf2, "Konfigurasi", "videoState", "PUBLISHED")
    set_param(wf2, "Gdrive: download video", "url", media_url)
    n8n_put(FB_REEL_WF, wf2)
    print("FB Reel: Konfigurasi + node unduh di-update.")

    code1, body1 = n8n_fire(IG_REEL_HOOK)
    print(f"IG Reel webhook fired: HTTP {code1} {body1[:120]}")
    code2, body2 = n8n_fire(FB_REEL_HOOK)
    print(f"FB Reel webhook fired: HTTP {code2} {body2[:120]}")

    entry["status"] = "published"
    entry["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry["caption"] = caption
    save_state(state)

    telegram(
        f"✅ Dipublish: {args.name}\nIG Reel webhook: HTTP {code1}\nFB Reel webhook: HTTP {code2}\n"
        "Cek manual akun Go Go Bud utk konfirmasi tayang (verifikasi Graph API, jangan percaya status webhook saja)."
    )
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    sub.add_parser("list")
    p_skip = sub.add_parser("skip")
    p_skip.add_argument("name")
    p_appr = sub.add_parser("approve")
    p_appr.add_argument("name")
    p_appr.add_argument("caption")
    p_appr.add_argument("--go", action="store_true")
    args = ap.parse_args()
    fn = {"scan": cmd_scan, "list": cmd_list, "skip": cmd_skip, "approve": cmd_approve}[args.cmd]
    if args.cmd == "scan":
        # cron tiap 15mnt, tanpa pengawasan -- jangan biarkan exception tak
        # terduga (network/API eksternal apa pun) jadi traceback mentah di
        # log; cukup WARN, tick berikutnya coba lagi sendiri.
        try:
            sys.exit(fn(args) or 0)
        except Exception as e:
            log(f"WARN scan gagal tak terduga: {e}")
            sys.exit(0)
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
