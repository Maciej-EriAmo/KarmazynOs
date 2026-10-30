# Trwały dysk: dwa rozruchy płyty na tym samym dysku virtio (out/karmazyn-disk-test.raw).
# Rozruch 1: pusty dysk → shell zakłada ext2, montuje go jako ext4 pod /data;
# atom, bąbel kodu, sync zapisuje świat KAFD (KAFX) w
# /data/cynober/worlds/karmazyn.kafd. Rozruch 2: shell wczytuje świat,
# atom jest z powrotem, program z bąbla się uruchamia, a narzędzie
# o etykiecie działa jako `tool`, także z biblioteką powiązaną przez code.link
# i napisane w nano (bąbel razy, z pustą linią).
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
            $proc.WaitForExit(5000) | Out-Null
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
$prog = "lua karmazyn.code.write('hello',""return function(n) return 'hej '..n end"")"
$tool = "lua karmazyn.code.write('powitanie',""local n = ...; return 'witaj '..(n or '?')"")"
$lib = "lua karmazyn.code.write('mat',""return { dodaj = function(a,b) return a+b end }"")"
$suma = "lua karmazyn.code.write('suma',""local a,b = ...; return require('mat').dodaj(tonumber(a), tonumber(b))"")"
$link = "lua karmazyn.code.link('suma','mat')"
# nano przez serial: wszystkie linie edycji idą naraz, nano czyta je z tego samego stdin
$nano = "tool nano razy`nlocal a, b = ...`n`nreturn tonumber(a) * tonumber(b)`n.save"
# edytor z kursorem: pusty plik, "return a", Home, wstaw linię nad, End, dopisz, ^S, ^Q
# dwie porcje: po pierwszej edytor rysuje tylko zmienione wiersze (linia 1 + pasek)
$keys = "`e[Hlocal a = ...`r`e[F..' kursor'" + [char]0x13 + [char]0x11
$seeds = @(Get-ChildItem (Join-Path $Repo "lua_bin\*.lua")).Count
# ziarno + trwaly, hello, powitanie, mat, suma, razy, kursor, po_sync
$atoms = $seeds + 8
$one = Invoke-Boot @("disk", "atom trwaly hej 80", $prog, $tool, $lib, $suma, $link, $nano,
    "edit kursor", @{ after = 'L1:1'; send = "return a" }, @{ after = 'L1:9'; send = $keys },
    "lua return karmazyn.code.read('kursor')", "sync",
    "lua karmazyn.fs.write('dev','po_sync','txt','autosync ok')", "disk") 45471
Write-Host "--- rozruch 1 ---"
Write-Host (Tail $one)
if ($one -notmatch 'aid=(\d+) state=') {
    Write-Host "BRAK: aid atomu trwaly"
    exit 1
}
$aid = $Matches[1]
$two = Invoke-Boot @("info $aid", "assert has $aid", "lua return load(karmazyn.code.read('hello'))()('swiat')",
    "tool powitanie Karmazyn", "tool suma 40 2", "tool razy 6 9", "lua return karmazyn.code.read('razy')",
    "tool kursor Hej", "lua return karmazyn.fs.read('dev','po_sync')", "disk") 45472
Write-Host "--- rozruch 2 ---"
Write-Host (Tail $two)

$raw = $null
foreach ($try in 1..20) {
    try {
        $raw = [IO.File]::ReadAllBytes($disk)
        break
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if ($null -eq $raw) { throw "dysk zajęty: $disk" }
$rawText = [Text.Encoding]::GetEncoding(28591).GetString($raw)
$checks = [ordered]@{
    'pusty dysk → ext4'    = $one -match 'disk — /dev/vda ext4 → /data, sformatowano, nowy świat /data/cynober/worlds/karmazyn\.kafd, autosync'
    'sync'                 = $one -match 'sync /data/cynober/worlds/karmazyn\.kafd dokumenty=\d+'
    'nano bąbel razy'      = $one -match 'Zapisano razy \(3 linii\)'
    # echo terminala może wstawić pustą linię przed pierwszym "> "
    'nano bufor przed >'   = $one -match '===== razy =====\s+Komendy:[^\n]*\n\s*> '
    'edit zamknięty'       = $one -match 'edit: zamknięto kursor'
    'edit rysuje przyrost' = $one -match '\x1b\[1;1Hreturn a\x1b\[K\x1b\[23;1H\x1b\[7m[^\x1b]*L1:9'
    'edit treść'           =$one -match "local a = \.\.\.\r?\nreturn a\.\.' kursor'"
    'restore'              = $two -match "disk — /dev/vda ext4 → /data, świat /data/cynober/worlds/karmazyn\.kafd atoms=$atoms"
    'atom'                 = ($two -match 's=trwaly e=hej') -and ($two -match 'assert ok')
    'program bąbla'        = $two -match '(?m)^hej swiat'
    'tool po etykiecie'    = $two -match '(?m)^witaj Karmazyn'
    'require powiązanie'   = $two -match '(?m)^42\s*$'
    'tool z nano'          = ($two -match '(?m)^54\s*$') -and ($two -match 'local a, b = \.\.\.\r?\n\r?\nreturn')
    'tool z edit'          = $two -match '(?m)^Hej kursor'
    'autosync po sync'     = $two -match '(?m)^autosync ok'
    # rozruch 2 tylko czyta i uruchamia narzędzia: autosync nie pisze (heat to nie treść)
    # rozruch 2 tylko czyta i uruchamia narzędzia: autosync nie pisze (heat to nie treść)
    'odczyt bez zapisu'    = $two -match 'świat=/data/cynober/worlds/karmazyn\.kafd KAFX \(AES-GCM\) bytes=\d+ zapisy=0'
    # surowy dysk: superblok ext2/ext4, świat w kopercie KAFX, bez jawnych programów
    'ext na dysku'         = $raw.Length -gt 1081 -and $raw[1080] -eq 0x53 -and $raw[1081] -eq 0xEF
    'KAFX na dysku'        = $rawText.Contains('KAFX')
    'bez jawnej treści'    = -not $rawText.Contains("return function(n)") -and -not $rawText.Contains("autosync ok")
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
