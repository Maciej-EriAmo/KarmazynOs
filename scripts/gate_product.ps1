# gate_product.ps1 — Enterprise G0 gate (exit 0 = pass)
# Usage:  .\scripts\gate_product.ps1
#         .\scripts\gate_product.ps1 -SkipLua -SkipStudio
param(
    [switch]$SkipLua,
    [switch]$SkipStudio,
    [switch]$SkipCargo,
    [string]$Substrate = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:PYTHONPATH = @(
    $Root,
    (Join-Path $Root "archiwum\kernel_python"),
    (Join-Path $Root "software"),
    (Join-Path $Root "native")
) -join [IO.Path]::PathSeparator
$env:KARMAZYN_SUBSTRATE = $Substrate
$env:KARMAZYN_LUA = Join-Path $Root "LUA"

function Step($name, $scriptBlock) {
    Write-Host ""
    Write-Host "== $name ==" -ForegroundColor Cyan
    & $scriptBlock
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        Write-Host "FAIL: $name (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "OK: $name" -ForegroundColor Green
}

Write-Host "KarmazynOs gate_product  root=$Root  substrate=$Substrate"

if (-not $SkipCargo) {
    Step "cargo test slab" {
        cargo test --manifest-path (Join-Path $Root "native\karmazyn_slab\Cargo.toml") -q
    }
    Step "cargo test substrate" {
        cargo test --manifest-path (Join-Path $Root "native\karmazyn_substrate\Cargo.toml") -q
    }
    Step "cargo test lisp" {
        cargo test --manifest-path (Join-Path $Root "native\karmazyn_lisp\Cargo.toml") -q
    }
    Step "cargo test shell" {
        cargo test --manifest-path (Join-Path $Root "native\karmazyn_shell\Cargo.toml") -q
    }
    Step "cargo test kcc (Rust tool)" {
        cargo test --manifest-path (Join-Path $Root "toolchain\kcc\Cargo.toml") -q
    }
}

Step "kernel_boundary" {
    python (Join-Path $Root "kernel_boundary.py") `
        (Join-Path $Root "archiwum\kernel_python") `
        (Join-Path $Root "software")
}

Step "unittest io_thermal + host_tools + bootcfg + kentry" {
    python -m unittest software.test_io_thermal software.test_host_tools software.test_bootcfg software.test_kentry_marker -q
}

if (-not $SkipStudio) {
    Step "unittest studio_sdl" {
        python -m unittest software.test_studio_sdl -q
    }
}

if (-not $SkipLua) {
    $luaGate = Join-Path $Root "software\test_lua_release.py"
    if (Test-Path $luaGate) {
        Step "lua release gate" {
            python $luaGate
        }
    } else {
        Write-Host "SKIP: lua release (missing $luaGate)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  GATE PRODUCT PASS" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
exit 0
