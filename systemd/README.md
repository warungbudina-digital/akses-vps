# systemd/ — unit files yang jalan di HOST akses-vps (bukan di container)

Disalin ke `/etc/systemd/system/` secara manual (`sudo cp ... && sudo systemctl daemon-reload
&& sudo systemctl enable --now <unit>`). Ditaruh di sini supaya tercatat di git — kalau
mengedit unit yang aktif, salin balik hasil editnya ke sini.

## chrome-vps-tunnel.service

SSH local-forward dari hub ke CHROME-VPS (idcloudhost, `10.122.31.254`), bind
`172.19.0.1:13060` (gateway docker network `akses-vps_app-net`) -> `127.0.0.1:3060`
KasmVNC-nya CHROME-VPS. Satu-satunya jalur nginx (`nginx/conf.d/34-chrome-vps.conf`,
`https://chrome-vps.obc-crypto.com`) bisa menjangkau KasmVNC yang sengaja bind
`127.0.0.1`-saja di sisi CHROME-VPS. Dibatasi `ufw allow from 172.19.0.0/16 to
172.19.0.1 port 13060` — port ini TIDAK reachable dari luar host sama sekali,
cuma dari container di app-net.

Kalau mau ganti profil (bukan `balibruntattour`), edit angka port `3060` di
`-L` (lihat tabel port per-profil di `chromium-cookie-station/README.md`) lalu
`sudo systemctl daemon-reload && sudo systemctl restart chrome-vps-tunnel`.
