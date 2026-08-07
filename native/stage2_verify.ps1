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

    Write-Host "`n[7] assert / list / unbind / set_t (shell 0.3.1)"
    & $exe `
        -e "atom var a 80" `
        -e "bubble r" `
        -e "root 0" `
        -e "bind 0 name 0" `
        -e "assert has 0" `
        -e "assert lookup 0 name 0" `
        -e "assert t 0 ge 70" `
        -e "list" `
        -e "set_t 0 40" `
        -e "assert t 0 lt 50" `
        -e "unbind 0 name" `
        -e "assert nohas 99" `
        -e quit
    if ($LASTEXITCODE -ne 0) { throw "assert/list batch failed" }

    Write-Host "`n[8] assert failure must exit non-zero"
    & $exe -e "atom var z 10" -e "assert has 99" -e quit
    if ($LASTEXITCODE -eq 0) {
        throw "expected non-zero exit on failed assert"
    }
    Write-Host "  ok (exit $LASTEXITCODE)"

    Write-Host "`n[9] bubbles/binds/info/upsert/assert stats (shell 0.3.2)"
    & $exe `
        -e "atom var p 50" `
        -e "bubble root" `
        -e "root 0" `
        -e "bubble child 0" `
        -e "bind 1 x 0" `
        -e "assert root 0" `
        -e "assert noroot 1" `
        -e "assert lookup 1 x 0" `
        -e "binds 1" `
        -e "bubbles" `
        -e "roots" `
        -e "info 0" `
        -e "upsert 7 var fixed 30 5" `
        -e "assert has 7" `
        -e "assert val 7 5" `
        -e "assert stats total ge 2" `
        -e "assert stats bubbles eq 2" `
        -e quit
    if ($LASTEXITCODE -ne 0) { throw "bubbles/info batch failed" }
} finally { Pop-Location }

Write-Host "`n=== STAGE2_VERIFY_OK ===" -ForegroundColor Green
Write-Host "Shell: $exe (0.3.2+ bubbles/binds/assert stats)"
Write-Host "Snap:  $Snap"
exit 0
