# Trwały dysk: dwa rozruchy płyty na tym samym dysku virtio (out/karmazyn-disk-test.raw).
# Rozruch 1: pusty dysk, atom, program Lua w fs, sync. Rozruch 2: shell przy
# starcie czyta slot, atom jest z powrotem, program z fs się uruchamia, a narzędzie
# zapisane w fs bin działa jako `tool`, także z biblioteką z fs lib (`require`)
# i napisane w nano (bin/razy, z pustą linią).
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

$disk = Join-Path $Repo "out\karmazyn-disk-test.raw"
if (Test-Path $disk) { Remove-Item $disk -Force }
$f = [IO.File]::Create($disk)
$f.SetLength(16MB)
$f.Close()

# Jeden rozruch. Napis idzie po kolejnym prompcie k$. Tabela @{ after = 'regex';
# send = 'bajty' } idzie bez Entera, gdy od ostatniej wysyłki pojawi się `after`
# (klawisze dla edytora, który nie pokazuje k$).
function Invoke-Boot([object[]]$cmds, [int]$port) {
    $args = @(
        "-machine", "pc,accel=tcg",
        "-m", "256",
        "-boot", "d",
        "-cdrom", $iso,
        "-drive", "file=$disk,format=raw,if=virtio",
        "-no-reboot",
        "-display", "none",
        "-vga", "none",
        "-net", "none",
        "-chardev", "socket,id=ser,host=127.0.0.1,port=${port},server=on,wait=off",
        "-serial", "chardev:ser"
    )
    $proc = Start-Process -FilePath $qemu -ArgumentList $args -PassThru -NoNewWindow
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
        if (-not $client) { return "QEMU nie otworzył serialu." }
        $stream = $client.GetStream()
        $buf = New-Object byte[] 4096
        $chars = New-Object char[] 4096
        $dec = [Text.Encoding]::UTF8.GetDecoder()
        $end = (Get-Date).AddSeconds(70)
        $i = 0
        $seen = 0
        $mark = 0
        $done = $null
        while ((Get-Date) -lt $end) {
            if ($stream.DataAvailable) {
                $n = $stream.Read($buf, 0, $buf.Length)
                $c = $dec.GetChars($buf, 0, $n, $chars, 0)
                $text += [string]::new($chars, 0, $c)
            } else {
                Start-Sleep -Milliseconds 100
            }
            $prompts = ([regex]::Matches($text, 'k\$ ')).Count
            $next = if ($i -lt $cmds.Count) { $cmds[$i] } else { $null }
            if ($next -is [hashtable]) {
                if ($text.Substring($mark) -match $next.after) {
                    $p = [Text.Encoding]::UTF8.GetBytes($next.send)
                    $stream.Write($p, 0, $p.Length)
                    $i++
                    $mark = $text.Length
                }
            } elseif ($prompts -gt $seen) {
                $seen = $prompts
                if ($null -ne $next) {
                    $p = [Text.Encoding]::UTF8.GetBytes($next + "`n")
                    $stream.Write($p, 0, $p.Length)
                    $i++
                    $mark = $text.Length
                } elseif (-not $done) {
                    $done = (Get-Date).AddSeconds(1)
                }
            }
            if ($done -and (Get-Date) -gt $done) { break }
        }
    } finally {
        if ($client) { $client.Close() }
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    return $text
}

# Od wiersza „Run /init”; bez niego (panic, brak shella) ostatnie 40 wierszy.
function Tail([string]$t) {
    $k = $t.IndexOf("Run /init")
    if ($k -ge 0) { return $t.Substring($k) }
    return (($t -split "`n") | Select-Object -Last 40) -join "`n"
}

[Console]::OutputEncoding = [Text.Encoding]::UTF8
$prog = "lua karmazyn.fs.write('bin','hello','lua',""return function(n) return 'hej '..n end"")"
$tool = "lua karmazyn.fs.write('bin','powitanie','lua',""local n = ...; return 'witaj '..(n or '?')"")"
$lib = "lua karmazyn.fs.write('lib','mat','lua',""return { dodaj = function(a,b) return a+b end }"")"
$suma = "lua karmazyn.fs.write('bin','suma','lua',""local a,b = ...; return require('mat').dodaj(tonumber(a), tonumber(b))"")"
# nano przez serial: wszystkie linie edycji idą naraz, nano czyta je z tego samego stdin
$nano = "tool nano bin/razy`nlocal a, b = ...`n`nreturn tonumber(a) * tonumber(b)`n.save"
# edytor z kursorem: pusty plik, "return a", Home, wstaw linię nad, End, dopisz, ^S, ^Q
$keys = "return a`e[Hlocal a = ...`r`e[F..' kursor'" + [char]0x13 + [char]0x11
$one = Invoke-Boot @("disk", "atom trwaly hej 80", $prog, $tool, $lib, $suma, $nano,
    "edit bin/kursor", @{ after = 'L1:1'; send = $keys },
    "lua return karmazyn.fs.read('bin','kursor')", "sync",
    "lua karmazyn.fs.write('dev','po_sync','txt','autosync ok')", "disk") 45471
Write-Host "--- rozruch 1 ---"
Write-Host (Tail $one)
$two = Invoke-Boot @("info 0", "assert has 0", "lua return load(karmazyn.fs.read('bin','hello'))()('swiat')",
    "tool powitanie Karmazyn", "tool suma 40 2", "tool razy 6 9", "lua return karmazyn.fs.read('bin','razy')",
    "tool kursor Hej", "lua return karmazyn.fs.read('dev','po_sync')", "disk") 45472
Write-Host "--- rozruch 2 ---"
Write-Host (Tail $two)

$checks = [ordered]@{
    'pusty dysk, autosync' = $one -match 'disk — /dev/vda pusty, autosync'
    'sync'                 = $one -match 'sync /dev/vda gen=\d+'
    'nano bin/razy'        = $one -match 'Zapisano bin/razy \(3 linii\)'
    'nano bufor przed >'   = $one -match '===== bin/razy =====\s+Komendy:[^\n]*\n> '
    'edit zamknięty'       = $one -match 'edit: zamknięto bin/kursor'
    'edit treść'           = $one -match "local a = \.\.\.\r?\nreturn a\.\.' kursor'"
    'restore'              = $two -match 'disk — /dev/vda gen=\d+ atoms=8'
    'atom'                 = ($two -match 's=trwaly e=hej') -and ($two -match 'assert ok')
    'program fs'           = $two -match '(?m)^hej swiat'
    'tool fs bin'          = $two -match '(?m)^witaj Karmazyn'
    'require fs lib'       = $two -match '(?m)^42\s*$'
    'tool z nano'          = ($two -match '(?m)^54\s*$') -and ($two -match 'local a, b = \.\.\.\r?\n\r?\nreturn')
    'tool z edit'          = $two -match '(?m)^Hej kursor'
    'autosync po sync'     = $two -match '(?m)^autosync ok'
}
$checks.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { Write-Host "BRAK: $($_.Key)" }
$pass = -not ($checks.Values -contains $false)
Remove-Item $disk -Force -ErrorAction SilentlyContinue
if ($pass) {
    Write-Host "LINUX DISK PASS"
    exit 0
}
Write-Host "LINUX DISK FAIL"
exit 1
