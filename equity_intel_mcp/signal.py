"""The single return type every data source produces.

A uniform contract is what lets an LLM reason *across* heterogeneous signals
(insider buying vs. analyst downgrades vs. rich valuation) without each source
inventing its own shape. Directional sources contribute a score to the composite
verdict; informational sources (e.g. a quote snapshot) carry data only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def clamp(x: float, lo: float, hi: float) -> float:
    """Constrain x to the inclusive [lo, hi] range."""
    return max(lo, min(hi, x))


def label(score: float) -> str:
    """Human label for a -100..+100 directional score."""
    if score >= 40:
        return "Bullish"
    if score >= 12:
        return "Lean bullish"
    if score > -12:
        return "Neutral"
    if score > -40:
        return "Lean bearish"
    return "Bearish"


@dataclass
class Signal:
    """Uniform result object returned by every source in `sources/`.

    Attributes:
        source:      short id of the producing source, e.g. "insider".
        ok:          True if data was fetched and the signal is meaningful.
        score:       -100 (bearish) .. +100 (bullish). 0 for informational sources.
        confidence:  0.0 .. 1.0 — how much to trust this signal given data quality/quantity.
        summary:     one-line human-readable takeaway.
        data:        raw structured details (source-specific).
        error:       failure reason when ok is False; None otherwise.
        directional: whether `score` should feed the composite verdict.
    """

    source: str
    ok: bool
    score: float = 0.0
    confidence: float = 0.0
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    directional: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def failed(cls, source: str, error: str, *, directional: bool = True) -> "Signal":
        """Graceful degradation: a missing source NEVER injects a fake bearish score.

        It returns ok=False with score 0 so the composite can simply skip it.
        """
        return cls(
            source=source,
            ok=False,
            score=0.0,
            confidence=0.0,
            summary=f"no data ({error})",
            data={},
            error=error,
            directional=directional,
        )
