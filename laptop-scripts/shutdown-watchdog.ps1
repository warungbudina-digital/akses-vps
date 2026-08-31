# =====================================================================
# shutdown-watchdog.ps1 -- matikan laptop setelah 14 jam menyala.
# (permintaan user 2026-08-31: laptop kerja 14 jam lalu shutdown total,
#  listrik dicabut manual sesudahnya.)
#
# !! KENAPA PAKAI TickCount, BUKAN JAM DINDING -- INI PENTING !!
#   Baterai CMOS laptop ini MATI dan listrik dicabut tiap malam, jadi jam
#   sistem ngaco saat boot lalu MELOMPAT saat sync-time.ps1 berhasil.
#   Kalau batas 14 jam dihitung dari Win32_OperatingSystem.LastBootUpTime
#   (yang diturunkan dari jam sistem itu), maka boot di tahun 2009 yang
#   lalu dikoreksi ke 2026 akan terbaca "uptime 17 tahun" -> laptop
#   SHUTDOWN beberapa detik setelah dinyalakan.
#   [Environment]::TickCount menghitung milidetik sejak boot lewat timer
#   perangkat keras -- sama sekali TIDAK terpengaruh koreksi jam.
#   (Int32, wrap di ~24,8 hari; tak relevan krn siklus kita 14 jam.)
#
# Dipanggil oleh Scheduled Task "NodeShutdown-14h" (At logon).
# Log: C:\chrome-cdp\shutdown-watchdog.log
# =====================================================================
$ErrorActionPreference = 'Continue'
$dir = 'C:\chrome-cdp'
$log = Join-Path $dir 'shutdown-watchdog.log'
$limitHours = 14
$warnSec = 120          # jeda peringatan sebelum benar-benar mati
$pollSec = 60
$heartbeatMin = 60      # tulis 1 baris tiap 60 menit biar kelihatan hidup

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Add-Content -Path $log -Value $line
}
try { if ((Test-Path $log) -and ((Get-Item $log).Length -gt 200KB)) {
  Set-Content -Path $log -Value (Get-Content $log -Tail 300)
} } catch {}

$limitMs = $limitHours * 3600 * 1000
Log ("=== watchdog MULAI: shutdown pada uptime {0} jam (uptime sekarang {1} menit) ===" -f $limitHours, [int]([Environment]::TickCount/60000))

# ---- PENGAMAN: jangan mematikan mesin yang sudah lama menyala ----
# Alur normal = boot -> auto-login -> watchdog mulai saat uptime ~1-2 menit.
# Kalau saat MULAI uptime sudah melewati batas, berarti watchdog dijalankan
# di TENGAH sesi lama (mis. user logoff-logon, atau task dipasang manual saat
# mesin sudah menyala berhari-hari). Mematikan seketika di situ = kejutan yang
# berpotensi menghilangkan pekerjaan user, bukan perilaku yang dimaksud.
# Kasus nyata: saat task ini dipasang 2026-08-31, uptime laptop 89 jam.
$startTick = [Environment]::TickCount
if ($startTick -ge $limitMs -or $startTick -lt 0) {
  Log ("BATAL (pengaman): uptime saat mulai sudah {0} jam, melewati batas {1} jam." -f [int]($startTick/3600000), $limitHours)
  Log "       Watchdog TIDAK mematikan mesin yang sudah lama menyala. Siklus 14 jam"
  Log "       akan berlaku normal pada boot berikutnya."
  exit 0
}

$lastBeat = -1
while ($true) {
  $tick = [Environment]::TickCount
  # TickCount Int32 bisa negatif kalau wrap (~24,8 hari). Kalau itu terjadi,
  # jelas sudah lewat 14 jam -> perlakukan sbg batas tercapai.
  if ($tick -lt 0) { Log "TickCount wrap (uptime > 24 hari) -- anggap batas tercapai."; break }
  if ($tick -ge $limitMs) { break }

  $mins = [int]($tick / 60000)
  if ($mins - $lastBeat -ge $heartbeatMin -or $lastBeat -lt 0) {
    Log ("hidup: uptime {0} jam {1} menit; sisa {2} menit." -f [int]($mins/60), ($mins % 60), [int](($limitMs - $tick)/60000))
    $lastBeat = $mins
  }
  Start-Sleep -Seconds $pollSec
}

$up = [int]([Environment]::TickCount / 60000)
Log ("BATAS TERCAPAI: uptime {0} jam {1} menit -> shutdown dalam {2} detik." -f [int]($up/60), ($up % 60), $warnSec)

# ---- Tutup Chrome RAPI dulu (dipindah dari pre-hibernate-sop.sh yg kini nonaktif) ----
# Kalau Chrome dibiarkan dibunuh paksa oleh proses shutdown Windows, ia mencatat
# exit_type="Crashed" -> pada boot berikutnya Chrome AUTO-RESTORE tab Cloud Shell
# kemarin. Di laptop 2 core/1,4 GHz itu berarti setiap pagi dimulai dengan beban
# tab mati yang justru ingin kita hindari. Jadi: tutup baik-baik, lalu tandai
# exit_type=Normal. Hanya menyentuh flag housekeeping -- BUKAN password/cookie/history.
try {
  $procs = @(Get-Process chrome -ErrorAction SilentlyContinue)
  Log ("menutup Chrome dengan rapi ({0} proses)..." -f $procs.Count)
  foreach ($p in $procs) { if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() } }
  Start-Sleep -Seconds 5
  $sisa = @(Get-Process chrome -ErrorAction SilentlyContinue)
  if ($sisa.Count -gt 0) { $sisa | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }
  $base = 'C:\Users\warungbudina\AppData\Local\Google\Chrome\User Data'
  # "Profile 11" (ogis) SENGAJA ikut dibersihkan meski ogis sudah dinonaktifkan
  # dari pipeline. Menonaktifkan ogis di skrip kita TIDAK mencegah Chrome
  # membukanya sendiri: Chrome menyimpan daftar "last_active_profiles" di
  # Local State dan memulihkan jendela profil itu saat start, apalagi kalau
  # exit_type-nya tertinggal "Crashed".
  # Kasus nyata 2026-08-31 (ditemukan USER lewat pengamatan langsung, bukan
  # dari log): last_active_profiles = ["Profile 11","Profile 29","Profile 26",
  # "Profile 10"] -- ogis dipulihkan PALING AWAL, sehingga laptop menjalankan
  # 4 tab Cloud Shell, bukan 3. Itulah sebab `yuni` (yg jadi tab KEEMPAT)
  # selalu gagal dan Chrome selalu crash, termasuk pada boot yang bersih.
  foreach ($t in @('Profile 10','Profile 26','Profile 29','Profile 11')) {
    $pf = Join-Path $base "$t\Preferences"
    if (Test-Path $pf) {
      $raw = Get-Content $pf -Raw
      $new = $raw -replace '"exit_type"\s*:\s*"[^"]+"', '"exit_type":"Normal"'
      $new = $new -replace '"exited_cleanly"\s*:\s*(true|false)', '"exited_cleanly":true'
      if ($new -ne $raw) { Set-Content -Path $pf -Value $new -NoNewline -Encoding UTF8 }
    }
  }
  Log ("Chrome ditutup ({0} -> {1} proses), exit_type dipatch Normal." -f $procs.Count, (@(Get-Process chrome -ErrorAction SilentlyContinue)).Count)
  # Keluarkan "Profile 11" (ogis) dari daftar profil yang akan dipulihkan
  # Chrome pada start berikutnya. Tanpa ini, sekali saja ogis pernah terbuka,
  # ia akan terus muncul sendiri tiap boot dan menambah beban tab keempat.
  $lsPath = Join-Path $base 'Local State'
  if (Test-Path $lsPath) {
    $ls = Get-Content $lsPath -Raw
    $m = [regex]::Match($ls, '"last_active_profiles"\s*:\s*\[([^\]]*)\]')
    if ($m.Success -and $m.Groups[1].Value -match 'Profile 11') {
      $items = $m.Groups[1].Value -split ',' | Where-Object { $_ -notmatch 'Profile 11' }
      $newArr = '"last_active_profiles":[' + ($items -join ',') + ']'
      Set-Content -Path $lsPath -Value ($ls.Remove($m.Index, $m.Length).Insert($m.Index, $newArr)) -NoNewline -Encoding UTF8
      Log ("last_active_profiles dibersihkan dari Profile 11 -> [{0}]" -f ($items -join ','))
    } else { Log "last_active_profiles sudah bersih dari Profile 11." }
  }
} catch { Log ("WARN gagal menutup Chrome rapi: {0}" -f $_.Exception.Message) }
Log "    Setelah mati, user mencabut listrik (jam akan ter-reset; sync-time.ps1 membetulkannya saat boot berikutnya)."
& shutdown /s /t $warnSec /c "Batas kerja 14 jam tercapai - laptop dimatikan otomatis. Simpan pekerjaan Anda."
Log ("perintah shutdown dikirim (exit={0})." -f $LASTEXITCODE)
