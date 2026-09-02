# Email-Ready Submission Summary

Copy/adapt when replying to Mason.

---

**Subject:** Take-Home Submission — Balancer V2 Exploit Analysis & InvariantBreaker PoC

Hi Mason,

Please find my take-home submission below.

**GitHub:** https://github.com/yuto-kazuma/balancer-invariant-guard  
*(Push this repo to that name, then update the link if needed)*

---

## Exploit Choice: Balancer V2 Composable Stable Pool (Nov 3, 2025, ~$128M)

I chose this exploit because it represents the exact class of vulnerability pre-deployment tooling must solve: a **rounding-direction asymmetry** in the exact-out swap path that survived **10+ audits** because it only manifests under **adversarial multi-step batch execution** (65+ micro-swaps at 8–9 wei boundaries).

Unlike key-compromise or bridge infra attacks, this is pure smart-contract math — deterministic, reproducible, and preventable with invariant checks + executable PoCs.

## Why It's Interesting

The root cause is subtle: `_upscale` uses `mulDown` on the GIVEN_OUT path, underestimating `amountIn`. Combined with non-unitary rate providers (wstETH/cbETH) and low-liquidity manipulation via exitSwap, precision loss compounds until invariant `D` collapses and BPT is underpriced — enabling a $128M drain in under 30 minutes.

## Tool: InvariantBreaker

I architected **InvariantBreaker**, an agent-style security tool with:

1. **AI context layer** — infers economic invariants from protocol code
2. **Deterministic rounding analyzer** — flags asymmetric mulDown/divUp on upscale/downscale pairs
3. **Invariant engine** — enforces per-transaction BPT rate stability (max 1% change)
4. **PoC synthesizer** — emits Foundry tests that prove the violation

> AI orchestrates. The deterministic core proves.

## Proof-of-Concept

The repo includes:

- `poc/` — Minimal vulnerable pool + Foundry exploit reproducing D collapse and attacker profit
- `tool/rounding_scanner.py` — Working analyzer that flags the exact Balancer pattern
- `demo.sh` — One command runs scan + PoC

```bash
./demo.sh
# Scanner: CRITICAL — asymmetric upscale rounding
# PoC: test_rounding_exploit_drains_pool PASS (proves invariant break)
```

## How It Would Have Prevented Balancer

| Gate | Detection |
|------|-----------|
| PR scan | Rounding scanner flags `_upscale` + `mulDown` on `_swapGivenOut` |
| CI invariant | `bptRateAfter / bptRateBefore < 1.01` fails on 20x manipulation |
| PoC generation | Auto-emitted Foundry test demonstrates exploit before merge |

Happy to walk through the architecture and PoC on a call.

Best,  
Yuto
