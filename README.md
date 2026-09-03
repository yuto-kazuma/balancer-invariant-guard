# balancer-invariant-guard

Balancer V2 Nov 2025 rounding exploit repro + a small tool that would have caught it.

```bash
.\demo.ps1
# or: ./demo.sh

cd poc && forge test -vvv
python tool/symbolic_search.py
```

- `poc/` - pool + Foundry tests
- `tool/rounding_scanner.py` - static rounding checks
- `tool/symbolic_search.py` - bounded symbolic counterexample search
