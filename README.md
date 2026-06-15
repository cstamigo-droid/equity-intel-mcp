# equity-intel-mcp

**Institutional-grade equity analysis for any LLM, over the Model Context Protocol.**

Most "stock" integrations just echo a price. This one gives an AI agent the
signals professionals actually look at — **insider buying from SEC filings**,
**what renowned value investors are holding**, analyst consensus, options-implied
moves, and valuation — and blends them into a single, confidence-weighted verdict.

It runs entirely on **free / public data** (Yahoo Finance, SEC EDGAR, Dataroma),
fails gracefully when a source is missing, and never fabricates a signal it
doesn't have.

```
# Equity Intelligence — MSFT

## Verdict: Neutral → HOLD
[........|#.......] +11/100  · confidence 69%  · 5 source(s)

| Source        | Signal       | Score  | Conf | Weight |
|---------------|--------------|-------:|-----:|-------:|
| insider       | Bearish      |   -77  |  70% |   0.25 |
| superinvestor | Lean bullish |   +33  | 100% |   0.30 |
| analysts      | Bullish      |   +64  |  75% |   0.15 |
| valuation     | Bullish      |   +91  |  60% |   0.09 |
| options       | Lean bullish |   +19  |  40% |   0.04 |

- insider: Insiders net selling $13.5M over 180d (62 filings).
- superinvestor: 38 tracked superinvestors hold MSFT; 19 buys / 18 sells.
- analysts: 66 analysts: 23 strong buy / 38 buy / 5 hold.
- valuation: Fair value ~$569 vs $391 (+46% upside); health 84/100.
- options: 1-month implied move +/-7.6%; put/call OI 0.53.
```

---

## Tools

| Tool | What it does | Source | Status |
|------|--------------|--------|:------:|
| `equity_analyze_ticker` | **Hero tool.** Runs every source in parallel and returns one scored verdict (BUY → AVOID) with a per-source breakdown. | composite | ✅ |
| `equity_insider_activity` | Net insider buying vs. selling from SEC **Form 4** filings (180-day window), weighted by USD value. | SEC EDGAR | ✅ |
| `equity_superinvestors` | Which of ~80 tracked value investors hold the stock, plus recent net buying/selling. | Dataroma | ✅ |
| `equity_get_quote` | Live price snapshot + position in the 52-week range. | Yahoo Finance | ✅ |
| `equity_analyst_consensus` | Wall Street buy/hold/sell consensus — scored from distribution of strong-buy to strong-sell ratings. | Finnhub | ✅ |
| `equity_options_signal` | 1-month implied move (straddle/spot) + put/call OI skew. Primary use: risk-sizing. | Yahoo Finance | ✅ |
| `equity_valuation` | Fair-value estimate (forward EPS × sector P/E) + financial-health score (debt, liquidity, margins). | Yahoo Finance | ✅ |

Every tool returns **Markdown** (human-readable, default) or **JSON**
(`response_format="json"`) for programmatic use.

---

## Quick start

```bash
git clone <your-repo-url> equity-intel-mcp
cd equity-intel-mcp
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

copy .env.example .env        # then edit .env (set EDGAR_IDENTITY)
python -m equity_intel_mcp    # starts the MCP server over stdio
```

**Smoke test** (hits the live sources and prints each signal):

```bash
python tests/test_smoke.py AAPL
```

### Configure (`.env`)

```ini
# Required by SEC fair-access policy — any "Name email@example.com"
EDGAR_IDENTITY=Your Name you@example.com
# Required by equity_analyst_consensus (free key at finnhub.io)
FINNHUB_API_KEY=your-key-here
```

---

## Use it in Claude Desktop

Add this to `claude_desktop_config.json`
(`%APPDATA%\Claude\` on Windows, `~/Library/Application Support/Claude/` on macOS),
then restart Claude Desktop:

```json
{
  "mcpServers": {
    "equity-intel": {
      "command": "python",
      "args": ["-m", "equity_intel_mcp"],
      "cwd": "C:/path/to/equity-intel-mcp",
      "env": { "EDGAR_IDENTITY": "Your Name you@example.com" }
    }
  }
}
```

Then just ask Claude: *"Give me a full read on NVDA"* or *"Are insiders buying PLTR?"*

---

## Why it's built this way

- **Uniform signal contract.** Every source returns the same shape
  (`score -100..+100`, `confidence 0..1`, `data`, `summary`). That's what lets an
  LLM reason *across* heterogeneous evidence instead of parsing five formats.
- **Graceful degradation.** A stock with no Form 4 activity returns *"no signal"*,
  not a fake bearish score. Missing data lowers confidence; it never invents a call.
- **Confidence-weighted blending.** The composite weights each source by its
  importance × its own confidence, so thin signals don't outvote strong ones.
- **Resilient + cached.** Short per-source TTL caches avoid hammering rate-limited
  endpoints when an agent calls several tools on the same ticker in one turn.

See [ROADMAP.md](ROADMAP.md) for what's next.

---

## Disclaimer

For research and educational use only. **Not investment advice.** Data comes from
third-party public sources and may be delayed or incomplete. Do your own due
diligence.

## License

MIT
