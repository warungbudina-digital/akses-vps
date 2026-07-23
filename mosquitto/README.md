# Mosquitto Setup Notes

## Membuat user/password
```bash
docker run --rm -v $(pwd)/config:/mosquitto/config eclipse-mosquitto \
  mosquitto_passwd -b /mosquitto/config/passwd grpc-service '<STRONG_PASSWORD>'
docker run --rm -v $(pwd)/config:/mosquitto/config eclipse-mosquitto \
  mosquitto_passwd -b /mosquitto/config/passwd genieacs-service '<STRONG_PASSWORD>'
docker run --rm -v $(pwd)/config:/mosquitto/config eclipse-mosquitto \
  mosquitto_passwd -b /mosquitto/config/passwd monitor '<STRONG_PASSWORD>'
```
File `passwd` berisi hash (bukan plaintext) — tetap **jangan** commit ke git, sudah masuk `.gitignore`.

## Sertifikat TLS
Listener TLS (`8883`) **saat ini dinonaktifkan** di `mosquitto.conf` — cert
domain asli belum ada. Deployment ini sudah tidak memakai certbot/Let's
Encrypt (TLS publik domain lain ditangani Cloudflare Tunnel, lihat
`docs/06-component-explanation.md`), jadi kalau listener 8883 ini
diaktifkan lagi nanti, sumber `mosquitto/certs/{ca.pem,fullchain.pem,privkey.pem}`
perlu direncanakan ulang — bukan lagi disalin dari `certbot/renew-hook.sh`
yang sudah tidak ada di repo ini.

## Kenapa `per_listener_settings true`?
Supaya listener 1883 (internal-only, tidak pernah publish ke luar lewat NAT) dan listener 8883/9001 (yang lebih exposed) bisa punya kebijakan ACL/auth terpisah bila suatu saat perlu dibedakan.
