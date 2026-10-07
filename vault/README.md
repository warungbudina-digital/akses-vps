# vault — penyimpanan sesi browser persisten (DB-VPS)

Sumber-kebenaran **sesi login** (cookies + storageState) untuk ekosistem browser,
menggantikan peran laptop SUARAHATI. Hidup di **DB-VPS** (persisten, 24/7); diakses
HANYA dari **akses-vps** (hub) karena Cloud Shell (`.60`/`.61`) di WG tak bisa capai
DB-VPS langsung (pg_hba `10.122.31.0/24`).

```
 .61 gui-chromium (login visual, 8GB)        .60 full-tool-browser (scraping)
        │ export/inject sesi                        ▲ /sessions import
        └────────► akses-vps (HUB) ◄────────────────┘
                      │ ssh db-vps 'sudo -u postgres psql'
                      ▼
               DB-VPS  schema vault  ◄── SUMBER KEBENARAN (persisten)
               CHROME-VPS (n8n) ─ baca vault bila perlu
```

## Kenapa
- SOP: analisa/scraping browser **DILARANG lewat laptop** (lihat memori
  `feedback_browser_analysis_no_laptop`). Sesi harus hidup di tier durable, bukan laptop.
- `.61` (Cloud Shell, RAM 8GB) = stasiun login GUI **on-demand** (ephemeral → BUKAN gudang).
- Simpan **SESI saja** (KB–MB), JANGAN profil Chrome penuh (GB).

## Schema (DB `scraper` @ DB-VPS, owner role `scraper`)
- `vault.profile(code PK, display_name, platform, account_email, notes, created_at, updated_at)`
- `vault.session(id, profile_code→profile, domain, cookies_netscape text, storage_state jsonb,
   captured_at, expires_at, source_node, UNIQUE(profile_code,domain))`
- `vault.audit(id, profile_code, domain, action, node, at)` — jejak push/pull/login/expire
- DDL: `vault_schema.sql` (idempoten; `SET ROLE scraper` agar objek dimiliki scraper).

## Script (jalankan DI akses-vps)
Payload cookies/json di-**base64** (`base64 -w0` → `convert_from(decode(...,'base64'),'UTF8')`)
agar kebal quote-chain bash→ssh→psql (cookies bisa berisi `'" ; spasi`).

**Simpan sesi → vault:**
```bash
./vault-push.sh <code> <domain> <cookies.txt> [storage_state.json] \
    [--node N] [--name NAMA] [--platform P] [--email E]
# contoh:
./vault-push.sh gogobud13-ig instagram.com /tmp/ig-cookies.txt /tmp/ig-ss.json \
    --name "Go Go Bud IG" --platform instagram --node .61
```

**Ambil sesi dari vault:**
```bash
./vault-pull.sh <code> <domain> [--out-cookies FILE] [--out-ss FILE] [--to60]
# --to60 : POST /sessions/<code>/import ke .60 (cookiesTxt)
./vault-pull.sh gogobud13-ig instagram.com --out-cookies /tmp/c.txt --to60
```

## Jebakan (SUDAH difix di script; jangan diulang)
1. **Banner login DB-VPS ke STDERR** → selalu `2>/dev/null` (JANGAN `sed 1,Nd` — memotong isi).
2. **`SET ROLE scraper;` membocorkan tag "SET" ke stdout `-tAc`** → JANGAN pakai di query BACA
   (postgres superuser baca `vault.*` tanpa role). Tetap pakai `SET ROLE` di query TULIS (ownership).
3. **Postgres `encode(...,'base64')` membungkus tiap 76 char** → `tr -d '\n'` sebelum `base64 -d`.
4. **`.60` `/sessions/:profile/import` memvalidasi `platform` = enum `instagram|tiktok|twitter`**;
   domain arbitrer → HTTP 400. (Fase 4: perluas enum / map domain→platform.)

## Keputusan desain (user, 2026-10-07)
- Sesi disimpan **cleartext** (bukan enkripsi) — DB-VPS privat & gated.
- `.61` **boleh login medsos** (relax SOP laptop khusus `.61`).
- Egress analisa/tarik-data & login medsos lewat **proxy residensial di-relay (Denpasar)**.
- GUI via domain publik **`browser-gui.obc-crypto.com`** (nginx hub + basic-auth) — Fase 3.

## Prasyarat
- **DB-VPS NYALA** (start di-gate → user `!`; toh n8n juga butuh). Verifikasi:
  `ssh db-vps 'sudo -n -u postgres psql -d scraper -tAc "select 1"' 2>/dev/null`
- akses-vps bisa `ssh db-vps` (sudo NOPASSWD) + capai `.60`/`.61` via WG.

## Status fase
- ✅ **Fase 1** — schema + `vault-push.sh`/`vault-pull.sh`, round-trip teruji IDENTIK.
- ⏳ Fase 2 — `gui-chromium` (noVNC) di `.61` + `bring-up-gui-61.sh` (restore sesi saat start, egress di-relay).
- ⏳ Fase 3 — nginx `browser-gui.obc-crypto.com` + auth → proxy noVNC `.61`.
- ✅ Fase 4 — `vault-pull --to60` memetakan domain → platform enum `.60` (instagram|tiktok|twitter;
  domain lain ditolak). `vault-push` mengisi `expires_at` dari cookie berexpiry paling dini.
  `vault-check.sh` (cron 06:15 WITA harian) mencatat `expiring`/`expired` ke `vault.audit`, dedupe 24 jam.
  Tidak ada auto-refresh: login ulang tetap manual (lihat jejak `expiring`).
- ⏳ Fase 5 — n8n fokus di CHROME-VPS (lepas cookie-station).
