"""Quote snapshot from Yahoo Finance (yfinance).

Informational source: it carries price/volume/valuation context but does not
vote in the composite verdict (directional=False). It does surface where price
sits inside its 52-week range, which downstream tools and the LLM can interpret.
"""
from __future__ import annotations

import yfinance as yf

from .. import cache
from ..signal import Signal

_TTL_S = 60.0


def _pull(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    fi = tk.fast_info  # mapping-like; tolerate missing keys

    def g(*keys):
        for k in keys:
            try:
                val = fi[k]
            except (KeyError, TypeError):
                val = getattr(fi, k, None)
            if val is not None:
                return val
        return None

    price = g("last_price", "lastPrice")
    prev = g("previous_close", "previousClose")
    out = {
        "price": price,
        "previous_close": prev,
        "open": g("open"),
        "day_low": g("day_low", "dayLow"),
        "day_high": g("day_high", "dayHigh"),
        "year_low": g("year_low", "yearLow"),
        "year_high": g("year_high", "yearHigh"),
        "market_cap": g("market_cap", "marketCap"),
        "volume": g("last_volume", "lastVolume"),
        "currency": g("currency"),
    }
    if price and prev:
        out["change_pct"] = round((price - prev) / prev * 100, 2)
    lo, hi = out["year_low"], out["year_high"]
    if price and lo and hi and hi > lo:
        out["pct_of_52w_range"] = round((price - lo) / (hi - lo) * 100, 1)
    return out


def fetch(ticker: str) -> Signal:
    """Return a quote snapshot Signal for `ticker` (informational, non-directional)."""
    t = ticker.upper().strip()
    try:
        data = cache.get_or_fetch(f"quote:{t}", _TTL_S, lambda: _pull(t))
    except Exception as e:  # network / parse failure
        return Signal.failed("quote", str(e), directional=False)

    if not data.get("price"):
        return Signal.failed("quote", f"no price data for {t}", directional=False)

    chg = data.get("change_pct")
    rng = data.get("pct_of_52w_range")
    bits = [f"{t} @ {data['price']:,.2f} {data.get('currency') or ''}".strip()]
    if chg is not None:
        bits.append(f"{chg:+.2f}% today")
    if rng is not None:
        bits.append(f"{rng:.0f}% of 52w range")
    data["url"] = f"https://finance.yahoo.com/quote/{t}"

    return Signal(
        source="quote",
        ok=True,
        score=0.0,
        confidence=0.9,
        summary=" · ".join(bits),
        data=data,
        directional=False,
    )
