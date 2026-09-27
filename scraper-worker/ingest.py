#!/usr/bin/env python3
"""Ingest JSONL scraper (dari .61) -> DB-VPS schema `trend` (jalan di HUB).

Reuse pola tiktok_trend.py: SQL disuap via `ssh db-vps 'psql -d scraper -f -'`.
Hanya HUB yang punya akses ssh db-vps (pg_hba mengunci ke 10.66.66.1). Skema =
social-analytics/tiktok_trend_schema.sql (dipakai bersama, TIDAK menambah tabel).

Pakai:  python3 run_worker.py ... | ssh .61 ...   # sebenarnya via run.sh
        cat records.jsonl | python3 ingest.py
"""
from __future__ import annotations

import sys
import json
import subprocess

DB_CMD = ["ssh", "-o", "BatchMode=yes", "db-vps",
          "sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -q -f -"]


def q(v):
    """Quote nilai untuk SQL literal (None -> NULL)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):  # text[]
        inner = ",".join('"' + str(x).replace('"', '\\"') + '"' for x in v)
        return "'{" + inner + "}'"
    return "'" + str(v).replace("'", "''") + "'"


def to_ts(epoch):
    return f"to_timestamp({int(epoch)})" if epoch else "NULL"


def build_sql(records: list[dict]) -> str:
    out = ["SET ROLE scraper;"]
    for r in records:
        t = r.get("type")
        if t == "account":
            out.append(
                "INSERT INTO trend.tiktok_account_snapshot "
                "(run_id,handle,status,nickname,bio,followers,following,likes,videos,cards_seen,error) "
                f"VALUES ({q(r['run_id'])},{q(r['handle'])},{q(r['status'])},{q(r.get('nickname'))},"
                f"{q(r.get('bio'))},{q(r.get('followers'))},{q(r.get('following'))},{q(r.get('likes'))},"
                f"{q(r.get('videos'))},{q(r.get('cards_seen'))},{q(r.get('error'))});")
        elif t == "video":
            url = f"https://www.tiktok.com/@{r['handle']}/video/{r['video_id']}"
            out.append(
                "INSERT INTO trend.tiktok_video (video_id,handle,url,description,hashtags,music,duration_s,created_at) "
                f"VALUES ({q(r['video_id'])},{q(r['handle'])},{q(url)},{q(r.get('desc'))},"
                f"{q(r.get('hashtags') or [])},{q(r.get('music'))},{q(r.get('duration_s'))},{to_ts(r.get('created_at'))}) "
                "ON CONFLICT (video_id) DO UPDATE SET description=EXCLUDED.description;")
        elif t == "vsnap":
            out.append(
                "INSERT INTO trend.tiktok_video_snapshot (run_id,video_id,plays,likes,comments,shares,saves) "
                f"VALUES ({q(r['run_id'])},{q(r['video_id'])},{q(r.get('plays'))},{q(r.get('likes'))},"
                f"{q(r.get('comments'))},{q(r.get('shares'))},{q(r.get('saves'))});")
        # video_err / done: tak ditulis (cukup di log)
    return "\n".join(out)


def main() -> int:
    records = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"lewati baris non-JSON: {line[:80]}", file=sys.stderr)
    sql = build_sql(records)
    if sql.strip() == "SET ROLE scraper;":
        print("tak ada record untuk di-ingest", file=sys.stderr)
        return 0
    p = subprocess.run(DB_CMD, input=sql, text=True, capture_output=True)
    if p.returncode != 0:
        print("psql GAGAL: " + p.stderr.strip()[-400:], file=sys.stderr)
        return 1
    n = sum(1 for r in records if r.get("type") in ("account", "video", "vsnap"))
    print(f"ingest OK: {n} baris DB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
