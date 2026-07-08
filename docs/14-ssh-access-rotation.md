# 14 — SSH Access & Key Rotation (AKSES-VPS)

## Akses saat ini

- Host: `warungbudina@103.217.144.104`
- Autentikasi: SSH key (ed25519) saja, **satu key** terdaftar di
  `~/.ssh/authorized_keys` di VPS — bukan multi-key, bukan password auth.
- Komentar key saat ini: `warungbudina@akses-vps`.

Cek key yang terdaftar sekarang:

```bash
ssh warungbudina@103.217.144.104 "cat ~/.ssh/authorized_keys"
ssh warungbudina@103.217.144.104 "ssh-keygen -lf ~/.ssh/authorized_keys"   # lihat fingerprint tanpa expose key mentah
```

## Kapan harus rotate

- Private key pernah terekspos di tempat yang tidak seharusnya (chat, log,
  screen share, dsb.) — anggap bocor begitu private key-nya pernah terlihat
  di luar penyimpanan aman, walaupun cuma sekali dan cuma ke pihak yang
  dipercaya.
- Rutin (disarankan tiap 90 hari, selaras dengan rekomendasi rotasi secret
  lain di `docs/08-security-hardening-checklist.md`).
- Setelah ada perubahan tim/akses (orang yang sebelumnya butuh akses tidak
  lagi butuh).

## Cara rotate (manual, step by step)

Prinsip: **selalu tambah key baru dulu, baru hapus yang lama** — supaya
tidak ke-lockout kalau ada masalah di tengah jalan.

### 1. Generate keypair baru (di mesin client, BUKAN di VPS)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/akses-vps_new -C "warungbudina@akses-vps-$(date +%Y%m%d)"
```

### 2. Tambahkan public key baru ke VPS (masih pakai key lama untuk login)

```bash
ssh-copy-id -i ~/.ssh/akses-vps_new.pub warungbudina@103.217.144.104
```

Atau manual kalau `ssh-copy-id` tidak tersedia:

```bash
cat ~/.ssh/akses-vps_new.pub | ssh warungbudina@103.217.144.104 "cat >> ~/.ssh/authorized_keys"
```

### 3. Tes key baru bekerja SEBELUM lanjut

```bash
ssh -i ~/.ssh/akses-vps_new warungbudina@103.217.144.104 "echo BERHASIL"
```

Kalau gagal — **jangan lanjut ke langkah 4**. Key lama masih berfungsi
sebagai fallback selama langkah ini belum sukses.

### 4. Hapus key LAMA dari VPS

```bash
ssh -i ~/.ssh/akses-vps_new warungbudina@103.217.144.104 \
  "grep -v '<fingerprint-atau-potongan-unik-key-lama>' ~/.ssh/authorized_keys > /tmp/ak.tmp && mv /tmp/ak.tmp ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### 5. Konfirmasi cuma key baru yang tersisa

```bash
ssh -i ~/.ssh/akses-vps_new warungbudina@103.217.144.104 "cat ~/.ssh/authorized_keys"
```

### 6. Bersihkan private key lama

Hapus dari penyimpanan lokal, password manager, atau tempat lain private
key lama itu pernah disimpan. Nilainya sudah tidak berguna lagi setelah
langkah 4, tapi baik untuk dibersihkan juga.

## Catatan

- Prosedur ini murni untuk **akses SSH ke host VPS itu sendiri**
  (`warungbudina@103.217.144.104`) — beda dari rotasi key WireGuard per-client
  (lihat `docs/12-wireguard-vpn.md`) atau secret aplikasi (JWT, API key
  internal, password DB — lihat `docs/08-security-hardening-checklist.md`).
- VPS ini cuma menerima key-based auth (tidak ada password auth ke SSH),
  jadi kehilangan akses ke SATU-SATUNYA private key yang valid berarti
  lockout total kecuali masih ada akses lain (console provider, dsb.) —
  makanya langkah 1-3 di atas selalu "tambah dulu, baru hapus", tidak pernah
  overwrite langsung.
