"""
Unit tests for APIKeyManager — key rotation, exhaustion tracking, and reset.
"""
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _set_api_keys(monkeypatch):
    """Provide 3 test keys so we don't need real credentials."""
    monkeypatch.setenv("API_KEY", "key-AAA")
    monkeypatch.setenv("API_KEY_2", "key-BBB")
    monkeypatch.setenv("API_KEY_3", "key-CCC")
    monkeypatch.setenv("ACTIVE_API_KEY_INDEX", "0")


def _fresh_manager():
    """Import and instantiate a fresh APIKeyManager (bypasses module-level singleton)."""
    from app.utils.api_key_manager import APIKeyManager
    return APIKeyManager()


class TestAPIKeyManager:

    def test_loads_all_configured_keys(self):
        mgr = _fresh_manager()
        assert mgr.keys == ["key-AAA", "key-BBB", "key-CCC"]
        assert mgr.current_index == 0

    def test_get_current_key(self):
        mgr = _fresh_manager()
        assert mgr.get_current_key() == "key-AAA"

    def test_switch_rotates_to_next(self):
        mgr = _fresh_manager()
        new_key = mgr.switch_to_next_key()
        assert new_key == "key-BBB"
        assert mgr.current_index == 1

    def test_switch_skips_exhausted(self):
        mgr = _fresh_manager()
        mgr._exhausted.add(1)  # mark key-BBB as spent
        new_key = mgr.switch_to_next_key()
        assert new_key == "key-CCC"
        assert mgr.current_index == 2

    def test_switch_raises_when_all_exhausted(self):
        mgr = _fresh_manager()
        mgr._exhausted = {0, 1, 2}
        with pytest.raises(RuntimeError, match="All YouTube API keys exhausted"):
            mgr.switch_to_next_key()

    def test_has_available_keys(self):
        mgr = _fresh_manager()
        assert mgr.has_available_keys() is True
        mgr._exhausted = {0, 1, 2}
        assert mgr.has_available_keys() is False

    def test_is_quota_exhausted_property(self):
        mgr = _fresh_manager()
        assert mgr.is_quota_exhausted is False
        mgr._exhausted = {0}
        assert mgr.is_quota_exhausted is False
        mgr._exhausted = {0, 1, 2}
        assert mgr.is_quota_exhausted is True

    def test_reset_exhausted_clears_state(self):
        mgr = _fresh_manager()
        mgr._exhausted = {0, 1, 2}
        assert mgr.is_quota_exhausted is True
        mgr.reset_exhausted()
        assert mgr.is_quota_exhausted is False
        assert mgr.has_available_keys() is True

    def test_get_remaining_keys_count(self):
        mgr = _fresh_manager()
        assert mgr.get_remaining_keys_count() == 3
        mgr.mark_exhausted()
        assert mgr.get_remaining_keys_count() == 2

    def test_mark_exhausted_adds_current(self):
        mgr = _fresh_manager()
        mgr.mark_exhausted()
        assert 0 in mgr._exhausted

    def test_full_rotation_cycle(self):
        mgr = _fresh_manager()
        # exhaust key 0 → switch to 1
        k1 = mgr.switch_to_next_key()
        assert k1 == "key-BBB"
        # exhaust key 1 → switch to 2
        k2 = mgr.switch_to_next_key()
        assert k2 == "key-CCC"
        # exhaust key 2 → no more
        with pytest.raises(RuntimeError):
            mgr.switch_to_next_key()
        assert mgr.is_quota_exhausted

    def test_legacy_has_more_keys_compat(self):
        mgr = _fresh_manager()
        assert mgr.has_more_keys() is True


class TestMissingKeys:

    def test_no_keys_raises(self, monkeypatch):
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("API_KEY_2", raising=False)
        monkeypatch.delenv("API_KEY_3", raising=False)
        monkeypatch.delenv("API_KEY_4", raising=False)
        with pytest.raises(RuntimeError, match="No YouTube API keys configured"):
            _fresh_manager()
