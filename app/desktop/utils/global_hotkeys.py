"""
Globalne skróty (działają gdy okno nie ma fokusu / jest ukryte).
Wymaga pakietu pynput.

Domyślnie (działają w całym systemie):
  *           stop
  |           następny utwór
  Ctrl+Alt+M  pokaż/ukryj okno aplikacji
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


def start_global_hotkeys(
    *,
    on_mute: Callable[[], None] = None,
    on_show_hide: Callable[[], None] = None,
    on_play_pause: Callable[[], None],
    on_prev: Callable[[], None] = None,
    on_next: Callable[[], None] = None,
) -> Callable[[], None]:
    """
    Uruchamia nasłuch w tle. Zwraca funkcję stop() do wywołania przy zamykaniu aplikacji.
    """
    try:
        from pynput.keyboard import GlobalHotKeys, Key, KeyCode, Listener
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

    # Ctrl+Alt+M — osobny listener bo GlobalHotKeys nie obsługuje modyfikatorów
    _show_hide_listener = None
    if on_show_hide:
        _state = {"ctrl": False, "alt": False}

        def _on_press(key):
            try:
                if key in (Key.ctrl_l, Key.ctrl_r):
                    _state["ctrl"] = True
                elif key in (Key.alt_l, Key.alt_r):
                    _state["alt"] = True
                elif _state["ctrl"] and _state["alt"]:
                    if hasattr(key, "char") and key.char == "m":
                        _main(on_show_hide)
                    elif key == KeyCode.from_char("m"):
                        _main(on_show_hide)
            except Exception:
                pass

        def _on_release(key):
            try:
                if key in (Key.ctrl_l, Key.ctrl_r):
                    _state["ctrl"] = False
                elif key in (Key.alt_l, Key.alt_r):
                    _state["alt"] = False
            except Exception:
                pass

        _show_hide_listener = Listener(on_press=_on_press, on_release=_on_release)
        _show_hide_listener.start()

    def stop() -> None:
        try:
            hotkeys.stop()
        except Exception:
            pass
        if _show_hide_listener:
            try:
                _show_hide_listener.stop()
            except Exception:
                pass

    log.info("Global hotkeys: * stop, | next, Ctrl+Alt+M show/hide")
    return stop
