import os
from flask import Flask, jsonify
from flask_cors import CORS
import json
from ..db.db_controller import DbController


def handle_like(video_id: str, liked: bool) -> None:
    try:

        DbController().update_like(video_id, liked)

        return ("Song liked updated"), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
