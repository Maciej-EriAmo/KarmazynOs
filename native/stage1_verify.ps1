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
        Write-Host "`n[4/4] C clients SKIPPED (gcc not in PATH)" -ForegroundColor Yellow
    } else {
        Write-Host "`n[4/4] C ABI clients (gcc)"
        $inc = Join-Path $Sub "include"
        $lib = Join-Path $Sub "target\release"
        $dll = Join-Path $lib "karmazyn_substrate.dll"
        if (-not (Test-Path $dll)) { throw "missing $dll" }
        $env:PATH = "$lib;$env:PATH"
        # Link the DLL directly — avoids stale MinGW import lib (lib*.dll.a)
        # that can lag behind cargo-exported symbols (e.g. ksub_atom_set_t).

        $src1 = Join-Path $Root "c_smoke\stage1_c_smoke.c"
        $exe1 = Join-Path $lib "stage1_c_smoke.exe"
        & gcc $src1 "-I$inc" $dll -o $exe1
        if ($LASTEXITCODE -ne 0) { throw "gcc link stage1_c_smoke failed" }
        & $exe1
        if ($LASTEXITCODE -ne 0) { throw "stage1_c_smoke failed" }

        $src2 = Join-Path $Root "c_smoke\ksub_client.c"
        $exe2 = Join-Path $lib "ksub_client.exe"
        Write-Host "  ksub_client (Tor A thin C)"
        & gcc $src2 "-I$inc" $dll -o $exe2
        if ($LASTEXITCODE -ne 0) { throw "gcc link ksub_client failed" }
        & $exe2
        if ($LASTEXITCODE -ne 0) { throw "ksub_client failed" }
    }
} else {
    Write-Host "`n[4/4] C clients skipped (-SkipC)" -ForegroundColor Yellow
}

Write-Host "`n=== STAGE1_VERIFY_OK ===" -ForegroundColor Green
exit 0
