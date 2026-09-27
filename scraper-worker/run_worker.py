#!/usr/bin/env python3
"""Runner scraper (jalan di CS .61) — STATELESS, emit JSONL ke stdout.

.61 tak punya akses ssh `db-vps`; penulisan DB dikerjakan ingest.py di HUB.
Alur: hub -> ssh .61 'python3 run_worker.py' -> tangkap JSONL -> ingest.py -> DB-VPS.

Tiap baris stdout = satu record JSON dgn `type`:
  {"type":"account", "run_id":..., "handle":..., "status":..., "nickname":..., ...}
  {"type":"video",   "run_id":..., "handle":..., "video_id":..., "desc":..., "hashtags":[...], ...}
  {"type":"vsnap",   "run_id":..., "video_id":..., "plays":..., "likes":..., "comments":..., ...}

Pemakaian:
  python3 run_worker.py --watchlist ../social-analytics/tiktok_watchlist.json
  python3 run_worker.py --watchlist wl.json --max-accounts 8 --videos 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

from tiktok_scraper import TikTokScraper, objective_proxies


def emit(rec: dict):
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description="TikTok scraper worker (requests-only, emit JSONL)")
    ap.add_argument("--watchlist", required=True, help="path tiktok_watchlist.json")
    ap.add_argument("--max-accounts", type=int, default=None)
    ap.add_argument("--videos", type=int, default=None, help="video_per_account (top-by-play)")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    wl = json.load(open(args.watchlist, encoding="utf-8"))
    accounts = wl.get("accounts", [])
    max_acc = args.max_accounts or wl.get("max_accounts_per_run", 8)
    per_acc = args.videos or wl.get("videos_per_account", 4)
    delay = (wl.get("delay_min_s", 25), wl.get("delay_max_s", 45))
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]

    sc = TikTokScraper(delay=delay)
    accounts = accounts[:max_acc]

    for i, handle in enumerate(accounts):
        acc = sc.fetch_account(handle)
        emit({"type": "account", "run_id": run_id, "handle": handle, "status": acc.status,
              "nickname": acc.nickname, "bio": acc.bio, "followers": acc.followers,
              "following": acc.following, "likes": acc.likes, "videos": acc.videos_total,
              "cards_seen": len(acc.video_list), "error": acc.error})

        if acc.status == "ok":
            top = sorted(acc.video_list, key=lambda v: v["plays"], reverse=True)[:per_acc]
            for v in top:
                sc.sleep_jitter()
                det = sc.fetch_video_detail(handle, v["video_id"])
                if det.get("status") != "ok":
                    emit({"type": "video_err", "run_id": run_id, "handle": handle,
                          "video_id": v["video_id"], "status": det.get("status"),
                          "error": det.get("error")})
                    continue
                emit({"type": "video", "run_id": run_id, "handle": handle,
                      "video_id": det["video_id"], "desc": det.get("desc"),
                      "hashtags": det.get("hashtags", []), "music": det.get("music"),
                      "duration_s": det.get("duration_s"), "created_at": det.get("created_at")})
                emit({"type": "vsnap", "run_id": run_id, "video_id": det["video_id"],
                      "plays": det.get("plays"), "likes": det.get("likes"),
                      "comments": det.get("comments"), "shares": det.get("shares"),
                      "saves": det.get("saves"),
                      "proxies": objective_proxies(det.get("plays"), det.get("likes"),
                                                   det.get("comments"), det.get("shares"),
                                                   det.get("saves"))})
        # jeda antar-akun (kecuali terakhir)
        if i < len(accounts) - 1:
            sc.sleep_jitter()

    emit({"type": "done", "run_id": run_id, "accounts": len(accounts)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
