"""Quick composite test — runs all 6 sources + composite verdict for MSFT."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from equity_intel_mcp import analyze
from equity_intel_mcp.sources import analysts, insider, options, quote, superinvestor, valuation


async def main():
    loop = asyncio.get_running_loop()
    ticker = sys.argv[1] if len(sys.argv) > 1 else "MSFT"

    def _r(fn):
        return loop.run_in_executor(None, lambda: fn(ticker))

    signals = list(await asyncio.gather(
        _r(quote.fetch),
        _r(insider.fetch),
        _r(superinvestor.fetch),
        _r(analysts.fetch),
        _r(valuation.fetch),
        _r(options.fetch),
    ))
    result = analyze.composite(signals)
    print(f"Ticker: {ticker}")
    print(f"Score:    {result['score']}")
    print(f"Verdict:  {result['verdict']}")
    print(f"Coverage: {result['coverage']}")
    print(f"Conf:     {result['confidence']}")
    print(f"N direct: {result['n_sources']}")
    for b in result["breakdown"]:
        print(f"  {b['source']:15s}  score={b['score']:7.1f}  conf={b['confidence']:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
