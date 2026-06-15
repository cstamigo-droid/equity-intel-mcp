#!/usr/bin/env python3
"""equity_intel_mcp — MCP server exposing institutional-grade equity analysis tools.

Transport: stdio (local — Claude Desktop / Claude Code / agents).

Tools:
  equity_get_quote        — price snapshot + 52-week range position
  equity_insider_activity — SEC Form 4 net insider buying/selling (180d)
  equity_superinvestors   — Dataroma smart-money ownership & recent activity

Each tool returns a uniform, scored Signal rendered as Markdown (default) or JSON.
Sources fail gracefully: a missing data source returns "no signal", never a
fabricated bearish/bullish score.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import analyze
from .formatting import ResponseFormat, render, render_composite
from .signal import Signal
from .sources import analysts, insider, options, quote, superinvestor, valuation

# Load .env from the project root (parent of this package), if present.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

mcp = FastMCP("equity_intel_mcp")


# ─── shared helpers ──────────────────────────────────────────────────────────

async def _run(fn, *args):
    """Run a blocking source function in a thread so the event loop stays free."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args))


class TickerInput(BaseModel):
    """Shared input for single-ticker analysis tools."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ticker: str = Field(
        ...,
        description="Stock symbol, e.g. 'AAPL', 'MSFT', 'TSLA'. Case-insensitive.",
        min_length=1,
        max_length=10,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' for a human-readable report or 'json' for structured data.",
    )

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.upper().strip()


# ─── tools ───────────────────────────────────────────────────────────────────

@mcp.tool(
    name="equity_get_quote",
    annotations={
        "title": "Stock Quote Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_get_quote(params: TickerInput) -> str:
    """Get a current price snapshot for a stock, with 52-week range context.

    Informational (not a buy/sell signal). Use this to anchor any analysis with
    live price, daily change, market cap, volume, and where price sits inside its
    52-week range (0% = at the low, 100% = at the high).

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown report or JSON with fields: price, previous_close, open,
        day_low, day_high, year_low, year_high, market_cap, volume, currency,
        change_pct, pct_of_52w_range.

    Examples:
        - "What's Apple trading at?" -> ticker='AAPL'
        - "Is NVDA near its 52-week high?" -> ticker='NVDA'
    """
    sig = await _run(quote.fetch, params.ticker)
    return render(sig, f"Quote — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_insider_activity",
    annotations={
        "title": "Insider Buying/Selling (SEC Form 4)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_insider_activity(params: TickerInput) -> str:
    """Measure net insider buying vs. selling from SEC Form 4 filings (last 180 days).

    Aggregates open-market Purchase (P) and Sale (S) transactions by USD value and
    returns a directional score from -100 (heavy net selling) to +100 (heavy net
    buying). Insider buying is among the more predictive public signals. If a
    company has no qualifying Form 4 activity, returns "no signal" rather than a
    fabricated score.

    Requires the EDGAR_IDENTITY env var (any 'Name email@example.com') per SEC
    fair-access policy.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown or JSON with score, confidence, and data: net_usd, buys_usd,
        sells_usd, n_filings, net_selling, window_days.

    Examples:
        - "Are insiders buying Tesla?" -> ticker='TSLA'
        - "Insider sentiment for PLTR" -> ticker='PLTR'
    """
    sig = await _run(insider.fetch, params.ticker)
    return render(sig, f"Insider Activity — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_superinvestors",
    annotations={
        "title": "Superinvestor Holdings (Dataroma)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_superinvestors(params: TickerInput) -> str:
    """Check which renowned value investors hold a stock and their recent activity.

    Reads Dataroma's tracking of ~80 superinvestors' 13F portfolios. Returns a
    directional score blending ownership breadth (how many hold it) with recent
    net buying/selling. A widely-held, recently-bought name scores positive.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown or JSON with score, confidence, and data: count_owners,
        recent_buys, recent_sells, avg_hold_price, owners_sample.

    Examples:
        - "Do any famous investors own Berkshire?" -> ticker='BRK.B'
        - "Smart-money interest in GOOGL" -> ticker='GOOGL'
    """
    sig = await _run(superinvestor.fetch, params.ticker)
    return render(sig, f"Superinvestor Holdings — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_analyst_consensus",
    annotations={
        "title": "Wall Street Analyst Consensus",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_analyst_consensus(params: TickerInput) -> str:
    """Get Wall Street buy/hold/sell consensus for a stock (Finnhub).

    Returns a directional score from the distribution of analyst ratings.
    Requires FINNHUB_API_KEY; returns "no signal" if unset or no coverage.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown or JSON with score, confidence, and data: strong_buy, buy,
        hold, sell, strong_sell, analysts_count, period.

    Examples:
        - "What do analysts think of AMD?" -> ticker='AMD'
        - "Is MSFT a buy according to Wall Street?" -> ticker='MSFT'
    """
    sig = await _run(analysts.fetch, params.ticker)
    return render(sig, f"Analyst Consensus — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_valuation",
    annotations={
        "title": "Intrinsic Valuation + Financial Health",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_valuation(params: TickerInput) -> str:
    """Estimate fair value and financial health for a stock (Yahoo Finance).

    Computes a fair-value range using forward EPS × sector P/E band, then
    measures balance-sheet health (debt/equity, current ratio, gross margin).
    Score: positive = stock trades below fair value, negative = expensive.
    A cheap-but-fragile balance sheet halves any positive score.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown or JSON with score, fair_value, upside_pct, tag,
        health_score, and underlying fundamentals.

    Examples:
        - "Is KO undervalued right now?" -> ticker='KO'
        - "What's the intrinsic value of AAPL?" -> ticker='AAPL'
    """
    sig = await _run(valuation.fetch, params.ticker)
    return render(sig, f"Valuation — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_options_signal",
    annotations={
        "title": "Options Market Signal (Implied Move + Skew)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_options_signal(params: TickerInput) -> str:
    """Get the 1-month implied move and put/call OI skew for a stock (yfinance).

    The implied move (straddle / spot) is primarily a risk-sizing tool — it tells
    you how much the market expects the stock to move before the nearest ~30-day
    expiration. The directional score from put/call OI skew is LOW conviction
    (options flow is noisy); treat this as a weak secondary indicator only.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown or JSON with implied_move_pct, expiry, pc_oi_ratio, score.

    Examples:
        - "How volatile is NVDA expected to be?" -> ticker='NVDA'
        - "What does options flow say about AAPL?" -> ticker='AAPL'
    """
    sig = await _run(options.fetch, params.ticker)
    return render(sig, f"Options Signal — {params.ticker}", params.response_format)


@mcp.tool(
    name="equity_analyze_ticker",
    annotations={
        "title": "Full Equity Analysis (Composite Verdict)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def equity_analyze_ticker(params: TickerInput) -> str:
    """Run a full multi-source analysis of a stock and return one scored verdict.

    Fans out to every available source in parallel (price context, insider Form 4
    activity, superinvestor holdings) and blends the directional signals into a
    confidence-weighted verdict from -100 (Bearish/AVOID) to +100 (Bullish/BUY),
    with a per-source breakdown. Sources that have no data are reported as "no
    signal" and excluded from the score rather than guessed.

    This is the primary tool — prefer it for "should I look at X?" questions; use
    the individual tools when you only need one dimension.

    Args:
        params: ticker (str) and response_format ('markdown'|'json').

    Returns:
        str: Markdown verdict with gauge, action, signal-breakdown table, and each
        source's one-line takeaway; or JSON with the full verdict + raw signals.

    Examples:
        - "Give me a full read on Microsoft" -> ticker='MSFT'
        - "Should I be looking at PLTR?" -> ticker='PLTR'
    """
    quote_sig, insider_sig, si_sig, analyst_sig, val_sig, opt_sig = await asyncio.gather(
        _run(quote.fetch, params.ticker),
        _run(insider.fetch, params.ticker),
        _run(superinvestor.fetch, params.ticker),
        _run(analysts.fetch, params.ticker),
        _run(valuation.fetch, params.ticker),
        _run(options.fetch, params.ticker),
    )
    signals = [quote_sig, insider_sig, si_sig, analyst_sig, val_sig, opt_sig]
    result = analyze.composite(signals)
    return render_composite(params.ticker, result, signals, params.response_format)


def main() -> None:
    """Console entrypoint — runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
