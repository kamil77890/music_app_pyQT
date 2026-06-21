import pytest


@pytest.fixture(autouse=True)
def disable_local_ai_by_default(monkeypatch):
    """Keep unit tests fast and deterministic unless a test opts into local AI."""
    monkeypatch.setenv("LOCAL_AI_METADATA_ENABLED", "false")
    monkeypatch.setenv("LOCAL_AI_MODEL", "")
