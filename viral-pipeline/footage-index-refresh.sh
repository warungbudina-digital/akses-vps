#!/usr/bin/env bash
# footage-index-refresh.sh — snapshot isi gfootage:RAW-VIDEO (inbox footage sumber,
# BUKAN VN-exports yg isinya hasil render) jadi JSON statis buat dashboard editor
# (nginx/dashboards/editor/footage-index.json) — supaya user bisa PILIH footage gdrive
# nyata alih-alih menebak nama file, tanpa dashboard butuh backend live (tetap statis,
# cuma dibaca via fetch()).
#
# Pakai: cron tiap 30 menit. Read-only (cuma `rclone lsjson`), tak menyentuh isi Drive.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/../nginx/dashboards/editor/footage-index.json"
TMP="$(mktemp)"

RAW_JSON=$(rclone lsjson gfootage:RAW-VIDEO -R --files-only --no-mimetype 2>/dev/null)
RC=$?

python3 - "$RAW_JSON" "$RC" > "$TMP" <<'PYEOF'
import json, sys, datetime
raw, rc = sys.argv[1], sys.argv[2]
files = []
if rc == "0" and raw.strip():
    try:
        items = json.loads(raw)
        for it in items:
            files.append({
                "path": f"gfootage:RAW-VIDEO/{it['Path']}",
                "name": it["Name"],
                "size_bytes": it.get("Size", 0),
                "modified": it.get("ModTime"),
            })
    except Exception:
        pass
out = {
    "remote": "gfootage:RAW-VIDEO",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "ok": rc == "0",
    "files": files,
}
print(json.dumps(out, indent=2, ensure_ascii=False))
PYEOF

chmod 644 "$TMP"   # mktemp default 600 -> nginx worker (user "nginx", beda dari owner
                    # file) gagal baca -> 403 senyap. Sama akar bug spt .htpasswd-editor.
mv "$TMP" "$OUT"
echo "footage-index.json ditulis ($(python3 -c "import json;print(len(json.load(open('$OUT'))['files']))") file) — $(date -u +%FT%TZ)"
