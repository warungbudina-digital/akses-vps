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
`mosquitto/certs/{ca.pem,fullchain.pem,privkey.pem}` di-symlink/copy dari output certbot (`certbot/renew-hook.sh` menyalin otomatis setelah renewal).

## Kenapa `per_listener_settings true`?
Supaya listener 1883 (internal-only, tidak pernah publish ke luar lewat NAT) dan listener 8883/9001 (yang lebih exposed) bisa punya kebijakan ACL/auth terpisah bila suatu saat perlu dibedakan.
