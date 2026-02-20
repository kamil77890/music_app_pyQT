import os

def cleanup_temp_files(
    base_path: str,
    keep_exts=('mp3', 'srt', 'txt')
) -> None:
    directory = os.path.dirname(base_path)
    base_name = os.path.basename(base_path)

    if not os.path.isdir(directory):
        return

    for fname in os.listdir(directory):
        if not fname.startswith(base_name):
            continue

        ext = fname.split('.')[-1].lower()
        if ext not in keep_exts:
            try:
                os.remove(os.path.join(directory, fname))
            except Exception as e:
                print(f"Cleanup failed for {fname}: {e}")
