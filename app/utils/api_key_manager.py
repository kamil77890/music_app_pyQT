import os
from app.config.stałe import Parameters


class APIKeyManager:
    def __init__(self):
        self.keys = Parameters.get_api_keys()
        self.current_index = Parameters.get_active_api_key_index()

    def get_current_key(self):
        """Get the currently active API key"""
        print(self.keys[self.current_index])
        return self.keys[self.current_index]

    def switch_to_next_key(self):
        """Switch to the next available API key"""
        if not self.has_more_keys():
            raise Exception("No more API keys available")

        self.current_index = (self.current_index + 1) % len(self.keys)
        Parameters.set_active_api_key_index(self.current_index)
        print(f"🔄 Switched to API key #{self.current_index + 1}")
        return self.get_current_key()

    def has_more_keys(self):
        """Check if there are more API keys available"""
        return len(self.keys) > 1

    def get_remaining_keys_count(self):
        """Get count of remaining unused keys"""
        return len(self.keys) - 1


api_key_manager = APIKeyManager()
