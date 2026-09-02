#!/usr/bin/env python3
"""
InvariantBreaker - Rounding Direction Analyzer

Scans Solidity source for rounding asymmetries that caused the Balancer V2
Nov 2025 exploit (_upscale mulDown on GIVEN_OUT path).

Usage:
    python rounding_scanner.py <file.sol>
    python rounding_scanner.py --recursive src/
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    severity: str
    title: str
    detail: str
    line: int
    snippet: str


@dataclass
class ScanResult:
    file: str
    findings: list[Finding] = field(default_factory=list)


ROUNDING_OPS = re.compile(r"(mulDown|mulUp|divDown|divUp)\s*\(", re.IGNORECASE)
UPSCALE_PATTERN = re.compile(r"function\s+_?upscale\s*\(", re.IGNORECASE)
SWAP_GIVEN_OUT = re.compile(r"function\s+_?swapGivenOut\s*\(", re.IGNORECASE)
FUNCTION_BLOCK = re.compile(r"function\s+\w+[^{]*\{", re.MULTILINE)


def extract_function_body(source: str, func_pattern: re.Pattern) -> tuple[str, int] | None:
    match = func_pattern.search(source)
    if not match:
        return None
    start = match.start()
    line_no = source[:start].count("\n") + 1
    brace_start = source.find("{", match.end() - 1)
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start : i + 1], line_no
    return None


def line_number(source: str, pos: int) -> int:
    return source[:pos].count("\n") + 1


def scan_file(path: Path) -> ScanResult:
    source = path.read_text(encoding="utf-8", errors="replace")
    result = ScanResult(file=str(path))
    lines = source.splitlines()

    upscale_body = extract_function_body(source, UPSCALE_PATTERN)
    if upscale_body:
        body, start_line = upscale_body
        if "mulDown" in body and "mulUp" not in body:
            result.findings.append(
                Finding(
                    severity="CRITICAL",
                    title="Asymmetric upscale rounding (mulDown only)",
                    detail=(
                        "_upscale uses mulDown without mulUp alternative. "
                        "On GIVEN_OUT paths this underestimates amountOut before "
                        "amountIn calculation. Root cause of Balancer V2 Nov 2025 exploit."
                    ),
                    line=start_line,
                    snippet=lines[start_line - 1].strip() if start_line <= len(lines) else "",
                )
            )

    swap_body = extract_function_body(source, SWAP_GIVEN_OUT)
    if swap_body:
        body, start_line = swap_body
        if "_upscale" in body or "upscale" in body.lower():
            if "mulDown" in body or ("upscale" in body and "mulUp" not in body):
                result.findings.append(
                    Finding(
                        severity="HIGH",
                        title="GIVEN_OUT path uses down-rounding on upscale",
                        detail=(
                            "_swapGivenOut adjusts amountOut via _upscale before computing "
                            "amountIn. Rounding down violates 'rounding must favor protocol'."
                        ),
                        line=start_line,
                        snippet=lines[start_line - 1].strip() if start_line <= len(lines) else "",
                    )
                )

    for match in ROUNDING_OPS.finditer(source):
        op = match.group(1)
        ctx_start = max(0, match.start() - 80)
        ctx_end = min(len(source), match.end() + 40)
        context = source[ctx_start:ctx_end].replace("\n", " ")

        if op.lower() == "muldown" and ("upscale" in context.lower() or "givenout" in context.lower()):
            ln = line_number(source, match.start())
            if not any(f.line == ln and "mulDown" in f.title for f in result.findings):
                result.findings.append(
                    Finding(
                        severity="MEDIUM",
                        title=f"mulDown in swap/upscale context (line {ln})",
                        detail="Verify rounding direction favors protocol on this path.",
                        line=ln,
                        snippet=lines[ln - 1].strip() if ln <= len(lines) else "",
                    )
                )

    if "rate" in source.lower() and "mulDown" in source and "_upscale" in source:
        if not any(f.severity == "CRITICAL" for f in result.findings):
            result.findings.append(
                Finding(
                    severity="HIGH",
                    title="Non-unitary rate scaling with mulDown",
                    detail=(
                        "Rate providers introduce non-unitary scaling factors. "
                        "Combined with mulDown at low balances (8-9 wei), precision "
                        "loss can reach ~10% per operation."
                    ),
                    line=1,
                    snippet="(file-level pattern)",
                )
            )

    batch_pattern = re.compile(r"function\s+batchSwap", re.IGNORECASE)
    if batch_pattern.search(source) and not any(
        f.title.startswith("Recommend") for f in result.findings
    ):
        result.findings.append(
            Finding(
                severity="INFO",
                title="Recommend: per-transaction BPT rate invariant",
                detail=(
                    "Add invariant: assert(bptRateAfter * 100 <= bptRateBefore * 101) "
                    "within single batchSwap. Would have caught Balancer 20x rate change."
                ),
                line=1,
                snippet="invariant_bptRateStablePerTransaction()",
            )
        )

    return result


def print_report(results: list[ScanResult]) -> int:
    total_critical = 0
    print("=" * 72)
    print("InvariantBreaker - Rounding Direction Analysis Report")
    print("=" * 72)

    for res in results:
        print(f"\nFile: {res.file}")
        if not res.findings:
            print("  [OK] No rounding asymmetries detected.")
            continue

        for f in res.findings:
            icon = {"CRITICAL": "[!!]", "HIGH": "[!]", "MEDIUM": "[~]", "INFO": "[i]"}.get(
                f.severity, "[ ]"
            )
            print(f"\n  {icon} [{f.severity}] {f.title}")
            print(f"     Line {f.line}: {f.detail}")
            if f.snippet:
                print(f"     > {f.snippet}")
            if f.severity in ("CRITICAL", "HIGH"):
                total_critical += 1

    print("\n" + "=" * 72)
    if total_critical:
        print(f"RESULT: FAIL - {total_critical} high-severity finding(s). Run PoC tests.")
        print("Suggested: cd poc && forge test --match-test test_rounding_exploit -vvv")
    else:
        print("RESULT: PASS - no critical rounding issues detected.")
    print("=" * 72)
    return 1 if total_critical else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="InvariantBreaker rounding scanner")
    parser.add_argument("paths", nargs="+", help="Solidity file(s) or directories")
    parser.add_argument("--recursive", "-r", action="store_true", help="Scan directories recursively")
    args = parser.parse_args()

    files: list[Path] = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            pattern = "**/*.sol" if args.recursive else "*.sol"
            files.extend(path.glob(pattern))
        elif path.suffix == ".sol":
            files.append(path)

    if not files:
        print("No .sol files found.", file=sys.stderr)
        return 2

    results = [scan_file(f) for f in sorted(set(files))]
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
