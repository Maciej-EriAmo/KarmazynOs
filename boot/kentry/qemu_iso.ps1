# GRUB z ISO ładuje kentry (Multiboot2). Halt nie wraca — QEMU jest ubijane.
# Exit 0 gdy serial ma KARMAZYN_KENTRY_OK, MB2_MAGIC_OK, karmazyn.kentry=1 i SLAB_OK.
# Exit 2 gdy brak qemu albo ISO (najpierw scripts\build_kentry_iso.ps1).
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$iso = Join-Path $Repo "out\karmazyn-kentry.iso"
if (-not (Test-Path $iso)) {
    Write-Host "Brak ISO. Najpierw: scripts\build_kentry_iso.ps1"
    exit 2
}

$qemu = $env:QEMU_BIN
if (-not $qemu) {
    $cmd = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
    if ($cmd) { $qemu = $cmd.Source }
}
if (-not $qemu -or -not (Test-Path $qemu)) {
    $fallback = "C:\Program Files\qemu\qemu-system-x86_64.exe"
    if (Test-Path $fallback) { $qemu = $fallback }
}
if (-not $qemu -or -not (Test-Path $qemu)) {
    Write-Host "Brak qemu-system-x86_64 (PATH albo QEMU_BIN)."
    exit 2
}

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

$log = Join-Path $env:TEMP "karmazyn_kentry_iso_serial.log"
$err = Join-Path $env:TEMP "karmazyn_kentry_iso_qemu.err"
if (Test-Path $log) { Remove-Item $log -Force }
if (Test-Path $err) { Remove-Item $err -Force }

$argList = @(
    "-machine", "pc,accel=tcg",
    "-m", "64",
    "-boot", "d",
    "-cdrom", $iso,
    "-no-reboot",
    "-display", "none",
    "-vga", "none",
    "-net", "none",
    "-serial", "file:$log"
)
Write-Host "qemu=$qemu"
Write-Host "iso=$iso"
$proc = Start-Process -FilePath $qemu -ArgumentList $argList -PassThru -WindowStyle Hidden -RedirectStandardError $err
try {
    $deadline = (Get-Date).AddSeconds(40)
    $text = ""
    do {
        Start-Sleep -Milliseconds 250
        try { $text = Read-SharedText $log } catch { $text = "" }
        if ($text -match "SLAB_OK" -and $text -match "KARMAZYN_KENTRY_OK" -and $text -match "MB2_MAGIC_OK") { break }
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
$ok = $text -match "KARMAZYN_KENTRY_OK" -and $text -match "SLAB_OK" -and $text -notmatch "SLAB_FAIL" `
    -and $text -match "MB2_MAGIC_OK" -and $text -match "karmazyn\.kentry=1"
if ($ok) {
    Write-Host "ISO GRUB PASS"
    exit 0
}
Write-Host "ISO GRUB FAIL"
exit 1
