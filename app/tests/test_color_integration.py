from fastapi.testclient import TestClient
from app.app import app
from app.db.db_controller import DbController


client = TestClient(app)


def test_get_all_songs_includes_colors():
    """Test that /playlists/all-songs returns colors for each song"""
    response = client.get("/playlists/all-songs")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "songs" in data
    
    if data["songs"]:  # Only test if songs exist
        song = data["songs"][0]
        
        # Check new fields exist
        assert "dominantColor" in song
        assert "colorPalette" in song
        
        # Check format
        if song.get("dominantColor"):
            assert song["dominantColor"].startswith("#")
            assert len(song["dominantColor"]) == 7
        
        if song.get("colorPalette"):
            assert isinstance(song["colorPalette"], list)
            assert len(song["colorPalette"]) == 3
            for color in song["colorPalette"]:
                assert color.startswith("#")
                assert len(color) == 7


def test_api_songs_includes_color_fields():
    response = client.get("/api/songs")

    assert response.status_code == 200
    data = response.json()
    assert "songs" in data

    if data["songs"]:
        song = data["songs"][0]
        assert "dominantColor" in song
        assert "colorPalette" in song

        if song.get("dominantColor"):
            assert song["dominantColor"].startswith("#")
            assert len(song["dominantColor"]) == 7

        if song.get("colorPalette"):
            assert isinstance(song["colorPalette"], list)
            assert len(song["colorPalette"]) == 3
            for color in song["colorPalette"]:
                assert color.startswith("#")
                assert len(color) == 7


def test_database_stores_colors():
    """Test that songs table has color columns"""
    db = DbController()
    
    try:
        # Query should not raise error
        result = db.execute("PRAGMA table_info(songs);")
        column_names = [row[1] for row in result]
        
        assert "dominant_color" in column_names
        assert "color_palette" in column_names
    finally:
        db.close()
