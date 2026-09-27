#!/usr/bin/env python3
"""Scraper TikTok requests-only (TANPA browser/Chromium).

Terbukti Langkah-0 (27/9): baik halaman embed maupun video-detail mengembalikan
JSON SSR lewat plain HTTP + User-Agent browser. Ini menggantikan jalur browser
.60 yang berat (Chromium 150% CPU). Modul ini DB-agnostik: fetch + parse saja,
kembalikan dict; penulisan ke DB dikerjakan ingest.py di hub.

Dua endpoint:
  - embed        https://www.tiktok.com/embed/@<h>
                 -> __FRONTITY_CONNECT_STATE__ .source.data["/embed/@<h>"]
                 -> userInfo (FLAT: uniqueId/nickname/followerCount/...) + videoList (playCount)
  - video-detail https://www.tiktok.com/@<h>/video/<id>
                 -> __UNIVERSAL_DATA_FOR_REHYDRATION__ __DEFAULT_SCOPE__["webapp.video-detail"]
                    .itemInfo.itemStruct.statsV2 (play/digg/comment/share/collect)

Status dibedakan tegas (pelajaran "kegagalan menyamar sukses"):
  ok | no_videos | not_found | captcha | error
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field

import requests

# UA DESKTOP wajib: embed jalan dgn UA apa pun, TAPI video-detail hanya
# mengembalikan SSR penuh (itemStruct) utk UA desktop — UA mobile dapat shell
# tanpa data (status "no_data"). Terbukti dari IP CS .61 (27/9).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"}
EMBED_URL = "https://www.tiktok.com/embed/@{h}"
VIDEO_URL = "https://www.tiktok.com/@{h}/video/{vid}"


@dataclass
class Account:
    handle: str
    status: str = "error"
    nickname: str | None = None
    bio: str | None = None
    followers: int | None = None
    following: int | None = None
    likes: int | None = None
    videos_total: int | None = None
    video_list: list[dict] = field(default_factory=list)  # {video_id, desc, plays}
    error: str | None = None


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _extract_json(html: str, marker: str) -> dict | None:
    """Ambil objek JSON tepat setelah `marker` (baik `= {...}` maupun `>{...}</script>`)."""
    i = html.find(marker)
    if i < 0:
        return None
    b = html.find("{", i)
    if b < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[b:])
        return obj
    except json.JSONDecodeError:
        return None


class TikTokScraper:
    def __init__(self, session: requests.Session | None = None, timeout: int = 25,
                 delay=(25, 45), max_retry: int = 2):
        self.s = session or requests.Session()
        self.s.headers.update(HEADERS)
        self.timeout = timeout
        self.delay = delay
        self.max_retry = max_retry

    def _get(self, url: str) -> requests.Response:
        """GET dengan backoff pada 503/429 (throttle nyata — lihat Langkah-0)."""
        last = None
        for attempt in range(self.max_retry + 1):
            r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
            last = r
            if r.status_code in (429, 503):
                time.sleep(min(60, 8 * (attempt + 1)))
                continue
            return r
        return last

    def sleep_jitter(self):
        time.sleep(random.uniform(*self.delay))

    # --- akun (embed) ---
    def fetch_account(self, handle: str) -> Account:
        acc = Account(handle=handle)
        try:
            r = self._get(EMBED_URL.format(h=handle))
        except requests.RequestException as e:
            acc.status, acc.error = "error", str(e)[:200]
            return acc
        if r.status_code in (429, 503):
            acc.status, acc.error = "captcha", f"HTTP {r.status_code} (throttle)"
            return acc
        if r.status_code != 200:
            acc.status, acc.error = "error", f"HTTP {r.status_code}"
            return acc
        state = _extract_json(r.text, "__FRONTITY_CONNECT_STATE__")
        node = (((state or {}).get("source") or {}).get("data") or {}).get(f"/embed/@{handle}")
        if not node:
            acc.status, acc.error = "error", "state/embed node tak ada"
            return acc
        ui = node.get("userInfo") or {}
        if not ui or ui.get("code") not in (200, None) or not ui.get("uniqueId"):
            acc.status = "not_found"
            return acc
        acc.nickname = ui.get("nickname")
        acc.bio = ui.get("signature")
        acc.followers = _to_int(ui.get("followerCount"))
        acc.following = _to_int(ui.get("followingCount"))
        acc.likes = _to_int(ui.get("heartCount"))
        for v in node.get("videoList") or []:
            stats = v.get("stats") or {}
            plays = _to_int(v.get("playCount")) or _to_int(stats.get("playCount")) or 0
            vid = v.get("id") or (v.get("video") or {}).get("id")
            if vid:
                acc.video_list.append({"video_id": str(vid),
                                       "desc": v.get("desc") or "",
                                       "plays": plays})
        acc.videos_total = len(acc.video_list)
        acc.status = "ok" if acc.video_list else "no_videos"
        return acc

    # --- statistik penuh (video-detail) ---
    def fetch_video_detail(self, handle: str, video_id: str) -> dict:
        """Kembalikan {status, plays, likes, comments, shares, saves, desc, music,
        duration_s, created_at, hashtags[]}. Engagement TIDAK ada di embed → wajib sini."""
        out = {"video_id": str(video_id), "status": "error"}
        try:
            r = self._get(VIDEO_URL.format(h=handle, vid=video_id))
        except requests.RequestException as e:
            out["error"] = str(e)[:200]
            return out
        if r.status_code in (429, 503):
            out["status"] = "captcha"
            return out
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}"
            return out
        obj = _extract_json(r.text, "__UNIVERSAL_DATA_FOR_REHYDRATION__")
        item = ((((obj or {}).get("__DEFAULT_SCOPE__") or {})
                 .get("webapp.video-detail") or {}).get("itemInfo") or {}).get("itemStruct")
        if not item:
            out["status"] = "no_data"  # kemungkinan challenge/redirect
            return out
        s = item.get("statsV2") or item.get("stats") or {}
        out.update({
            "status": "ok",
            "plays": _to_int(s.get("playCount")),
            "likes": _to_int(s.get("diggCount")),
            "comments": _to_int(s.get("commentCount")),
            "shares": _to_int(s.get("shareCount")),
            "saves": _to_int(s.get("collectCount")),
            "desc": item.get("desc") or "",
            "music": (item.get("music") or {}).get("title"),
            "duration_s": _to_int((item.get("video") or {}).get("duration")),
            "created_at": _to_int(item.get("createTime")),
            "hashtags": [c.get("title") for c in (item.get("challenges") or []) if c.get("title")],
        })
        return out


# proxy objektif Scorecard Tier-1 dari satu snapshot video (dipakai ingest/scorecard)
def objective_proxies(plays, likes, comments, shares, saves):
    if not plays:
        return {}
    return {
        "save_rate_pct": round(100 * (saves or 0) / plays, 3),      # -> 'Nilai Berbagi'
        "comment_rate_pct": round(100 * (comments or 0) / plays, 3),  # -> 'Potensi Diskusi'
        "share_rate_pct": round(100 * (shares or 0) / plays, 3),
        "like_rate_pct": round(100 * (likes or 0) / plays, 3),
    }
