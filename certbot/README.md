# Let's Encrypt / Certbot Setup

## Penerbitan awal (sekali jalan, sebelum service certbot renewal loop aktif)

```bash
docker run --rm \
  -v letsencrypt-certs:/etc/letsencrypt \
  -v letsencrypt-www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  --email admin@domain.com --agree-tos --no-eff-email \
  -d acs.domain.com -d cwmp.domain.com -d mqtt.domain.com \
  -d api.domain.com -d grafana.domain.com -d prometheus.domain.com
```

Syarat: nginx sudah jalan dan melayani `/.well-known/acme-challenge/` di port 80
untuk semua subdomain di atas (lihat `nginx/conf.d/*.conf`), dan DNS record
tiap subdomain sudah mengarah ke IP publik VPS/CHR.

## Auto Renewal

Container `certbot` di `docker-compose.reference.yml` menjalankan loop
`certbot renew` setiap 12 jam (certbot sendiri hanya benar-benar renew kalau
sertifikat < 30 hari dari expired, jadi aman dijalankan sesering ini).

Setelah renewal berhasil, `--deploy-hook /renew-hook.sh` dijalankan otomatis
untuk reload nginx (lihat `renew-hook.sh`).

## Di MikroTik CHR (tanpa docker-compose)

Jalankan certbot sebagai container terpisah dengan mount volume yang sama
dengan yang dipakai nginx (`/container mounts add name=nginx-certs ...`),
lalu jadwalkan renewal lewat RouterOS scheduler yang men-trigger
`docker exec certbot certbot renew` — atau lebih simpel, jalankan certbot
sebagai one-shot container yang di-start oleh `/system scheduler` tiap hari.

```
/system scheduler add name=certbot-renew interval=1d on-event=":execute script=./certbot-renew.sh"
```
