from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_background_badge_uses_existing_youtube_tab_state():
    background_js = ROOT / "browser_extension" / "firefox" / "background.js"
    source = background_js.read_text(encoding="utf-8")

    assert "let currentYouTubeTab" in source
    assert "currentTabInfo.isYouTube" not in source
    assert "currentYouTubeTab.isYouTube" in source


def test_floating_button_click_does_not_stop_on_stale_offline_state():
    content_js = ROOT / "browser_extension" / "firefox" / "content" / "youtube.js"
    source = content_js.read_text(encoding="utf-8")
    handle_click = source.split("async function handleClick()", 1)[1].split("function getErrorMessage", 1)[0]
    download_index = handle_click.index("DOWNLOAD_CURRENT_VIDEO")

    assert "if (!state.backendOnline)" not in handle_click[:download_index]


def test_sidebar_renders_optional_classification_fields_safely():
    sidebar_js = ROOT / "browser_extension" / "firefox" / "sidebar" / "sidebar.js"
    source = sidebar_js.read_text(encoding="utf-8")

    assert 'song.primary_genre || song.genre || "Unknown Genre"' in source
    assert '(song.tags || [])' in source
    assert '(song.mood || [])' in source
    assert "renderDynamicFilters" in source
    assert "collectFilterValues" in source


def test_sidebar_html_has_dynamic_filter_container_only():
    sidebar_html = ROOT / "browser_extension" / "firefox" / "sidebar" / "sidebar.html"
    source = sidebar_html.read_text(encoding="utf-8")

    assert 'id="library-filters"' in source
    for label in ["Piano", "Nightcore", "Anime", "Electronic", "Rock", "Unknown"]:
        assert f'data-filter="{label}"' not in source
