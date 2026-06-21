def test_jellyfin_sync_disabled_without_api_key(monkeypatch):
    from app.logic.jellyfin_sync import fetch_jellyfin_music_items

    monkeypatch.setenv("JELLYFIN_API_KEY", "")

    result = fetch_jellyfin_music_items()

    assert result["enabled"] is False
    assert result["items"] == []
    assert "JELLYFIN_API_KEY" in result["message"]
