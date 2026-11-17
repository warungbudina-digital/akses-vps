#!/usr/bin/env bash
# install-manual-fetch-api.sh — pasang systemd unit utk manual_fetch_api.py
# (backend form manual-fetch.html, pipeline.obc-crypto.com) + rule UFW baru
# + reload nginx. Scope SAMA PERSIS install-dashboard-api.sh (hanya langkah
# ber-sudo -- manual_fetch_api.py/manual-fetch.html/31-pipeline.conf sudah
# ditulis terpisah sbg file biasa, SEBELUM script ini). Jalankan SEKALI via
# `!` (classifier blokir Claude bikin unit+ufw rule langsung -- lihat memori
# feedback_automode_classifier_gating). Lihat plan crispy-mapping-cherny.md.
set -euo pipefail

UNIT_DST="/etc/systemd/system/viral-manual-fetch-api.service"

echo "[1/5] tulis unit -> $UNIT_DST"
sudo tee "$UNIT_DST" >/dev/null <<'EOF'
[Unit]
Description=viral-pipeline manual footage fetch API (manual-fetch.html, pipeline.obc-crypto.com)
After=network.target

[Service]
User=warungbudina
WorkingDirectory=/home/warungbudina/akses-vps/viral-pipeline
Environment=MANUAL_FETCH_API_BIND=172.19.0.1
Environment=MANUAL_FETCH_API_PORT=8098
ExecStart=/usr/bin/python3 /home/warungbudina/akses-vps/viral-pipeline/manual_fetch_api.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[2/5] daemon-reload + enable + start"
sudo systemctl daemon-reload
sudo systemctl enable --now viral-manual-fetch-api

echo "[3/5] cek health lokal (lewat gateway docker, bukan localhost)"
sleep 1
curl -sf http://172.19.0.1:8098/api/manual-fetch/health && echo " <- OK" \
  || echo " <- GAGAL, cek: sudo journalctl -u viral-manual-fetch-api -n 50"

echo "[4/5] rule UFW baru (8097 sudah ada, 8098 BELUM -- ditambah manual, bukan warisan)"
sudo ufw allow from 172.19.0.0/16 to 172.19.0.1 port 8098 proto tcp comment 'nginx -> manual-fetch-api'

echo "[5/5] reload nginx (muat location /api/manual-fetch/ baru di 31-pipeline.conf)"
sudo docker exec akses-vps-nginx-1 nginx -t
sudo docker exec akses-vps-nginx-1 nginx -s reload

echo "Selesai. Tes dari luar: https://pipeline.obc-crypto.com/api/manual-fetch/health"
echo "Halaman: https://pipeline.obc-crypto.com/manual-fetch.html"
