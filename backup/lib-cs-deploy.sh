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
reachable_cs() {
  ssh "${CS_SSHOPTS[@]}" "$1" true 2>/dev/null
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
  local host="gogobuda65@10.66.66.61"
  local cred="$HOME/.config/n8n-uploader/credentials.env"
  local oauth="$HOME/.config/n8n-uploader/oauth-client.env"
  local token_src="$HOME/.config/n8n-uploader/token.json"
  # gfootage (2026-08-24, fix gap): akun Gdrive TEMPAT hasil export Reel RN7
  # benar2 mendarat, beda dari akun gdrive (gogobuda65 sendiri) yg dipasang
  # RCLONE_CLIENT_ID/SECRET di atas. Sumbernya rclone.conf HUB SENDIRI (sudah
  # punya remote [gfootage] sehat, dipakai skrip lain di hub) - ekstrak
  # stanza-nya (header sampai section berikutnya/EOF), base64, kirim ke
  # deploy.sh via env (lihat configure_rclone() di mcp-video-editor). OPSIONAL:
  # kalau file/section tak ada, deploy tetap lanjut, cuma remote [gfootage]
  # yg absen di gogobuda (bukan blocker deploy keseluruhan).
  local gfootage_conf="$HOME/.config/rclone/rclone.conf"
  local gfootage_b64=""
  if [ -f "$gfootage_conf" ]; then
    gfootage_b64="$(awk '/^\[gfootage\]/{p=1} /^\[/ && !/^\[gfootage\]/{p=0} p' "$gfootage_conf" | base64 -w0 2>/dev/null || true)"
  fi
  if [ -z "$gfootage_b64" ]; then
    echo ".61 (gogobuda) WARN: remote [gfootage] tak ditemukan di $gfootage_conf - deploy lanjut, tapi workflow n8n yg baca VN-exports akan gagal sampai ini diisi."
  fi

  if ! reachable_cs "$host"; then
    echo ".61 (gogobuda) belum reachable."
    return 1
  fi
  if [ ! -f "$cred" ] || [ ! -f "$oauth" ]; then
    echo ".61 (gogobuda) reachable TAPI kredensial belum lengkap ($cred / $oauth) - skip deploy."
    return 1
  fi

  echo ".61 (gogobuda) reachable -> bring-up n8n-uploader"
  # shellcheck disable=SC1090
  set -a; . "$cred"; . "$oauth"; set +a

  local token_b64=""
  if [ -f "$token_src" ]; then
    token_b64="$(base64 -w0 "$token_src" 2>/dev/null || base64 "$token_src" | tr -d '\n')"
  fi

  # (2026-08-25 fix: kondisi ini SEMPAT terbalik -- `!` bikin cabang "GAGAL"
  # kepicu justru saat ssh SUKSES exit 0, dan sebaliknya lolos ke healthz-loop
  # di bawah justru saat GAGAL. Terbukti reproducible: cs-auto-deploy re-run
  # idempoten [Container n8n Running] TETAP lapor "GAGAL" krn bug ini.)
  if ssh "${CS_SSHOPTS[@]}" "$host" bash -s <<REMOTE_EOF
set -euo pipefail
cd ~
if [ -d mcp-video-editor/.git ]; then
  cd mcp-video-editor && git pull --ff-only
else
  git clone https://github.com/warungbudina-digital/mcp-video-editor.git
  cd mcp-video-editor
fi
TOKEN_B64='$token_b64'
if [ -n "\$TOKEN_B64" ]; then
  echo "\$TOKEN_B64" | base64 -d > token.json
fi
export DB_POSTGRESDB_HOST='$DB_POSTGRESDB_HOST'
export DB_POSTGRESDB_PORT='$DB_POSTGRESDB_PORT'
export DB_POSTGRESDB_DATABASE='$DB_POSTGRESDB_DATABASE'
export DB_POSTGRESDB_USER='$DB_POSTGRESDB_USER'
export DB_POSTGRESDB_PASSWORD='$DB_POSTGRESDB_PASSWORD'
export RCLONE_CLIENT_ID='$RCLONE_CLIENT_ID'
export RCLONE_CLIENT_SECRET='$RCLONE_CLIENT_SECRET'
export GFOOTAGE_RCLONE_STANZA_B64='$gfootage_b64'
export N8N_ENCRYPTION_KEY='$N8N_ENCRYPTION_KEY'
export N8N_BASIC_AUTH_USER='$N8N_BASIC_AUTH_USER'
export N8N_BASIC_AUTH_PASSWORD='$N8N_BASIC_AUTH_PASSWORD'
bash n8n-script.sh
REMOTE_EOF
  then
    echo ".61 n8n-uploader bring-up perintah SELESAI, TAPI belum diverifikasi sehat -> cek healthz."
  else
    echo ".61 n8n-uploader bring-up GAGAL (SSH/script exit != 0)."
    return 1
  fi

  # n8n-script.sh sendiri TIDAK memverifikasi health (beda dari bring-up-analyzer.sh
  # / bring-up-browser.sh) -> verifikasi eksplisit di sini, poll container Up +
  # /healthz, MAKS 90s (n8n cuma start image yg sudah di-pull, bukan build lama).
  local i st health
  for i in $(seq 1 18); do
    st="$(ssh "${CS_SSHOPTS[@]}" "$host" "docker inspect -f '{{.State.Status}}' n8n 2>/dev/null || echo none")"
    if [ "$st" = "running" ]; then
      health="$(ssh "${CS_SSHOPTS[@]}" "$host" "curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:5678/healthz 2>/dev/null || echo 000")"
      if [ "$health" = "200" ]; then
        echo ".61 n8n-uploader SEHAT terverifikasi (container running, /healthz 200)."
        return 0
      fi
    fi
    sleep 5
  done
  echo ".61 n8n-uploader TAK sehat setelah 90s menunggu (container status=$st, healthz=${health:-belum-dicek}) -> cek: ssh gogobuda65@10.66.66.61 'docker logs n8n'."
  return 1
}
