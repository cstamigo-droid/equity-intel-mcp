"""Wall Street analyst consensus from Finnhub (/stock/recommendation, free tier).

Score: (strongBuy*2 + buy - sell - strongSell*2) / (total*2) * 100.
Confidence capped at 0.75 — consensus lags price. Needs FINNHUB_API_KEY.
"""
from __future__ import annotations

import os

import requests

from .. import cache
from ..signal import Signal, clamp

_URL = "https://finnhub.io/api/v1/stock/recommendation"
_TTL_S = 3600.0
_CONF_CAP = 0.75


def _pull(ticker: str, key: str) -> dict | None:
    resp = requests.get(_URL, params={"symbol": ticker, "token": key}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) and data else None  # newest period first


def fetch(ticker: str) -> Signal:
    t = ticker.upper().strip()
    key = os.getenv("FINNHUB_API_KEY", "")
    if not key:
        return Signal.failed("analysts", "FINNHUB_API_KEY not set")
    try:
        rec = cache.get_or_fetch(f"finnhub:{t}", _TTL_S, lambda: _pull(t, key))
    except Exception as e:
        return Signal.failed("analysts", str(e))
    if not rec:
        return Signal.failed("analysts", f"no analyst coverage for {t}")

    sb, b = rec.get("strongBuy", 0), rec.get("buy", 0)
    h, s, ss = rec.get("hold", 0), rec.get("sell", 0), rec.get("strongSell", 0)
    total = sb + b + h + s + ss
    if total == 0:
        return Signal.failed("analysts", "0 analysts covering")

    score = clamp((sb * 2 + b - s - ss * 2) / (total * 2) * 100, -100.0, 100.0)
    confidence = min(total / 20.0, 1.0) * _CONF_CAP
    summary = (
        f"{total} analysts: {sb} strong buy / {b} buy / {h} hold / "
        f"{s} sell / {ss} strong sell (period {rec.get('period', '?')})."
    )
    return Signal(
        source="analysts",
        ok=True,
        score=round(score, 1),
        confidence=round(confidence, 2),
        summary=summary,
        data={
            "strong_buy": sb, "buy": b, "hold": h, "sell": s, "strong_sell": ss,
            "analysts_count": total, "period": rec.get("period", "?"),
            "url": "https://finnhub.io/",
        },
    )
