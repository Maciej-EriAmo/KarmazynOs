# Faza 1 mapy Documents/linux_hss_roadmap.md
# Statyczny shell + jądro virt + GRUB. Wynik: out/karmazyn-linux.iso
# Nie jest płytą kentry i nie jest obrazem do promptu karmazyn>.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$shellDir = Join-Path $Repo "native\karmazyn_shell"
$target = "x86_64-unknown-linux-musl"
$elf = Join-Path $shellDir "target\$target\release\karmazyn_shell"

rustup target add $target
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$lld = Join-Path $env:USERPROFILE ".rustup\toolchains\stable-x86_64-pc-windows-msvc\lib\rustlib\x86_64-pc-windows-msvc\bin\rust-lld.exe"
if (-not (Test-Path $lld)) {
    Write-Host "Brak rust-lld: $lld"
    exit 2
}
$env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER = $lld
cargo build --release --target $target --manifest-path (Join-Path $shellDir "Cargo.toml")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path $elf)) {
    Write-Host "Brak ELF: $elf"
    exit 1
}

$cache = Join-Path $env:LOCALAPPDATA "KarmazynOs"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$vmlinuz = Join-Path $cache "vmlinuz-virt"
if (-not (Test-Path $vmlinuz) -or (Get-Item $vmlinuz).Length -lt 1000000) {
    $urls = @(
        "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/netboot/vmlinuz-virt",
        "https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/netboot/vmlinuz-virt"
    )
    $ok = $false
    foreach ($u in $urls) {
        Write-Host "GET $u"
        & curl.exe -fL --retry 2 -o $vmlinuz $u
        if ($LASTEXITCODE -eq 0 -and (Test-Path $vmlinuz) -and (Get-Item $vmlinuz).Length -gt 1000000) {
            $ok = $true
            break
        }
    }
    if (-not $ok) {
        Write-Host "Nie pobrano vmlinuz-virt."
        exit 2
    }
}

$out = Join-Path $Repo "out"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$initrd = Join-Path $out "initramfs.cpio"
python (Join-Path $Repo "scripts\pack_initramfs.py") $elf $initrd
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$grub = $env:GRUB_DIR
if (-not $grub) { $grub = Join-Path $cache "grub-2.12-for-windows" }
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

$stage = Join-Path $out "linux-iso-root"
$iso = Join-Path $out "karmazyn-linux.iso"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage "boot\grub") | Out-Null
Copy-Item (Join-Path $Repo "boot\linux\grub.cfg") (Join-Path $stage "boot\grub\grub.cfg")
Copy-Item $vmlinuz (Join-Path $stage "boot\vmlinuz")
Copy-Item $initrd (Join-Path $stage "boot\initramfs.cpio")
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
& $xorriso -as mkisofs -iso-level 3 -R -J -volid "KARMAZYN_LINUX" `
    -o (To-MsysPath $iso) `
    -c boot/grub/boot.cat `
    -b boot/grub/i386-pc/eltorito.img `
    -no-emul-boot -boot-load-size 4 -boot-info-table `
    --grub2-boot-info `
    (To-MsysPath $stage)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "OK iso=$iso size=$((Get-Item $iso).Length) elf=$((Get-Item $elf).Length)"
