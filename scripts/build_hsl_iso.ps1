# Faza 2: osobna płyta. Jądro 6.18.57, moduł holo_hsl.ko, shell z fazy 1.
# Nie nadpisuje out/karmazyn-linux.iso.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Cache = Join-Path $env:LOCALAPPDATA "KarmazynOs"
$vmlinuz = Join-Path $Cache "vmlinuz-virt-6.18.57"
$built = Join-Path $Repo "out\hsl-build"
$shell = Join-Path $Repo "native\karmazyn_shell\target\x86_64-unknown-linux-musl\release\karmazyn_shell"
foreach ($p in @(
    $vmlinuz,
    (Join-Path $built "holo_hsl.ko"),
    (Join-Path $built "hsl-check"),
    (Join-Path $built "init-hsl"),
    $shell
)) {
  if (-not (Test-Path $p)) {
    Write-Host "Brak $p"
    exit 2
  }
}

$work = Join-Path $Repo "out\hsl-init"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force -Path $work, "$work\proc", "$work\sys", "$work\dev", "$work\mnt" | Out-Null
Copy-Item (Join-Path $built "init-hsl") (Join-Path $work "init")
Copy-Item (Join-Path $built "holo_hsl.ko") (Join-Path $work "holo_hsl.ko")
Copy-Item (Join-Path $built "hsl-check") (Join-Path $work "hsl-check")
Copy-Item $shell (Join-Path $work "karmazyn_shell")
$cpio = Join-Path $Repo "out\hsl-initramfs.cpio"
python (Join-Path $Repo "scripts\pack_tree_cpio.py") $work $cpio
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$grub = $env:GRUB_DIR
if (-not $grub) { $grub = Join-Path $Cache "grub-2.12-for-windows" }
$mkimage = Join-Path $grub "grub-mkimage.exe"
if (-not (Test-Path $mkimage)) {
  Write-Host "Brak grub-mkimage (GRUB 2.12). Ustaw GRUB_DIR."
  exit 2
}
$xorriso = $env:XORRISO
if (-not $xorriso) { $xorriso = "C:\msys64\usr\bin\xorriso.exe" }
if (-not (Test-Path $xorriso)) {
  Write-Host "Brak xorriso."
  exit 2
}

$out = Join-Path $Repo "out"
$stage = Join-Path $out "hsl-iso-root"
$iso = Join-Path $out "karmazyn-linux-hsl.iso"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage "boot\grub") | Out-Null
Copy-Item (Join-Path $Repo "boot\linux\grub.cfg") (Join-Path $stage "boot\grub\grub.cfg")
Copy-Item $vmlinuz (Join-Path $stage "boot\vmlinuz")
Copy-Item $cpio (Join-Path $stage "boot\initramfs.cpio")
Copy-Item (Join-Path $grub "i386-pc") (Join-Path $stage "boot\grub\i386-pc") -Recurse
$elt = Join-Path $stage "boot\grub\i386-pc\eltorito.img"
& $mkimage -O i386-pc-eltorito -o $elt -p "/boot/grub" -d (Join-Path $grub "i386-pc") `
  biosdisk boot iso9660 normal configfile linux serial
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

function To-MsysPath([string]$path) {
  $full = [IO.Path]::GetFullPath($path)
  if ($full -match "^([A-Za-z]):\\(.*)$") {
    return "/" + $Matches[1].ToLower() + "/" + ($Matches[2] -replace "\\", "/")
  }
  return ($full -replace "\\", "/")
}
if (Test-Path $iso) { Remove-Item $iso -Force }
$env:Path = "C:\msys64\usr\bin;" + $env:Path
$env:MSYS2_ARG_CONV_EXCL = "*"
& $xorriso -as mkisofs -iso-level 3 -R -J -volid "KARMAZYN_HSL" `
  -o (To-MsysPath $iso) `
  -c boot/grub/boot.cat `
  -b boot/grub/i386-pc/eltorito.img `
  -no-emul-boot -boot-load-size 4 -boot-info-table `
  --grub2-boot-info `
  (To-MsysPath $stage)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "OK iso=$iso size=$((Get-Item $iso).Length)"
