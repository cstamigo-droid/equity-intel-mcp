# ROADMAP — equity-intel-mcp

Status: **v0.2 shipped & tested live.** 7 tools, composite coverage 100% (5/5 directional
sources), 10 evals verified. See [BITACORA.md](BITACORA.md) for session history.

**v0.1 (2026-06-14):** 4 tools (quote, insider, superinvestor, analyze_ticker).
**v0.2 (2026-06-14):** +3 sources (analysts/Finnhub, valuation/Yahoo, options/Yahoo), 7 tools total.

**Pendiente (Fase 6 — acciones humanas):** Claude Desktop config · demo video 60s · GitHub publish.
See BITACORA.md for details.

---

## How to add a source (the recipe)

1. Create `equity_intel_mcp/sources/<name>.py` with `def fetch(ticker) -> Signal`.
   - Wrap the network call in `cache.get_or_fetch(...)` with a sensible TTL.
   - Return `Signal.failed("<name>", reason)` on no-data — **never a fake score**.
   - Map your raw read to a `score` in -100..+100 and a `confidence` in 0..1.
2. Add a `@mcp.tool` wrapper in `server.py` (copy an existing one).
3. The key already exists in `analyze.SOURCE_WEIGHTS` — add the source to the
   `asyncio.gather(...)` call inside `equity_analyze_ticker`.
4. Add it to `tests/test_smoke.py` and run `python tests/test_smoke.py <TICKER>`.

---

## Next sources (priority order)

### 1. `equity_analyst_consensus` — Finnhub  (weight 0.20)
- Endpoint: `GET https://finnhub.io/api/v1/stock/recommendation?symbol=X&token=KEY`
  (free tier). Also `/quote` for target price if desired.
- Score: `(strongBuy*2 + buy - sell - strongSell*2) / total * 50`, clamp ±100.
- Confidence: scale by total analysts (cap ~0.8; analyst consensus lags).
- Reference logic: `Dios/MAAT/tools/finnhub_tool.py`.
- Needs `FINNHUB_API_KEY` in `.env` → fall back to `Signal.failed` if absent.

### 2. `equity_valuation` — Yahoo fundamentals  (weight 0.15)
- `yfinance` `.info`: trailingEps, forwardEps, sector P/E, debtToEquity,
  currentRatio, quickRatio, targetMeanPrice.
- Score: blend (forward P/E vs sector) for cheap/rich + a 0..100 financial-health
  sub-score from the balance-sheet ratios. Cheap + healthy → positive.
- Reference logic: `Dios/MAAT/tools/valuation_tool.py` (already canibalized from
  Raúl's Swing Pro tool — reuse its sector-multiple table).

### 3. `equity_options_signal` — Yahoo options chain  (weight 0.10)
- `yfinance` `.option_chain()` near-the-money IV → implied move for next expiry.
- Compare implied move to historical realized move around earnings.
- Score: a large implied move with bullish skew → mild positive, etc. Keep
  confidence low (0.5–0.65) — this is the noisiest signal.
- Reference logic: `Dios/MAAT/tools/probabilistic_tool.py`.

---

## Beyond sources

- **Evaluations** (`evals/`): 10 read-only Q&A pairs per the mcp-builder
  evaluation guide (e.g. "Which of AAPL/MSFT/NVDA has the most superinvestor
  owners?") to prove the tools actually answer real questions. Stable answers only.
- **Packaging**: publish to GitHub (public), tag `mcp` + `claude` topics. Optional
  PyPI release so clients `pip install equity-intel-mcp`.
- **Hosted tier (commercial)**: wrap with `mcp.run(transport="streamable_http")`,
  add an API key check + per-key rate limiting, deploy on Railway (same as AEGIS).
  Free local server = lead magnet; hosted multi-client = the paid product.
- **Demo asset for Upwork**: a 60-second screen recording of Claude Desktop calling
  `equity_analyze_ticker` on a live ticker. This is the portfolio piece.

---

## Known limitations (be honest in the README / to clients)

- Dataroma / Yahoo are scraped/undocumented; markup changes can break a parser.
  Each source is isolated so one breakage never takes down the server.
- Insider signal is USD-net only; it doesn't yet distinguish 10b5-1 planned sales
  from discretionary ones (a known refinement).
- Not real-time: quotes are delayed; filings appear with SEC's normal lag.
