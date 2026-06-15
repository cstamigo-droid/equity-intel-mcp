"""Options market signal from yfinance option_chain.

Primary value: the 1-month implied move (a volatility/risk-sizing tool).
Secondary: directional skew from put/call OI ratio (low conviction — options
are noisy; keep weight low in the composite and confidence capped at 0.40).
"""
from __future__ import annotations

import datetime

import yfinance as yf

from .. import cache
from ..signal import Signal, clamp

_TTL_S = 900.0  # 15 min — options data changes fast during market hours


def _days_to(exp_str: str) -> int:
    """Number of calendar days from today to the expiration date string 'YYYY-MM-DD'."""
    exp = datetime.date.fromisoformat(exp_str)
    return (exp - datetime.date.today()).days


def _pull(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    exps = tk.options  # tuple of 'YYYY-MM-DD' strings, sorted ascending
    if not exps:
        return {}

    spot = None
    try:
        spot = float(tk.fast_info["last_price"])
    except Exception:
        pass
    if not spot:
        return {}

    # Pick expiry closest to 30 calendar days out (minimum 7 days)
    valid = [(abs(_days_to(e) - 30), e) for e in exps if _days_to(e) >= 7]
    if not valid:
        return {}
    _, exp = min(valid)
    days = _days_to(exp)

    oc = tk.option_chain(exp)
    calls, puts = oc.calls, oc.puts
    if calls.empty or puts.empty:
        return {}

    # ATM row = row whose strike is closest to spot
    atm_call = calls.iloc[(calls["strike"] - spot).abs().values.argmin()]
    atm_put = puts.iloc[(puts["strike"] - spot).abs().values.argmin()]
    straddle = float(atm_call["lastPrice"]) + float(atm_put["lastPrice"])
    implied_move_pct = straddle / spot * 100.0
    atm_strike = float(atm_call["strike"])

    put_oi = puts["openInterest"].fillna(0).sum()
    call_oi = calls["openInterest"].fillna(0).sum()
    pc_oi = put_oi / max(call_oi, 1)

    return {
        "spot": spot,
        "exp": exp,
        "days_to_expiry": days,
        "atm_strike": atm_strike,
        "straddle": round(straddle, 2),
        "implied_move_pct": round(implied_move_pct, 2),
        "pc_oi_ratio": round(pc_oi, 2),
    }


def fetch(ticker: str) -> Signal:
    t = ticker.upper().strip()
    try:
        d = cache.get_or_fetch(f"options:{t}", _TTL_S, lambda: _pull(t))
    except Exception as e:
        return Signal.failed("options", str(e))

    if not d:
        return Signal.failed("options", "no option chain data available")

    pc_oi = d["pc_oi_ratio"]
    implied_move_pct = d["implied_move_pct"]

    # Directional skew: low p/c ratio → call-heavy → bullish bias (low conviction)
    score = clamp((1.0 - pc_oi) * 40.0, -40.0, 40.0)
    confidence = 0.40

    summary = (
        f"1-month implied move +/-{implied_move_pct:.1f}% (to {d['exp']}); "
        f"put/call OI ratio {pc_oi:.2f}."
    )
    return Signal(
        source="options",
        ok=True,
        score=round(score, 1),
        confidence=confidence,
        summary=summary,
        data={
            "implied_move_pct": implied_move_pct,
            "expiry": d["exp"],
            "days_to_expiry": d["days_to_expiry"],
            "atm_strike": d["atm_strike"],
            "pc_oi_ratio": pc_oi,
            "straddle_price": d["straddle"],
            "url": f"https://finance.yahoo.com/quote/{t}/options",
        },
    )
