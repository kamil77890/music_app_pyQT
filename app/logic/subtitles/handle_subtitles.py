
import os
import srt
from mutagen.id3 import ID3, SYLT, Encoding


def parse_srt_to_sync(srt_path):
    with open(srt_path, 'r', encoding='utf-8') as f:
        subs = list(srt.parse(f.read()))
    return [(sub.content.strip(), int(sub.start.total_seconds() * 1000)) for sub in subs]


def embed_sylt(mp3_path, sync_list, lang="eng"):
    tags = ID3(mp3_path)
    tags.setall("SYLT", [SYLT(encoding=Encoding.UTF8,
                              lang=lang,
                              format=2,
                              type=1,
                              text=sync_list)])
    tags.save(v2_version=3)


def convert_srt_to_txt(srt_path: str, output_path: str = None) -> str:
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"Plik nie istnieje: {srt_path}")

    base_dir = os.path.dirname(srt_path)
    lyrics_dir = os.path.join(base_dir, "lyrics")
    os.makedirs(lyrics_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(srt_path))[0]

    if output_path is None:
        output_path = os.path.join(lyrics_dir, base_name + ".txt")

    with open(srt_path, 'r', encoding='utf-8') as f:
        subtitles = list(srt.parse(f.read()))

    text_lines = [sub.content.strip()
                  for sub in subtitles if sub.content.strip()]
    full_text = "\n".join(text_lines)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_text)

    os.remove(srt_path)

    return output_path
