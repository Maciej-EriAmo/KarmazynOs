# Build freestanding kentry (Rust only)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "boot\kentry")

rustup target add x86_64-unknown-none | Out-Null
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    # already installed → rustup may still exit 0; ignore soft noise
}
cargo build --release --target x86_64-unknown-none
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$elf = Join-Path $PWD "target\x86_64-unknown-none\release\karmazyn_kentry"
if (-not (Test-Path $elf)) { throw "ELF missing: $elf" }
$bytes = [IO.File]::ReadAllBytes($elf)
$text = [Text.Encoding]::ASCII.GetString($bytes)
if ($text -notmatch "KARMAZYN_KENTRY_OK") { throw "marker missing in ELF" }
Write-Host "OK kentry ELF=$elf size=$($bytes.Length) MARKER=yes"
