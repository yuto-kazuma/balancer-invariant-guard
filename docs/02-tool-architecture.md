# InvariantBreaker — Tool Architecture

## Design Philosophy

InvariantBreaker is a pre-deployment security agent for DeFi protocols. It targets the class of bugs exemplified by the Balancer V2 exploit: **subtle arithmetic inconsistencies that become exploitable only under adversarial multi-step execution**.

The architecture deliberately separates:

| Component | Role | Nature |
|-----------|------|--------|
| **Context Builder** | Infer invariants, dependencies, threat model | AI-orchestrated |
| **Rounding Analyzer** | Check mulDown/divUp consistency | Deterministic |
| **Invariant Engine** | Evaluate economic properties | Deterministic |
| **Sequence Searcher** | Find adversarial swap paths | Bounded symbolic + fuzz |
| **PoC Synthesizer** | Emit Foundry/Rust tests | Deterministic templates + AI fill |

> AI orchestrates exploration. The deterministic core proves violations.

This mirrors Olympix's model: formal methods + symbolic execution + BugPoCer-style PoC generation.

---

## System Architecture

```
                    ┌──────────────────────────────────────┐
                    │           Developer Workflow          │
                    │  CLI / VS Code / GitHub Action / PR   │
                    └───────────────────┬──────────────────┘
                                        │
                    ┌───────────────────▼──────────────────┐
                    │         1. Context Builder (AI)       │
                    │  • Parse project (Solidity AST/IR)    │
                    │  • Infer protocol type (AMM, vault…)    │
                    │  • Extract documented invariants      │
                    │  • Build dependency graph             │
                    │  • Rank high-impact functions         │
                    └───────────────────┬──────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
┌─────────────────┐         ┌─────────────────────┐       ┌──────────────────┐
│ 2a. Rounding    │         │ 2b. Invariant       │       │ 2c. Sequence     │
│     Graph       │         │     Spec Engine     │       │     Searcher     │
│                 │         │                     │       │                  │
│ • Map mulDown/  │         │ • D monotonicity    │       │ • Batch swap     │
│   divUp/divDown │         │ • BPT rate bounds   │       │   permutations   │
│ • Pair upscale/ │         │ • Protocol-favoring │       │ • Boundary values│
│   downscale ops │         │   rounding          │       │ • Guided fuzz    │
│ • Flag asymmetry│         │ • Per-tx rate caps  │       │ • Symbolic exec  │
└────────┬────────┘         └──────────┬──────────┘       └────────┬─────────┘
         │                             │                             │
         └─────────────────────────────┼─────────────────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │      3. Violation Aggregator          │
                    │  Merge findings, dedupe, rank severity│
                    └───────────────────┬──────────────────┘
                                        ▼
                    ┌──────────────────────────────────────┐
                    │      4. PoC Synthesizer               │
                    │  • Foundry .t.sol / Hardhat tests     │
                    │  • Fork tests with realistic state    │
                    │  • Invariant regression tests         │
                    └───────────────────┬──────────────────┘
                                        ▼
                    ┌──────────────────────────────────────┐
                    │      5. CI Gate + PR Comments         │
                    │  Block merge if PoC passes            │
                    │  Attach exploit test to review        │
                    └──────────────────────────────────────┘
```

---

## Layer 1: Context Builder (AI)

**Input:** Solidity source, docs, existing tests, `foundry.toml`

**Output:** Structured context document (similar to BugPoCer's context approval step)

```yaml
protocol_type: AMM_StablePool
core_contracts:
  - ComposableStablePool
  - StableMath
  - BaseGeneralPool
invariants:
  - name: rounding_favors_protocol
    scope: all_swap_paths
  - name: invariant_D_monotonic
    scope: single_transaction
  - name: bpt_rate_stable
    threshold: 1% per tx
dependencies:
  - FixedPoint.mulDown
  - IRateProvider
high_risk_functions:
  - _swapGivenOut
  - _upscale
  - batchSwap
```

The AI layer reads NatSpec, README, and test files to infer what the protocol *intends* to guarantee. Human approval step optional for CI (auto-approve known patterns).

---

## Layer 2a: Rounding Graph Analyzer (Deterministic)

**Problem:** Balancer's bug was `_upscale` using `mulDown` on the GIVEN_OUT path while `_downscale` used bidirectional rounding.

**Algorithm:**

1. Build CFG for each swap function (`swap`, `batchSwap`, `_swapGivenOut`)
2. Extract all `FixedPoint.*` calls with direction (Up/Down)
3. Classify by operation type: upscale, downscale, fee, invariant calc
4. For each upscale/downscale pair on the same token path:
   - Check if rounding direction favors protocol
   - Flag asymmetry: upscale=Down + downscale=Down on output path

**Implementation in this repo:** `tool/rounding_scanner.py` (AST-light regex + heuristics)

**Production extension:** Parse via `solc --ast-compact-json` or Olympix IR for sound analysis.

---

## Layer 2b: Invariant Spec Engine (Deterministic)

Pre-defined invariant templates by protocol type:

### Stable Pool Invariants

```solidity
// Generated by InvariantBreaker — do not edit manually
invariant_bpt_rate_stable() public {
    uint256 rateBefore = pool.getRate();
    // ... execute bounded swap sequence ...
    uint256 rateAfter = pool.getRate();
    assertLe(rateAfter, rateBefore * 101 / 100); // max 1% increase
    assertGe(rateAfter, rateBefore * 99 / 100);  // max 1% decrease
}

invariant_D_non_decreasing() public {
    uint256 dBefore = pool.calculateInvariant();
    // ... single swap ...
    uint256 dAfter = pool.calculateInvariant();
    assertGe(dAfter, dBefore - epsilon);
}
```

For Balancer specifically, the **per-transaction BPT rate cap** would have caught the 20x manipulation.

Reference: [Phylax Balancer assertion](https://docs.phylax.systems/assertions-book/previous-hacks/balancer-v2-stable-rate-exploit)

---

## Layer 2c: Sequence Searcher (Hybrid)

**Problem:** Single-swap tests never hit the 65-step boundary sequence.

**Approach:**

1. **Seed values:** Token balances at 1, 2, …, 10 wei (rounding boundary targets)
2. **Guided fuzz:** Mutate batch swap arrays; fitness = |ΔD| + |ΔBPT_rate|
3. **Symbolic bounds:** Constrain swap amounts to ranges where `upscale(x) < x * rate`
4. **Early stop:** When fitness exceeds threshold, hand off to PoC synthesizer

Bounded exploration avoids path explosion — same strategy Olympix describes for signal-guided symbolic execution.

---

## Layer 3: PoC Synthesizer

When a violation is found, generate a self-contained Foundry test:

```solidity
function test_INVARIANT_BREAK_BPT_rate_manipulation() public {
    // Setup: fork or mock pool at realistic liquidity
    // Sequence: [swap steps from searcher]
    // Assert: rate change exceeds threshold (PROVES bug)
    // Profit: attacker balance increased
}
```

The PoC in `poc/test/Exploit.t.sol` is the template output for the Balancer case.

---

## CI Integration

```yaml
# .github/workflows/invariant-breaker.yml
name: InvariantBreaker
on: [pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run InvariantBreaker
        run: |
          python tool/rounding_scanner.py --recursive src/
          cd poc && forge test --match-contract Invariant
      - name: Block on violation
        run: exit 1  # if PoC test passes (= bug reproduced)
```

PR comments include:
- Finding severity
- Invariant violated
- Rounding graph snippet
- Attached `.t.sol` PoC

---

## Comparison to Olympix BugPoCer

| Capability | BugPoCer | InvariantBreaker (this design) |
|------------|----------|--------------------------------|
| AI context building | ✓ | ✓ (documented) |
| Symbolic execution | ✓ (proprietary IR) | Sequence search (bounded) |
| PoC generation | ✓ | ✓ (implemented) |
| Rounding-specific analysis | General detectors | **Specialized rounding graph** |
| Invariant templates | User-provided | **Auto-inferred by protocol type** |
| Pre-deploy CI | ✓ | ✓ |

InvariantBreaker is complementary: it deepens one vulnerability class (arithmetic/invariant) that general scanners under-weight.

---

## How It Prevents Balancer Specifically

| Stage | Action | Result |
|-------|--------|--------|
| **Dev** | Rounding scanner flags `_upscale` + `mulDown` on `_swapGivenOut` | Developer fixes before merge |
| **CI** | Invariant test: BPT rate stable per tx | 20x change fails build |
| **Audit prep** | PoC auto-generated for auditor review | Demonstrates exploit path |
| **Fork test** | Sequence searcher finds 8-wei boundary path | Confirms exploitability |

---

## Future Work

1. Full solc AST integration for sound rounding graphs
2. Integration with Olympix IR / BugPoCer as specialized invariant module
3. Mainnet fork PoC against archived Balancer pool state (Nov 2, 2025)
4. Extend to Sonne Finance, Hundred Finance (same rounding class, 2023–2024)
5. Rust/Anchor support for Solana AMM rounding issues
