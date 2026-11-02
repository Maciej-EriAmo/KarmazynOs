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
        $waitUntil = $null
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
            if ($next -is [hashtable] -and $next.ContainsKey('wait')) {
                # epoki płyną same: odczekaj, potem wyślij
                if (-not $waitUntil) {
                    $waitUntil = (Get-Date).AddSeconds($next.wait)
                } elseif ((Get-Date) -gt $waitUntil) {
                    $p = [Text.Encoding]::UTF8.GetBytes($next.send + "`n")
                    $stream.Write($p, 0, $p.Length)
                    $i++
                    $mark = $text.Length
                    $waitUntil = $null
                }
            } elseif ($next -is [hashtable]) {
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
# servitor: bąbel kodu powiązany z bąblem servitory, krok w każdej epoce
$svc = "lua karmazyn.code.write('licznik',""k = (k or 0) + 1 print('krok '..k) return true"")"
# nano przez serial: wszystkie linie edycji idą naraz, nano czyta je z tego samego stdin
$nano = "tool nano razy`nlocal a, b = ...`n`nreturn tonumber(a) * tonumber(b)`n.save"
# edytor z kursorem: pusty plik, "return a", Home, wstaw linię nad, End, dopisz, ^S, ^Q
# dwie porcje: po pierwszej edytor rysuje tylko zmienione wiersze (linia 1 + pasek)
$keys = "`e[Hlocal a = ...`r`e[F..' kursor'" + [char]0x13 + [char]0x11
$seeds = @(Get-ChildItem (Join-Path $Repo "lua_bin\*.lua")).Count
# ziarno + trwaly, hello, powitanie, mat, suma, razy, kursor, po_sync, licznik
# (bez stempla czasu i wpisów dziennika: tych przybywa z każdym rozruchem)
$atoms = $seeds + 9
$one = Invoke-Boot @("disk", "atom trwaly hej 80", $prog, $tool, $lib, $suma, $link, $nano,
    "edit kursor", @{ after = 'L1:1'; send = "return a" }, @{ after = 'L1:9'; send = $keys },
    "lua return karmazyn.code.read('kursor')", $svc, "servitor up licznik", "tick 2", "sync",
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
    "tool kursor Hej", "lua return karmazyn.fs.read('dev','po_sync')", "servitor",
    @{ wait = 7; send = "lua return 'kroki='..tostring(k)" }, "dziennik 400", "disk") 45472
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
    # formater zakłada dziennik JBD2: jądro montuje z księgowaniem, a po twardym
    # wyłączeniu (Stop-Process między rozruchami) nie widzi niesprawdzonego fs
    'dziennik ext4'        = ($one -match 'EXT4-fs \(vda\): mounted filesystem .* r/w with ordered data mode') -and
                             ($two -match 'EXT4-fs \(vda\): mounted filesystem .* r/w with ordered data mode') -and
                             ($two -notmatch 'mounting unchecked fs') -and ($two -notmatch 'EXT4-fs error')
    'pusty dysk → ext4'    = $one -match 'disk — /dev/vda ext4 → /data, sformatowano, nowy świat /data/cynober/worlds/karmazyn\.kafd, autosync'
    'sync'                 = $one -match 'sync /data/cynober/worlds/karmazyn\.kafd dokumenty=\d+'
    'nano bąbel razy'      = $one -match 'Zapisano razy \(3 linii\)'
    # echo terminala może wstawić pustą linię przed pierwszym "> "
    'nano bufor przed >'   = $one -match '===== razy =====\s+Komendy:[^\n]*\n\s*> '
    'edit zamknięty'       = $one -match 'edit: zamknięto kursor'
    'edit rysuje przyrost' = $one -match '\x1b\[1;1Hreturn a\x1b\[K\x1b\[23;1H\x1b\[7m[^\x1b]*L1:9'
    'edit treść'           =$one -match "local a = \.\.\.\r?\nreturn a\.\.' kursor'"
    'restore'              = ($two -match "disk — /dev/vda ext4 → /data, świat /data/cynober/worlds/karmazyn\.kafd atoms=(\d+)") -and ([int]$Matches[1] -gt $atoms)
    'atom'                 = ($two -match 's=trwaly e=hej') -and ($two -match 'assert ok')
    'program bąbla'        = $two -match '(?m)^hej swiat'
    'tool po etykiecie'    = $two -match '(?m)^witaj Karmazyn'
    'require powiązanie'   = $two -match '(?m)^42\s*$'
    'tool z nano'          = ($two -match '(?m)^54\s*$') -and ($two -match 'local a, b = \.\.\.\r?\n\r?\nreturn')
    'tool z edit'          = $two -match '(?m)^Hej kursor'
    'autosync po sync'     = $two -match '(?m)^autosync ok'
    # zapis przyrostowy: po `sync` dziennik pusty (8 B), autosync dopisuje tylko
    # zmianę do .kafs, koperta .kafd zostaje; rozruch 2 odtwarza ją z dziennika
    'dziennik zmian KAFS'  = ([regex]::Matches($one, 'dziennik=(\d+)') | ForEach-Object { [int]$_.Groups[1].Value } |
                              Select-Object -Last 1) -gt 8
    # servitor, dziennik i stempel są treścią świata: przechodzą przez restart
    'servitor krok'        = $one -match '(?m)^servitor licznik: krok \d+'
    # rozruch 2 nie woła tick: kroki robi zegar epok PID 1 (KARMAZYN_TICK_MS)
    'zegar epok'           = ($two -match 'epoki — co 2000 ms') -and ($two -match 'kroki=[1-9]')
    'servitor po restarcie' = ($two -match '(?m)^\s+(HOT|WARM)\s+[\d.]+\s+licznik') -and ($two -match 'servitor:licznik krok')
    'dziennik po restarcie' = ($two -match 'dziennik — [1-9]\d* wpisów z poprzednich sesji') -and ($two -match 'shell servitor up licznik')
    'stempel po restarcie' = ($one -match 'czas — pierwszy stempel') -and ($two -match 'czas — stempel zgodny')
    # rozruch 2 tylko czyta i uruchamia narzędzia: jedyny zapis to nowy stempel czasu
    # (heat, krok servitora i wpisy dziennika nie są treścią dla autosync)
    'odczyt bez zapisu'    = $two -match 'świat=/data/cynober/worlds/karmazyn\.kafd KAFX \(AES-GCM\) bytes=\d+ dziennik=\d+ zapisy=1'
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
