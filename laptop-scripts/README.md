# laptop-scripts — siklus MANUAL-POWER laptop SUARAHATI (2026-08-31)

Salinan skrip yang **jalan di laptop** (`C:\chrome-cdp\`). Ditaruh di git supaya
tak hilang & bisa ditelusuri; laptop bukan bagian repo, jadi ini bukan
sumber-kebenaran — kalau mengedit, push balik ke laptop lewat `scp`.

## Kenapa siklus ini menggantikan hibernasi

Sebelumnya laptop menyala 24/7 dengan hibernate/wake terjadwal (RTC), diorkestrasi
dari hub. Pada 2026-08-31 Chrome 109 crash **8 kali** dan setiap crash menjatuhkan
seluruh pekerjaan hari itu. Tersangka terkuat: akumulasi state lintas ~7 siklus
hibernate pada uptime 3,5 hari. User memilih kembali ke pola lama yang terbukti:
nyalakan manual, kerja 14 jam, shutdown total, cabut listrik.

## Alur

```
user nyalakan laptop
  -> auto-login (AutoAdminLogon, sudah ada sebelumnya)
  -> [At startup ] NodeBoot-TimeSync   : sync-time.ps1        (SEGERA, SYSTEM)
  -> [At logon   ] NodeShutdown-14h    : shutdown-watchdog.ps1 (pantau uptime)
  -> [At logon   ] NodeDaily-Launcher  : run-daily-launch.ps1  (jeda 7 menit di dalam skrip)
       -> balibruntattour -> gogobuda -> yuni  (satu per satu)
  -> hub: cs-auto-deploy.sh (tiap 5 menit) mendeteksi node naik lalu men-deploy
  -> uptime 14 jam -> Chrome ditutup rapi -> shutdown -> user cabut listrik
```

## Dua jebakan yang ditangani (jangan dihapus tanpa paham)

1. **Baterai CMOS MATI + listrik dicabut = jam ter-reset tiap boot.** Jam salah
   membuat sertifikat TLS ditolak, sehingga Cloud Shell & login Google GAGAL.
   Karena itu sync waktu jalan di **At startup tanpa jeda**, dan launcher
   MENOLAK jalan sebelum penanda `time-sync.ok` ada.
   Windows juga **diam-diam menolak** koreksi waktu besar; `sync-time.ps1`
   membuka `MaxPos/MaxNegPhaseCorrection` lebih dulu, kalau tidak `w32tm /resync`
   akan "sukses" tanpa membetulkan apa pun.
2. **Batas 14 jam memakai `[Environment]::TickCount`, bukan jam dinding.**
   `LastBootUpTime` diturunkan dari jam sistem — boot di tahun salah lalu
   dikoreksi ke 2026 akan terbaca "uptime belasan tahun" dan mematikan laptop
   beberapa detik setelah menyala. TickCount memakai timer perangkat keras.
   Ada pengaman tambahan: kalau saat watchdog MULAI uptime sudah lewat batas
   (mis. dipasang di tengah sesi lama), ia menolak mematikan mesin.

## Fix 2026-10-28 — overlay invisible Cloud Shell silent-drop ketikan + tab lama di-skip (cshell.py / open-and-bootstrap-cs.py)

Insiden pasca-outage-listrik 27/10: ketiga Cloud Shell (yuni/balibruntattour/
gogobuda) stuck >24 jam tanpa tunnel WireGuard naik, walau tab-nya live &
ter-autentikasi. Dua bug akar ditemukan live di DOM Cloud Shell, bukan nebak:

1. **`click_terminal()` di `cshell.py`** klik berdasar KOORDINAT -> kena
   elemen invisible full-viewport `<security-blocking-indicator>`
   (`position:fixed; z-index:99999; pointer-events:auto`, konten kosong —
   diduga gate sisi-Google utk browser EOL spt Chrome 109 di laptop ini,
   dialognya gagal render tapi blocking-nya tetap aktif). Klik ini
   MENCABUT fokus dari textarea tepat sblm mengetik -> command silent-drop
   total (scrape tetap bersih, nol jejak command). **Fix:** cek
   `elementFromPoint` dulu; kalau titik klik diblok elemen non-xterm,
   lewati klik koordinat, cukup `focus()` JS (terverifikasi live tetap
   tembus walau overlay ada).
2. **`open_profile()` di `open-and-bootstrap-cs.py`** vonis "tab tak
   terdeteksi" kalau tab profil itu SUDAH terbuka (klik shortcut cuma
   fokus ke window lama, bukan buka baru) -> bootstrap di-skip total,
   padahal tab lama itu live & siap pakai. **Fix:** `find_existing_tab()`
   scrape akun (`...@cloudshell`) semua shell target SEBELUM klik shortcut;
   kalau cocok, pakai ulang tab itu langsung.

Dampak: ketiga node pulih + deploy ulang terverifikasi sehat (health-check
masing-masing: analyzer V2 ML, browser automation, GUI) pada hari yang sama.
`backup/cs-manual-activate.sh` ikut ditambah pre-check `reachable_cs` di
awal supaya pemanggilan manual saat node SUDAH sehat tak memaksa ketik ulang
ke sesi yang sedang foreground menjalankan `ping` keepalive.

## Mengembalikan ke siklus hibernasi lama

`Disable-ScheduledTask` ketiga task di atas, `Enable-ScheduledTask` untuk
`NodeWake-0600`/`NodeBreak-1400`/`NodeWake2-1505`/`NodeHibernate-2300`, lalu di hub
hapus prefix `#DIJEDA# ` di crontab (atau `crontab ~/crontab.bak-20260831-manual-mode`).
