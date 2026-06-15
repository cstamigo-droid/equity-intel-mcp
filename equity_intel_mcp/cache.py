"""Tiny thread-safe TTL cache.

External data sources (Yahoo, SEC, Dataroma) are slow and rate-limited. A short
in-process cache means an agent that calls several tools on the same ticker in
one turn — or the composite `analyze_ticker` that fans out to every source —
doesn't refetch the same data seconds apart. TTLs are per-source (a quote ages
in 60s; a 13F holding list can live for an hour).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def get_or_fetch(key: str, ttl_s: float, fetch: Callable[[], Any]) -> Any:
    """Return a cached value if fresh, otherwise call `fetch()` and store it.

    `fetch` runs OUTSIDE the lock so a slow network call never blocks other
    cache readers. A rare duplicate fetch under concurrency is acceptable.
    """
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and (now - hit[0]) < ttl_s:
            return hit[1]

    value = fetch()

    with _lock:
        _store[key] = (time.monotonic(), value)
    return value


def clear() -> None:
    """Drop all cached entries (used by tests)."""
    with _lock:
        _store.clear()
