# 17 — SOP Siklus Wake↔Hibernasi Laptop SUARAHATI (Cloud Shell 3-profil)

> Dokumen ini ditulis SANGAT eksplisit (tabel, langkah bernomor, tanpa
> istilah tersirat) supaya bisa diikuti bahkan oleh model AI yang lemah
> atau operator yang baru pertama kali pegang sistem ini. Kalau ragu soal
> apa yang HARUS terjadi di suatu tahap, jawabannya selalu ada di sini —
> jangan menebak dari nama file.

## 1. Apa sistem ini

Laptop **SUARAHATI** (ASUS X450EA, lemah — AMD E1-2500, 2 core) bukan
node 24/7. Dia **wake↔hibernate 2 SIKLUS/hari** (pagi + siang-malam,
lihat §2), dan selama "hidup" dia jadi host untuk **3 sesi Google
Cloud Shell** (VM gratis
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

## 2. Siklus harian — 2 SIKLUS/hari (jam WITA, UTC = WITA − 8)

**✅ 2026-08-16 (v2):** diubah dari 1 siklus/hari (wake pagi → hibernate
malam nonstop) jadi **2 siklus/hari** dgn jeda istirahat siang, atas
permintaan user. Karena Cloud Shell **ephemeral**, tiap wake = VM
Cloud Shell BARU (bukan lanjutan sesi lama) → project (terutama
analyzer yuni, ~13-15mnt kalau build dari nol) **bisa ke-build ulang
2×/hari**. Ini KONSEKUENSI YANG DITERIMA (keputusan user), bukan bug.

**✅ 2026-08-28 (v3): jam digeser total** (permintaan user — mulai lebih
pagi, istirahat siang lebih panjang). Wake1 08:30→**06:00**, Break
12:35→**14:00**, Wake2 13:00→**15:05** (sengaja +5mnt dari rencana awal
15:00 — rollout dieksekusi PAS lewat jam 15:00, digenapkan buffer),
Hibernate 22:45→**23:00**. Task Windows di-rename total (lihat §6).

| Jam WITA | Jam UTC | Kejadian | Dikendalikan dari |
|---|---|---|---|
| **06:00** | 22:00 (h-1) | Laptop **wake #1** (RTC, task `NodeWake-0600`) | Laptop (Task Scheduler lokal) |
| 06:00:20 | 22:00:20 (h-1) | `ensure-chrome-cdp` pastikan Chrome+CDP hidup (trigger event-wake, otomatis di KEDUA wake) | Laptop |
| **06:03** | **22:03 (h-1)** | **`wake-orchestrator.sh` mulai** — alur bertahap 3 profil, urutan balibruntattour→gogobuda→yuni (§3) | **HUB (cron)** |
| 06:00–14:00 | 22:00 (h-1)–06:00 | `cs-auto-deploy.sh` jalan tiap 5 menit sbg **jaring pengaman** (§4) | HUB (cron) |
| **13:57** | **05:57** | `pre-hibernate-sop.sh` — stop container node + tutup Chrome laptop dgn rapi (§5) | HUB (cron) |
| **14:00** | **06:00** | Laptop **break/hibernate #1** (task `NodeBreak-1400`) | Laptop (Task Scheduler lokal) |
| 14:00–15:05 | 06:00–07:05 | **Jeda istirahat ~1 jam** — laptop tidur, semua no-op wajar | — |
| **15:05** | **07:05** | Laptop **wake #2** (RTC, task `NodeWake2-1505`) | Laptop (Task Scheduler lokal) |
| **15:08** | **07:08** | **`wake-orchestrator.sh` mulai lagi** — alur bertahap 3 profil dari nol (VM baru) | **HUB (cron)** |
| 15:05–23:00 | 07:05–15:00 | `cs-auto-deploy.sh` jaring pengaman lanjut | HUB (cron) |
| **22:57** | **14:57** | `pre-hibernate-sop.sh` — penutupan malam | HUB (cron) |
| **23:00** | **15:00** | Laptop **hibernate total** (task `NodeHibernate-2300`) | Laptop (Task Scheduler lokal) |

Siklus ini berulang tiap hari (`DaysInterval=1` di keempat task Windows).
Jadwal lama (v2, 08:30/12:35/13:00/22:45) ada di riwayat §8 kalau perlu
rollback.

**Prinsip kunci:** laptop TAK PERNAH mengambil keputusan sendiri soal
"buka profil mana, deploy apa" — itu semua diperintah dari **HUB**
(akses-vps, 24/7). Laptop cuma eksekutor (buka Chrome, upload file,
jalankan perintah) saat diminta. Ini supaya logika rumit (nunggu sehat,
berhenti kalau gagal, dst) hidup di satu tempat yang selalu menyala,
bukan di Windows Task Scheduler yang kaku.

## 3. Alur wake bertahap (`wake-orchestrator.sh`, di HUB)

Untuk **tiap profil, berurutan** (**balibruntattour dulu, baru gogobuda,
baru yuni TERAKHIR** — urutan direvisi 2026-08-28 v5, permintaan user;
dulu yuni dulu):

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
4. HUB polling LANGSUNG ke VM Cloud Shell tujuan (SSH ringan tiap 5
   detik, maks 240 detik) — **bukan lagi** baca `C:\chrome-cdp\open-cs.log`
   laptop via SSH (v2, direvisi 2026-08-24: polling-ke-laptop TERBUKTI
   ikut rebutan CPU dgn laptop yg lagi sibuk Chrome+CDP, jadi 5/5 gagal
   sebelum akhirnya fallback — sekarang cek VM langsung dari awal, jauh
   lebih cepat & tak membebani laptop). Kalau timeout, log laptop tetap
   dibaca SEKALI sbg info diagnostik saja (bukan penentu).
        │
        ▼
5. HUB verifikasi SEKALI LAGI node ini SUDAH BISA di-SSH langsung
   (biasanya instan krn langkah 4 di atas sudah memastikannya)
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
7b. GAGAL di tahap 2-3 (trigger/bootstrap, laptop BELUM beres
    bagiannya) → HARD-FAIL. Di-RETRY otomatis (lihat kotak retry
    di bawah) — kalau tetap gagal setelah retry habis, profil ini
    ditandai gagal TAPI TETAP LANJUT ke profil berikutnya (ulang
    dari langkah 1, BUKAN lagi berhenti total).                ATAU
7c. GAGAL di tahap 5-6 (reachable/deploy, laptop SUDAH beres
    bagiannya) → SOFT-FAIL, LANJUT ke profil berikutnya (ulang
    dari langkah 1) TANPA retry di sini — jaring pengaman
    `cs-auto-deploy.sh` (§4) yg akan terus coba lagi tiap 5 menit
    sepanjang jendela wake. Profil ini dicatat gagal di ringkasan
    akhir, tapi tak menghalangi yang lain.
```

**⚠️ Revisi 2026-08-24 (v3): "berhenti total" kini BERSYARAT, bukan
mutlak lagi.** Keputusan asli 2026-08-16 ("satu gagal, semua
berhenti") didasari asumsi kalau satu profil bermasalah, kemungkinan
besar akar masalahnya di laptop/jaringan secara umum — memaksa lanjut
cuma menambah beban ke laptop yang sedang kewalahan. Tapi kejadian
nyata 24 Agustus membuktikan tak semua kegagalan seperti itu: `yuni`
sukses penuh di sisi laptop (tab terbuka, bootstrap tuntas), tapi
`deploy_yuni` kalah race lock 27 detik lawan cron `cs-auto-deploy.sh`
— gagalnya murni di sisi cloud, laptop sama sekali tak terlibat/tak
kewalahan. Dulu ini tetap memblokir `balibruntattour`+`gogobuda` total,
padahal tak ada alasan teknis untuk itu.

**Fix v3:** kebijakan dipecah berdasar TAHAP kegagalan (lihat komentar
`wake-orchestrator.sh`, fungsi `process_profile()`):
- **HARD-FAIL** (tahap 2-3, trigger task ATAU laptop tak kunjung lapor
  bootstrap selesai) = laptop sendiri yang bermasalah → (v3) berhenti
  total.
- **SOFT-FAIL** (tahap 5-6, node tak reachable ATAU deploy tak sehat) =
  laptop sudah tuntas bagiannya, masalah di cloud → lanjut ke profil
  berikutnya, TIDAK berhenti.

**✅ Revisi 2026-08-28 (v5): "berhenti total" DIHAPUS SAMA SEKALI +
kebijakan retry "jalankan hingga berhasil" (permintaan user).**
Insiden 27 Agustus membuktikan pola HARD-FAIL paling sering ("prompt
Cloud Shell belum siap dlm 180 detik") **BUKAN eksklusif satu
akun/laptop kewalahan** — bisa kena akun MANAPUN scr acak, murni
Google Cloud Shell lambat provisioning. Teknik pemulihan manual yg
terbukti jalan hari itu: tab yg "gagal" TETAP terbuka & idle, ~25
menit kemudian jadi siap sendiri, tinggal `schtasks /run` ULANG (tanpa
buka tab baru). Ini sekarang DIOTOMATISASI via fungsi
`process_profile_with_retry()` di `wake-orchestrator.sh`:

| Parameter | Nilai (kebijakan KONSERVATIF, permintaan user) |
|---|---|
| Retry per profil (HARD-FAIL saja) | maks **2x tambahan** (total 3 percobaan) |
| Jeda antar percobaan | **10 menit** |
| Kalau retry habis & tetap gagal | profil ditandai gagal, **TETAP LANJUT** ke profil berikutnya (tak lagi berhenti total, tak ada lagi kondisi apa pun yg menghentikan seluruh rantai) |
| SOFT-FAIL | TAK di-retry di sini (sudah tanggung jawab `cs-auto-deploy.sh` §4) |

Konsekuensi: `wake-orchestrator.sh` kini **SELALU mencoba ke-3 profil**
tiap run (tak pernah lagi berhenti di tengah), TAPI satu run bisa makan
waktu lebih lama dari dulu kalau ada profil yg butuh retry (worst-case
~3 profil × 2 retry × 10mnt ≈ 1 jam, masih jauh di bawah lebar jendela
wake 8 jam).

### Kalau semua sukses
Log `~/wake-orchestrator.log` (di HUB) berakhir dengan baris:
```
=== RINGKASAN AKHIR: balibruntattour=OK, gogobuda=OK, yuni=OK ===
```
+ notifikasi Telegram "✅ wake-orchestrator SUKSES PENUH".

### Kalau tak semua sukses
Log SELALU berakhir dengan baris `=== RINGKASAN AKHIR:
balibruntattour=<status>, gogobuda=<status>, yuni=<status> ===` —
baris ini SATU-SATUNYA sumber kebenaran yang dibaca
`check-wake-pipeline.sh` (jangan lagi menyimpulkan dari pola baris
`!!! X GAGAL`, sejak v3 bisa ada lebih dari satu per run). Tiap profil
berstatus salah satu dari: `OK` / `GAGAL (hard, retry habis)` /
`GAGAL (soft, pasca-bootstrap)` / `BELUM DICOBA` (sejak v5 seharusnya
TAK PERNAH muncul lagi — semua profil selalu dicoba — kecuali laptop
TAK terjangkau sama sekali di prasyarat awal, lihat §7).

Baca alasan gagal spesifik di baris `!!! <profil> GAGAL (hard/soft):
<alasan>` di badan log — biasanya salah satu dari:
- **"trigger task tak sukses"** *(hard, di-retry maks 2x/jeda 10mnt —
  §3)* → laptop tak terjangkau SSH sama sekali (mungkin belum
  wake/masih boot) atau task `open-cs-<profil>` hilang dari Task
  Scheduler (cek ulang §7 kalau ini terjadi).
- **"laptop tak kunjung selesai proses bootstrap"** *(hard, di-retry
  maks 2x/jeda 10mnt — §3)* → tab Cloud Shell gagal dibuka/prompt tak
  muncul dlm batas waktu (pola paling sering: "prompt Cloud Shell
  belum siap dlm 180 detik", MURNI Google lambat provisioning, sering
  hilang sendiri stlh 1-2 retry), ATAU laptop sedang sangat lambat.
  Cek `C:\chrome-cdp\open-cs.log` langsung.
- **"node tak reachable via SSH"** *(soft)* → bootstrap laptop kelar
  tapi WireGuard/sshd VM Cloud Shell belum naik. Bisa VM gagal
  provision, atau kredensial WG-nya bermasalah.
- **"deploy tak sehat"** *(soft)* → node reachable tapi project-nya
  gagal build/start, ATAU (kejadian nyata 24 Agustus) kalah race lock
  lawan `cs-auto-deploy.sh` — cek `CS_DEPLOY_LOCK_WAIT` di
  `lib-cs-deploy.sh` (default 1200s) kalau ini polanya berulang. Cek
  detail di baris sebelumnya (biasanya ada pesan spesifik dari
  `bring-up-*.sh` atau `docker logs`).

## 4. Jaring pengaman siang hari (`cs-auto-deploy.sh`)

Tetap jalan tiap 5 menit (06:00–23:00 WITA, lintas tengah malam UTC)
SETELAH `wake-orchestrator.sh` selesai pagi. Fungsinya BUKAN lagi jalur
utama — cuma jaga-jaga kalau:
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

Jalan 2x/hari, 3 menit sebelum tiap break/hibernate paksa: **13:57
WITA** (sblm break 14:00) & **22:57 WITA** (sblm hibernate 23:00).
Urutan:

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
| `NodeWake-0600` | Ya, harian 06:00 | RTC wake #1 (v3, ganti `NodeWake-0830` lama) |
| `NodeBreak-1400` | Ya, harian 14:00 | Break/hibernate siang (v3, ganti `NodeBreak-1235` lama) |
| `NodeWake2-1505` | Ya, harian 15:05 | RTC wake #2 (v3, ganti `NodeWake2-1300` lama; +5mnt dari rencana 15:00 krn rollout pas lewat jam) |
| `NodeHibernate-2300` | Ya, harian 23:00 | Hibernate malam (v3, ganti `NodeHibernate-2245` lama) |
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
- **2026-08-16 (v1)**: redesign total dari "buka 3 tab staggered lalu
  deploy async via cron 5-menitan" (banyak gagal krn resource-starvation
  laptop lemah) menjadi alur bertahap ketat per-profil (dokumen ini).
  Sekaligus fix bug Chrome auto-restore-sesi pasca `pre-hibernate-sop.sh`
  (§5c).
- **2026-08-16 (v2, sore hari)**: jadwal diubah dari 1 siklus/hari jadi
  **2 siklus/hari** dgn jeda istirahat siang 12:35–13:00 WITA (§2). Task
  Windows laptop di-rename total (`NodeWake-0830`/`NodeBreak-1235`/
  `NodeWake2-1300`/`NodeHibernate-2245`, `NodeWake-0845`/
  `NodeHibernate-2230` lama dihapus). Cron hub: `wake-orchestrator.sh`
  & `pre-hibernate-sop.sh` masing2 jadi 2× jadwal/hari. Konsekuensi
  diterima: build project (terutama analyzer yuni) berpotensi 2×/hari
  krn Cloud Shell ephemeral (tiap wake = VM baru, tak ada cache
  persisten lintas siklus).
- **2026-08-24 (v3)**: kebijakan "berhenti total kalau satu gagal"
  direvisi jadi bersyarat (HARD-FAIL tetap berhenti total, SOFT-FAIL
  lanjut ke profil berikutnya) — lihat §3. Dipicu insiden nyata: `yuni`
  kalah race lock 27 detik lawan `cs-auto-deploy.sh` (`lib-cs-deploy.sh`
  `CS_DEPLOY_LOCK_WAIT` 900→1200s sekaligus dinaikkan), yang dulu ikut
  memblokir `balibruntattour`+`gogobuda` padahal laptop sama sekali tak
  bermasalah. `check-wake-pipeline.sh` ikut diupdate baca baris
  `=== RINGKASAN AKHIR: ... ===` sbg satu-satunya sumber kebenaran.
- **2026-08-24 (v4, sesi sama)**: pengujian live end-to-end (dipicu
  manual, bukan nunggu jadwal) menemukan dua bug LAGI: (1) `reachable_cs`
  pakai `StrictHostKeyChecking=accept-new` yg gagal DETERMINISTIK begitu
  IP VM ephemeral (.50/.60/.61) dapat host-key baru dari wake sebelumnya
  — diganti `StrictHostKeyChecking=no` (aman, IP ini cuma reachable via
  WireGuard privat kita sendiri). (2) `wait_bootstrap_result()` yg
  polling `open-cs.log` laptop tiap 8s TERBUKTI gagal 5/5 percobaan hari
  itu — laptop lemah ikut kewalahan oleh polling-nya SENDIRI (spawn SSH+
  PowerShell baru tiap 8 detik) di saat bersamaan sedang sibuk Chrome+CDP,
  bukan soal isi log. Diganti: cek `reachable_cs` LANGSUNG ke VM tujuan
  jadi sinyal utama (§3 langkah 4), polling log laptop turun jadi info
  diagnostik saja. Kedua fix TERBUKTI via `ssh -v` (host-key) & data
  timestamp log lokal vs log HUB (polling) sebelum diterapkan.
- **2026-08-28 (v5)**: revisi besar permintaan user — (1) **jadwal
  digeser total**: Wake1 08:30→06:00, Break 12:35→14:00, Wake2
  13:00→15:05, Hibernate 22:45→23:00 (§2); task Windows di-rename total
  (`NodeWake-0600`/`NodeBreak-1400`/`NodeWake2-1505`/
  `NodeHibernate-2300`, 4 task v3 lama dihapus — §6). (2) **urutan
  profil dibalik**: balibruntattour→gogobuda→yuni (dulu yuni dulu).
  (3) **kebijakan "berhenti total" DIHAPUS SAMA SEKALI** — diganti
  retry otomatis KONSERVATIF (maks 2x tambahan/jeda 10mnt) utk
  HARD-FAIL, baru lanjut ke profil berikutnya kalau retry habis (§3) —
  memenuhi permintaan user "jalankan hingga berhasil", berdasar bukti
  27/8 bahwa pola HARD-FAIL paling sering ("prompt Cloud Shell blm
  siap 180dtk") murni provisioning Google yg lambat & sering pulih
  sendiri, bukan laptop rusak. Rollout dieksekusi live sore 28/8 (laptop
  kebetulan hidup dari siklus lama) sbg tes langsung tanpa nunggu
  besok — lihat `~/wake-orchestrator.log` run 07:0x UTC 28/8 & memori
  `project_laptop_wol_power` utk hasil verifikasi.
