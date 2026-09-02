# InvariantBreaker - Olympix Take-Home Submission

**Author:** [Yuto Kazuma](https://github.com/yuto-kazuma)  
**Exploit analyzed:** Balancer V2 Composable Stable Pool, November 3, 2025 (~$128M)  
**Submission date:** September 2026

---

## Executive Summary

On November 3, 2025, attackers drained **$128M+** from Balancer V2 Composable Stable Pools across nine chains. The root cause was not a missing access check or reentrancy bug. It was a **rounding-direction asymmetry** in the exact-out swap path that, when combined with rate providers and adversarial batch swaps, systematically deflated the pool invariant `D` and underpriced BPT.

This bug survived **10+ audits** because it only manifests under **multi-step adversarial execution**. That is exactly the class of vulnerability that pre-deployment tooling with **formal invariants and executable PoCs** must catch.

**InvariantBreaker** is the tool I architect to prevent this class of exploit. It combines:

1. **AI context layer**: infers economic invariants and threat model from Solidity
2. **Deterministic analyzer**: checks rounding-direction consistency and searches for invariant violations
3. **PoC synthesizer**: emits Foundry tests that prove the break, not just flag a pattern

AI orchestrates. The deterministic core proves.

This mirrors Olympix's thesis: act on demonstrated exploits, not a backlog of maybes.

---

## Quick Start

```bash
# Run the full demo (tool scan + PoC exploit)
./demo.sh          # Linux/macOS
.\demo.ps1         # Windows

# Or step by step:
cd tool && python rounding_scanner.py ../poc/src/VulnerableStablePool.sol
cd ../poc && forge test -vvv
```

---

## Repository Structure

- `README.md` - This file
- `docs/01-exploit-analysis.md` - Why Balancer, root cause, attack flow
- `docs/02-tool-architecture.md` - InvariantBreaker design
- `poc/src/` - Minimal vulnerable pool (Balancer bug repro)
- `poc/test/` - Foundry exploit and invariant tests
- `tool/rounding_scanner.py` - Rounding consistency checker
- `tool/templates/invariant.t.sol.template` - Generated invariant test template
- `demo.sh` / `demo.ps1` - One-command demo
- `SUBMISSION.md` - Email-ready summary for Mason

---

## Why Balancer V2?

| Criterion | Balancer |
|-----------|----------|
| Within 18 months | Nov 2025 |
| Smart-contract logic | Pure math/rounding bug |
| Missed by audits | 10+ audits since 2021 |
| PoC feasible | Foundry reproducible |
| Olympix alignment | Invariant breaking + proven PoC |

See [docs/01-exploit-analysis.md](docs/01-exploit-analysis.md) for the full analysis.

---

## How InvariantBreaker Would Have Prevented It

### Detection layers

| Layer | What it catches | Balancer-specific |
|-------|-----------------|-------------------|
| **Rounding graph** | Asymmetric mulDown/divUp on paired upscale/downscale | `_upscale` rounds down on GIVEN_OUT path |
| **Invariant specs** | Economic properties that must hold per-tx | BPT price must not drop >1% in one `batchSwap` |
| **Sequence search** | Adversarial multi-step paths | 65+ micro-swaps compounding precision loss |
| **PoC generation** | Runnable Foundry proof | `test_balancer_rounding_exploit` in this repo |

### Pre-deployment integration

1. PR opened, InvariantBreaker CI runs
2. Scan changed `.sol` files for rounding asymmetry
3. Run invariant tests on fork
4. If PoC passes (invariant broken), block merge and attach exploit test

---

## PoC Results

The minimal vulnerable pool in `poc/` reproduces the core mechanism:

1. Attacker forces pool into low-liquidity state via exit swap
2. Executes batch swaps at rounding boundaries (~8 wei)
3. Pool invariant `D` drops; BPT becomes underpriced
4. Attacker extracts value at manipulated rate

Run: `cd poc && forge test --match-test test_rounding_exploit_drains_pool -vvv`

---

## Tool Demo

The rounding scanner analyzes Solidity for the exact pattern that caused Balancer:

```bash
python tool/rounding_scanner.py poc/src/VulnerableStablePool.sol
```

Expected output: flags `_upscale` using `mulDown` without protocol-favoring rounding on the GIVEN_OUT path.

---

## Limitations and Future Work

- Minimal pool simplifies StableMath; full mainnet fork PoC possible with archive node
- Sequence search is bounded fuzzing; production would use symbolic execution (Olympix IR engine)
- AI context layer is documented but not fully implemented; deterministic core is the PoC focus

---

## References

- [Balancer post-mortem](https://medium.com/balancer-protocol/nov-3-exploit-post-mortem-51dcbeb6b020)
- [OpenZeppelin analysis](https://www.openzeppelin.com/news/understanding-the-balancer-v2-exploit)
- [Trail of Bits guidance](https://blog.trailofbits.com/2025/11/07/balancer-hack-analysis-and-guidance-for-the-defi-ecosystem/)
- [Check Point Research](https://research.checkpoint.com/2025/how-an-attacker-drained-128m-from-balancer-through-rounding-error-exploitation/)
- [Phylax invariant assertion](https://docs.phylax.systems/assertions-book/previous-hacks/balancer-v2-stable-rate-exploit)
- [Olympix BugPoCer docs](https://olympix.github.io/cli/bugpocer/)

---

## Contact

- GitHub: https://github.com/yuto-kazuma
- Portfolio: https://yuto-kazuma.vercel.app
