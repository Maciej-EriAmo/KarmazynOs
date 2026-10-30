# Konsola VGA + serial: płyta z kartą graficzną (bez okna). Na klawiaturze
# (monitor QEMU, sendkey) idzie `lua return 6*7`, przez serial `atom z_serialu …`.
# Pass: na serialu jest echo linii z klawiatury i jej wynik 42 oraz wynik
# polecenia z serialu. Zrzut ekranu VGA: out/karmazyn-vga.png (do obejrzenia).
# Exit 0 = pass, 1 = fail, 2 = brak qemu albo ISO.
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

$shot = Join-Path $Repo "out\karmazyn-vga.png"
if (Test-Path $shot) { Remove-Item $shot -Force }
$mport = 45481
$sport = 45482
$args = @(
    "-machine", "pc,accel=tcg",
    "-m", "256",
    "-boot", "d",
    "-cdrom", $iso,
    "-no-reboot",
    "-display", "none",
    "-vga", "std",
    "-net", "none",
    "-monitor", "tcp:127.0.0.1:${mport},server,nowait",
    "-chardev", "socket,id=ser,host=127.0.0.1,port=${sport},server=on,wait=off",
    "-serial", "chardev:ser"
)
$proc = Start-Process -FilePath $qemu -ArgumentList $args -PassThru -NoNewWindow

function Connect-Port([int]$port) {
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $c.Connect("127.0.0.1", $port)
            return $c
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    return $null
}

$text = ""
$ser = $null
$mon = $null
try {
    $ser = Connect-Port $sport
    $mon = Connect-Port $mport
    if (-not $ser -or -not $mon) {
        Write-Host "QEMU nie otworzył serialu albo monitora."
        exit 1
    }
    $ss = $ser.GetStream()
    $ms = $mon.GetStream()
    $buf = New-Object byte[] 8192
    $dec = [Text.Encoding]::UTF8.GetDecoder()
    $chars = New-Object char[] 8192
    function Pump {
        while ($ss.DataAvailable) {
            $n = $ss.Read($buf, 0, $buf.Length)
            $c = $dec.GetChars($buf, 0, $n, $chars, 0)
            $script:text += [string]::new($chars, 0, $c)
        }
        while ($ms.DataAvailable) { [void]$ms.Read($buf, 0, $buf.Length) }
    }
    function Send-Monitor([string]$line) {
        $b = [Text.Encoding]::ASCII.GetBytes($line + "`n")
        $ms.Write($b, 0, $b.Length)
        Start-Sleep -Milliseconds 120
        Pump
    }

    $end = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $end -and $text -notmatch 'k\$ ') {
        Pump
        Start-Sleep -Milliseconds 200
    }
    # klawiatura → tty1
    foreach ($k in @("l", "u", "a", "spc", "r", "e", "t", "u", "r", "n", "spc", "6", "shift-8", "7", "ret")) {
        Send-Monitor "sendkey $k"
    }
    Start-Sleep -Seconds 2
    Pump
    # serial → ttyS0
    $p = [Text.Encoding]::UTF8.GetBytes("atom z_serialu tak 60`n")
    $ss.Write($p, 0, $p.Length)
    Start-Sleep -Seconds 2
    Pump
    Send-Monitor "screendump $($shot -replace '\\', '/') -f png"
    Start-Sleep -Seconds 2
} finally {
    if ($ser) { $ser.Close() }
    if ($mon) { $mon.Close() }
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

[Console]::OutputEncoding = [Text.Encoding]::UTF8
$k = $text.IndexOf("Run /init")
Write-Host $(if ($k -ge 0) { $text.Substring($k) } else { $text })
$checks = [ordered]@{
    'konsola tty1 + ttyS0'      = $text -match 'console — tty1 \+ ttyS0'
    'echo linii z klawiatury'   = $text -match 'k\$ lua return 6\*7\r?\n42'
    'polecenie z serialu'       = $text -match 'aid=\d+ state=\w+ t=60\.000'
    'zrzut ekranu'              = Test-Path $shot
}
$checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { Write-Host "BRAK: $($_.Key)" }
if (-not ($checks.Values -contains $false)) {
    Write-Host "zrzut: $shot"
    Write-Host "LINUX VGA PASS"
    exit 0
}
Write-Host "LINUX VGA FAIL"
exit 1
