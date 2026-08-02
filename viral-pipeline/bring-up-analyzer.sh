#!/usr/bin/env bash
# =====================================================================
# bring-up-analyzer.sh — siapkan viral_analyzer di .50 (Cloud Shell
# warungbudina, ephemeral). Dijalankan DI .50, sesudah bootstrap WG+SSH.
#
# Idempoten:
#   - kalau container sudah healthy  -> tak melakukan apa-apa (exit 0).
#   - kalau VM fresh (repo/image hilang pasca-recycle) -> clone + build + up.
#
# Pemakaian: ./bring-up-analyzer.sh [v1|v2]     (default v1)
#   v1 = core deterministik (image ~1.7GB, build ~2.5mnt)
#   v2 = + model HF whisper/CLIP (image ~5.86GB, build ~8mnt, butuh ~9GB disk)
# Ganti varian saat container LAIN sedang jalan: hentikan dulu
#   (docker rm -f viral_analyzer) lalu jalankan ulang skrip.
# =====================================================================
set -euo pipefail

VARIANT="${1:-v1}"
REPO_DIR="$HOME/tool-analisa-video"
REPO_URL="https://github.com/warungbudina-digital/tool-analisa-video.git"
IMAGE="tool-analisa-video-viral_analyzer:latest"
COMPOSE="docker-compose.render-worker.yml"
PORT="${VIRAL_ANALYZER_PORT:-9021}"

case "$VARIANT" in
  v1) WITH_ML=0 ;;
  v2) WITH_ML=1 ;;
  *)  echo "varian tak dikenal: '$VARIANT' (pakai v1 atau v2)"; exit 2 ;;
esac

log(){ echo "[bring-up $(date +%H:%M:%S)] $*"; }

# 0. sudah healthy? -> selesai
if curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  log "analyzer SUDAH jalan & healthy:"
  curl -s "http://127.0.0.1:$PORT/healthz"; echo
  exit 0
fi

log "analyzer belum jalan -> bring-up varian $VARIANT"

# 1. repo (clone kalau absen; repo PUBLIC, HTTPS keyless)
if [ ! -d "$REPO_DIR/.git" ]; then
  log "repo absen -> git clone"
  git clone --depth 1 "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# 2. .env (skema var-host; .env.example repo sudah benar sejak commit cf69766)
[ -f .env ] || { log ".env absen -> cp dari .env.example"; cp .env.example .env; }
mkdir -p data/input

# 3. image (build legacy kalau absen; buildkit bikin cache-ganda yg meledakkan disk)
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "image sudah ada -> skip build"
else
  log "image absen -> build $VARIANT (WITH_ML=$WITH_ML), bisa lama..."
  DOCKER_BUILDKIT=0 docker build --build-arg WITH_ML="$WITH_ML" -t "$IMAGE" .
fi

# 4. up (pakai image yg sudah ada, jangan rebuild via compose/buildkit)
log "docker compose up -d"
docker compose -f "$COMPOSE" up -d --no-build

# 5. tunggu healthy
log "menunggu healthy..."
for i in $(seq 1 30); do
  st="$(docker inspect -f '{{.State.Health.Status}}' viral_analyzer 2>/dev/null || echo none)"
  if [ "$st" = healthy ]; then
    log "HEALTHY:"; curl -s "http://127.0.0.1:$PORT/healthz"; echo
    exit 0
  fi
  sleep 5
done
log "!!! belum healthy setelah 150s — cek: docker logs viral_analyzer"
exit 1
