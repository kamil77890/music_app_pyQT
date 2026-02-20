import os

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


class Parameters:
    def __init__(self):
        self.download_dir = os.environ.get(
            'FILEPATH', os.path.join(os.getcwd(), 'app', 'songs'))
        self.json_file = os.environ.get(
            'JSONFILE', os.path.join(self.download_dir, 'songs.json'))
        self.subtitles_files = os.environ.get(
            'SUBTITLES_FILES', os.path.join(os.getcwd(), 'app', 'songs', 'subtitles'))

    @staticmethod
    def get_download_dir():
        return os.environ.get('FILEPATH', os.path.join(os.getcwd(), 'app', 'songs'))

    @staticmethod
    def get_subtitles_dir():
        return os.environ.get('SUBTITLES_FILES', os.path.join(os.getcwd(), 'app', 'songs', 'subtitles'))

    @staticmethod
    def get_json_file():
        return os.environ.get('JSONFILE', os.path.join(Parameters.get_download_dir(), 'songs.json'))

    @staticmethod
    def get_api_keys():
        return [
            os.environ.get(
                'API_KEY', 'AIzaSyD-GhNz8WyvqiuDgtj7Qt_r-GsnGR1mN5Q'),
            os.environ.get(
                'API_KEY_2', 'AIzaSyAzy1Qf_lhA4snxKLL7FP6EmNGk7euZRIE')
        ]

    @staticmethod
    def get_active_api_key_index():
        return int(os.environ.get('ACTIVE_API_KEY_INDEX', '0'))

    @staticmethod
    def set_active_api_key_index(index: int):
        os.environ['ACTIVE_API_KEY_INDEX'] = str(index)

    @staticmethod
    def get_active_api_key():
        keys = Parameters.get_api_keys()
        active_index = Parameters.get_active_api_key_index()
        return keys[active_index]

    @staticmethod
    def switch_to_next_api_key():
        keys = Parameters.get_api_keys()
        current_index = Parameters.get_active_api_key_index()
        next_index = (current_index + 1) % len(keys)
        Parameters.set_active_api_key_index(next_index)
        return next_index

    @staticmethod
    def get_yt_search_url():
        return YT_SEARCH_URL

    @staticmethod
    def get_yt_playlist_items_url():
        return YT_PLAYLIST_ITEMS_URL
