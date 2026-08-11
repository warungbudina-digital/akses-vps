#!/usr/bin/env bash
# dashboard-deploy.sh — regen dashboard pipeline (media.* DB-VPS + alur naskah/footage)
# lalu copy ke nginx (mount read-only -> live tanpa reload). https://pipeline.obc-crypto.com
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
NGINX_DEST="$DIR/../nginx/dashboards/pipeline/index.html"
python3 "$DIR/dashboard.py"
cp "$DIR/dashboard.html" "$NGINX_DEST"
echo "deployed -> $NGINX_DEST ($(wc -c < "$NGINX_DEST") byte) · https://pipeline.obc-crypto.com"
