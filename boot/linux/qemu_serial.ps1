# Faza 1: GRUB → Linux → /init = karmazyn_shell.
# Exit 0 gdy serial ma prompt k$ i wynik linii (+ 1 2), oraz „pid 1 stays” po quit.
# Exit 2 gdy brak qemu albo ISO (najpierw scripts\build_linux_shell.ps1).
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$iso = Join-Path $Repo "out\karmazyn-linux.iso"
if (-not (Test-Path $iso)) {
    Write-Host "Brak $iso"
    exit 2
}
$qemu = $env:QEMU_BIN
if (-not $qemu) {
    $cmd = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
    if ($cmd) { $qemu = $cmd.Source }
}
if (-not $qemu) { $qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe" }
if (-not (Test-Path $qemu)) {
    Write-Host "Brak qemu-system-x86_64."
    exit 2
}

$port = 45454
$err = Join-Path $env:TEMP "karmazyn_linux_qemu.err"
$args = @(
    "-machine", "pc,accel=tcg",
    "-m", "256",
    "-boot", "d",
    "-cdrom", $iso,
    "-no-reboot",
    "-display", "none",
    "-vga", "none",
    "-net", "none",
    "-chardev", "socket,id=ser,host=127.0.0.1,port=${port},server=on,wait=off",
    "-serial", "chardev:ser"
)
$proc = Start-Process -FilePath $qemu -ArgumentList $args -PassThru -NoNewWindow -RedirectStandardError $err
$client = $null
$text = ""
try {
    $deadline = (Get-Date).AddSeconds(8)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect("127.0.0.1", $port)
            break
        } catch {
            $client = $null
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $client) {
        Write-Host "QEMU nie otworzył serialu."
        exit 1
    }
    $stream = $client.GetStream()
    $stream.ReadTimeout = 500
    $buf = New-Object byte[] 4096
    $end = (Get-Date).AddSeconds(70)
    $sent = $false
    $quitSent = $false
    while ((Get-Date) -lt $end) {
        if (-not $proc.HasExited -and $stream.DataAvailable) {
            $n = $stream.Read($buf, 0, $buf.Length)
            if ($n -gt 0) {
                $text += [Text.Encoding]::ASCII.GetString($buf, 0, $n)
            }
        } else {
            Start-Sleep -Milliseconds 100
        }
        if (-not $sent -and $text -match 'k\$ ') {
            $payload = [Text.Encoding]::ASCII.GetBytes("(+ 1 2)`n")
            $stream.Write($payload, 0, $payload.Length)
            $sent = $true
        }
        if ($sent -and -not $quitSent -and $text -match '(?m)^3\s*$') {
            $payload = [Text.Encoding]::ASCII.GetBytes("quit`n")
            $stream.Write($payload, 0, $payload.Length)
            $quitSent = $true
        }
        if ($quitSent -and $text -match "pid 1 stays") { break }
    }
} finally {
    if ($client) { $client.Close() }
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
Write-Host $text
$pass = ($text -match 'k\$ ') -and ($text -match '(?m)^3\s*$') -and ($text -match 'pid 1 stays')
if ($pass) {
    Write-Host "LINUX SHELL PASS"
    exit 0
}
Write-Host "LINUX SHELL FAIL"
if (Test-Path $err) { Get-Content $err -Tail 40 }
exit 1
