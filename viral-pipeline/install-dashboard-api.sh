#!/usr/bin/env bash
# install-dashboard-api.sh — pasang systemd unit utk dashboard_api.py (backend
# form input URL pipeline.obc-crypto.com/input.html) + reload nginx supaya
# proxy /api/ aktif. Jalankan SEKALI via `!` (butuh sudo, classifier blokir
# Claude bikin unit baru langsung -- lihat memori feedback_automode_classifier_gating).
set -euo pipefail

UNIT_DST="/etc/systemd/system/viral-dashboard-api.service"

echo "[1/4] tulis unit -> $UNIT_DST"
sudo tee "$UNIT_DST" >/dev/null <<'EOF'
[Unit]
Description=viral-pipeline dashboard input API (enqueue URL via web, pipeline.obc-crypto.com/input.html)
After=network.target

[Service]
User=warungbudina
WorkingDirectory=/home/warungbudina/akses-vps/viral-pipeline
Environment=DASHBOARD_API_BIND=172.19.0.1
Environment=DASHBOARD_API_PORT=8097
ExecStart=/usr/bin/python3 /home/warungbudina/akses-vps/viral-pipeline/dashboard_api.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[2/4] daemon-reload + enable + start"
sudo systemctl daemon-reload
sudo systemctl enable --now viral-dashboard-api

echo "[3/4] cek health lokal (lewat gateway docker, bukan localhost)"
sleep 1
curl -sf http://172.19.0.1:8097/api/health && echo " <- OK" || echo " <- GAGAL, cek: sudo journalctl -u viral-dashboard-api -n 50"

echo "[4/4] reload nginx (muat location /api/ baru di 31-pipeline.conf)"
sudo docker exec akses-vps-nginx-1 nginx -t
sudo docker exec akses-vps-nginx-1 nginx -s reload

echo "Selesai. Tes dari luar: https://pipeline.obc-crypto.com/api/health"
