# Faza 1 mapy Documents/linux_hss_roadmap.md
# Statyczny shell + jądro virt + GRUB. Wynik: out/karmazyn-linux.iso
# Nie jest płytą kentry i nie jest obrazem do promptu karmazyn>.
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$shellDir = Join-Path $Repo "native\karmazyn_shell"
$target = "x86_64-unknown-linux-musl"
$elf = Join-Path $shellDir "target\$target\release\karmazyn_shell"

$cache = Join-Path $env:LOCALAPPDATA "KarmazynOs"
New-Item -ItemType Directory -Force -Path $cache | Out-Null

# Skrypty build.rs hosta: MSVC bez link.exe w PATH (zwykły PowerShell) → toolchain GNU.
if (-not $env:RUSTUP_TOOLCHAIN -and -not (Get-Command link.exe -ErrorAction SilentlyContinue)) {
    $gnu = "stable-x86_64-pc-windows-gnu"
    if ((rustup toolchain list) -match [regex]::Escape($gnu)) {
        Write-Host "Brak link.exe, host = $gnu"
        $env:RUSTUP_TOOLCHAIN = $gnu
    }
}
rustup target add $target
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$lld = Join-Path $env:USERPROFILE ".rustup\toolchains\stable-x86_64-pc-windows-msvc\lib\rustlib\x86_64-pc-windows-msvc\bin\rust-lld.exe"
if (-not (Test-Path $lld)) {
    Write-Host "Brak rust-lld: $lld"
    exit 2
}
$env:CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER = $lld

# mlua (vendored) kompiluje Lua z C. Potrzebny cc dla x86_64-linux-musl: zig cc.
$zig = $env:ZIG
if (-not $zig) {
    $zigVer = "0.17.0"
    $zigSha = "b5663f69581dcf391293fbf16c06cb80d81d806545ce618b4d0bab7f0eb8c428"
    $zigDir = Join-Path $cache "zig-x86_64-windows-$zigVer"
    $zig = Join-Path $zigDir "zig.exe"
    if (-not (Test-Path $zig)) {
        $zip = "$zigDir.zip"
        $u = "https://ziglang.org/download/$zigVer/zig-x86_64-windows-$zigVer.zip"
        Write-Host "GET $u"
        & curl.exe -fL --retry 2 -o $zip $u
        if ($LASTEXITCODE -ne 0) { Write-Host "Nie pobrano zig."; exit 2 }
        if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $zigSha) {
            Remove-Item $zip -Force
            Write-Host "Zła suma SHA-256 zig."
            exit 2
        }
        Expand-Archive $zip -DestinationPath $cache -Force
        Remove-Item $zip -Force
    }
}
if (-not (Test-Path $zig)) {
    Write-Host "Brak zig: $zig (ustaw ZIG)"
    exit 2
}
$wrap = Join-Path $cache "musl-cc"
New-Item -ItemType Directory -Force -Path $wrap | Out-Null
$cc = Join-Path $wrap "x86_64-linux-musl-cc.cmd"
$ar = Join-Path $wrap "x86_64-linux-musl-ar.cmd"
Set-Content -Encoding ascii $cc ("@`"$zig`" cc -target x86_64-linux-musl -O2 -fPIC " +
    "-ffunction-sections -fdata-sections -fno-sanitize=undefined %*")
Set-Content -Encoding ascii $ar "@`"$zig`" ar %*"
# cc-rs dopisuje --target=x86_64-unknown-linux-musl (triple Rusta), którego zig nie zna.
# Bez domyślnych flag; potrzebne (-O2, -fPIC, sekcje) są w wrapperze.
$env:CRATE_CC_NO_DEFAULTS = "1"
$env:CC_x86_64_unknown_linux_musl = $cc
$env:AR_x86_64_unknown_linux_musl = $ar

cargo build --release --target $target --manifest-path (Join-Path $shellDir "Cargo.toml")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path $elf)) {
    Write-Host "Brak ELF: $elf"
    exit 1
}

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
python (Join-Path $Repo "scripts\pack_initramfs.py") $elf $initrd --dir "lua_bin=$(Join-Path $Repo 'lua_bin')"
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
