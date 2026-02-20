
import os
from flask import Response, jsonify
from urllib.parse import quote


def send_file_response(file_path: str):
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    with open(file_path, "rb") as f:
        data = f.read()

    mimetype = (
        "application/zip"
        if file_path.endswith(".zip")
        else "audio/mpeg"
    )

    response = Response(data, mimetype=mimetype)
    filename = os.path.basename(file_path)

    try:
        filename.encode("latin-1")
        disposition = f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"

    response.headers["Content-Disposition"] = disposition
    response.headers["Content-Length"] = str(len(data))
    return response
