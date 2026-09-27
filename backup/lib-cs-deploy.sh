#!/usr/bin/env bash
# =====================================================================
# lib-cs-deploy.sh — library BERSAMA (bukan skrip berdiri sendiri, di-
# `source` saja) berisi 3 fungsi deploy_<profil> untuk node Cloud Shell
# (yuni/.50, balibruntattour/.60, gogobuda/.61). Dipakai oleh DUA
# pemanggil:
#   - cs-auto-deploy.sh   (cron */5, jaring pengaman sepanjang hari)
#   - wake-orchestrator.sh (alur bertahap sekuensial pasca-wake)
# supaya logika deploy TIDAK dobel-tulis di dua tempat (sumber-tunggal).
#
# KONTRAK tiap fungsi deploy_<profil>:
#   - Input: tidak ada (semua config lewat env var/file kredensial tetap).
#   - Output: tulis progres ke stdout (pemanggil yg atur redirect ke log).
#   - Return: 0 = SEHAT TERVERIFIKASI (healthz/health beneran true, bukan
#             cuma "command sukses") -- 1 = GAGAL/timeout/belum reachable.
#   - Blocking/sinkron: fungsi BARU return setelah verifikasi selesai
#     (bisa makan menit, terutama yuni yg build ML ~10-15mnt kalau image
#     belum ada). Pemanggil yg atur timeout keseluruhan kalau perlu.
# =====================================================================

CS_ADMIN_KEY="${CS_ADMIN_KEY:-$HOME/.ssh/akses-vps-cloudshell-admin}"
# ⚠️ StrictHostKeyChecking=no + UserKnownHostsFile=/dev/null (BUKAN accept-new)
# -- ditemukan 2026-08-24 saat pengujian live: Cloud Shell EPHEMERAL berarti
# VM di IP yg SAMA (.50/.60/.61) dapat host-key BARU tiap wake. `accept-new`
# cuma otomatis terima kalau BELUM ada entri sama sekali -- begitu ada entri
# lama (dari wake sebelumnya) yg beda, ssh MENOLAK KONEKSI TOTAL ("Host key
# has changed", dikira MITM) tanpa fallback apa pun. Ini bikin reachable_cs()
# gagal DETERMINISTIK (bukan soal timing/laptop) di wake KEDUA dst untuk
# profil manapun -- persis pola yg bikin balibruntattour+gogobuda "GAGAL
# (soft)" di uji coba manual hari ini padahal bootstrap-nya sendiri sukses.
# Aman dimatikan krn IP ini HANYA reachable via WireGuard mesh privat kita
# sendiri (bukan internet terbuka) -- pinning host-key tak menambah proteksi
# nyata di sini, WG tunnel + admin SSH key sudah jadi trust boundary asli.
CS_SSHOPTS=(-i "$CS_ADMIN_KEY" -o IdentitiesOnly=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes)

# reachable_cs <user@ip> -> 0/1, cek SSH cepat (bukan cuma ping, krn WG bisa
# up tapi sshd di VM belum siap sesaat setelah bootstrap).
#
# ⚠️ 2026-08-31: versi lama `ssh ... true 2>/dev/null` MEMBUANG stderr, jadi
# "Permission denied (publickey)" TAK BISA dibedakan dari "VM mati" -- keduanya
# cuma muncul sbg "belum reachable" di log. Akibatnya kondisi kunci-admin-hilang
# tersamar sbg recycle biasa (dikonfirmasi insiden 2026-08-30 22:40 WITA: node
# ping OK + sshd menjawab, tapi kunci ditolak, dan tak seorang pun tahu).
# Beda keduanya PENTING secara operasional:
#   - VM mati        -> `Connection timed out`; menunggu wake berikutnya WAJAR.
#   - kunci ditolak  -> VM masih HIDUP; menunggu TAK menyembuhkan apa pun,
#                       node wajib di-bootstrap ulang (buka tab lagi).
# Return code SENGAJA tak berubah (0 = reachable) supaya semua pemanggil lama
# berperilaku persis sama; yg ditambah cuma peringatan eksplisit ke stderr,
# dibatasi SEKALI per host per proses biar loop polling tak membanjiri log.
CS_LAST_SSH_ERR=""

reachable_cs() {
  local host="$1" err rc=0 seen_var
  # `|| rc=$?` wajib: lib ini di-source di skrip ber-`set -e`, tanpa itu
  # assignment yg gagal akan mematikan seluruh skrip pemanggil.
  err="$(ssh "${CS_SSHOPTS[@]}" "$host" true 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ]; then CS_LAST_SSH_ERR=""; return 0; fi
  CS_LAST_SSH_ERR="$err"
  if printf '%s' "$err" | grep -qi 'permission denied'; then
    seen_var="CS_KEYWARN_$(printf '%s' "$host" | tr -c 'A-Za-z0-9' '_')"
    if [ -z "${!seen_var:-}" ]; then
      {
        echo "!!! $host: VM HIDUP tapi MENOLAK kunci admin (Permission denied)."
        echo "    Ini BUKAN recycle biasa. Dugaan: watchdog kunci mati (PTY tab putus)"
        echo "    sementara VM+wg0 terus hidup, lalu Cloud Shell me-reset /etc/ssh/keys."
        echo "    Node ini butuh BOOTSTRAP ULANG -- menunggu tak akan menyembuhkannya."
      } >&2
      printf -v "$seen_var" '%s' 1
    fi
  fi
  return "$rc"
}

# _locked_deploy <nama-profil> <nama-fungsi-impl> — SERIALISASI panggilan
# deploy_<profil> lintas-PROSES (bukan cuma lintas-thread dlm 1 skrip).
# WAJIB ada: cs-auto-deploy.sh (cron tiap 5mnt) dan wake-orchestrator.sh
# (jalur utama pasca-wake) SAMA-SAMA bisa memanggil deploy_yuni dst, dan
# tanpa lock ini keduanya bisa jalan BERSAMAAN kalau jadwalnya kebetulan
# tumpang tindih -> docker build dobel-jalan bersamaan pd image/tag yg
# SAMA (kejadian nyata 2026-08-16 saat testing: 2 proses `docker build`
# rebutan, boros CPU+network, berpotensi hasil akhir tak terduga kalau
# keduanya menulis tag sama nyaris berbarengan).
# Nunggu (BUKAN langsung gagal) sampai lock lain kelar, maks
# CS_DEPLOY_LOCK_WAIT detik (default 1200 = 20mnt) -- kalau invocation
# lain lagi jalan, lebih aman antre drpd race; begitu dapat giliran,
# fast-path healthz di tiap fungsi bikin panggilan ke-2 ini cepat
# (langsung "sudah sehat, skip").
# ⚠️ Sebelumnya default 900 (15mnt) -- kejadian nyata 2026-08-24:
# cs-auto-deploy.sh rebuild yuni fresh-VM (ML: whisper+CLIP, unduh
# ~139MB) makan ~17mnt (05:05Z-05:22:35Z), sedangkan wake-orchestrator.sh
# yg antre lock sama nyerah pas 900s (05:22:08Z) -- KALAH 27 DETIK dari
# saat lock dilepas. Akibatnya deploy yuni SUKSES (via cs-auto-deploy)
# tapi wake-orchestrator lapor GAGAL & stop-total (strict sequential),
# balibruntattour+gogobuda tak pernah dicoba. 1200s kasih margin aman
# di atas rebuild terlama yg pernah terekam.
_locked_deploy() {
  # ⚠️ WAJIB baris terpisah (bukan `local a=$1 b=$a` dlm 1 command) --
  # semua sisi-kanan di `local a=X b=$a` di-expand DULU sblm assignment
  # manapun jalan (word-expansion command dieval sblm eksekusi), jadi
  # `$a` di assignment ke-2 masih merujuk scope LUAR (unbound under -u).
  # Kejadian nyata 2026-08-16: bikin cs-auto-deploy.sh crash tiap tick.
  local name="$1"
  local fn="$2"
  local lockfile="/tmp/.cs-deploy-${name}.lock"
  local wait="${CS_DEPLOY_LOCK_WAIT:-1200}"
  local fd
  eval "exec {fd}>\"$lockfile\""
  if ! flock -w "$wait" "$fd"; then
    echo ".$name: GAGAL dapat lock deploy dlm ${wait}s (invocation lain nyangkut?) -> batal."
    eval "exec {fd}>&-"
    return 1
  fi
  "$fn"
  local rc=$?
  eval "exec {fd}>&-"
  return $rc
}

# ---------------------------------------------------------------------
# deploy_yuni — .50, viral_analyzer V2 (ML: whisper+CLIP)
# ---------------------------------------------------------------------
deploy_yuni() { _locked_deploy yuni _deploy_yuni_impl; }
_deploy_yuni_impl() {
  local host="warungbudina@10.66.66.50"
  if ! reachable_cs "$host"; then
    echo ".50 (yuni) belum reachable."
    return 1
  fi
  echo ".50 (yuni) reachable -> pastikan analyzer V2 (ML) jalan"
  local is_v2
  is_v2="$(ssh "${CS_SSHOPTS[@]}" "$host" 'bash -s' <<'CHECKEOF' 2>/dev/null
H=$(curl -sf http://127.0.0.1:9021/healthz 2>/dev/null)
if echo "$H" | grep -q '"asr": *true' && echo "$H" | grep -q '"semantic": *true'; then
  echo 1
else
  echo 0
fi
CHECKEOF
)"
  [ -z "$is_v2" ] && is_v2=0
  if [ "$is_v2" = "1" ]; then
    echo ".50 analyzer V2 SUDAH jalan sehat, skip rebuild."
    return 0
  fi
  # container lama (kalau ada) BUKAN V2 -> bring-up-analyzer.sh sendiri tak
  # deteksi varian (cuma cek /healthz ada-tidaknya), jadi hapus dulu.
  ssh "${CS_SSHOPTS[@]}" "$host" 'docker rm -f viral_analyzer 2>/dev/null || true'
  if ssh "${CS_SSHOPTS[@]}" "$host" 'bash -s -- v2' < "$HOME/viral-pipeline/bring-up-analyzer.sh"; then
    echo ".50 analyzer V2 bring-up OK (healthz terverifikasi oleh bring-up-analyzer.sh sendiri)."
    return 0
  fi
  echo ".50 analyzer V2 bring-up GAGAL."
  return 1
}

# ---------------------------------------------------------------------
# deploy_balibruntattour — .60, full-tool-browser
# ---------------------------------------------------------------------
deploy_balibruntattour() { _locked_deploy balibruntattour _deploy_balibruntattour_impl; }
_deploy_balibruntattour_impl() {
  local host="balibruntattour@10.66.66.60"
  if ! reachable_cs "$host"; then
    echo ".60 (balibruntattour) belum reachable."
    return 1
  fi
  echo ".60 (balibruntattour) reachable -> bring-up browser"
  if bash "$HOME/akses-vps/backup/bring-up-browser.sh"; then
    echo ".60 browser bring-up OK (health+auth terverifikasi oleh bring-up-browser.sh sendiri)."
    return 0
  fi
  echo ".60 browser bring-up GAGAL."
  return 1
}

# ---------------------------------------------------------------------
# deploy_gogobuda — .61, n8n-uploader (repo mcp-video-editor)
# ---------------------------------------------------------------------
deploy_gogobuda() { _locked_deploy gogobuda _deploy_gogobuda_impl; }
_deploy_gogobuda_impl() {
  # .61 (gogobuda) KINI = worker SCRAPER riset tren TikTok (requests-only), BUKAN
  # n8n (n8n medsos pindah ke CHROME-VPS, 27/9). Deploy RINGAN: scp kode
  # scraper-worker + watchlist, pastikan `requests`, verifikasi modul importable.
  # Idempoten (dipanggil cron */5 begitu laptop boot & .61 naik); file kecil, nol build.
  local host="gogobuda65@10.66.66.61"
  local sw="$HOME/akses-vps/scraper-worker"
  local wl="$HOME/akses-vps/social-analytics/tiktok_watchlist.json"
  local rdir="scraper-worker"

  if ! reachable_cs "$host"; then
    echo ".61 (gogobuda) belum reachable."
    return 1
  fi

  ssh "${CS_SSHOPTS[@]}" "$host" "mkdir -p $rdir" || { echo ".61 (gogobuda) mkdir gagal."; return 1; }
  if ! scp "${CS_SSHOPTS[@]}" "$sw/tiktok_scraper.py" "$sw/run_worker.py" "$host:$rdir/" >/dev/null 2>&1; then
    echo ".61 (gogobuda) scp kode scraper GAGAL."
    return 1
  fi
  if [ -f "$wl" ]; then
    scp "${CS_SSHOPTS[@]}" "$wl" "$host:$rdir/watchlist.json" >/dev/null 2>&1 \
      || echo ".61 (gogobuda) WARN: watchlist tak terkirim (deploy lanjut)."
  fi

  # requests biasanya sudah ada di Cloud Shell; pasang bila tidak.
  ssh "${CS_SSHOPTS[@]}" "$host" 'python3 -c "import requests" 2>/dev/null || pip install --quiet --user requests' \
    || { echo ".61 (gogobuda) requests tak bisa dipasang."; return 1; }

  # SEHAT (kontrak: 0 = verified) = modul scraper importable + kelas kunci ada.
  if ssh "${CS_SSHOPTS[@]}" "$host" "cd $rdir && python3 -c 'import tiktok_scraper as t; assert hasattr(t,\"TikTokScraper\")'" >/dev/null 2>&1; then
    echo ".61 (gogobuda) scraper-worker SEHAT terverifikasi (kode + requests siap)."
    return 0
  fi
  echo ".61 (gogobuda) scraper-worker verifikasi import GAGAL."
  return 1
}

# ---------------------------------------------------------------------
# deploy_ogis — .8, full-tool-browser (instance scraper terpisah, akun
# maydualapan8@gmail.com / Chrome "Ogis-Chain" di laptop). Reuse
# bring-up-browser.sh APA ADANYA lewat env override C60_HOST/BROWSER_API
# (skrip itu sudah baca dari env, pola sama dgn browser-db-backup.sh) --
# TIDAK ada script baru, cuma instance kedua dari stack yg sama.
# Ditambahkan 2026-08-29 (Fase 1 onboarding profil ke-4 wake-orchestrator).
# ---------------------------------------------------------------------
deploy_ogis() { _locked_deploy ogis _deploy_ogis_impl; }
_deploy_ogis_impl() {
  local host="maydualapan8@10.66.66.8"
  if ! reachable_cs "$host"; then
    echo ".8 (ogis) belum reachable."
    return 1
  fi
  echo ".8 (ogis) reachable -> bring-up browser (instance scraper terpisah)"
  local browser_rc=1
  if C60_HOST="$host" BROWSER_API="http://${host#*@}:8080" \
     bash "$HOME/akses-vps/backup/bring-up-browser.sh"; then
    echo ".8 ogis browser bring-up OK (health+auth terverifikasi oleh bring-up-browser.sh sendiri)."
    browser_rc=0
  else
    echo ".8 ogis browser bring-up GAGAL."
  fi

  # Stack Ollama+RAG mandiri + 5 profil browser + link Gdrive -- SENGAJA
  # independen dari status browser_rc di atas (2 stack terpisah, lihat
  # akses-vps/ogis-vault/README.md). Kegagalan di sini TIDAK menjatuhkan
  # keseluruhan deploy_ogis (browser tetap jadi syarat utama profil "OK"
  # di wake-orchestrator) -- cuma dilog, supaya gampang diaudit terpisah.
  if bash "$HOME/akses-vps/ogis-vault/bring-up-ogis-vault.sh"; then
    echo ".8 ogis-vault (Ollama+index) bring-up OK."
  else
    echo ".8 ogis-vault (Ollama+index) bring-up GAGAL (tak menjatuhkan status browser)."
  fi
  bash "$HOME/akses-vps/ogis-vault/setup-browser-profiles.sh" \
    || echo ".8 setup-browser-profiles GAGAL/no-op (lihat log di atas)."
  bash "$HOME/akses-vps/ogis-vault/setup-gdrive-remotes.sh" \
    || echo ".8 setup-gdrive-remotes GAGAL/no-op (lihat log di atas)."

  return "$browser_rc"
}
