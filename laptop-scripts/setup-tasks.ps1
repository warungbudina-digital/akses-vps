# setup-tasks.ps1 -- daftarkan 3 scheduled task siklus MANUAL-POWER (2026-08-31).
# Menggantikan siklus hibernate lama (NodeWake/NodeBreak/NodeHibernate, sudah Disabled).
$ErrorActionPreference = 'Stop'
$dir  = 'C:\chrome-cdp'
$user = 'SUARAHATI\warungbudina'
$ps   = 'powershell.exe'

function Reg($name, $action, $trigger, $principal, $settings) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings | Out-Null
  $t = Get-ScheduledTask -TaskName $name
  "{0,-22} {1}" -f $name, $t.State
}

# ---- 1) NodeBoot-TimeSync : At STARTUP, SYSTEM, sesegera mungkin ----
# Sengaja TANPA jeda: jam salah bikin TLS gagal, jadi ini harus tuntas
# SEBELUM launcher jalan di menit ke-7.
$a1 = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dir\sync-time.ps1`""
$t1 = New-ScheduledTaskTrigger -AtStartup
$p1 = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$s1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Reg 'NodeBoot-TimeSync' $a1 $t1 $p1 $s1

# ---- 2) NodeDaily-Launcher : At LOGON + jeda 7 menit, sesi interaktif user ----
# WAJIB interaktif: python/CDP harus bisa memfokuskan window Chrome.
$a2 = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dir\run-daily-launch.ps1`""
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $user
# (jeda 7 menit dipindah ke dalam run-daily-launch.ps1 -- properti Delay tak ada di PS 4.0)
$p2 = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Reg 'NodeDaily-Launcher' $a2 $t2 $p2 $s2

# ---- 3) NodeShutdown-14h : At LOGON, jalan terus memantau uptime ----
# ExecutionTimeLimit 0 = tanpa batas (task ini memang hidup belasan jam).
$a3 = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dir\shutdown-watchdog.ps1`""
$t3 = New-ScheduledTaskTrigger -AtLogOn -User $user
$p3 = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$s3 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Reg 'NodeShutdown-14h' $a3 $t3 $p3 $s3
