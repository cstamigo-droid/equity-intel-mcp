# Evaluations — equity-intel-mcp

10 read-only, deterministic Q/A pairs for spot-checking tool correctness.
No LLM key required — all answers are verifiable by running the source functions directly.

## Running manually

```bash
# From the repo root:
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from equity_intel_mcp.sources import superinvestor, insider, analysts, valuation, options
from equity_intel_mcp import analyze

# Eval 1 — KO superinvestors
s = superinvestor.fetch('KO')
print('Eval 1 KO owners:', s.data.get('count_owners'))

# Eval 3 — AAPL insider direction
i = insider.fetch('AAPL')
print('Eval 3 AAPL net_selling:', i.data.get('net_selling'))

# Eval 4 — AAPL analyst count
a = analysts.fetch('AAPL')
print('Eval 4 AAPL analysts_count:', a.data.get('analysts_count'))

# Eval 6 — KO valuation tag
v = valuation.fetch('KO')
print('Eval 6 KO tag:', v.data.get('tag'))
"
```

## Notes

- Evals 1–4, 6 depend on live data and may drift over time (re-verify quarterly).
- Evals 5, 7–10 are structural constants baked into the source code — they never drift.
- The XML file (`equity_intel_eval.xml`) is the ground truth; this README is for humans.
