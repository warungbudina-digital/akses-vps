#!/usr/bin/env python3
"""
figma_comment.py — kelola komentar Figma via API (list/add/delete).

Ini bagian dari pemetaan "apa yg SUNGGUHAN bisa diedit/ditulis via Figma REST
API" (lihat FIGMA-API-CAPABILITIES.md di folder yang sama). Comment adalah
SATU-SATUNYA konten file yang bisa ditulis script langsung ke Figma via API
resmi (TERBUKTI live 2026-08-23: post lalu delete berhasil, HTTP 200 keduanya)
-- berguna utk workflow "AI kasih review/anotasi kreatif" di atas desain,
BUKAN utk mengubah desain itu sendiri (shape/teks/warna elemen TAK BISA
ditulis via REST API apa pun, lihat dokumen kapabilitas).

Prasyarat: token di ~/.config/figma/warungbudina_api-key.txt (scope
file_comments:read + file_comments:write, SUDAH dimiliki token akses-vps-full-access).

Contoh:
  python3 figma_comment.py list <file_key>
  python3 figma_comment.py add <file_key> "Pesan komentar" --x 100 --y 200
  python3 figma_comment.py add <file_key> "Balasan" --reply-to <comment_id>
  python3 figma_comment.py delete <file_key> <comment_id>
"""
import argparse
import re
import sys
from pathlib import Path

import requests

TOKEN_PATH = Path.home() / ".config" / "figma" / "warungbudina_api-key.txt"
API = "https://api.figma.com/v1"


def load_token() -> str:
    if not TOKEN_PATH.exists():
        sys.exit(f"Token Figma tak ditemukan di {TOKEN_PATH}")
    return TOKEN_PATH.read_text().strip()


def parse_file_key(url_or_key: str) -> str:
    m = re.search(r"figma\.com/(?:file|design|buzz)/([a-zA-Z0-9]+)", url_or_key)
    return m.group(1) if m else url_or_key.strip()


def cmd_list(key: str, token: str) -> None:
    r = requests.get(f"{API}/files/{key}/comments", headers={"X-Figma-Token": token}, timeout=20)
    r.raise_for_status()
    comments = r.json().get("comments", [])
    if not comments:
        print("(tak ada komentar)")
        return
    for c in comments:
        who = c["user"]["handle"]
        status = "RESOLVED" if c.get("resolved_at") else "open"
        print(f"[{c['id']}] ({status}) {who}: {c['message']}")


def cmd_add(key: str, token: str, message: str, x: float | None, y: float | None,
            node_id: str | None, reply_to: str | None) -> None:
    body: dict = {"message": message}
    if reply_to:
        body["comment_id"] = reply_to
    elif node_id:
        body["client_meta"] = {"node_id": node_id, "node_offset": {"x": x or 0, "y": y or 0}}
    elif x is not None and y is not None:
        body["client_meta"] = {"x": x, "y": y}
    r = requests.post(f"{API}/files/{key}/comments", headers={"X-Figma-Token": token}, json=body, timeout=20)
    r.raise_for_status()
    c = r.json()
    print(f"Komentar dibuat: id={c['id']}")


def cmd_delete(key: str, token: str, comment_id: str) -> None:
    r = requests.delete(f"{API}/files/{key}/comments/{comment_id}", headers={"X-Figma-Token": token}, timeout=20)
    r.raise_for_status()
    print("Komentar dihapus.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Tampilkan semua komentar di file")
    p_list.add_argument("file")

    p_add = sub.add_parser("add", help="Tambah komentar baru (atau balasan)")
    p_add.add_argument("file")
    p_add.add_argument("message")
    p_add.add_argument("--x", type=float, default=None, help="Posisi x di kanvas (pin komentar)")
    p_add.add_argument("--y", type=float, default=None, help="Posisi y di kanvas (pin komentar)")
    p_add.add_argument("--node-id", default=None, help="Tempelkan ke node id spesifik, bukan koordinat bebas")
    p_add.add_argument("--reply-to", default=None, help="ID komentar yang dibalas (thread)")

    p_del = sub.add_parser("delete", help="Hapus komentar milik sendiri")
    p_del.add_argument("file")
    p_del.add_argument("comment_id")

    args = ap.parse_args()
    token = load_token()
    key = parse_file_key(args.file)

    if args.cmd == "list":
        cmd_list(key, token)
    elif args.cmd == "add":
        cmd_add(key, token, args.message, args.x, args.y, args.node_id, args.reply_to)
    elif args.cmd == "delete":
        cmd_delete(key, token, args.comment_id)


if __name__ == "__main__":
    main()
