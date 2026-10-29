# ISO GRUB dla kentry (Multiboot2). Nie jest obrazem do promptu produktu.
# Wymaga: ELF kentry, GRUB 2.12 for Windows (GRUB_DIR albo %LOCALAPPDATA%\KarmazynOs\grub-2.12-for-windows), xorriso.
# GRUB 2.14 for Windows ma i386-pc/kernel.img z VMA 0 zamiast 0x9000 — grub-mkimage go odrzuca.
# Wynik: out/karmazyn-kentry.iso
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$elf = Join-Path $Repo "boot\kentry\target\x86_64-unknown-none\release\karmazyn_kentry"
if (-not (Test-Path $elf)) {
    & (Join-Path $Repo "scripts\build_kentry.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$grub = $env:GRUB_DIR
if (-not $grub) {
    $grub = Join-Path $env:LOCALAPPDATA "KarmazynOs\grub-2.12-for-windows"
}
$mkimage = Join-Path $grub "grub-mkimage.exe"
$grubFile = Join-Path $grub "grub-file.exe"
if (-not (Test-Path $mkimage)) {
    Write-Host "Brak grub-mkimage. Rozpakuj https://ftp.gnu.org/gnu/grub/grub-2.12-for-windows.zip i ustaw GRUB_DIR."
    exit 2
}

$xorriso = $env:XORRISO
if (-not $xorriso) { $xorriso = "C:\msys64\usr\bin\xorriso.exe" }
if (-not (Test-Path $xorriso)) {
    Write-Host "Brak xorriso (XORRISO albo C:\msys64\usr\bin\xorriso.exe)."
    exit 2
}

& $grubFile --is-x86-multiboot2 $elf
if ($LASTEXITCODE -ne 0) {
    Write-Host "ELF nie jest Multiboot2 wg grub-file."
    exit 1
}

$stage = Join-Path $Repo "out\kentry-iso-root"
$iso = Join-Path $Repo "out\karmazyn-kentry.iso"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage "boot\grub") | Out-Null
Copy-Item (Join-Path $Repo "boot\grub\grub.cfg") (Join-Path $stage "boot\grub\grub.cfg")
Copy-Item $elf (Join-Path $stage "boot\karmazyn_kentry")
Copy-Item (Join-Path $grub "i386-pc") (Join-Path $stage "boot\grub\i386-pc") -Recurse

$elt = Join-Path $stage "boot\grub\i386-pc\eltorito.img"
& $mkimage -O i386-pc-eltorito -o $elt -p "/boot/grub" -d (Join-Path $grub "i386-pc") `
    biosdisk boot iso9660 normal configfile multiboot2 serial
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $iso) { Remove-Item $iso -Force }
$env:Path = "C:\msys64\usr\bin;" + $env:Path
# xorriso to binarka MSYS: ścieżka Windows jest sklejana z cwd. Podajemy /c/... i wyłączamy konwersję.
function To-MsysPath([string]$path) {
    $full = [IO.Path]::GetFullPath($path)
    if ($full -match "^([A-Za-z]):\\(.*)$") {
        return "/" + $Matches[1].ToLower() + "/" + ($Matches[2] -replace "\\", "/")
    }
    return ($full -replace "\\", "/")
}
$env:MSYS2_ARG_CONV_EXCL = "*"
& $xorriso -as mkisofs -iso-level 3 -R -J -volid "KARMAZYN_KENTRY" `
    -o (To-MsysPath $iso) `
    -c boot/grub/boot.cat `
    -b boot/grub/i386-pc/eltorito.img `
    -no-emul-boot -boot-load-size 4 -boot-info-table `
    --grub2-boot-info `
    (To-MsysPath $stage)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "OK iso=$iso size=$((Get-Item $iso).Length)"
