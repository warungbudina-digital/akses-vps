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

## Mengembalikan ke siklus hibernasi lama

`Disable-ScheduledTask` ketiga task di atas, `Enable-ScheduledTask` untuk
`NodeWake-0600`/`NodeBreak-1400`/`NodeWake2-1505`/`NodeHibernate-2300`, lalu di hub
hapus prefix `#DIJEDA# ` di crontab (atau `crontab ~/crontab.bak-20260831-manual-mode`).
