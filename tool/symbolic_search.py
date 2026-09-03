#!/usr/bin/env python3
"""
Bounded symbolic search for Balancer-style rounding undercharge.

Not a full IR / path-explosion symbolic engine.
Models FixedPoint ops over a finite domain, finds inputs that break
"rounding favors the protocol", then emits a Foundry-ready counterexample.

Usage:
    python symbolic_search.py
    python symbolic_search.py --max-amount 200 --steps 20 --emit-forge
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


ONE = 10**18


def mul_down(a: int, b: int) -> int:
    return (a * b) // ONE


def mul_up(a: int, b: int) -> int:
    product = a * b
    if product == 0:
        return 0
    return ((product - 1) // ONE) + 1


def calc_in_given_out(
    bal_in: int,
    bal_out: int,
    amount_out: int,
    undercharge: bool,
) -> int:
    if bal_in == 0 or bal_out == 0 or amount_out == 0:
        return 0
    if bal_out < amount_out:
        return 0
    amount_in = (amount_out * bal_in) // bal_out
    if amount_in == 0 and amount_out > 0:
        amount_in = 1
    if undercharge and 0 < amount_out <= 100:
        amount_in = mul_down(amount_in, ONE - 5 * 10**15)
    return amount_in


@dataclass
class Counterexample:
    amount_out: int
    rate: int
    bal_in: int
    bal_out: int
    scaled_down: int
    scaled_up: int
    paid_vuln: int
    paid_fair: int

    @property
    def undercharge(self) -> int:
        return self.paid_fair - self.paid_vuln


def find_upscale_breaks(rate: int, max_amount: int) -> list[tuple[int, int, int]]:
    hits = []
    for x in range(1, max_amount + 1):
        down = mul_down(x, rate)
        up = mul_up(x, rate)
        if down < up:
            hits.append((x, down, up))
    return hits


def find_undercharge(
    rate: int,
    bal_in: int,
    bal_out: int,
    max_amount: int,
) -> list[Counterexample]:
    found: list[Counterexample] = []
    for x in range(1, min(max_amount, bal_out) + 1):
        scaled_down = mul_down(x, rate)
        scaled_up = mul_up(x, rate)
        paid_vuln = calc_in_given_out(bal_in, bal_out, scaled_down, undercharge=True)
        paid_fair = calc_in_given_out(bal_in, bal_out, scaled_up, undercharge=False)
        if paid_vuln == 0 or paid_fair == 0:
            continue
        if paid_vuln < paid_fair:
            found.append(
                Counterexample(
                    amount_out=x,
                    rate=rate,
                    bal_in=bal_in,
                    bal_out=bal_out,
                    scaled_down=scaled_down,
                    scaled_up=scaled_up,
                    paid_vuln=paid_vuln,
                    paid_fair=paid_fair,
                )
            )
    return found


def apply_swap(
    b0: int,
    b1: int,
    token_in: int,
    token_out: int,
    amount_out: int,
    rate0: int,
) -> tuple[int, int, int] | None:
    """Returns (new_b0, new_b1, undercharge) or None if invalid."""
    bal_in = b0 if token_in == 0 else b1
    bal_out = b0 if token_out == 0 else b1
    if amount_out > bal_out or amount_out <= 0:
        return None
    rate = rate0 if token_out == 0 else ONE
    scaled_down = mul_down(amount_out, rate)
    scaled_up = mul_up(amount_out, rate)
    paid_v = calc_in_given_out(bal_in, bal_out, scaled_down, True)
    paid_f = calc_in_given_out(bal_in, bal_out, scaled_up, False)
    if paid_v == 0 or paid_f == 0 or paid_v >= paid_f:
        return None
    nb_in = bal_in + paid_v
    nb_out = bal_out - amount_out
    if token_in == 0 and token_out == 1:
        return nb_in, nb_out, paid_f - paid_v
    if token_in == 1 and token_out == 0:
        return nb_out, nb_in, paid_f - paid_v
    return None


def search_sequence(
    rate0: int,
    bal0: int,
    bal1: int,
    max_amount: int,
    steps: int,
) -> tuple[list[tuple[int, int, int]], int, tuple[int, int]]:
    b0, b1 = bal0, bal1
    seq: list[tuple[int, int, int]] = []
    gain = 0

    for _ in range(steps):
        step_best = None
        step_gain = -1
        step_state = (b0, b1)

        for token_in in (0, 1):
            token_out = 1 - token_in
            for x in range(1, max_amount + 1):
                applied = apply_swap(b0, b1, token_in, token_out, x, rate0)
                if applied is None:
                    continue
                nb0, nb1, g = applied
                if g > step_gain:
                    step_gain = g
                    step_best = (token_in, token_out, x)
                    step_state = (nb0, nb1)

        if step_best is None:
            break
        seq.append(step_best)
        gain += step_gain
        b0, b1 = step_state

    return seq, gain, (b0, b1)


def emit_foundry_snippet(cex: Counterexample) -> str:
    return f"""// from tool/symbolic_search.py
function test_symbolic_counterexample() public {{
    // balances ~ ({cex.bal_in}, {cex.bal_out}), amountOut={cex.amount_out}
    uint256 fairIn = pool.fairAmountIn(1, 0, {cex.amount_out});
    uint256 before = token1.balanceOf(attacker);
    vm.prank(attacker);
    pool.swapGivenOut(1, 0, {cex.amount_out});
    uint256 paid = before - token1.balanceOf(attacker);
    assertLt(paid, fairIn); // paid_vuln={cex.paid_vuln} < paid_fair={cex.paid_fair}
}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded symbolic rounding search")
    parser.add_argument("--rate", type=int, default=1114 * 10**15)
    parser.add_argument("--max-amount", type=int, default=64)
    parser.add_argument("--bal-in", type=int, default=9)
    parser.add_argument("--bal-out", type=int, default=9)
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--emit-forge", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("InvariantBreaker - Bounded Symbolic Search")
    print("=" * 72)
    print()
    print("Model:")
    print("  upscale_down(x) = floor(x * rate / 1e18)")
    print("  upscale_up(x)   = ceil(x * rate / 1e18)")
    print("  find x where paid_vuln(x) < paid_fair(x)")
    print()

    gaps = find_upscale_breaks(args.rate, args.max_amount)
    print(f"[1] Upscale asymmetry (rate={args.rate})")
    print(f"    amounts with mulDown < mulUp: {len(gaps)} / {args.max_amount}")
    if gaps:
        print("    samples (amountOut, down, up):")
        for x, d, u in gaps[:8]:
            print(f"      {x}: {d} < {u}")
    print()

    cexs = find_undercharge(args.rate, args.bal_in, args.bal_out, args.max_amount)
    print(f"[2] Undercharge counterexamples @ balances ({args.bal_in}, {args.bal_out})")
    print(f"    found: {len(cexs)}")
    if not cexs:
        print("    none in bound")
        return 1

    best = max(cexs, key=lambda c: c.undercharge)
    print(
        f"    best: amountOut={best.amount_out} "
        f"paid_vuln={best.paid_vuln} paid_fair={best.paid_fair} "
        f"undercharge={best.undercharge}"
    )
    print(f"    broken: paid_vuln < paid_fair ({best.paid_vuln} < {best.paid_fair})")
    print()

    seq, gain, end = search_sequence(
        args.rate, args.bal_in, args.bal_out, min(args.max_amount, 8), args.steps
    )
    print(f"[3] Bounded batch path search (steps<={args.steps})")
    print(f"    sequence length: {len(seq)}")
    print(f"    cumulative undercharge: {gain}")
    print(f"    end balances: {end}")
    if seq:
        print("    steps (tokenIn, tokenOut, amountOut):")
        for s in seq[:10]:
            print(f"      {s}")
    print()

    print("[4] Verdict")
    print("    property broken in-bound: rounding favors protocol on GIVEN_OUT")
    print()

    if args.emit_forge:
        print(emit_foundry_snippet(best))

    print("=" * 72)
    print("RESULT: counterexample found")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
