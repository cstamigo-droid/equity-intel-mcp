"""Intrinsic valuation + financial-health from Yahoo fundamentals.

Fair value = forward EPS x sector P/E band (free, deterministic — no premium API).
Score: cheap = +, rich = - (upside_pct x 2, clamped). A "cheap but fragile"
balance sheet (health < 40) halves a positive score (don't buy a falling knife).
"""
from __future__ import annotations

import yfinance as yf

from .. import cache
from ..signal import Signal, clamp

_TTL_S = 3600.0
_SECTOR_PE = {
    "Technology": 28.0, "Communication Services": 20.0, "Consumer Cyclical": 22.0,
    "Consumer Defensive": 20.0, "Healthcare": 22.0, "Financial Services": 14.0,
    "Industrials": 20.0, "Energy": 12.0, "Utilities": 18.0, "Real Estate": 30.0,
    "Basic Materials": 16.0,
}
_SECTOR_PE_DEFAULT = 18.0


def _interp(x, pts):
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _health(info: dict) -> tuple[int | None, dict]:
    subs, detail = [], {}
    de = info.get("debtToEquity")
    if de is not None:
        de = float(de) / 100.0  # yfinance gives a percentage
        subs.append(_interp(de, [(0.0, 100), (1.0, 70), (2.0, 40), (3.0, 10)]))
        detail["debt_to_equity"] = round(de, 2)
    cr = info.get("currentRatio")
    if cr is not None:
        subs.append(_interp(float(cr), [(0.8, 20), (1.0, 50), (1.5, 80), (2.0, 100)]))
        detail["current_ratio"] = round(float(cr), 2)
    qr = info.get("quickRatio")
    if qr is not None:
        subs.append(_interp(float(qr), [(0.5, 20), (1.0, 70), (1.5, 100)]))
        detail["quick_ratio"] = round(float(qr), 2)
    gm = info.get("grossMargins")
    if gm is not None:
        subs.append(_interp(float(gm), [(0.10, 20), (0.30, 60), (0.50, 85), (0.65, 100)]))
        detail["gross_margin_pct"] = round(float(gm) * 100, 1)
    if not subs:
        return None, {}
    return round(sum(subs) / len(subs)), detail


def _pull(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    info = tk.info or {}
    if not info.get("currentPrice"):
        try:
            info["currentPrice"] = float(tk.fast_info["last_price"])
        except Exception:
            pass
    return info


def fetch(ticker: str) -> Signal:
    t = ticker.upper().strip()
    try:
        info = cache.get_or_fetch(f"info:{t}", _TTL_S, lambda: _pull(t))
    except Exception as e:
        return Signal.failed("valuation", str(e))

    price = info.get("currentPrice")
    eps_fwd = info.get("forwardEps") or info.get("trailingEps")
    if not price or not eps_fwd or eps_fwd <= 0:
        return Signal.failed("valuation", "no forward EPS / price to value")

    sector = info.get("sector") or ""
    pe_sector = _SECTOR_PE.get(sector, _SECTOR_PE_DEFAULT)
    fair_value = eps_fwd * pe_sector * 1.05  # midpoint of 0.95x..1.15x band
    upside_pct = (fair_value / float(price) - 1.0) * 100.0

    health_score, health_detail = _health(info)
    score = clamp(upside_pct * 2.0, -100.0, 100.0)
    if health_score is not None and health_score < 40 and score > 0:
        score *= 0.5  # cheap + fragile != buy

    inputs_ok = sum(x is not None for x in (eps_fwd, info.get("bookValue"),
                                            info.get("trailingPE"), health_score))
    confidence = {0: 0.0, 1: 0.25, 2: 0.4, 3: 0.5, 4: 0.6}[inputs_ok]

    tag = ("undervalued" if upside_pct >= 25 else "fairly valued"
           if upside_pct >= -5 else "overvalued" if upside_pct >= -20 else "richly valued")
    summary = (
        f"Fair value ~${fair_value:,.0f} vs ${price:,.0f} "
        f"({upside_pct:+.0f}% upside, {tag}); financial health "
        f"{health_score if health_score is not None else 'n/a'}/100."
    )
    return Signal(
        source="valuation",
        ok=True,
        score=round(score, 1),
        confidence=confidence,
        summary=summary,
        data={
            "fair_value": round(fair_value, 2), "price": round(float(price), 2),
            "upside_pct": round(upside_pct, 1), "tag": tag,
            "sector": sector, "sector_pe": pe_sector,
            "trailing_pe": info.get("trailingPE"),
            "health_score": health_score, **health_detail,
            "url": f"https://finance.yahoo.com/quote/{t}/key-statistics",
        },
    )
