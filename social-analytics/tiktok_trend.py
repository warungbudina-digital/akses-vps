#!/usr/bin/env python3
"""Riset tren TikTok: pantau watchlist kreator niche, simpan statistik ke DB-VPS.

Otak di hub (akses-vps), mesin browser = Chromium container di Cloud Shell
balibruntattour (.60) lewat full-tool-browser API. Hasil ke DB-VPS schema
`trend` (lihat tiktok_trend_schema.sql) supaya tetap ada walau VM .60 recycle.

Jalur data (hasil uji 2026-09-25 dari IP Cloud Shell, pengunjung anonim):
  - /tag/ & /discover/        → ditolak ("Something went wrong") → tak dipakai
  - halaman profil /@handle   → info user ada, TAPI daftar video memicu CAPTCHA
  - widget embed /embed/@handle → info user + ±13 video (3 populer + 10 terbaru),
                                  TANPA CAPTCHA → dipakai utk profil & daftar video
  - halaman video             → statistik lengkap (SSR) → dipakai per video
Kandidat akun baru = akun yg di-@mention di caption (sinyal kolaborasi).

Volume sengaja rendah + jeda acak. Begitu CAPTCHA terlihat, run BERHENTI
(tak dipaksa) dan tercatat `captcha`.

Pakai:
  tiktok_trend.py                    # run normal (dipanggil cron)
  tiktok_trend.py --dry-run          # ambil data, cetak, TANPA tulis DB
  tiktok_trend.py --only tommythings # batasi ke satu handle
  tiktok_trend.py --check @handle    # cek akun (pengikut, bio, bahasa) sebelum masuk watchlist
Exit: 0 ok / dilewati krn .60 mati · 2 dihentikan CAPTCHA · 1 semua gagal.
"""
import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(HERE, "tiktok_watchlist.json")
CRED = os.path.expanduser("~/.config/browser-api/credentials.env")
API = os.environ.get("TREND_BROWSER_API", "http://10.66.66.60:8080")
PROFILE = os.environ.get("TREND_BROWSER_PROFILE", "pool-3")
DB_CMD = ["ssh", "-o", "BatchMode=yes", "db-vps",
          "sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -q -f -"]

# ── JS yg dievaluasi di halaman ──────────────────────────────────────────────
JS_CAPTCHA = r"""(txt) => /Drag the slider|fit the puzzle|Verify to continue/i.test(txt || '')
  || !!document.querySelector('#captcha-verify-container, .captcha_verify_container')"""

JS_EMBED = r"""() => {
  const txt = document.body ? document.body.innerText : '';
  const captcha = (%s)(txt);
  let d = null;
  try {
    const src = JSON.parse(document.getElementById('__FRONTITY_CONNECT_STATE__').textContent).source.data;
    const key = Object.keys(src).find(k => k.indexOf('/embed/@') === 0);
    d = key ? src[key] : null;
  } catch (e) {}
  const u = d && !d.isError && d.userInfo ? d.userInfo : null;  // akun tak ada → isError:true, userInfo cuma {uniqueId}
  return {
    captcha, isError: d ? d.isError : null,
    user: u ? { handle: u.uniqueId, nickname: u.nickname, bio: u.signature,
                followers: u.followerCount, following: u.followingCount,
                likes: u.heartCount, isPrivate: u.privateAccount, code: u.code } : null,
    videos: ((d && d.videoList) || []).map(v => ({ id: v.id, plays: v.playCount })),
    head: txt.slice(0, 200),
  };
}""" % JS_CAPTCHA

JS_VIDEO = r"""() => {
  const txt = document.body ? document.body.innerText : '';
  const captcha = (%s)(txt);
  try {
    const scope = JSON.parse(document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__').textContent).__DEFAULT_SCOPE__ || {};
    const d = scope['webapp.video-detail'];
    const it = d && d.itemInfo && d.itemInfo.itemStruct;
    if (!it) return { captcha, err: /not available in your country|isn.t available in your/i.test(txt)
                      ? 'diblokir di wilayah IP .60 (Singapura)' : 'no itemStruct', statusCode: d ? d.statusCode : null };
    const st = it.statsV2 || it.stats || {};
    const extra = it.textExtra || [];
    return {
      captcha, id: it.id, author: it.author && it.author.uniqueId, desc: it.desc,
      createTime: Number(it.createTime) || null,
      duration: it.video && it.video.duration, music: it.music && it.music.title,
      isPhoto: !!it.imagePost, nImages: it.imagePost ? (it.imagePost.images || []).length : null,
      tags: extra.map(t => t.hashtagName).filter(Boolean),
      mentions: extra.map(t => t.userUniqueId).filter(Boolean),
      plays: st.playCount, likes: st.diggCount, comments: st.commentCount,
      shares: st.shareCount, saves: st.collectCount,
    };
  } catch (e) { return { captcha, err: String(e) }; }
}""" % JS_CAPTCHA


class Captcha(Exception):
    pass


def log(msg):
    print(f"[tiktok-trend {dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {msg}", flush=True)


def load_key():
    key = os.environ.get("BROWSER_API_KEY")
    if not key and os.path.exists(CRED):
        for line in open(CRED):
            if line.startswith("BROWSER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"\'')
    if not key:
        sys.exit("BROWSER_API_KEY tak ditemukan")
    return key


class Browser:
    def __init__(self, key):
        self.key = key

    def _call(self, method, path, body=None, timeout=60):
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def healthy(self):
        try:
            return self._call("GET", "/health", timeout=10).get("ok") is True
        except Exception:
            return False

    def request_path_ok(self):
        """Deteksi dini masalah MTU hub→.60: body >~1.3KB menggantung selamanya
        kalau rute 10.66.66.60 belum dipasangi mtu 1380 (lihat README)."""
        try:
            fn = "() => { " + " " * 2000 + "return 1; }"
            res = self._call("POST", "/browser/request",
                             {"profile": PROFILE, "action": "act",
                              "request": {"kind": "evaluate", "fn": fn}}, timeout=15)
            return res.get("result") == 1
        except Exception:
            return False

    def navigate(self, url, ready_fn):
        """Buka url lalu TUNGGU sampai `ready_fn` (JS) benar — bukan jeda tetap.
        Jeda tetap pernah membaca halaman SEBELUMNYA (data akun lain tercatat ke
        handle yg salah). ready_fn wajib memastikan URL sudah cocok target."""
        try:
            res = self._call("POST", "/browser/request",
                             {"profile": PROFILE, "action": "navigate", "url": url})
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": f"navigate HTTP {e.code}"}
        # TikTok kadang redirect/navigasi internal saat memuat → Playwright melempar
        # ("execution context destroyed") dan API membalas 500 walau halaman lalu
        # termuat normal (diuji 25/9). Jadi `wait` diulang, bukan langsung gagal.
        err = None
        for _ in range(3):
            try:
                self._call("POST", "/browser/request",
                           {"profile": PROFILE, "action": "act",
                            "request": {"kind": "wait", "fn": ready_fn, "timeoutMs": 15000}}, timeout=30)
                err = None
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:160]}"
            except Exception as e:
                err = str(e)
            time.sleep(3)
        if err:
            return {"ok": False, "error": f"halaman tak siap: {err}"}
        time.sleep(2)  # beri waktu hidrasi state
        return res

    def quiet(self):
        """Hentikan & kosongkan <video> di halaman: data yg diambil cuma JSON di HTML,
        sedangkan video autoplay memakan CPU .60 (2 vCPU). (Diuji 25/9: blokir resource
        via API tak bisa — requestSchema HTTP membuang field `types`.)"""
        try:
            self.evaluate("() => { document.querySelectorAll('video,audio').forEach(v => "
                          "{ try { v.pause(); v.removeAttribute('src'); v.load(); } catch (e) {} }); return 1; }")
        except Exception:
            pass

    def park(self):
        """Akhir run: tab ke about:blank. Semua profil remote-cdp BERBAGI halaman yg
        sama, dan tab TikTok yg ditinggal memutar video pernah membuat API .60 150%
        CPU + halaman timeout sampai container di-restart (25/9)."""
        try:
            self._call("POST", "/browser/request",
                       {"profile": PROFILE, "action": "navigate", "url": "about:blank"}, timeout=30)
        except Exception as e:
            log(f"peringatan: gagal parkir tab ke about:blank ({e})")

    def evaluate(self, fn):
        res = self._call("POST", "/browser/request",
                         {"profile": PROFILE, "action": "act",
                          "request": {"kind": "evaluate", "fn": fn}})
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "evaluate gagal")
        return res.get("result") or {}


def ready_embed(handle):
    return ("() => location.pathname.toLowerCase().indexOf('/embed/@%s') === 0 && "
            "(!!document.getElementById('__FRONTITY_CONNECT_STATE__') || "
            "/overload|puzzle|Verify to continue/i.test(document.body ? document.body.innerText : ''))" % handle)


def ready_video(video_id):
    return ("() => location.href.indexOf('%s') !== -1 && "
            "(!!document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__') || "
            "/puzzle|Verify to continue/i.test(document.body ? document.body.innerText : ''))" % video_id)


def to_int(v):
    """'1.2M' / '392.6K' / '58000' / 58000 → int; lainnya None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    mult = 1
    if s[-1:].upper() in ("K", "M", "B"):
        mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[s[-1].upper()]
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def id_time(video_id):
    """ID video TikTok = (unix detik << 32) | ... → waktu unggah tanpa request tambahan."""
    try:
        return dt.datetime.fromtimestamp(int(video_id) >> 32, dt.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def q(v):
    """Literal SQL aman (standard_conforming_strings=on)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\x00", "").replace("'", "''") + "'"


def q_arr(items):
    return "ARRAY[" + ",".join(q(i) for i in items) + "]::text[]" if items else "'{}'::text[]"


def run_sql(sql, dry):
    if dry:
        return
    p = subprocess.run(DB_CMD, input="SET ROLE scraper;\n" + sql, text=True,
                       capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError("psql gagal: " + p.stderr.strip()[-400:])


def pause(cfg):
    time.sleep(random.uniform(cfg["delay_min_s"], cfg["delay_max_s"]))


def collect_account(br, handle, cfg, run_id, dry):
    """Kembalikan (status, jumlah video tersimpan). Lempar Captcha → run berhenti."""
    nav = br.navigate(f"https://www.tiktok.com/embed/@{handle}", ready_embed(handle))
    if not nav.get("ok"):
        raise RuntimeError(nav.get("error"))
    p = br.evaluate(JS_EMBED)
    if (p.get("user") or {}).get("handle", handle).lower() != handle:
        raise RuntimeError(f"data milik @{p['user']['handle']}, bukan @{handle} — dibuang")
    user, videos = p.get("user"), p.get("videos") or []

    if p.get("captcha") and not user:
        status = "captcha"
    elif not user or p.get("isError"):
        status = "not_found"
    elif user.get("isPrivate"):
        status = "private"
    elif not videos:
        status = "no_videos"
    else:
        status = "ok"

    run_sql(f"""INSERT INTO trend.tiktok_account_snapshot
      (run_id, handle, status, nickname, bio, followers, following, likes, videos, cards_seen, error)
      VALUES ({q(run_id)}, {q(handle)}, {q(status)}, {q((user or {}).get('nickname'))},
              {q((user or {}).get('bio'))}, {q(to_int((user or {}).get('followers')))},
              {q(to_int((user or {}).get('following')))}, {q(to_int((user or {}).get('likes')))},
              NULL, {len(videos)},
              {q(None if status in ('ok', 'no_videos') else (p.get('head') or '')[:200])});""", dry)
    log(f"@{handle}: {status} · pengikut={(user or {}).get('followers')} · video di embed={len(videos)}")

    if status == "captcha":
        raise Captcha(handle)
    if status != "ok":
        return status, 0

    # Terbaru dulu (waktu dari ID). Embed menaruh video populer lama di depan —
    # itu bukan sinyal tren, jadi diurutkan ulang.
    latest = sorted(videos, key=lambda v: -int(v["id"]))[: cfg["videos_per_account"]]
    got = 0
    for v0 in latest:
        pause(cfg)
        url = f"https://www.tiktok.com/@{handle}/video/{v0['id']}"
        try:
            nav = br.navigate(url, ready_video(v0["id"]))
            if not nav.get("ok"):
                log(f"  video {v0['id']}: {nav.get('error')}")
                continue
            v = br.evaluate(JS_VIDEO)
            br.quiet()
        except Exception as e:  # satu video lambat/timeout tak boleh menggagalkan akun
            log(f"  video {v0['id']}: ERROR {e}")
            continue
        if v.get("captcha") and not v.get("id"):
            raise Captcha(f"{handle} video")
        if not v.get("id"):
            log(f"  video {v0['id']}: gagal ({v.get('err')})")
            continue
        if v["id"] != v0["id"]:
            log(f"  video {v0['id']}: terbaca id {v['id']} (halaman lain) — dibuang")
            continue
        media = "photo" if v.get("isPhoto") else "video"
        dur = None if media == "photo" else to_int(v.get("duration"))
        created = (dt.datetime.fromtimestamp(v["createTime"], dt.timezone.utc)
                   if v.get("createTime") else id_time(v["id"]))
        sql = [f"""INSERT INTO trend.tiktok_video
          (video_id, handle, url, description, hashtags, music, duration_s, created_at,
           media_type, n_images)
          VALUES ({q(v['id'])}, {q(handle)}, {q(url)}, {q(v.get('desc'))},
                  {q_arr(sorted({t.lower() for t in v.get('tags') or []}))}, {q(v.get('music'))},
                  {q(dur)}, {q(created.isoformat() if created else None)},
                  {q(media)}, {q(to_int(v.get('nImages')))})
          ON CONFLICT (video_id) DO UPDATE SET description = EXCLUDED.description,
            hashtags = EXCLUDED.hashtags, media_type = EXCLUDED.media_type,
            n_images = EXCLUDED.n_images, duration_s = EXCLUDED.duration_s;""",
               f"""INSERT INTO trend.tiktok_video_snapshot
          (run_id, video_id, plays, likes, comments, shares, saves)
          VALUES ({q(run_id)}, {q(v['id'])}, {q(to_int(v.get('plays')))}, {q(to_int(v.get('likes')))},
                  {q(to_int(v.get('comments')))}, {q(to_int(v.get('shares')))}, {q(to_int(v.get('saves')))});"""]
        for m in {x.lower() for x in v.get("mentions") or []} - {handle}:
            sql.append(f"""INSERT INTO trend.tiktok_candidate (handle, found_via) VALUES ({q(m)}, {q(handle)})
              ON CONFLICT (handle) DO UPDATE SET last_seen = now(),
                times_seen = trend.tiktok_candidate.times_seen + 1;""")
        run_sql("\n".join(sql), dry)
        got += 1
        log(f"  video {v['id']} ({created:%Y-%m-%d}): plays={v.get('plays')} likes={v.get('likes')} "
            f"saves={v.get('saves')} {media}{'' if media == 'photo' else f' {dur}s'} tags={len(v.get('tags') or [])}")
    return status, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--check", nargs="+", metavar="HANDLE")
    args = ap.parse_args()

    if args.check:
        br = Browser(load_key())
        if not (br.healthy() and br.request_path_ok()):
            sys.exit("browser API .60 tak siap (mati / rute MTU hilang)")
        for i, h in enumerate(args.check):
            h = h.lstrip("@").lower()
            if i:
                time.sleep(15)
            nav = br.navigate(f"https://www.tiktok.com/embed/@{h}", ready_embed(h))
            r = br.evaluate(JS_EMBED) if nav.get("ok") else {}
            u = r.get("user") or {}
            vids = sorted(r.get("videos") or [], key=lambda v: -int(v["id"]))
            if not nav.get("ok"):
                print(f"@{h}: GAGAL MENGUKUR ({nav.get('error')})")
            elif r.get("captcha") and not u:
                print(f"@{h}: GAGAL MENGUKUR (CAPTCHA)")
            elif not u:
                print(f"@{h}: tak ditemukan / tak terbaca ({(r.get('head') or '')[:60]!r})")
            else:
                last = id_time(vids[0]["id"]) if vids else None
                print(f"@{h}: {u.get('nickname')} · pengikut {u.get('followers')} · "
                      f"video terakhir {f'{last:%Y-%m-%d}' if last else '–'}"
                      f"{' · PRIVAT' if u.get('isPrivate') else ''}")
                if u.get("bio"):
                    print("   bio:", u["bio"].replace("\n", " / ")[:160])
        br.park()
        return 0

    cfg = json.load(open(WATCHLIST))
    handles = [h.lstrip("@").lower() for h in cfg["accounts"]]
    if args.only:
        handles = [args.only.lstrip("@").lower()]
    random.shuffle(handles)  # ratakan akun yg terpotong CAPTCHA antar hari
    handles = handles[: cfg["max_accounts_per_run"]]

    br = Browser(load_key())
    if not br.healthy():
        log(f"SKIP: browser API {API} tak sehat/mati (VM .60 belum naik) — bukan kegagalan data.")
        return 0
    if not br.request_path_ok():
        log("GAGAL: request besar ke .60 menggantung — rute MTU 10.66.66.60 hilang? "
            "Jalankan: sudo ip route replace 10.66.66.60/32 dev wg0 src 10.66.66.1 mtu 1380")
        return 1

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log(f"run {run_id}: {len(handles)} akun, profil browser {PROFILE}{' (DRY-RUN)' if args.dry_run else ''}")
    results, videos = {}, 0
    try:
        return collect_all(br, handles, cfg, run_id, args, results)
    finally:
        br.park()


def collect_all(br, handles, cfg, run_id, args, results):
    videos = 0
    try:
        for i, h in enumerate(handles):
            if i:
                pause(cfg)
            try:
                st, n = collect_account(br, h, cfg, run_id, args.dry_run)
            except Captcha:
                raise
            except Exception as e:  # satu akun gagal tak menggagalkan yg lain
                st, n = "error", 0
                log(f"@{h}: ERROR {e}")
            results[h], videos = st, videos + n
    except Captcha as c:
        results[str(c).split()[0]] = "captcha"
        log(f"BERHENTI: CAPTCHA muncul di {c} — sisa akun dilewati supaya IP tak makin dicurigai.")
        log(f"ringkasan: {json.dumps(results)} · video tersimpan={videos}")
        return 2

    ok = sum(1 for s in results.values() if s in ("ok", "no_videos"))
    log(f"ringkasan: {json.dumps(results)} · video tersimpan={videos}")
    if ok == 0:
        log("GAGAL: tak satu pun akun terbaca.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
