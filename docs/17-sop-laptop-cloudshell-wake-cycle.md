# 17 — SOP Siklus Wake↔Hibernasi Laptop SUARAHATI (Cloud Shell 3-profil)

> Dokumen ini ditulis SANGAT eksplisit (tabel, langkah bernomor, tanpa
> istilah tersirat) supaya bisa diikuti bahkan oleh model AI yang lemah
> atau operator yang baru pertama kali pegang sistem ini. Kalau ragu soal
> apa yang HARUS terjadi di suatu tahap, jawabannya selalu ada di sini —
> jangan menebak dari nama file.

## 1. Apa sistem ini

Laptop **SUARAHATI** (ASUS X450EA, lemah — AMD E1-2500, 2 core) bukan
node 24/7. Dia **hibernate tiap malam, wake tiap pagi**, dan selama
"hidup" dia jadi host untuk **3 sesi Google Cloud Shell** (VM gratis
ephemeral Google, masing-masing terikat ke satu akun/profil Chrome),
tiap sesi menjalankan satu project:

| Profil Chrome (laptop) | Akun Google | WireGuard IP | Project yang dideploy |
|---|---|---|---|
| `yuni` (Profile 10) | warungbudina | `10.66.66.50` | `viral_analyzer` V2 (ML: whisper+CLIP) |
| `balibruntattour` (Profile 29) | balibruntat | `10.66.66.60` | `full-tool-browser` |
| `gogobuda` (Profile 26) | Gogo | `10.66.66.61` | `n8n-uploader` (repo `mcp-video-editor`) |

Karena laptopnya lemah, membuka ketiga tab Cloud Shell **sekaligus**
bikin CPU kewalahan → banyak gagal (bukti nyata 2026-08-16: 2 dari 3
gagal saat dibuka bersamaan). Makanya alur sekarang **bertahap satu
per satu**, lihat §3.

## 2. Siklus harian (jam WITA, UTC = WITA − 8)

| Jam WITA | Jam UTC | Kejadian | Dikendalikan dari |
|---|---|---|---|
| 08:45 | 00:45 | Laptop **wake** (RTC scheduled-wake, task `NodeWake-0845`) | Laptop (Task Scheduler lokal) |
| 08:45:20 | 00:45:20 | `ensure-chrome-cdp` pastikan Chrome+CDP port 9222 hidup | Laptop |
| **08:48** | **00:48** | **`wake-orchestrator.sh` mulai** — alur bertahap 3 profil (§3) | **HUB (cron)** |
| 08-22 | 00-14 | `cs-auto-deploy.sh` jalan tiap 5 menit sbg **jaring pengaman** (§4) | HUB (cron) |
| 22:27 | 14:27 | `pre-hibernate-sop.sh` — stop container node + tutup Chrome laptop dgn rapi (§5) | HUB (cron) |
| 22:30 | 14:30 | Laptop **hibernate** (task `NodeHibernate-2230`) | Laptop (Task Scheduler lokal) |

**Prinsip kunci:** laptop TAK PERNAH mengambil keputusan sendiri soal
"buka profil mana, deploy apa" — itu semua diperintah dari **HUB**
(akses-vps, 24/7). Laptop cuma eksekutor (buka Chrome, upload file,
jalankan perintah) saat diminta. Ini supaya logika rumit (nunggu sehat,
berhenti kalau gagal, dst) hidup di satu tempat yang selalu menyala,
bukan di Windows Task Scheduler yang kaku.

## 3. Alur wake bertahap (`wake-orchestrator.sh`, di HUB)

Untuk **tiap profil, berurutan** (yuni dulu, baru balibruntattour, baru
gogobuda — urutan ini TETAP, tak berubah):

```
1. HUB kirim perintah "buka profil ini" ke laptop
   (ssh ltap-mini "schtasks /run /tn open-cs-<profil>")
        │
        ▼
2. Laptop buka 1 tab Chrome Cloud Shell profil itu SAJA
   (task open-cs-<profil> → open-cs.ps1 -Profile <nama>
    → open-and-bootstrap-cs.py --profile <nama>)
        │
        ▼
3. Laptop tunggu prompt Cloud Shell siap (maks 180 detik),
   upload script bootstrap (WireGuard+SSH admin), jalankan.
   Ini HANYA menyalakan akses (WG+SSH) — BUKAN deploy project.
        │
        ▼
4. HUB polling: apakah laptop sudah lapor "selesai" utk profil ini?
   (baca C:\chrome-cdp\open-cs.log via SSH, maks 240 detik)
        │
        ▼
5. HUB polling: apakah node Cloud Shell ini SUDAH BISA di-SSH langsung?
   (bukan cuma ping WireGuard — sshd di VM butuh beberapa detik lagi)
        │
        ▼
6. HUB jalankan fungsi deploy_<profil> (dari lib-cs-deploy.sh):
   git clone/pull → build/start container → TUNGGU SAMPAI BENAR-BENAR
   SEHAT (curl /healthz atau setara, BUKAN cuma "container ada").
   Ini BISA MAKAN WAKTU LAMA:
     - yuni (analyzer ML)  : ~1 menit (image sudah ada) s/d ~15 menit (build baru)
     - balibruntattour     : ~10 detik (sudah live) s/d ~6 menit (build baru)
     - gogobuda (n8n)      : ~10-90 detik (cuma start image, tak pernah build lama)
        │
        ▼
7a. SEHAT → lanjut ke profil berikutnya (ulang dari langkah 1)     ATAU
7b. GAGAL di tahap manapun (2-6) → BERHENTI TOTAL, profil
    berikutnya TIDAK DICOBA. Kirim notifikasi Telegram. Selesai.
```

**Kenapa "berhenti total" dan bukan "lewati saja"?** Keputusan sadar
(2026-08-16): kalau satu profil sudah bermasalah, kemungkinan besar
akar masalahnya di laptop/jaringan secara umum (bukan spesifik satu
profil) — memaksa lanjut cuma bikin kegagalan beruntun yang
membingungkan dibaca. Lebih baik berhenti, kasih tahu, biar dicek
manual dulu apa yang salah.

### Kalau semua sukses
Log `~/wake-orchestrator.log` (di HUB) berakhir dengan baris:
```
=== SEMUA 3 PROFIL TUNTAS SEHAT (yuni=OK, balibruntattour=OK, gogobuda=OK) ===
```
+ notifikasi Telegram "✅ wake-orchestrator SUKSES PENUH".

### Kalau berhenti di tengah
Log akan berhenti tepat setelah baris `!!! <profil> GAGAL: <alasan>`.
Baca alasannya — biasanya salah satu dari:
- **"trigger task tak sukses"** → laptop tak terjangkau SSH sama sekali
  (mungkin belum wake/masih boot) atau task `open-cs-<profil>` hilang
  dari Task Scheduler (cek ulang §7 kalau ini terjadi).
- **"laptop tak kunjung selesai proses bootstrap"** → tab Cloud Shell
  gagal dibuka/prompt tak muncul dlm 180s, ATAU laptop sedang sangat
  lambat. Cek `C:\chrome-cdp\open-cs.log` langsung.
- **"node tak reachable via SSH"** → bootstrap laptop kelar tapi
  WireGuard/sshd VM Cloud Shell belum naik. Bisa VM gagal provision,
  atau kredensial WG-nya bermasalah.
- **"deploy tak sehat"** → node reachable tapi project-nya gagal
  build/start. Cek detail di baris sebelumnya (biasanya ada pesan
  spesifik dari `bring-up-*.sh` atau `docker logs`).

## 4. Jaring pengaman siang hari (`cs-auto-deploy.sh`)

Tetap jalan tiap 5 menit (08:00–22:00 WITA) SETELAH `wake-orchestrator.sh`
selesai pagi. Fungsinya BUKAN lagi jalur utama — cuma jaga-jaga kalau:
- User me-refresh manual salah satu tab Cloud Shell siang hari (VM baru,
  perlu di-deploy ulang) — poller ini akan mendeteksi & membangunkan lagi
  tanpa perlu tunggu wake besok.
- Container sempat mati sendiri (crash, dsb) — poller idempoten
  membangunkan lagi.

Poller ini **best-effort per-profil, TIDAK strict-sequential** — beda
dgn `wake-orchestrator.sh`. Satu profil gagal tak menghalangi yang lain
dicoba tick berikutnya. Ini SENGAJA beda kebijakan karena konteksnya
beda: siang hari cuma jaga-jaga, bukan alur utama yang perlu ketat.

Kedua skrip (`wake-orchestrator.sh` dan `cs-auto-deploy.sh`) memanggil
fungsi deploy YANG SAMA dari **`lib-cs-deploy.sh`** — logika deploy
tidak pernah ditulis dua kali.

## 5. Penutupan malam (`pre-hibernate-sop.sh`)

Jalan 22:27 WITA (3 menit sebelum hibernate paksa jam 22:30). Urutan:

1. Untuk tiap node Cloud Shell yang masih reachable: `docker stop` semua
   container + hentikan proses `ping` keepalive. (Node yang sudah
   recycle/mati wajar dilewati — bukan error.)
2. Tutup Chrome di laptop:
   a. Coba **graceful** (`CloseMainWindow`, setara klik tombol close) —
      kasih waktu 4 detik.
   b. Kalau masih ada proses nyangkut (Cloud Shell suka ada dialog
      "leave site?" yang mengganjal), **paksa** (`Stop-Process -Force`).
   c. **PENTING (fix 2026-08-16):** setelah proses benar-benar mati,
      tulis ulang field `exit_type` jadi `"Normal"` di file Preferences
      3 profil Cloud Shell. Ini WAJIB — tanpa langkah ini, Chrome
      mengira dirinya "crash" (karena sempat di-force-kill) dan akan
      **otomatis me-restore semua tab lama** begitu dibuka lagi besok
      paginya, yang persis gejala "sisa aplikasi kemarin masih ada"
      yang pernah dikeluhkan user.

## 6. Inventaris file (siapa hidup di mana)

### Di HUB (`akses-vps`, folder `~/akses-vps/backup/`)
| File | Peran |
|---|---|
| `wake-orchestrator.sh` | Jalur utama pasca-wake, alur bertahap ketat (§3) |
| `cs-auto-deploy.sh` | Jaring pengaman 5-menitan siang hari (§4) |
| `lib-cs-deploy.sh` | **Library bersama** — 3 fungsi `deploy_yuni`/`deploy_balibruntattour`/`deploy_gogobuda`, dipakai KEDUA skrip di atas |
| `bring-up-browser.sh` | Deploy detail utk balibruntattour (dipanggil dari lib) |
| `pre-hibernate-sop.sh` | Penutupan malam (§5) |
| `send-telegram.sh` | Helper notifikasi (dipakai wake-orchestrator) |

Analyzer (`bring-up-analyzer.sh`) ada di `~/viral-pipeline/` (repo
terpisah `tool-analisa-video-viral`), dipanggil via SSH ke .50 (jalan
DI SANA, bukan di hub — beda pola dari browser/n8n yg dikendalikan
dari hub).

### Di laptop (`C:\chrome-cdp\`)
| File | Peran |
|---|---|
| `open-and-bootstrap-cs.py` | Buka tab + bootstrap. Mode `--profile <nama>` (baru, dipakai hub) ATAU tanpa argumen (mode lama all-3, cuma manual/darurat) |
| `open-cs.ps1` | Wrapper PowerShell, terima `-Profile <nama>` |
| `ensure-chrome-cdp.ps1` | Jaga CDP port 9222 tetap hidup (independen, tetap auto-trigger di wake/logon) |

### Scheduled Task di laptop
| Task | Trigger otomatis? | Kapan dipakai |
|---|---|---|
| `NodeWake-0845` | Ya, harian 08:45 | RTC wake |
| `NodeHibernate-2230` | Ya, harian 22:30 | Hibernate |
| `ensure-chrome-cdp` | Ya, tiap wake-event+logon | Jaga CDP hidup |
| `open-cs-yuni` | **Tidak** (dicabut 2026-08-16) | Hub trigger via `schtasks /run` |
| `open-cs-balibruntattour` | **Tidak** | Hub trigger via `schtasks /run` |
| `open-cs-gogobuda` | **Tidak** | Hub trigger via `schtasks /run` |
| `open-cs` (lama, all-3) | **Tidak** (dicabut 2026-08-16) | **Fallback manual/darurat SAJA** — kalau `wake-orchestrator.sh` mau di-bypass total, jalankan ini manual (`ssh ltap-mini "schtasks /run /tn open-cs"`), tapi ingat ini balik ke pola lama (3 tab sekaligus, rawan resource-starvation) |

## 7. Operasi manual / troubleshooting

**Jalankan alur wake manual (mis. laptop baru dinyalakan siang hari):**
```bash
ssh akses-vps  # atau langsung kalau sudah di hub
bash ~/akses-vps/backup/wake-orchestrator.sh
tail -f ~/wake-orchestrator.log   # pantau progres live
```

**Cek status 1 profil tanpa jalankan semuanya:**
```bash
source ~/akses-vps/backup/lib-cs-deploy.sh
deploy_yuni            # atau deploy_balibruntattour / deploy_gogobuda
echo "exit: $?"        # 0 = sehat, 1 = gagal
```

**Buka 1 tab profil manual dari hub (tanpa deploy):**
```bash
ssh ltap-mini "schtasks /run /tn open-cs-yuni"
# lalu tunggu ~1-3 menit, cek log:
ssh ltap-mini "powershell -Command \"Get-Content C:\chrome-cdp\open-cs.log -Tail 20 -Encoding Unicode\""
```

**Cek 3 task baru masih ada & tanpa trigger otomatis (harusnya begitu):**
```bash
ssh ltap-mini "powershell -Command \"Get-ScheduledTask -TaskName 'open-cs-*' | Select-Object TaskName,State\""
```

**Kalau mau kembali ke mode lama (all-3 sekaligus) sementara:**
```bash
ssh ltap-mini "schtasks /run /tn open-cs"
```
(Tak disarankan permanen — ini sumber masalah yang sedang diperbaiki
dokumen ini. Cuma utk darurat/testing.)

## 8. Riwayat perubahan
- **2026-08-16**: redesign total dari "buka 3 tab staggered lalu deploy
  async via cron 5-menitan" (banyak gagal krn resource-starvation laptop
  lemah) menjadi alur bertahap ketat per-profil (dokumen ini). Sekaligus
  fix bug Chrome auto-restore-sesi pasca `pre-hibernate-sop.sh` (§5c).
