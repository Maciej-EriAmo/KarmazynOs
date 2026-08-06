# Install Tor A runtime into a prefix (shell + C header + substrate cdylib).
# No Python required.
#
#   .\native\install_prefix.ps1
#   .\native\install_prefix.ps1 -Prefix C:\karmazyn-prefix
#   .\native\install_prefix.ps1 -SkipBuild

param(
    [string]$Prefix = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Native = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Native
if (-not $Prefix) {
    $Prefix = Join-Path $Root "dist\prefix"
}

$Sub = Join-Path $Native "karmazyn_substrate"
$Shell = Join-Path $Native "karmazyn_shell"
$Bin = Join-Path $Prefix "bin"
$Lib = Join-Path $Prefix "lib"
$Inc = Join-Path $Prefix "include"
$Share = Join-Path $Prefix "share\karmazyn"

Write-Host "=== KarmazynOS install_prefix (Tor A) ===" -ForegroundColor Cyan
Write-Host "prefix: $Prefix"

if (-not $SkipBuild) {
    Write-Host "`n[build] substrate --release"
    Push-Location $Sub
    try {
        cargo build --release
        if ($LASTEXITCODE -ne 0) { throw "substrate build failed" }
    } finally { Pop-Location }

    Write-Host "[build] shell --release"
    Push-Location $Shell
    try {
        cargo build --release
        if ($LASTEXITCODE -ne 0) { throw "shell build failed" }
    } finally { Pop-Location }
}

New-Item -ItemType Directory -Force -Path $Bin, $Lib, $Inc, $Share | Out-Null

function Copy-One {
    param([string]$From, [string]$ToDir, [string]$Name = "")
    if (-not (Test-Path $From)) { throw "missing: $From" }
    $destName = if ($Name) { $Name } else { Split-Path -Leaf $From }
    $dest = Join-Path $ToDir $destName
    Copy-Item -Force $From $dest
    Write-Host "  + $dest"
}

$shellExe = Join-Path $Shell "target\release\karmazyn_shell.exe"
if (-not (Test-Path $shellExe)) {
    $shellExe = Join-Path $Shell "target\release\karmazyn_shell"
}
Copy-One $shellExe $Bin

$hdr = Join-Path $Sub "include\karmazyn_substrate.h"
Copy-One $hdr $Inc

# Windows: dll + import lib; Unix-ish: .so / .a if present
$rel = Join-Path $Sub "target\release"
$copiedLib = $false
foreach ($n in @(
        "karmazyn_substrate.dll",
        "karmazyn_substrate.dll.lib",
        "libkarmazyn_substrate.rlib",
        "libkarmazyn_substrate.so",
        "libkarmazyn_substrate.a",
        "libkarmazyn_substrate.dylib"
    )) {
    $p = Join-Path $rel $n
    if (Test-Path $p) {
        Copy-One $p $Lib
        $copiedLib = $true
    }
}
if (-not $copiedLib) {
    Write-Host "  (warn) no cdylib/rlib found under $rel" -ForegroundColor Yellow
}

$smoke = Join-Path $Shell "examples\smoke.ksh"
if (Test-Path $smoke) {
    Copy-One $smoke $Share
}

$readme = Join-Path $Prefix "README.txt"
@"
KarmazynOS Tor A prefix
=======================
bin/karmazyn_shell     — Stage 2 native shell (no Python)
include/               — C ABI header
lib/                   — substrate cdylib / rlib (host rustc build)
share/karmazyn/        — example .ksh scripts

Run:
  $Bin\karmazyn_shell.exe
  $Bin\karmazyn_shell.exe --version

Docs: Documents/BOOTSTRAP_STAGES.pl.md
"@ | Set-Content -Encoding utf8 $readme
Write-Host "  + $readme"

Write-Host "`n=== INSTALL_PREFIX_OK ===" -ForegroundColor Green
Write-Host "Prefix: $Prefix"
exit 0
