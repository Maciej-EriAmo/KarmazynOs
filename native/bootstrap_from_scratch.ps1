# KarmazynOS Stage 3 starter — build homogeneous core from rustc+Cargo only.
# No Python required.
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

# ── Stage 1 gate ───────────────────────────────────────────────────────────
$verify = Join-Path $Native "stage1_verify.ps1"
if ($SkipC) {
    & $verify -SkipC
} else {
    & $verify
}
if ($LASTEXITCODE -ne 0) { throw "stage1_verify failed" }

# ── Stage 2 shell build ────────────────────────────────────────────────────
Write-Host "`n[shell] cargo build --release" -ForegroundColor Cyan
Push-Location $Shell
try {
    cargo build --release
    if ($LASTEXITCODE -ne 0) { throw "karmazyn_shell build failed" }
} finally { Pop-Location }

$shellExe = Join-Path $Shell "target\release\karmazyn_shell.exe"
if (-not (Test-Path $shellExe)) {
    $shellExe = Join-Path $Shell "target\release\karmazyn_shell"
}
if (-not (Test-Path $shellExe)) { throw "shell binary missing" }

if (-not $SkipShellSmoke) {
    Write-Host "`n[shell smoke] save/load snapshot" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Out | Out-Null
    if (Test-Path $Snap) { Remove-Item $Snap -Force }

    & $shellExe `
        -e "atom var hello 50" `
        -e "bubble root" `
        -e "root 0" `
        -e "bind 0 hi 0" `
        -e "save $Snap" `
        -e quit
    if ($LASTEXITCODE -ne 0) { throw "shell save smoke failed" }
    if (-not (Test-Path $Snap)) { throw "snapshot not written: $Snap" }

    & $shellExe -e "load $Snap" -e stats -e "lookup 0 hi" -e quit
    if ($LASTEXITCODE -ne 0) { throw "shell load smoke failed" }
    Write-Host "  snapshot: $Snap"
}

Write-Host "`n=== BOOTSTRAP_FROM_SCRATCH_OK ===" -ForegroundColor Green
Write-Host "Kernel:  $Sub\target\release\ (karmazyn_substrate)"
Write-Host "Shell:   $shellExe"
Write-Host "Next:    run shell interactively:  $shellExe"
Write-Host "Docs:    Documents\BOOTSTRAP_STAGES.pl.md"
exit 0
