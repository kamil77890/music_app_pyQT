from __future__ import annotations

from typing import Any

from app.logic.recommendations.user_taste_graph import (
    build_user_taste_graph,
    graph_hash,
)


def library_hash() -> str:
    return graph_hash()


def build_taste_profile(*, use_cache: bool = True) -> dict[str, Any]:
    return build_user_taste_graph(use_cache=use_cache)
