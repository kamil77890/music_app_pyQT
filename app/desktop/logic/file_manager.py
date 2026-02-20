import os
import shutil
from typing import List

class FileManager:
    """Manages file operations"""
    
    @staticmethod
    def ensure_directory(path: str):
        """Ensure directory exists"""
        os.makedirs(path, exist_ok=True)
    
    @staticmethod
    def safe_move(src: str, dst: str):
        """Safely move file"""
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            return True
        except Exception as e:
            print(f"Error moving file: {e}")
            return False
    
    @staticmethod
    def safe_copy(src: str, dst: str):
        """Safely copy file"""
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.copy2(src, dst)
            return True
        except Exception as e:
            print(f"Error copying file: {e}")
            return False
    
    @staticmethod
    def get_file_size(path: str) -> int:
        """Get file size in bytes"""
        try:
            return os.path.getsize(path) if os.path.exists(path) else 0
        except Exception:
            return 0