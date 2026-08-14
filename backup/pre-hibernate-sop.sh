#!/usr/bin/env bash
# pre-hibernate-sop.sh — SOP pra-hibernasi laptop SUARAHATI (node terjadwal).
# Laptop hibernate 22:30 WITA (task NodeHibernate-2230). SOP ini jalan 3 menit
# sebelumnya = 22:27 WITA (14:27 UTC) via crontab HUB (akses-vps, 24/7).
#
# Urutan (permintaan user): matikan container running -> hentikan ping ->
# tutup tab & browser (Chrome) di laptop.
#
# Dijalankan dari HUB karena: (a) hub 24/7, (b) hub punya SSH admin ke node
# Cloud Shell (key from=10.66.66.1), (c) hub bisa `ssh ltap-mini` ke laptop.
# Laptop TIDAK bisa SSH node (key dibatasi ke hub), makanya hub yang orkestrasi.
#
# Pemakaian: pre-hibernate-sop.sh [--dry-run]
set -uo pipefail

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
LOG_TS() { date '+%F %T %Z'; }
say() { echo "[$(LOG_TS)] $*"; }
run() { if [ "$DRY" = 1 ]; then echo "    (dry-run) $*"; else eval "$@"; fi; }

ADMIN_KEY="$HOME/.ssh/akses-vps-cloudshell-admin"
SSHOPT="-i $ADMIN_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

# Node Cloud Shell: label=IP:user
NODES="10.66.66.50:warungbudina 10.66.66.60:balibruntattour 10.66.66.61:gogobuda65"

say "=== SOP pra-hibernasi MULAI (dry-run=$DRY) ==="

# ---- 1) Node: stop container + stop ping (hanya yang terjangkau) ----
for spec in $NODES; do
  ip="${spec%%:*}"; user="${spec##*:}"
  if timeout 5 ping -c1 -W2 "$ip" >/dev/null 2>&1; then
    say "node $user ($ip): terjangkau -> stop container + ping"
    if [ "$DRY" = 1 ]; then
      echo "    (dry-run) ssh $user@$ip: docker stop \$(docker ps -q); pkill -f 'ping 8.8.8.8'"
    else
      timeout 30 ssh $SSHOPT "$user@$ip" '
        C=$(docker ps -q 2>/dev/null);
        if [ -n "$C" ]; then docker stop $C >/dev/null 2>&1 && echo "  container dihentikan: $(echo $C|wc -w)"; else echo "  tak ada container running"; fi
        if pkill -f "ping 8.8.8.8" 2>/dev/null; then echo "  ping dihentikan"; else echo "  tak ada ping"; fi
      ' 2>&1 | grep -vE 'Warning: (Perman|the)' | sed 's/^/    /'
    fi
  else
    say "node $user ($ip): TAK terjangkau (mungkin sudah recycle) -> skip"
  fi
done

# ---- 2) Laptop: tutup tab + browser Chrome (biarkan watcher pythonw hidup:
#         ia beku-terpulihkan lintas hibernate & siap di wake berikutnya) ----
if timeout 8 ssh -o ConnectTimeout=6 -o BatchMode=yes ltap-mini 'exit' 2>/dev/null; then
  say "laptop: terjangkau -> tutup Chrome (tab + browser)"
  if [ "$DRY" = 1 ]; then
    echo "    (dry-run) ssh ltap-mini: taskkill Chrome (EncodedCommand)"
  else
    # PowerShell via -EncodedCommand (base64 UTF-16LE) — hindari mimpi quoting bersarang ssh->PS.
    PS_KILL='$n=(Get-Process chrome -ErrorAction SilentlyContinue).Count; Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Write-Output ("chrome proc: "+$n+" -> "+(Get-Process chrome -ErrorAction SilentlyContinue).Count)'
    EB=$(printf '%s' "$PS_KILL" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)
    timeout 25 ssh ltap-mini "powershell -NoProfile -EncodedCommand $EB" 2>&1 | grep -vE 'CLIXML|<Objs' | grep -iE 'chrome proc' | sed 's/^/    /'
  fi
else
  say "laptop: TAK terjangkau -> skip tutup Chrome"
fi

say "=== SOP pra-hibernasi SELESAI ==="
