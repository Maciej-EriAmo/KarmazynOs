# Stage 1 gate — pure Rust (+ optional C ABI). No Python required.
# Usage (from repo root or native/):
#   .\native\stage1_verify.ps1
#   .\native\stage1_verify.ps1 -SkipC

param(
    [switch]$SkipC
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sub = Join-Path $Root "karmazyn_substrate"
$Slab = Join-Path $Root "karmazyn_slab"

Write-Host "=== KarmazynOS Stage 1 verify (no Python) ===" -ForegroundColor Cyan
Write-Host "substrate: $Sub"

Push-Location $Slab
try {
    Write-Host "`n[1/4] karmazyn_slab cargo test --release"
    cargo test --release
} finally { Pop-Location }

Push-Location $Sub
try {
    Write-Host "`n[2/4] karmazyn_substrate cargo test --release"
    cargo test --release

    Write-Host "`n[3/4] stage1_bootstrap example"
    cargo run --example stage1_bootstrap --release
    if ($LASTEXITCODE -ne 0) { throw "stage1_bootstrap failed" }

    Write-Host "`n[build] release cdylib for C smoke"
    cargo build --release
} finally { Pop-Location }

if (-not $SkipC) {
    $gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $gcc) {
        Write-Host "`n[4/4] C smoke SKIPPED (gcc not in PATH)" -ForegroundColor Yellow
    } else {
        Write-Host "`n[4/4] C ABI smoke (gcc)"
        $inc = Join-Path $Sub "include"
        $lib = Join-Path $Sub "target\release"
        $src = Join-Path $Root "c_smoke\stage1_c_smoke.c"
        $exe = Join-Path $lib "stage1_c_smoke.exe"
        & gcc $src "-I$inc" "-L$lib" -lkarmazyn_substrate -o $exe
        if ($LASTEXITCODE -ne 0) { throw "gcc link failed" }
        $env:PATH = "$lib;$env:PATH"
        & $exe
        if ($LASTEXITCODE -ne 0) { throw "stage1_c_smoke failed" }
    }
} else {
    Write-Host "`n[4/4] C smoke skipped (-SkipC)" -ForegroundColor Yellow
}

Write-Host "`n=== STAGE1_VERIFY_OK ===" -ForegroundColor Green
exit 0
