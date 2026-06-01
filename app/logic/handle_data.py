
from ..db.db_controller import DbController
from .color_extractor import extract_color_palette

from flask import jsonify
import json


def handle_data(new_data):
    try:
        title = new_data.get("title")
        videoId = new_data.get("videoId")
        liked = new_data.get("liked", False)
        src = new_data.get("src", "")
        duration_minutes = new_data.get("duration_minutes", "Unknown")
        duration_seconds = new_data.get("duration_seconds", "Unknown")
        cover = new_data.get("cover", "")

        user_id = new_data.get("user_id")

        db = DbController()

        # Extract color palette from cover image
        color_data = extract_color_palette(cover) if cover else {"dominantColor": None, "colorPalette": None}
        color_palette_json = json.dumps(color_data.get("colorPalette")) if color_data.get("colorPalette") else None

        song_columns = ["user_id", "title", "videoId", "liked",
                        "src", "duration_minutes", "duration_seconds", "dominant_color", "color_palette"]
        song_values = [user_id, title, videoId, liked,
                       src, duration_minutes, duration_seconds, color_data.get("dominantColor"), color_palette_json]

        db.insert("songs", song_columns, song_values)
        db.commit()

        return jsonify({"message": "Song added successfully!", "data": new_data}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500
