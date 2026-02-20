import pytest
import time
from unittest.mock import patch, MagicMock
from app.logic.handle_song import dowlaond_song


@pytest.mark.asyncio
@patch("app.logic.handle_song.sleep", return_value=None)
@patch("app.logic.handle_song.add_metadata", return_value=True)
@patch("app.logic.handle_song.os.path.exists", return_value=True)
@patch("app.logic.handle_song.YoutubeDL")
@patch("app.logic.handle_song.send_file")
async def test_dowlaond_song_only(
    mock_send_file,
    mock_yt_dlp,
    mock_exists,
    mock_add_metadata,
    mock_sleep,
):
    mock_yt_instance = MagicMock()
    mock_yt_dlp.return_value.__enter__.return_value = mock_yt_instance

    mock_response = MagicMock()
    mock_response.mimetype = 'audio/mpeg'
    mock_send_file.return_value = mock_response

    start_time = time.time()
    response = await dowlaond_song("abc123", 999, "mp3")
    duration = time.time() - start_time

    mock_yt_instance.download.assert_called_once_with(
        ["https://www.youtube.com/watch?v=abc123"])
    mock_add_metadata.assert_called_once()
    mock_send_file.assert_called_once()

    assert response.mimetype == 'audio/mpeg'
    assert duration < 0.5, f"Function took too long: {duration}s"
