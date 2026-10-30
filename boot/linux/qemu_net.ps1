# Sieć + Cynober: płyta łączy się z Karmin_DB (DBase cynober_server.py na hoście).
# QEMU: sieć użytkownika z virtio-net; host widziany z płyty jako 10.0.2.2.
# Shell podnosi eth0 z KARMAZYN_IP/KARMAZYN_GW (grub.cfg), potem przez serial:
#   db connect 10.0.2.2 <port> · db ZDROWIE · db info · db LISTA ŚWIATÓW
# PSK i profil HSS nie są na linii jądra (plik: /data/cynober/client.json).
# Ta bramka nie podkłada dysku, więc tunel zostaje ECDH.
# Exit 0 = pass, 1 = fail, 2 = brak qemu, ISO, Pythona albo DBase.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$iso = Join-Path $Repo "out\karmazyn-linux.iso"
$dbase = if ($env:KARMAZYN_DBASE) { $env:KARMAZYN_DBASE } else { "C:\Users\drwis\DBase" }
if (-not (Test-Path $iso)) { Write-Host "Brak $iso"; exit 2 }
if (-not (Test-Path (Join-Path $dbase "cynober_server.py"))) { Write-Host "Brak DBase: $dbase"; exit 2 }
$qemu = $env:QEMU_BIN
if (-not $qemu) {
    $cmd = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
    if ($cmd) { $qemu = $cmd.Source }
}
if (-not $qemu) { $qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe" }
if (-not (Test-Path $qemu)) { Write-Host "Brak qemu-system-x86_64."; exit 2 }

function Get-FreePort {
    $l = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $l.Start(); $p = $l.LocalEndpoint.Port; $l.Stop(); return $p
}
$dbPort = Get-FreePort
$serPort = Get-FreePort

# serwer DBase na hoście, własny katalog danych (inny node_id niż płyta)
$srvHome = Join-Path $env:TEMP ("karmazyn_net_srv_" + $PID)
$psi = [Diagnostics.ProcessStartInfo]::new("python", "cynober_server.py 127.0.0.1 $dbPort")
$psi.WorkingDirectory = $dbase
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
foreach ($k in @("KARM_HSS_PROFILE", "KARM_PSK", "KARM_QKD_SEED", "CYNOBER_MIN_CRYPTO")) { $psi.Environment.Remove($k) | Out-Null }
$psi.Environment["CYNOBER_DATA_HOME"] = $srvHome
$psi.Environment["PYTHONIOENCODING"] = "utf-8"
$srv = [Diagnostics.Process]::Start($psi)
$srvOut = $srv.StandardOutput.ReadToEndAsync()

$args = @(
    "-machine", "pc,accel=tcg", "-m", "256", "-boot", "d", "-cdrom", $iso,
    "-no-reboot", "-display", "none", "-vga", "none",
    "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0",
    "-chardev", "socket,id=ser,host=127.0.0.1,port=${serPort},server=on,wait=off",
    "-serial", "chardev:ser"
)
$proc = Start-Process -FilePath $qemu -ArgumentList $args -PassThru -NoNewWindow
$cmds = @("db connect 10.0.2.2 $dbPort", "db ZDROWIE", "db info", "db LISTA ŚWIATÓW")
$text = ""
$client = $null
try {
    for ($i = 0; $i -lt 40 -and -not $client; $i++) {
        try { $client = [Net.Sockets.TcpClient]::new("127.0.0.1", $serPort) } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $client) { Write-Host "QEMU nie otworzył serialu."; exit 1 }
    $stream = $client.GetStream()
    $buf = New-Object byte[] 8192
    $chars = New-Object char[] 8192
    $dec = [Text.Encoding]::UTF8.GetDecoder()
    $end = (Get-Date).AddSeconds(120)
    $i = 0; $seen = 0; $done = $null
    while ((Get-Date) -lt $end) {
        if ($stream.DataAvailable) {
            $n = $stream.Read($buf, 0, $buf.Length)
            $c = $dec.GetChars($buf, 0, $n, $chars, 0)
            $text += [string]::new($chars, 0, $c)
        } else { Start-Sleep -Milliseconds 100 }
        $prompts = ([regex]::Matches($text, 'k\$ ')).Count
        if ($prompts -gt $seen) {
            $seen = $prompts
            if ($i -lt $cmds.Count) {
                $p = [Text.Encoding]::UTF8.GetBytes($cmds[$i] + "`n")
                $stream.Write($p, 0, $p.Length); $i++
            } elseif (-not $done) { $done = (Get-Date).AddSeconds(1) }
        }
        if ($done -and (Get-Date) -gt $done) { break }
    }
} finally {
    if ($client) { $client.Close() }
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    if (-not $srv.HasExited) { $srv.Kill() }
}
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$k = $text.IndexOf("Run /init")
Write-Host $(if ($k -ge 0) { $text.Substring($k) } else { $text })
$kcmd = [regex]::Match($text, 'Kernel command line: ([^\r\n]+)').Groups[1].Value
$checks = [ordered]@{
    'net eth0'          = $text -match 'net — eth0 10\.0\.2\.15/24 gw 10\.0\.2\.2'
    'tunel'             = $text -match "db: 10\.0\.2\.2:$dbPort ecdh hsl=true node_"
    'ZDROWIE'           = $text -match '"action":"HEALTH"' -and $text -match '"protocol":"Cynober-Secure-1\.2"'
    'db info'           = $text -match 'db Cynober-Secure-1\.2 ecdh hsl=true'
    'LISTA ŚWIATÓW'     = $text -match '"action":"LIST_WORLDS"'
    'linia jądra'       = [bool]$kcmd
    'sekret poza linią' = [bool]($kcmd -and $kcmd -notmatch 'KARM_PSK' -and $kcmd -notmatch 'KARM_HSS_PROFILE')
}
$checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { Write-Host "BRAK: $($_.Key)" }
Remove-Item $srvHome -Recurse -Force -ErrorAction SilentlyContinue
if (-not ($checks.Values -contains $false)) { Write-Host "LINUX NET PASS"; exit 0 }
Write-Host "serwer DBase:"; Write-Host (($srvOut.Result -split "`n") | Select-Object -Last 8)
Write-Host "LINUX NET FAIL"
exit 1
