from __future__ import annotations

import os
import threading
from contextvars import ContextVar

_max_calls = int(os.environ.get("RECOMMENDATION_MAX_YT_CALLS", "25"))
_used: ContextVar[int] = ContextVar("yt_quota_used", default=0)
_lock = threading.Lock()


def reset() -> None:
    _used.set(0)


def remaining() -> int:
    return max(0, _max_calls - _used.get())


def can_call(n: int = 1) -> bool:
    return _used.get() + n <= _max_calls


def record(n: int = 1) -> None:
    with _lock:
        _used.set(_used.get() + n)


def max_calls() -> int:
    return _max_calls


def used() -> int:
    return _used.get()
