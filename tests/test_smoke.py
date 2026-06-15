"""Smoke test — hits the real data sources and prints each Signal.

Run:  python tests/test_smoke.py [TICKER]
This is a live network test (Yahoo, SEC, Dataroma, Finnhub), not a unit test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from equity_intel_mcp.formatting import ResponseFormat, render  # noqa: E402
from equity_intel_mcp.sources import (  # noqa: E402
    analysts,
    insider,
    options,
    quote,
    superinvestor,
    valuation,
)


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    sources = [
        ("quote", quote),
        ("insider", insider),
        ("superinvestor", superinvestor),
        ("analysts", analysts),
        ("valuation", valuation),
        ("options", options),
    ]
    for name, src in sources:
        print(f"\n{'=' * 70}\n  {name.upper()}\n{'=' * 70}")
        sig = src.fetch(ticker)
        print(render(sig, f"{name} — {ticker}", ResponseFormat.MARKDOWN))
        print(f"\n[ok={sig.ok}  score={sig.score}  confidence={sig.confidence}]")


if __name__ == "__main__":
    main()
