"""Composite verdict — blends every directional source into one scored call.

The blend is a confidence-weighted average: each source's directional score is
weighted by (source importance x its own confidence), so a high-conviction
insider signal moves the needle more than a thin, low-confidence one. Sources
that returned no data are simply absent from the average — missing data lowers
overall confidence but never drags the score toward a false bearish/bullish read.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from .signal import Signal, clamp

# Relative importance of each directional source in the final verdict.
# Sources not yet implemented are listed so `coverage` reflects the full design.
SOURCE_WEIGHTS: dict[str, float] = {
    "insider": 0.35,
    "superinvestor": 0.30,
    "analysts": 0.20,
    "valuation": 0.15,
    "options": 0.10,
}


def _verdict(score: float) -> tuple[str, str]:
    """Map a composite score to (verdict label, recommended action)."""
    if score >= 40:
        return "Bullish", "BUY"
    if score >= 15:
        return "Lean bullish", "ACCUMULATE"
    if score > -15:
        return "Neutral", "HOLD"
    if score > -40:
        return "Lean bearish", "TRIM"
    return "Bearish", "AVOID"


def composite(signals: list[Signal]) -> dict[str, Any]:
    """Blend directional signals into a single verdict.

    Returns a dict: score (-100..100), confidence (0..1), verdict, action,
    n_sources, coverage, and a per-source breakdown list.
    """
    directional = [s for s in signals if s.directional and s.ok]
    if not directional:
        return {
            "score": 0.0,
            "confidence": 0.0,
            "verdict": "No data",
            "action": "INSUFFICIENT DATA",
            "n_sources": 0,
            "coverage": 0.0,
            "breakdown": [],
        }

    num = den = 0.0
    breakdown = []
    for s in directional:
        weight = SOURCE_WEIGHTS.get(s.source, 0.1) * s.confidence
        num += s.score * weight
        den += weight
        breakdown.append(
            {
                "source": s.source,
                "score": s.score,
                "confidence": s.confidence,
                "effective_weight": round(weight, 3),
                "summary": s.summary,
            }
        )

    score = clamp(num / den if den else 0.0, -100.0, 100.0)
    verdict, action = _verdict(score)

    # Confidence reflects both per-source quality and how many of the designed
    # sources actually reported (coverage).
    coverage = len(directional) / len(SOURCE_WEIGHTS)
    confidence = mean(s.confidence for s in directional) * (0.5 + 0.5 * coverage)

    return {
        "score": round(score, 1),
        "confidence": round(confidence, 2),
        "verdict": verdict,
        "action": action,
        "n_sources": len(directional),
        "coverage": round(coverage, 2),
        "breakdown": breakdown,
    }
