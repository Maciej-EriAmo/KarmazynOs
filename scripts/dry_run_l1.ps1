# dry_run_l1.ps1 — wrapper → scripts/dry_run_l1.py
param([switch]$SkipGate)
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$argsList = @()
if ($SkipGate) { $argsList += "--skip-gate" }
& python (Join-Path $Root "scripts\dry_run_l1.py") @argsList
exit $LASTEXITCODE
