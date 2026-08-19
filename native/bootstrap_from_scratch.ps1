# KarmazynOS Stage 3 starter — LFS pattern (rustc) then product smoke.
# No Python required. C ABI smoke is optional FFI, not the world.
#
#   .\native\bootstrap_from_scratch.ps1
#   .\native\bootstrap_from_scratch.ps1 -SkipC -SkipShellSmoke

param(
    [switch]$SkipC,
    [switch]$SkipShellSmoke
)

$ErrorActionPreference = "Stop"
$Native = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Native
$Sub = Join-Path $Native "karmazyn_substrate"
$Shell = Join-Path $Native "karmazyn_shell"
$Out = Join-Path $Root "out"
$Snap = Join-Path $Out "bootstrap_demo.ksub"

Write-Host "=== KarmazynOS bootstrap from scratch (Stage 3 starter) ===" -ForegroundColor Cyan
Write-Host "root: $Root"

# ── tool check ─────────────────────────────────────────────────────────────
$rustc = Get-Command rustc -ErrorAction SilentlyContinue
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $rustc -or -not $cargo) {
    throw "Need rustc + cargo on PATH (https://rustup.rs/). Python is NOT required."
}
Write-Host "rustc: $(& rustc --version)"
Write-Host "cargo: $(& cargo --version)"

# ── Tor B pattern: rustc rebuilds the package set ─────────────────────────
$rebuild = Join-Path $Native "verify_rebuild.ps1"
Write-Host "`n[pattern] verify_rebuild.ps1 (slab → substrate → shell → kcc)" -ForegroundColor Cyan
& $rebuild
if ($LASTEXITCODE -ne 0) { throw "verify_rebuild failed" }

# ── Optional FFI (not LFS world) ──────────────────────────────────────────
if (-not $SkipC) {
    $gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $gcc) {
        Write-Host "`n[ffi] C ABI SKIPPED (gcc not in PATH)" -ForegroundColor Yellow
    } else {
        Write-Host "`n[ffi] C ABI clients (optional, not pattern)" -ForegroundColor Cyan
        Push-Location $Sub
        try {
            cargo build --release
            if ($LASTEXITCODE -ne 0) { throw "substrate cdylib build failed" }
        } finally { Pop-Location }
        $inc = Join-Path $Sub "include"
        $lib = Join-Path $Sub "target\release"
        $dll = Join-Path $lib "karmazyn_substrate.dll"
        if (-not (Test-Path $dll)) { $dll = Join-Path $lib "karmazyn_substrate.so" }
        if (-not (Test-Path $dll)) { throw "missing substrate cdylib" }
        $env:PATH = "$lib;$env:PATH"
        $src1 = Join-Path $Native "c_smoke\stage1_c_smoke.c"
        $exe1 = Join-Path $lib "stage1_c_smoke.exe"
        & gcc $src1 "-I$inc" $dll -o $exe1
        if ($LASTEXITCODE -ne 0) { throw "gcc link stage1_c_smoke failed" }
        & $exe1
        if ($LASTEXITCODE -ne 0) { throw "stage1_c_smoke failed" }
    }
} else {
    Write-Host "`n[ffi] C ABI skipped (-SkipC)" -ForegroundColor Yellow
}

# ── Stage 2 gate (shell + KSUB_SNAP) ───────────────────────────────────────
$stage2 = Join-Path $Native "stage2_verify.ps1"
if ($SkipShellSmoke) {
    Write-Host "`n[shell] cargo build --release only (-SkipShellSmoke)" -ForegroundColor Cyan
    Push-Location $Shell
    try {
        cargo build --release
        if ($LASTEXITCODE -ne 0) { throw "karmazyn_shell build failed" }
    } finally { Pop-Location }
} else {
    Write-Host "`n[stage2] stage2_verify.ps1 -SkipBuild" -ForegroundColor Cyan
    & $stage2 -SkipBuild
    if ($LASTEXITCODE -ne 0) { throw "stage2_verify failed" }
}

$shellExe = Join-Path $Shell "target\release\karmazyn_shell.exe"
if (-not (Test-Path $shellExe)) {
    $shellExe = Join-Path $Shell "target\release\karmazyn_shell"
}
if (-not (Test-Path $shellExe)) { throw "shell binary missing" }

# keep classic bootstrap_demo.ksub for docs / demos
if (-not $SkipShellSmoke) {
    Write-Host "`n[demo snap] bootstrap_demo.ksub" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Out | Out-Null
    if (Test-Path $Snap) { Remove-Item $Snap -Force }
    & $shellExe `
        -e "atom var hello 50" `
        -e "bubble root" `
        -e "root 0" `
        -e "bind 0 hi 0" `
        -e "save $Snap" `
        -e quit
    if ($LASTEXITCODE -ne 0) { throw "demo snap failed" }
    Write-Host "  snapshot: $Snap"
}

Write-Host "`n=== BOOTSTRAP_FROM_SCRATCH_OK ===" -ForegroundColor Green
Write-Host "Kernel:  $Sub\target\release\ (karmazyn_substrate)"
Write-Host "Shell:   $shellExe"
Write-Host "Gates:   verify_rebuild + stage2_verify"
Write-Host "Install: .\native\install_prefix.ps1"
Write-Host "Next:    run shell interactively:  $shellExe"
Write-Host "Docs:    Documents\BOOTSTRAP_STAGES.pl.md"
exit 0
