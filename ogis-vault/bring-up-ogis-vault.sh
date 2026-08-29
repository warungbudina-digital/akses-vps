#!/usr/bin/env bash
# =====================================================================
# bring-up-ogis-vault.sh — siapkan Ollama+index vektor MANDIRI di ogis
# (Cloud Shell maydualapan8, EPHEMERAL). Dijalankan DI akses-vps,
# MENGGERAKKAN ogis — pola sama `bring-up-browser.sh` (stack TERPISAH,
# tak menyentuh ~/browser yang dipakai bersama .60).
#
# Idempoten:
#   - ollama sudah live + model ada + index.db ada -> verifikasi, exit 0.
#   - VM fresh (dir ~/ogis-vault hilang pasca-recycle) -> push ulang
#     (tar pipe dari repo hub, BUKAN git clone publik — ogis-vault privat,
#     belum ada di GitHub), docker compose up, pull model.
#   - index.db lokal absen -> RESTORE OTOMATIS dari backup terbaru DB-VPS
#     (`ogis-vault-backup.sh`) kalau ada; kalau belum pernah backup,
#     dibiarkan kosong (ingest.py bikin fresh saat isi pertama).
#
# Pemakaian: ./bring-up-ogis-vault.sh
# Exit: 0 live & terverifikasi · 1 gagal / ogis belum reachable.
# =====================================================================
set -uo pipefail

OGIS_HOST="${OGIS_HOST:-maydualapan8@10.66.66.8}"
OGIS_KEY="${OGIS_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
DBVPS_HOST="${DBVPS_HOST:-db-vps}"
BACKUP_DIR="${BACKUP_DIR:-ogis-vault-backups}"   # relatif ke $HOME di DB-VPS
LOCAL_SRC="$(cd "$(dirname "$0")" && pwd)"       # akses-vps/ogis-vault (repo)

log(){ echo "[bring-up-ogis-vault $(date -u +%H:%M:%S)] $*"; }

sshogis(){ ssh -o ControlPath=none -i "$OGIS_KEY" -o IdentitiesOnly=yes \
           -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
           -o BatchMode=yes -p 22 "$OGIS_HOST" "$@"; }
sshdb(){ ssh -o ConnectTimeout=15 -o BatchMode=yes "$DBVPS_HOST" "$@" 2>/dev/null; }
hs(){ sshogis "curl -m8 -s -o /dev/null -w '%{http_code}' http://127.0.0.1:11434$1" 2>/dev/null; }

# ── 0. ogis bisa di-SSH? ─────────────────────────────────────────────────
if ! sshogis true 2>/dev/null; then
  log "GAGAL: ogis tak bisa di-SSH (belum bootstrap/wake)."
  exit 1
fi

# ── 1. Push source ogis-vault (scripts + wiki/_meta konvensi) ke ogis ────
# tar pipe, BUKAN git clone (repo privat, belum di-push publik). Idempoten:
# overwrite scripts/README/wiki/_meta, TAPI JANGAN timpa wiki/scrape-<real>/
# yg mungkin sudah diisi konten scrape nyata langsung di ogis -- exclude
# semua subfolder wiki/ KECUALI _meta dan scrape-example (template).
log "Push ogis-vault (scripts+konvensi) ke ogis..."
sshogis 'mkdir -p ~/ogis-vault/wiki'
tar -C "$LOCAL_SRC" -czf - \
    --exclude='index.db' \
    docker-compose.yml bring-up-ogis-vault.sh ingest.py ingest-append.py search.py \
    setup-browser-profiles.sh setup-gdrive-remotes.sh README.md \
    wiki/_meta wiki/scrape-example \
  | sshogis 'cd ~/ogis-vault && tar xzf -' || { log "GAGAL: push source ke ogis."; exit 1; }

# ── 2. docker compose up -d (ollama) ──────────────────────────────────────
log "docker compose up -d (ollama)..."
sshogis 'cd ~/ogis-vault && docker compose up -d' || { log "GAGAL: docker compose up."; exit 1; }

# tunggu healthy (maks 60s, image kecil + start_period 20s)
deadline=$(( $(date +%s) + 60 ))
healthy=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  st="$(sshogis "docker inspect -f '{{.State.Health.Status}}' ogis-vault-ollama 2>/dev/null || echo none")"
  [ "$st" = "healthy" ] && { healthy=1; break; }
  sleep 3
done
if [ -z "$healthy" ]; then
  log "GAGAL: container ollama tak healthy dlm 60s (status terakhir: ${st:-?})."
  exit 1
fi

# ── 3. Model nomic-embed-text ada? kalau tidak, pull (kecil, ~275MB) ─────
if ! sshogis "docker exec ogis-vault-ollama ollama list 2>/dev/null | grep -q nomic-embed-text"; then
  log "Model nomic-embed-text absen -> pull..."
  if ! sshogis "docker exec ogis-vault-ollama ollama pull nomic-embed-text"; then
    log "GAGAL: pull model nomic-embed-text."
    exit 1
  fi
fi

# ── 4. index.db lokal absen? coba restore dari backup DB-VPS terbaru ─────
if ! sshogis '[ -f ~/ogis-vault/index.db ]'; then
  log "index.db absen di ogis -> cek backup terbaru di DB-VPS..."
  LATEST="$(sshdb "ls -t ~/${BACKUP_DIR}/index-*.db.gz 2>/dev/null | head -1")"
  if [ -n "$LATEST" ]; then
    log "Restore dari ${DBVPS_HOST}:${LATEST}..."
    if sshdb "cat '$LATEST'" | gunzip | sshogis 'cat > ~/ogis-vault/index.db'; then
      log "OK: index.db ter-restore."
    else
      log "WARN: restore gagal, index.db akan mulai kosong (bukan fatal)."
    fi
  else
    log "Belum ada backup di DB-VPS (wajar kalau ini pertama kali)."
  fi
fi

# index.db MASIH absen (first-ever run, tak ada backup sama sekali)? bikin
# tabel kosong via ingest.py penuh (aman -- cuma domain corpus:true yg
# masuk, saat ini nol -> table ada, 0 baris) supaya ingest-append.py tak
# pernah crash "no such table: chunks" di pemakaian pertama.
if ! sshogis '[ -f ~/ogis-vault/index.db ]'; then
  log "Inisialisasi index.db kosong (ingest.py sekali, first-ever run)..."
  sshogis 'cd ~/ogis-vault && python3 ingest.py' || log "WARN: init index.db gagal (bukan fatal, coba lagi run berikutnya)."
fi

# ── 5. Verifikasi akhir ───────────────────────────────────────────────────
H=$(hs /api/tags)
if [ "$H" = "200" ]; then
  log "OK: ollama LIVE (http://127.0.0.1:11434 di ogis), model+index siap."
  exit 0
fi
log "!!! Verifikasi GAGAL (api/tags=$H)."
exit 1
