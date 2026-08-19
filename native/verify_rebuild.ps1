# Tor B — wzorzec LFS/Gentoo, język = Rust, slot kompilatora = rustc.
# Przebudowa ważnych crate’ów w kolejności. Bez Pythona. Bez gcc.
#
#   .\native\verify_rebuild.ps1
# → REBUILD_OK
#
# To NIE jest kcc→C. kcc tutaj = narzędzie w Rust (cargo test), nie „nasz gcc”.

$ErrorActionPreference = "Stop"
$Native = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Native
$Slab = Join-Path $Native "karmazyn_slab"
$Sub = Join-Path $Native "karmazyn_substrate"
$Lisp = Join-Path $Native "karmazyn_lisp"
$Shell = Join-Path $Native "karmazyn_shell"
$Kcc = Join-Path $Root "toolchain\kcc"

Write-Host "=== KarmazynOS rebuild (LFS pattern, rustc) ===" -ForegroundColor Cyan
Write-Host "host compiler: rustc (gcc slot). language: Rust (not C)."

$rustc = Get-Command rustc -ErrorAction SilentlyContinue
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $rustc -or -not $cargo) {
    throw "Need rustc + cargo on PATH. This gate does not use gcc or Python."
}
Write-Host "rustc: $(& rustc --version)"
Write-Host "cargo: $(& cargo --version)"

function Invoke-CrateTest {
    param([string]$Dir, [string]$Label)
    if (-not (Test-Path (Join-Path $Dir "Cargo.toml"))) {
        throw "missing crate: $Dir"
    }
    Write-Host ""
    Write-Host "[$Label] cargo test --release  ($Dir)" -ForegroundColor Cyan
    Push-Location $Dir
    try {
        $ok = $false
        foreach ($attempt in 1..3) {
            cargo test --release
            if ($LASTEXITCODE -eq 0) { $ok = $true; break }
            Write-Host "  retry $attempt (Windows link lock?)" -ForegroundColor Yellow
            Start-Sleep -Seconds 2
        }
        if (-not $ok) { throw "$Label cargo test failed" }
    } finally {
        Pop-Location
    }
}

# 1. prawo (jak libc / headers w LFS)
Invoke-CrateTest $Slab "1/5 slab"

# 2. jądro host (zależne od slab)
Invoke-CrateTest $Sub "2/5 substrate"
Write-Host ""
Write-Host "[2b] stage1_bootstrap example" -ForegroundColor Cyan
Push-Location $Sub
try {
    cargo run --example stage1_bootstrap --release
    if ($LASTEXITCODE -ne 0) { throw "stage1_bootstrap failed" }
} finally {
    Pop-Location
}

# 3. gość Lisp na szwach Store
Invoke-CrateTest $Lisp "3/5 lisp"

# 4. narzędzie userspace na substracie (jak coreutils/shell)
Write-Host ""
Write-Host "[4/5] karmazyn_shell cargo build --release" -ForegroundColor Cyan
Push-Location $Shell
try {
    cargo build --release
    if ($LASTEXITCODE -ne 0) { throw "karmazyn_shell build failed" }
} finally {
    Pop-Location
}
$shellExe = Join-Path $Shell "target\release\karmazyn_shell.exe"
if (-not (Test-Path $shellExe)) {
    $shellExe = Join-Path $Shell "target\release\karmazyn_shell"
}
if (-not (Test-Path $shellExe)) { throw "shell binary missing" }
& $shellExe --version
if ($LASTEXITCODE -ne 0) { throw "shell --version failed" }

# 4. kcc jako crate Rust (narzędzie, nie slot gcc)
Invoke-CrateTest $Kcc "5/5 kcc (rustc-built tool)"

Write-Host ""
Write-Host "=== REBUILD_OK ===" -ForegroundColor Green
Write-Host "Order: slab → substrate → shell → kcc. rustc only. No gcc, no Python."
Write-Host "kcc here is a Rust package, not a C backend."
exit 0
