"""
Globalne skróty (działają gdy okno nie ma fokusu / jest ukryte).
Wymaga pakietu pynput.

Domyślnie (działają w całym systemie):
  *           stop
  |           następny utwór
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


def start_global_hotkeys(
    *,
    on_play_pause: Callable[[], None],
    on_prev: Callable[[], None] = None,
    on_next: Callable[[], None] = None,
    on_mute: Callable[[], None] = None,
) -> Callable[[], None]:
    """
    Uruchamia nasłuch w tle. Zwraca funkcję stop() do wywołania przy zamykaniu aplikacji.
    """
    try:
        from pynput.keyboard import GlobalHotKeys
    except ImportError:
        log.info(
            "Global hotkeys: install pynput (uv sync) for shortcuts when app is in background."
        )
        return lambda: None

    try:
        from PyQt5.QtCore import QTimer
    except ImportError:
        return lambda: None

    def _main(fn: Callable[[], None]) -> None:
        QTimer.singleShot(0, fn)

    # Pojedyncze klawisze — tylko * (stop) i | (next)
    mapping = {
        "*": lambda: _main(on_play_pause),
        "|": lambda: _main(on_next),
    }

    try:
        hotkeys = GlobalHotKeys(mapping)
        hotkeys.start()
    except Exception as exc:
        log.warning("Global hotkeys could not start: %s", exc)
        return lambda: None

    def stop() -> None:
        try:
            hotkeys.stop()
        except Exception:
            pass

    log.info("Global hotkeys: * stop, | next")
    return stop
