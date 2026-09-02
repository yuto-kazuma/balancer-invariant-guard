$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================"
Write-Host " InvariantBreaker - Full Demo"
Write-Host " Balancer V2 Take-Home Submission"
Write-Host "========================================"
Write-Host ""

Write-Host '[Step 1] Rounding direction analysis'
Write-Host ""
python "$Root\tool\rounding_scanner.py" "$Root\poc\src\VulnerableStablePool.sol"
Write-Host ""

Write-Host '[Step 2] Foundry PoC - exploit reproduction'
Write-Host ""
Set-Location "$Root\poc"

$ForgeCmd = Get-Command forge -ErrorAction SilentlyContinue
$Forge = if ($ForgeCmd) { $ForgeCmd.Source } else { $null }
if (-not $Forge) {
    $Fallback = Join-Path $env:TEMP "foundry\forge.exe"
    if (Test-Path $Fallback) { $Forge = $Fallback }
}
if (-not $Forge) {
    Write-Host "Foundry not installed. Install: https://book.getfoundry.sh/getting-started/installation"
    exit 1
}

if (-not (Test-Path "lib\forge-std")) {
    git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std 2>$null
}

& $Forge test --match-test test_rounding_exploit_drains_pool -vvv
Write-Host ""

Write-Host '[Step 3] BPT rate invariant (would block in CI)'
Write-Host ""
& $Forge test --match-test test_bpt_rate_invariant_would_catch_exploit -vvv
Write-Host ""

Write-Host '[Step 4] Fixed rounding path (mitigation)'
Write-Host ""
& $Forge test --match-test test_fixed_rounding_prevents_exploit -vvv
Write-Host ""

Write-Host "========================================"
Write-Host " Demo complete."
Write-Host " See docs\ for full analysis + architecture."
Write-Host "========================================"
