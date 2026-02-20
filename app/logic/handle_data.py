
from ..db.db_controller import DbController

from flask import jsonify


def handle_data(new_data):
    try:
        title = new_data.get("title")
        videoId = new_data.get("videoId")
        liked = new_data.get("liked", False)
        src = new_data.get("src", "")
        duration_minutes = new_data.get("duration_minutes", "Unknown")
        duration_seconds = new_data.get("duration_seconds", "Unknown")

        user_id = new_data.get("user_id")

        db = DbController()

        song_columns = ["user_id", "title", "videoId", "liked",
                        "src", "duration_minutes", "duration_seconds"]
        song_values = [user_id, title, videoId, liked,
                       src, duration_minutes, duration_seconds]

        db.insert("songs", song_columns, song_values)
        db.commit()

        return jsonify({"message": "Song added successfully!", "data": new_data}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500
