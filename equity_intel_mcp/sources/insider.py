"""Insider activity from SEC EDGAR Form 4 filings (via edgartools).

Measures whether company insiders (officers/directors) are net BUYING or SELLING
over a trailing window, weighted by USD value of open-market Purchase (code P)
vs. Sale (code S) transactions. Insider buying is one of the few signals with
real predictive weight in academic literature, and it is genuinely hard to do
well — it requires parsing primary SEC filings, not a convenience API.

Graceful degradation: a company with no qualifying Form 4 activity returns
ok=False (no signal) — it never fabricates a bearish score from missing data.

Requires a SEC identity string (any "Name email@example.com") via the
EDGAR_IDENTITY env var — SEC's fair-access policy mandates a contact in the
User-Agent. See .env.example.
"""
from __future__ import annotations

import datetime as dt
import os

from ..signal import Signal, clamp

_identity_set = False
_DEFAULT_IDENTITY = "equity-intel-mcp anonymous@example.com"
_WINDOW_DAYS = 180
_MAX_FILINGS = 80  # newest-first; covers ~180d even for very active issuers


def _ensure_identity() -> None:
    global _identity_set
    if not _identity_set:
        from edgar import set_identity

        set_identity(os.getenv("EDGAR_IDENTITY", _DEFAULT_IDENTITY))
        _identity_set = True


def _fetch_trades(ticker: str, days: int = _WINDOW_DAYS) -> tuple[list[dict], int]:
    """Return (trades, n_filings). Each trade = {usd, acquired}. Only codes P/S."""
    import pandas as pd
    from edgar import Company

    _ensure_identity()
    cutoff = dt.date.today() - dt.timedelta(days=days)
    filings = Company(ticker.upper()).get_filings(form="4")

    trades: list[dict] = []
    n_filings = 0
    for filing in filings.head(_MAX_FILINGS):
        fdate = getattr(filing, "filing_date", None)
        if fdate and fdate < cutoff:
            break  # filings are newest-first → past the window, stop
        try:
            df = filing.obj().to_dataframe()
        except Exception:
            continue  # one broken filing must not sink the batch
        if df is None or getattr(df, "empty", True):
            continue
        n_filings += 1
        if "Code" not in df.columns or "Value" not in df.columns:
            continue
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip().upper()
            if code not in ("P", "S"):
                continue  # ignore awards, option exercises, gifts, etc.
            try:
                usd = float(pd.to_numeric(row["Value"], errors="coerce"))
            except (TypeError, ValueError):
                usd = 0.0
            if usd != usd or usd == 0.0:  # NaN or zero
                continue
            trades.append({"usd": abs(usd), "acquired": code == "P"})
    return trades, n_filings


def fetch(ticker: str) -> Signal:
    """Return an insider net-activity Signal for `ticker` over the last 180 days."""
    t = ticker.upper().strip()
    try:
        trades, n_filings = _fetch_trades(t)
    except ImportError as e:
        return Signal.failed("insider", f"edgartools/pandas not installed: {e}")
    except Exception as e:
        return Signal.failed("insider", str(e))

    if not trades:
        return Signal.failed("insider", f"no open-market Form 4 activity in {_WINDOW_DAYS}d")

    buys = sum(x["usd"] for x in trades if x["acquired"])
    sells = sum(x["usd"] for x in trades if not x["acquired"])
    gross = buys + sells
    if gross == 0:
        return Signal.failed("insider", "no valued transactions")

    net = buys - sells
    score = clamp(net / gross * 100.0, -100.0, 100.0)
    confidence = min(n_filings / 10.0, 1.0) * 0.7  # noisy data → cap at 0.7

    verb = "buying" if net >= 0 else "selling"
    summary = (
        f"Insiders net {verb} ${abs(net):,.0f} over {_WINDOW_DAYS}d "
        f"(${buys:,.0f} bought vs ${sells:,.0f} sold across {n_filings} filings)."
    )
    return Signal(
        source="insider",
        ok=True,
        score=round(score, 1),
        confidence=round(confidence, 2),
        summary=summary,
        data={
            "net_usd": round(net, 2),
            "buys_usd": round(buys, 2),
            "sells_usd": round(sells, 2),
            "n_filings": n_filings,
            "net_selling": net < 0,
            "window_days": _WINDOW_DAYS,
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&company={t}",
        },
    )
