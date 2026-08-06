# Stage 2 gate — native shell + KSUB_SNAP (no Python).
# Usage:
#   .\native\stage2_verify.ps1
#   .\native\stage2_verify.ps1 -SkipBuild

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Native = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Native
$Shell = Join-Path $Native "karmazyn_shell"
$Out = Join-Path $Root "out"
$Snap = Join-Path $Out "stage2_verify.ksub"
$Snap2 = Join-Path $Out "stage2_verify_roundtrip.ksub"

Write-Host "=== KarmazynOS Stage 2 verify (shell, no Python) ===" -ForegroundColor Cyan
Write-Host "shell: $Shell"

New-Item -ItemType Directory -Force -Path $Out | Out-Null

Push-Location $Shell
try {
    if (-not $SkipBuild) {
        Write-Host "`n[1] cargo build --release"
        cargo build --release
        if ($LASTEXITCODE -ne 0) { throw "karmazyn_shell build failed" }
    } else {
        Write-Host "`n[1] skip build (-SkipBuild)"
    }

    $exe = Join-Path $Shell "target\release\karmazyn_shell.exe"
    if (-not (Test-Path $exe)) {
        $exe = Join-Path $Shell "target\release\karmazyn_shell"
    }
    if (-not (Test-Path $exe)) { throw "shell binary missing: $exe" }

    Write-Host "`n[2] --version"
    & $exe --version
    if ($LASTEXITCODE -ne 0) { throw "version failed" }

    Write-Host "`n[3] batch -e save/load roundtrip"
    if (Test-Path $Snap) { Remove-Item $Snap -Force }
    & $exe `
        -e "atom var x 50" `
        -e "bubble r" `
        -e "root 0" `
        -e "bind 0 v 0" `
        -e "save $Snap" `
        -e quit
    if ($LASTEXITCODE -ne 0) { throw "save batch failed" }
    if (-not (Test-Path $Snap)) { throw "snapshot missing: $Snap" }
    $sz = (Get-Item $Snap).Length
    if ($sz -lt 16) { throw "snapshot too small: $sz bytes" }

    & $exe -e "load $Snap" -e stats -e "lookup 0 v" -e "has 0" -e quit
    if ($LASTEXITCODE -ne 0) { throw "load batch failed" }

    Write-Host "`n[4] script file smoke.ksh (cwd=repo root)"
    Push-Location $Root
    try {
        if (Test-Path (Join-Path $Out "shell_smoke.ksub")) {
            Remove-Item (Join-Path $Out "shell_smoke.ksub") -Force
        }
        $ksh = Join-Path $Shell "examples\smoke.ksh"
        & $exe $ksh
        if ($LASTEXITCODE -ne 0) { throw "smoke.ksh failed" }
        if (-not (Test-Path (Join-Path $Out "shell_smoke.ksub"))) {
            throw "smoke.ksh did not write out/shell_smoke.ksub"
        }
    } finally { Pop-Location }

    Write-Host "`n[5] batch fails on bad command (exit != 0)"
    & $exe -e "not_a_command_xyz" -e quit
    if ($LASTEXITCODE -eq 0) {
        throw "expected non-zero exit on unknown command"
    }
    Write-Host "  ok (exit $LASTEXITCODE)"

    Write-Host "`n[6] double save (stable path)"
    if (Test-Path $Snap2) { Remove-Item $Snap2 -Force }
    & $exe -e "load $Snap" -e "save $Snap2" -e quit
    if ($LASTEXITCODE -ne 0) { throw "double save failed" }
    if (-not (Test-Path $Snap2)) { throw "roundtrip snap missing" }
} finally { Pop-Location }

Write-Host "`n=== STAGE2_VERIFY_OK ===" -ForegroundColor Green
Write-Host "Shell: $exe"
Write-Host "Snap:  $Snap"
exit 0
