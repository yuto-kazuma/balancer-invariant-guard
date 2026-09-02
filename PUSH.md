# Prerequisites

- [Foundry](https://book.getfoundry.sh/getting-started/installation) (for PoC tests)
- Python 3.8+ (for rounding scanner)

# Setup

```bash
cd poc
git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std
forge test -vvv
```

# Push to GitHub

```bash
cd balancer-invariant-guard   # or your olympix folder
git init
git add .
git commit -m "Olympix take-home: Balancer exploit analysis and InvariantBreaker PoC"
git remote add origin https://github.com/yuto-kazuma/balancer-invariant-guard.git
git branch -M main
git push -u origin main
```

Then email Mason using `SUBMISSION.md` as the template.
