"""Render Signals as Markdown (human) or JSON (machine) for MCP tool output."""
from __future__ import annotations

import json
from enum import Enum

from .signal import Signal, clamp, label


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def _gauge(score: float) -> str:
    """A compact ASCII gauge for a -100..+100 score.

    Bearish fills left of center, bullish fills right, e.g.
    -100 -> `[########|........]`, +50 -> `[........|####....]`.
    """
    n = 8  # half-width
    s = clamp(score, -100, 100)
    filled = int(round(abs(s) / 100 * n))
    if s < 0:
        left, right = "." * (n - filled) + "#" * filled, "." * n
    elif s > 0:
        left, right = "." * n, "#" * filled + "." * (n - filled)
    else:
        left = right = "." * n
    return f"[{left}|{right}]"


def render(signal: Signal, title: str, fmt: ResponseFormat) -> str:
    """Format a single Signal for return to an MCP client."""
    if fmt == ResponseFormat.JSON:
        return json.dumps(signal.to_dict(), indent=2, default=str)

    lines = [f"# {title}"]
    if not signal.ok:
        lines += ["", f"⚠️ No signal available — {signal.error}"]
        return "\n".join(lines)

    if signal.directional:
        lines += [
            "",
            f"**Signal:** {label(signal.score)}  "
            f"`{_gauge(signal.score)}` {signal.score:+.0f}/100  "
            f"· confidence {signal.confidence:.0%}",
        ]
    if signal.summary:
        lines += ["", signal.summary]

    if signal.data:
        lines += ["", "## Details"]
        for k, v in signal.data.items():
            if v is None or k == "url":
                continue
            lines.append(f"- **{k.replace('_', ' ')}:** {_fmt_value(v)}")
        url = signal.data.get("url")
        if url:
            lines += ["", f"Source: {url}"]

    return "\n".join(lines)


def render_composite(ticker: str, result: dict, signals: list[Signal], fmt: ResponseFormat) -> str:
    """Render the composite `analyze_ticker` verdict plus its source breakdown."""
    if fmt == ResponseFormat.JSON:
        return json.dumps(
            {"ticker": ticker, "verdict": result, "signals": [s.to_dict() for s in signals]},
            indent=2,
            default=str,
        )

    lines = [
        f"# Equity Intelligence — {ticker}",
        "",
        f"## Verdict: {result['verdict']} → **{result['action']}**",
        f"`{_gauge(result['score'])}` {result['score']:+.0f}/100  "
        f"· confidence {result['confidence']:.0%}  "
        f"· {result['n_sources']} source(s), {result['coverage']:.0%} coverage",
    ]

    quote_sig = next((s for s in signals if s.source == "quote" and s.ok), None)
    if quote_sig:
        lines += ["", f"**Price context:** {quote_sig.summary}"]

    if result["breakdown"]:
        lines += [
            "",
            "## Signal breakdown",
            "| Source | Signal | Score | Conf | Weight |",
            "|---|---|---:|---:|---:|",
        ]
        for b in result["breakdown"]:
            lines.append(
                f"| {b['source']} | {label(b['score'])} | {b['score']:+.0f} "
                f"| {b['confidence']:.0%} | {b['effective_weight']:.2f} |"
            )
        lines += ["", "## What each source says"]
        for b in result["breakdown"]:
            lines.append(f"- **{b['source']}:** {b['summary']}")

    skipped = [s for s in signals if s.directional and not s.ok]
    if skipped:
        lines += ["", "## No signal (data unavailable)"]
        for s in skipped:
            lines.append(f"- **{s.source}:** {s.error}")

    return "\n".join(lines)


def _fmt_value(v: object) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v[:12]) + (" …" if len(v) > 12 else "")
    return str(v)
