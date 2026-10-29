# SF.2 — serial kentry bez ISO.
# qemu-system-x86_64 -kernel <ELF> -serial file:... ; halt nie wraca, proces jest ubijany.
# Exit 0 tylko gdy log zawiera KARMAZYN_KENTRY_OK i SLAB_OK.
# Exit 2 gdy brak qemu (QEMU_BIN albo PATH).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$elf64 = Join-Path $Root "target\x86_64-unknown-none\release\karmazyn_kentry"
if (-not (Test-Path $elf64)) {
    Write-Host "Brak ELF. Najpierw: scripts\build_kentry.ps1"
    exit 1
}

$qemu = $env:QEMU_BIN
if (-not $qemu) {
    $cmd = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
    if ($cmd) { $qemu = $cmd.Source }
}
if (-not $qemu -or -not (Test-Path $qemu)) {
    Write-Host "SF.2 otwarte: brak qemu-system-x86_64 (PATH albo QEMU_BIN)."
    exit 2
}

# QEMU 11 ładuje ten ELF notatką PVH (Multiboot2 zostaje dla GRUB).
$kernel = $elf64
Write-Host "kernel=$kernel"

function Read-SharedText([string]$path) {
    if (-not (Test-Path $path)) { return "" }
    $fs = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = New-Object IO.StreamReader($fs)
        return $reader.ReadToEnd()
    } finally {
        $reader.Dispose()
    }
}

$log = Join-Path $env:TEMP "karmazyn_kentry_serial.log"
$err = Join-Path $env:TEMP "karmazyn_kentry_qemu.err"
if (Test-Path $log) { Remove-Item $log -Force }
if (Test-Path $err) { Remove-Item $err -Force }

$argList = @(
    "-machine", "pc,accel=tcg",
    "-m", "64",
    "-no-reboot",
    "-display", "none",
    "-vga", "none",
    "-net", "none",
    "-serial", "file:$log",
    "-kernel", $kernel
)
Write-Host "qemu=$qemu"
$proc = Start-Process -FilePath $qemu -ArgumentList $argList -PassThru -WindowStyle Hidden -RedirectStandardError $err
try {
    $deadline = (Get-Date).AddSeconds(20)
    $text = ""
    do {
        Start-Sleep -Milliseconds 200
        try { $text = Read-SharedText $log } catch { $text = "" }
        if ($text -match "SLAB_OK" -and $text -match "KARMAZYN_KENTRY_OK") { break }
        if ($proc.HasExited) { break }
    } while ((Get-Date) -lt $deadline)
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $proc.WaitForExit(3000) | Out-Null
    }
}

if (-not $text -and (Test-Path $log)) {
    Start-Sleep -Milliseconds 300
    try { $text = Read-SharedText $log } catch { $text = "" }
}
Write-Host "---- serial ----"
Write-Host $text
if (Test-Path $err) {
    try { $errText = Read-SharedText $err } catch { $errText = "" }
    if ($errText) {
        Write-Host "---- qemu stderr ----"
        Write-Host $errText
    }
}
if ($text -match "KARMAZYN_KENTRY_OK" -and $text -match "SLAB_OK" -and $text -notmatch "SLAB_FAIL") {
    Write-Host "SF.2 PASS"
    exit 0
}
Write-Host "SF.2 FAIL"
exit 1
