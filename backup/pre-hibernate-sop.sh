#!/usr/bin/env bash
# pre-hibernate-sop.sh — SOP pra-hibernasi laptop SUARAHATI (node terjadwal).
# Dipanggil 3 menit sebelum TIAP hibernate/break laptop (v2026-08-28, 2
# siklus/hari: sblm break 14:00 WITA & sblm hibernate malam 23:00 WITA)
# via crontab HUB (akses-vps, 24/7) -- jam persis lihat crontab & docs/17.
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
    # GRACEFUL dulu (CloseMainWindow = WM_CLOSE), baru fallback Force kalau ada
    # proses yg masih nyangkut setelah jeda (jangan sampai skrip macet nunggu
    # window respons selamanya — Cloud Shell kerap punya dialog beforeunload
    # yg mengganjal CloseMainWindow, ujung-ujungnya tetap Force juga).
    # ⚠️ Force-kill (baik CloseMainWindow yg gagal maupun fallback Force) SELALU
    # bikin Chrome nyatat exit_type="Crashed" -> pas dibuka lagi di wake, Chrome
    # AUTO-RESTORE sesi/tab lama (persis yg dikeluhkan user "sisa aplikasi kemarin
    # masih ada"). Makanya SETELAH proses benar2 mati, exit_type dipatch manual
    # jadi "Normal" di file Preferences tiap profil Cloud Shell (Profile 10/26/29
    # = yuni/gogobuda/balibruntattour) — teknik standar cegah restore-prompt,
    # TAK menyentuh password/cookies/history, cuma flag housekeeping ini.
    PS_KILL='$procs=@(Get-Process chrome -ErrorAction SilentlyContinue); $n=$procs.Count; foreach ($p in $procs) { if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() } }; Start-Sleep -Seconds 4; $remain=@(Get-Process chrome -ErrorAction SilentlyContinue); if ($remain.Count -gt 0) { $remain | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }; $base="C:\Users\warungbudina\AppData\Local\Google\Chrome\User Data"; foreach ($t in @("Profile 10","Profile 26","Profile 29")) { $pf=Join-Path $base "$t\Preferences"; if (Test-Path $pf) { $raw=Get-Content $pf -Raw; $new=$raw -replace '"'"'"exit_type"\s*:\s*"[^"]+"'"'"', '"'"'"exit_type":"Normal"'"'"'; $new=$new -replace '"'"'"exited_cleanly"\s*:\s*(true|false)'"'"', '"'"'"exited_cleanly":true'"'"'; if ($new -ne $raw) { Set-Content -Path $pf -Value $new -NoNewline -Encoding UTF8 } } }; Write-Output ("chrome proc: "+$n+" -> "+(@(Get-Process chrome -ErrorAction SilentlyContinue)).Count+" (exit_type dipatch Normal)")'
    EB=$(printf '%s' "$PS_KILL" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)
    timeout 25 ssh ltap-mini "powershell -NoProfile -EncodedCommand $EB" 2>&1 | grep -vE 'CLIXML|<Objs' | grep -iE 'chrome proc' | sed 's/^/    /'
  fi
else
  say "laptop: TAK terjangkau -> skip tutup Chrome"
fi

say "=== SOP pra-hibernasi SELESAI ==="
