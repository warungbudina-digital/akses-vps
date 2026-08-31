# =====================================================================
# sync-time.ps1 -- sinkronisasi jam laptop SUARAHATI saat BOOT.
#
# LATAR: baterai CMOS laptop ini SUDAH MATI, dan sejak 2026-08-31 user
# mencabut listrik setiap selesai pakai. Akibatnya RTC tak punya sumber
# daya sama sekali -> jam ngaco/ter-reset setiap kali dinyalakan.
#
# KENAPA INI KRITIS (bukan sekadar kosmetik):
#   Jam salah = validasi sertifikat TLS GAGAL -> Chrome tak bisa membuka
#   shell.cloud.google.com & login Google ditolak. Jadi sync HARUS tuntas
#   SEBELUM launcher Cloud Shell jalan, bukan berbarengan.
#
# JEBAKAN YANG DITANGANI (ini alasan utama skrip ini ada, bukan sekadar
# `w32tm /resync`): Windows DIAM-DIAM MENOLAK koreksi waktu yang lebih
# besar dari MaxPos/MaxNegPhaseCorrection (default hanya beberapa jam).
# Kalau jam ter-reset ke tahun BIOS default, `w32tm /resync` akan "sukses"
# tanpa membetulkan apa pun. Maka batas itu dibuka ke unlimited (0xFFFFFFFF)
# LEBIH DULU, baru resync.
#
# Dipanggil oleh Scheduled Task "NodeBoot-TimeSync" (At startup, SYSTEM).
# Log: C:\chrome-cdp\time-sync.log
# =====================================================================
$ErrorActionPreference = 'Continue'
$dir = 'C:\chrome-cdp'
$log = Join-Path $dir 'time-sync.log'
$gateway = '192.168.70.1'          # MikroTik LtAP mini (gateway LAN)
$peers = 'time.google.com,0x8 pool.ntp.org,0x8 time.windows.com,0x8'
$netWaitSec = 300                   # tunggu jaringan maks 5 menit
$resyncTries = 10

if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Add-Content -Path $log -Value $line
  Write-Output $line
}
# jaga log tetap ramping
try { if ((Test-Path $log) -and ((Get-Item $log).Length -gt 200KB)) {
  Set-Content -Path $log -Value (Get-Content $log -Tail 300)
} } catch {}

Log "=== sync-time MULAI (uptime $([int]([Environment]::TickCount/1000))s) ==="
$before = Get-Date
Log ("jam SEBELUM : {0}" -f $before.ToString('yyyy-MM-dd HH:mm:ss'))

# ---- 1) Buka batas koreksi DULU (kalau tidak, koreksi besar ditolak diam-diam) ----
$cfg = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time\Config'
try {
  Set-ItemProperty -Path $cfg -Name MaxPosPhaseCorrection -Value 0xFFFFFFFF -Type DWord
  Set-ItemProperty -Path $cfg -Name MaxNegPhaseCorrection -Value 0xFFFFFFFF -Type DWord
  Log "batas koreksi dibuka (MaxPos/MaxNegPhaseCorrection = unlimited)."
} catch { Log ("WARN gagal set batas koreksi: {0}" -f $_.Exception.Message) }

# ---- 2) Pastikan layanan hidup (temuan 31/8: w32time SEDANG STOPPED) ----
try {
  Set-Service -Name w32time -StartupType Automatic -ErrorAction Stop
  $svc = Get-Service w32time
  if ($svc.Status -ne 'Running') { Start-Service w32time -ErrorAction Stop; Start-Sleep -Seconds 2 }
  Log ("layanan w32time: {0}" -f (Get-Service w32time).Status)
} catch { Log ("WARN layanan w32time: {0}" -f $_.Exception.Message) }

# ---- 3) Set sumber NTP (0x8 = mode client, jangan andalkan domain hierarchy) ----
try {
  & w32tm /config /manualpeerlist:"$peers" /syncfromflags:manual /reliable:no /update 2>&1 | Out-Null
  Log ("sumber NTP di-set: {0}" -f $peers)
} catch { Log ("WARN set peer: {0}" -f $_.Exception.Message) }

# ---- 4) Tunggu jaringan benar-benar siap (boot lambat di CPU 1,4 GHz) ----
$net = $false
$deadline = (Get-Date).AddSeconds($netWaitSec)
while ((Get-Date) -lt $deadline) {
  if (Test-Connection -ComputerName $gateway -Count 1 -Quiet -ErrorAction SilentlyContinue) { $net = $true; break }
  Start-Sleep -Seconds 5
}
if ($net) { Log "jaringan SIAP (gateway $gateway menjawab)." }
else { Log "WARN jaringan TAK siap dlm ${netWaitSec}s -- resync kemungkinan besar gagal." }

# ---- 5) Resync paksa, ulangi (NTP sendiri TIDAK butuh jam benar, jadi aman) ----
$ok = $false
for ($i = 1; $i -le $resyncTries; $i++) {
  $out = (& w32tm /resync /force 2>&1) -join ' '
  if ($LASTEXITCODE -eq 0 -and $out -notmatch 'error|gagal|failed') {
    Log ("resync SUKSES di percobaan {0}." -f $i); $ok = $true; break
  }
  Log ("resync percobaan {0}/{1} gagal: {2}" -f $i, $resyncTries, $out.Trim())
  Start-Sleep -Seconds 15
}

# ---- 6) Verifikasi & lapor selisih yang benar-benar terjadi ----
$after = Get-Date
$delta = [math]::Round(($after - $before).TotalSeconds, 1)
Log ("jam SESUDAH : {0}" -f $after.ToString('yyyy-MM-dd HH:mm:ss'))
Log ("pergeseran  : {0} detik (termasuk waktu jalan skrip ini)" -f $delta)
try {
  $st = (& w32tm /query /status 2>&1) | Select-String 'Source|Last Successful'
  foreach ($l in $st) { Log ("  status: {0}" -f $l.ToString().Trim()) }
} catch {}

if ($ok) {
  Log "=== sync-time SELESAI: BERHASIL ==="
  # Penanda dibaca run-daily-launch.ps1 sbg prasyarat. Isinya jam hasil sync.
  Set-Content -Path (Join-Path $dir 'time-sync.ok') -Value $after.ToString('o') -Encoding ASCII
  exit 0
} else {
  Log "=== sync-time SELESAI: GAGAL (jam TIDAK dapat dipercaya) ==="
  Remove-Item (Join-Path $dir 'time-sync.ok') -Force -ErrorAction SilentlyContinue
  exit 1
}
