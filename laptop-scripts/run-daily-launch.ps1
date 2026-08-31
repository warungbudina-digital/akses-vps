# =====================================================================
# run-daily-launch.ps1 -- launcher Cloud Shell harian, DIJALANKAN DI LAPTOP.
#
# PERUBAHAN ARSITEKTUR (2026-08-31, permintaan user):
#   DULU: hub (akses-vps) yang menyetir, lewat cron di jam UTC tetap ->
#         `schtasks /run /tn open-cs-<profil>` via ssh ltap-mini.
#   KINI: laptop dinyalakan MANUAL kapan saja, jadi hub tak bisa lagi
#         menjadwalkan. Pemicu pindah ke sini: At logon + jeda 7 menit.
#         Tahap DEPLOY tetap di hub, ditangani cs-auto-deploy.sh yang
#         memang sudah memeriksa tiap 5 menit dan men-deploy node yang
#         muncul -- jadi tak ada yang hilang.
#
# URUTAN: balibruntattour -> gogobuda -> yuni. SATU PER SATU sampai
# selesai, TIDAK paralel: laptop cuma 2 core/1,4 GHz dan 2026-08-31
# terbukti Chrome tumbang saat menahan beberapa halaman Cloud Shell.
# (ogis sengaja TIDAK ada di sini -- dinonaktifkan hari yang sama.)
#
# PRASYARAT JAM: baterai CMOS mati + listrik dicabut = jam ngaco tiap
# boot. Jam salah -> sertifikat TLS ditolak -> Cloud Shell & login Google
# GAGAL. Maka skrip ini MENOLAK jalan sebelum sync-time.ps1 sukses.
#
# Log: C:\chrome-cdp\daily-launch.log
# =====================================================================
$ErrorActionPreference = 'Continue'
$dir = 'C:\chrome-cdp'
$log = Join-Path $dir 'daily-launch.log'
$okFlag = Join-Path $dir 'time-sync.ok'
$openCs = Join-Path $dir 'open-cs.ps1'
$profiles = @('balibruntattour','gogobuda','yuni')
$startDelaySec = 420    # jeda 7 menit sejak logon (permintaan user)
$timeWaitSec = 600      # tunggu sync waktu maks 10 menit
$gapSec = 60            # jeda antar profil (beri Chrome napas)

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Add-Content -Path $log -Value $line
  Write-Output $line
}
try { if ((Test-Path $log) -and ((Get-Item $log).Length -gt 300KB)) {
  Set-Content -Path $log -Value (Get-Content $log -Tail 400)
} } catch {}

Log "=== run-daily-launch MULAI (uptime $([int]([Environment]::TickCount/1000))s) ==="

# ---- Jeda 7 menit sejak logon ----
# Sengaja DI SINI, bukan di trigger Task Scheduler: properti Delay tak
# tersedia di objek trigger PowerShell 4.0 (Win 8.1), dan menaruhnya di skrip
# membuat jedanya terlihat di log serta gampang diubah tanpa menyentuh
# Task Scheduler. Tujuannya memberi Windows waktu menuntaskan boot (CPU 2
# core/1,4 GHz) dan memberi sync-time.ps1 kesempatan selesai lebih dulu.
Log ("jeda {0} detik sejak logon sebelum menyentuh Cloud Shell..." -f $startDelaySec)
Start-Sleep -Seconds $startDelaySec
Log ("jeda selesai (uptime {0} menit)." -f [int]([Environment]::TickCount/60000))

# ---- Gerbang 1: jam WAJIB sudah tersinkron ----
# Tanpa ini launcher akan "jalan" lalu gagal misterius di TLS -- persis
# jenis kegagalan menyesatkan yang sudah memakan banyak waktu 31/8.
$waited = 0
while (-not (Test-Path $okFlag)) {
  if ($waited -ge $timeWaitSec) {
    Log "BATAL: sync waktu tak kunjung sukses dlm ${timeWaitSec}s (penanda time-sync.ok tak ada)."
    Log "       Jam salah = sertifikat TLS ditolak = Cloud Shell PASTI gagal. Cek time-sync.log."
    Log "=== run-daily-launch SELESAI: DIBATALKAN ==="
    exit 2
  }
  if ($waited -eq 0) { Log "menunggu sync-time.ps1 selesai..." }
  Start-Sleep -Seconds 10; $waited += 10
}
Log ("jam tersinkron OK (penanda dibuat {0}); jam sekarang {1}" -f (Get-Content $okFlag -Raw).Trim(), (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

# ---- Gerbang 2: jam masuk akal? (jaring pengaman kalau penanda basi) ----
if ((Get-Date).Year -lt 2026) {
  Log ("BATAL: tahun sistem {0} jelas salah -- sync gagal diam-diam." -f (Get-Date).Year)
  exit 2
}

# ---- Jalankan tiap profil, SATU PER SATU sampai tuntas ----
if (-not (Test-Path $openCs)) { Log "BATAL: $openCs tak ditemukan."; exit 2 }
$hasil = @()
foreach ($p in $profiles) {
  Log "--- profil $p : mulai ---"
  $t0 = Get-Date
  try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $openCs -Profile $p | Out-Null
    $rc = $LASTEXITCODE
  } catch { $rc = -1; Log ("  exception: {0}" -f $_.Exception.Message) }
  $dur = [int]((Get-Date) - $t0).TotalSeconds
  # Catatan: exit code open-cs.ps1 cuma indikasi KASAR (lihat catatan di
  # open-and-bootstrap-cs.py). Kebenaran sesungguhnya = node reachable dari
  # hub; itu diverifikasi cs-auto-deploy.sh, bukan di sini.
  Log ("--- profil {0} : selesai (exit={1}, {2}s) ---" -f $p, $rc, $dur)
  $hasil += ("{0}=exit{1}/{2}s" -f $p, $rc, $dur)
  if ($p -ne $profiles[-1]) {
    Log "jeda ${gapSec}s sebelum profil berikutnya (beri Chrome napas)."
    Start-Sleep -Seconds $gapSec
  }
}

Log ("=== run-daily-launch SELESAI: {0} ===" -f ($hasil -join ', '))
Log "    Status SEBENARNYA ditentukan hub (cs-auto-deploy.sh tiap 5 menit), bukan exit code di atas."
exit 0
