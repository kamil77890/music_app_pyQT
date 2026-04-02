"""
Globalne skróty (działają gdy okno nie ma fokusu / jest ukryte).
Wymaga pakietu pynput.

Domyślnie (działają w całym systemie — uważaj przy pisaniu w innych aplikacjach):
  *           play/pause
  .           wycisz / przywróć głośność
  ← / →       poprzedni / następny utwór

Uwaga: w pynput nie używaj słowa „space” — poprawny zapis to <space> (stare Ctrl+Shift+Space było źle parsowane).
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


def start_global_hotkeys(
    *,
    on_play_pause: Callable[[], None],
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

    # Pojedyncze klawisze — patrz docstring (parsowanie: GlobalHotKeys akceptuje m.in. ".", "*", "<left>", "<right>").
    mapping = {
        "*": lambda: _main(on_play_pause),
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

    log.info(
        "Global hotkeys: * play/pause, . mute, ←/→ prev/next"
    )
    return stop
