"""
Test the new tag-based recommendation algorithm
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.desktop.utils.recommender import (
    _parse_genres, 
    _extract_decade, 
    _clean_artist_name,
    _should_skip_artist,
    RecommenderThread
)


def test_parse_genres():
    """Test genre parsing"""
    # Single genre
    assert _parse_genres("Rock") == ["Rock"]
    
    # Multiple genres with commas
    assert _parse_genres("Rock, Pop, Alternative") == ["Rock", "Pop", "Alternative"]
    
    # Genres with semicolons
    assert _parse_genres("Electronic; Dance; House") == ["Electronic", "Dance", "House"]
    
    # Genres with slashes
    assert _parse_genres("Rock/Pop/Alternative") == ["Rock", "Pop", "Alternative"]
    
    # Skip unknown genres
    assert _parse_genres("Unknown, Rock, ") == ["Rock"]
    assert _parse_genres("") == []
    assert _parse_genres("Unknown") == []
    
    # Handle "Rock & Roll" as single genre
    assert _parse_genres("Rock & Roll") == ["Rock & Roll"]
    
    print("✓ test_parse_genres passed")


def test_extract_decade():
    """Test decade extraction"""
    # Simple year
    assert _extract_decade("1995") == "1990s"
    assert _extract_decade("2010") == "2010s"
    
    # Date format
    assert _extract_decade("2010-05-20") == "2010s"
    
    # Year in parentheses
    assert _extract_decade("(1985)") == "1980s"
    
    # Invalid years
    assert _extract_decade("") is None
    assert _extract_decade("unknown") is None
    assert _extract_decade("1800") is None  # Too old
    assert _extract_decade("2050") is None  # Too new
    
    print("✓ test_extract_decade passed")


def test_clean_artist_name():
    """Test artist name cleaning"""
    # Remove parentheticals
    assert _clean_artist_name("The Beatles (Remastered)") == "The Beatles"
    assert _clean_artist_name("Artist [Live Version]") == "Artist"
    
    # Remove feat/ft/with
    assert _clean_artist_name("Artist Name feat. Guest") == "Artist Name"
    assert _clean_artist_name("Artist ft. Guest") == "Artist"
    assert _clean_artist_name("Artist with Guest") == "Artist"
    
    # Empty names
    assert _clean_artist_name("") == ""
    assert _clean_artist_name(None) == ""
    
    print("✓ test_clean_artist_name passed")


def test_should_skip_artist():
    """Test artist filtering"""
    # Should skip
    assert _should_skip_artist("") == True
    assert _should_skip_artist("Unknown") == True
    assert _should_skip_artist("Unknown Artist") == True
    assert _should_skip_artist("Various Artists") == True
    assert _should_skip_artist("Various") == True
    assert _should_skip_artist("VA-001") == True
    assert _should_skip_artist("Compilation") == True
    
    # Should keep
    assert _should_skip_artist("The Beatles") == False
    assert _should_skip_artist("Daft Punk") == False
    assert _should_skip_artist("Pink Floyd") == False
    
    print("✓ test_should_skip_artist passed")


def test_analyze_tags():
    """Test tag analysis with mock data"""
    # Create mock songs
    mock_songs = [
        {"title": "Song 1", "artist": "Daft Punk", "album": "Random Access Memories", "genre": "Electronic, Dance", "year": "2013", "decade": "2010s"},
        {"title": "Song 2", "artist": "Daft Punk", "album": "Random Access Memories", "genre": "Electronic", "year": "2013", "decade": "2010s"},
        {"title": "Song 3", "artist": "The Beatles", "album": "Abbey Road", "genre": "Rock, Pop", "year": "1969", "decade": "1960s"},
        {"title": "Song 4", "artist": "The Beatles", "album": "Abbey Road", "genre": "Rock", "year": "1969", "decade": "1960s"},
        {"title": "Song 5", "artist": "The Beatles", "album": "Let It Be", "genre": "Rock", "year": "1970", "decade": "1970s"},
        {"title": "Song 6", "artist": "Miles Davis", "album": "Kind of Blue", "genre": "Jazz", "year": "1959", "decade": "1950s"},
    ]
    
    thread = RecommenderThread("/tmp")
    tag_analysis = thread._analyze_tags(mock_songs)
    
    # Check structure
    assert "artists" in tag_analysis
    assert "genres" in tag_analysis
    assert "decades" in tag_analysis
    assert "albums" in tag_analysis
    assert "top_artists" in tag_analysis
    assert "top_genres" in tag_analysis
    assert "top_decades" in tag_analysis
    assert "top_albums" in tag_analysis
    assert "artist_genres" in tag_analysis
    assert "total_songs" in tag_analysis
    
    # Check counts
    assert tag_analysis["total_songs"] == 6
    assert tag_analysis["artists"]["Daft Punk"] == 2
    assert tag_analysis["artists"]["The Beatles"] == 3
    assert tag_analysis["artists"]["Miles Davis"] == 1
    
    # Check genres (Electronic appears 3 times: 2 from Daft Punk + 1 Dance)
    assert tag_analysis["genres"]["Electronic"] >= 2
    assert tag_analysis["genres"]["Rock"] >= 3
    
    # Check decades
    assert tag_analysis["decades"]["2010s"] == 2
    assert tag_analysis["decades"]["1960s"] == 2
    
    # Check top lists
    assert tag_analysis["top_artists"][0] == "The Beatles"  # Most songs
    assert tag_analysis["top_genres"][0] == "Rock"  # Most songs
    
    print("✓ test_analyze_tags passed")


def test_generate_smart_queries():
    """Test smart query generation"""
    # Create mock tag analysis
    tag_analysis = {
        "artists": {"Daft Punk": 10, "The Beatles": 8, "Pink Floyd": 6},
        "genres": {"Electronic": 15, "Rock": 12, "Jazz": 5},
        "decades": {"2010s": 10, "1970s": 8, "1960s": 7},
        "albums": {"Random Access Memories": 10, "Abbey Road": 8},
        "top_artists": ["Daft Punk", "The Beatles", "Pink Floyd"],
        "top_genres": ["Electronic", "Rock", "Jazz"],
        "top_decades": ["2010s", "1970s", "1960s"],
        "top_albums": ["Random Access Memories", "Abbey Road"],
        "artist_genres": {
            "Daft Punk": ["Electronic", "Dance"],
            "The Beatles": ["Rock", "Pop"],
        },
        "total_songs": 25,
    }
    
    thread = RecommenderThread("/tmp", max_results=12)
    queries = thread._generate_smart_queries(tag_analysis)
    
    # Check we get queries
    assert len(queries) > 0
    assert len(queries) <= 12
    
    # Check query structure
    for query in queries:
        assert isinstance(query, str)
        assert len(query) > 5
        assert len(query) < 100
    
    # Check we have different types of queries
    has_artist_query = any("discography" in q or "similar artists" in q for q in queries)
    has_genre_query = any("best" in q and "music" in q for q in queries)
    has_decade_query = any("hits" in q or "essential" in q for q in queries)
    
    assert has_artist_query, "Should have artist-related queries"
    assert has_genre_query, "Should have genre-related queries"
    assert has_decade_query, "Should have decade-related queries"
    
    # Check no duplicates
    assert len(queries) == len(set(queries)), "Should have no duplicate queries"
    
    print(f"✓ test_generate_smart_queries passed (generated {len(queries)} queries)")
    print(f"  Sample queries: {queries[:5]}")


def test_full_thread_run():
    """Test full thread run with temporary directory"""
    import tempfile
    import shutil
    
    # Create temp directory with mock files
    temp_dir = tempfile.mkdtemp()
    try:
        # Create some mock audio files (empty files with right extensions)
        for i in range(5):
            with open(os.path.join(temp_dir, f"song{i}.mp3"), 'w') as f:
                f.write("")  # Empty file
        
        thread = RecommenderThread(temp_dir, max_results=10)
        queries = []
        song_count = []
        
        def on_queries_ready(q, count):
            queries.extend(q)
            song_count.append(count)
        
        thread.recommendations_ready.connect(on_queries_ready)
        thread.run()
        
        # Should complete without errors
        assert len(song_count) == 1
        assert song_count[0] == 5  # 5 files
        
        print(f"✓ test_full_thread_run passed (found {song_count[0]} songs, generated {len(queries)} queries)")
        
    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("Running tag-based recommendation algorithm tests...\n")
    
    test_parse_genres()
    test_extract_decade()
    test_clean_artist_name()
    test_should_skip_artist()
    test_analyze_tags()
    test_generate_smart_queries()
    test_full_thread_run()
    
    print("\n✅ All tests passed!")
