#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "========================================"
echo " InvariantBreaker - Full Demo"
echo " Balancer V2 Take-Home Submission"
echo "========================================"
echo ""

echo "[Step 1] Rounding direction analysis"
echo ""
python3 "$ROOT/tool/rounding_scanner.py" "$ROOT/poc/src/VulnerableStablePool.sol" || true
echo ""

echo "[Step 2] Bounded symbolic search"
echo ""
python3 "$ROOT/tool/symbolic_search.py" || true
echo ""

echo "[Step 3] Foundry PoC - exploit reproduction"
echo ""
cd "$ROOT/poc"
if ! command -v forge &>/dev/null; then
  echo "Foundry not installed. Install: https://book.getfoundry.sh/getting-started/installation"
  exit 1
fi

if [ ! -d "lib/forge-std" ]; then
  forge install foundry-rs/forge-std --no-commit 2>/dev/null || true
fi

forge test --match-test test_rounding_exploit_drains_pool -vvv
echo ""

echo "[Step 4] BPT rate invariant (would block in CI)"
echo ""
forge test --match-test test_bpt_rate_invariant_would_catch_exploit -vvv || true
echo ""

echo "[Step 5] Fixed rounding path (mitigation)"
echo ""
forge test --match-test test_fixed_rounding_prevents_exploit -vvv
echo ""

echo "========================================"
echo " Demo complete."
echo "========================================"
