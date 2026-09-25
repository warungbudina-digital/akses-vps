#!/usr/bin/env bash
# Permanenkan rute MTU hub -> Cloud Shell balibruntattour (.60).
#
# Masalah (ditemukan 2026-09-25): wg0 hub MTU 1420, wg0 di .60 MTU 1380. Paket
# TCP besar dari hub ke .60 dibuang diam-diam → request HTTP dgn body >~1.3KB ke
# browser API .60 menggantung selamanya (respons besar arah sebaliknya aman).
# Fix: rute khusus 10.66.66.60/32 ber-MTU 1380 (peer lain tak tersentuh).
#
# Skrip ini menambah SATU baris PostUp ke /etc/wireguard/wg0.conf (idempoten,
# backup dulu). `|| true` memastikan wg0 tetap naik walau perintah rute gagal.
# Tak me-restart WireGuard — rute runtime juga dipasang langsung.
set -euo pipefail

CONF=/etc/wireguard/wg0.conf
LINE='PostUp = ip route replace 10.66.66.60/32 dev wg0 src 10.66.66.1 mtu 1380 || true'

if sudo grep -qF "$LINE" "$CONF"; then
  echo "Sudah ada di $CONF — tak diubah."
else
  BAK="$CONF.bak-$(date +%Y%m%d-%H%M%S)-mtu60"
  sudo cp -p "$CONF" "$BAK"
  # sisipkan setelah baris PostUp pertama (bagian [Interface])
  sudo awk -v add="$LINE" '
    { print }
    !done && /^PostUp[[:space:]]*=/ {
      print "# MTU jalur hub->Cloud Shell .60 lebih kecil (wg0 .60 = 1380); tanpa ini body HTTP >~1.3KB ke .60 menggantung (2026-09-25)."
      print add; done=1
    }' "$BAK" | sudo tee "$CONF" >/dev/null
  echo "Ditambahkan. Backup: $BAK"
  sudo diff "$BAK" "$CONF" || true
fi

sudo ip route replace 10.66.66.60/32 dev wg0 src 10.66.66.1 mtu 1380
echo "Rute aktif:"; ip route show 10.66.66.60
