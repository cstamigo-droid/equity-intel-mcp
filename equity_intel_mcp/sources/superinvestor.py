"""Superinvestor holdings from Dataroma (/m/stock.php?sym=TICKER).

Dataroma tracks ~80 renowned value investors' 13F portfolios. Breadth of
ownership (how many hold it) plus recent net buying/selling is a "smart money
consensus" read. Scraped from public HTML — no API exists.

Score blends ownership breadth (0..+60) with recent net activity (±30).
"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..signal import Signal, clamp

_URL = "https://www.dataroma.com/m/stock.php?sym={ticker}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; equity-intel-mcp/0.1)"}
_MAX_OWNERS = 82  # total superinvestors Dataroma tracks
_TTL_S = 3600.0


def _pull(ticker: str) -> str:
    resp = requests.get(_URL.format(ticker=ticker), headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def _parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    count_owners = 0
    t1 = soup.find("table", id="t1")
    if t1:
        for row in t1.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "ownership count" in cells[0].get_text(strip=True).lower():
                try:
                    count_owners = int(cells[1].get_text(strip=True))
                except ValueError:
                    pass
                break
    if count_owners == 0:
        grid = soup.find("table", id="grid")
        if grid:
            count_owners = max(0, len(grid.find_all("tr")) - 1)

    # Activity cells: class="buy" = adds/new, class="sell" = reduces. Empty sell
    # cells mean "no change" — count only non-empty cells.
    recent_buys = sum(1 for c in soup.select("td.buy") if c.get_text(strip=True))
    recent_sells = sum(1 for c in soup.select("td.sell") if c.get_text(strip=True))

    avg_price = None
    if t1:
        for row in t1.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "hold price" in cells[0].get_text(strip=True).lower():
                raw = cells[1].get_text(strip=True).replace("$", "").replace(",", "")
                try:
                    avg_price = float(raw)
                except ValueError:
                    pass
                break

    owners: list[str] = []
    grid = soup.find("table", id="grid")
    if grid:
        for row in grid.find_all("tr")[1:11]:  # skip header, take top 10
            cells = row.find_all("td")
            if len(cells) >= 2:
                owners.append(cells[1].get_text(strip=True))

    return {
        "count_owners": count_owners,
        "recent_buys": recent_buys,
        "recent_sells": recent_sells,
        "avg_hold_price": avg_price,
        "owners_sample": owners,
    }


def fetch(ticker: str) -> Signal:
    """Return a smart-money consensus Signal for `ticker` from Dataroma."""
    t = ticker.upper().strip()
    try:
        html = cache.get_or_fetch(f"dataroma:{t}", _TTL_S, lambda: _pull(t))
        d = _parse(html)
    except Exception as e:
        return Signal.failed("superinvestor", str(e))

    if d["count_owners"] == 0:
        return Signal.failed("superinvestor", f"{t} not held by any tracked superinvestor")

    ownership_score = min(d["count_owners"] / _MAX_OWNERS, 1.0) * 60.0
    net_activity = d["recent_buys"] - d["recent_sells"]
    activity_score = clamp(net_activity * 5.0, -30.0, 30.0)
    score = clamp(ownership_score + activity_score, -100.0, 100.0)
    confidence = min(d["count_owners"] / 15.0, 1.0)

    summary = (
        f"{d['count_owners']} tracked superinvestors hold {t}; "
        f"recent quarter: {d['recent_buys']} buys / {d['recent_sells']} sells."
    )
    d["url"] = _URL.format(ticker=t)
    return Signal(
        source="superinvestor",
        ok=True,
        score=round(score, 1),
        confidence=round(confidence, 2),
        summary=summary,
        data=d,
    )
