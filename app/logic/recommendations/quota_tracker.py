from __future__ import annotations

import os
import threading

# Budget is expressed in REAL YouTube Data API units per recommendation request:
#   search.list   = 100 units
#   videos.list / channels.list / playlistItems.list = 1 unit
# Default keeps a single request well under the 10k daily quota.
_max_units = int(os.environ.get("RECOMMENDATION_MAX_YT_UNITS", "2500"))

SEARCH_UNITS = 100
CHEAP_UNITS = 1

_used = 0
_lock = threading.Lock()


def reset() -> None:
    global _used
    with _lock:
        _used = 0


def remaining() -> int:
    with _lock:
        return max(0, _max_units - _used)


def can_call(units: int = SEARCH_UNITS) -> bool:
    """True if `units` more units fit in the budget.

    NOTE: callers historically pass small integers (1, 2, 3) meaning "number of
    searches". Those are scaled to real search units so existing gates keep
    working against the unit budget.
    """
    scaled = units * SEARCH_UNITS if units < SEARCH_UNITS else units
    with _lock:
        return _used + scaled <= _max_units


def can_spend_units(units: int) -> bool:
    with _lock:
        return _used + units <= _max_units


def record(searches: int = 1) -> None:
    """Record `searches` search.list calls (each = 100 units)."""
    global _used
    with _lock:
        _used += searches * SEARCH_UNITS


def record_units(units: int) -> None:
    global _used
    with _lock:
        _used += units


def max_calls() -> int:
    return _max_units


def used() -> int:
    with _lock:
        return _used
