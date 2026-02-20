import sqlite3


class DbController:
    def __init__(self):
        self.conn = sqlite3.connect("database.db")
        self.cursor = self.conn.cursor()
        self.create_all_tables()

    def create_table(self, table_name: str, columns: str) -> None:
        self.cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")

    def execute(self, query: str, params=None) -> list:
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self.cursor.fetchall()

    def insert(self, table_name: str, columns: list, values: list) -> None:
        cols = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(values))
        query = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
        self.cursor.execute(query, values)

    def select(self, table_name: str, columns: str, condition=None) -> list:
        if condition:
            self.cursor.execute(
                f"SELECT {columns} FROM {table_name} WHERE {condition}")
        else:
            self.cursor.execute(f"SELECT {columns} FROM {table_name}")
        return self.cursor.fetchall()

    def update(self, table_name: str, columns: str, condition: str) -> None:
        self.cursor.execute(
            f"UPDATE {table_name} SET {columns} WHERE {condition}")

    def create_all_tables(self):
        self.create_table(
            "users",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL
            """
        )
        self.create_table(
            "songs",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT,
            album TEXT,
            videoId TEXT UNIQUE,
            liked BOOLEAN DEFAULT 0
            """
        )
        self.create_table(
            "user_songs",
            """
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                song_id INTEGER,
                liked BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(song_id) REFERENCES songs(id)""")

    def get_all_songs(self) -> list:
        return self.cursor.execute("SELECT * FROM songs").fetchall()

    def update_like(self, video_id: int, liked: bool) -> None:
        self.cursor.execute(
            f"UPDATE songs SET liked = {liked} WHERE videoId = '{video_id}'")

    def get_last_song_id(self) -> int:
        return self.cursor.execute("SELECT MAX(id) FROM songs").fetchone()[0]

    def delete(self, table_name: str, condition: str) -> None:
        self.cursor.execute(f"DELETE FROM {table_name} WHERE {condition}")

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()
