import numpy as np
import librosa
from librosa.feature.rhythm import tempo
from pydub import AudioSegment


def process_tempo_adjust(song_path: str):
    y, sr = librosa.load(song_path, sr=None)
    global_tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    local_tempi = tempo(onset_envelope=onset_env, sr=sr, aggregate=None)
    local_tempi = np.interp(
        np.linspace(0, len(local_tempi), num=20),
        np.arange(len(local_tempi)),
        local_tempi
    )

    audio = AudioSegment.from_file(song_path)
    win_ms = max(500, int(len(audio) / len(local_tempi))) 

    out = AudioSegment.empty()
    for i, bpm in enumerate(local_tempi):
        bpm = float(bpm)  # zapobiega błędom formatowania
        start = i * win_ms
        end = min((i + 1) * win_ms, len(audio))

        if start >= len(audio):
            break

        segment = audio[start:end]

        if len(segment) < 150:
            continue

        if bpm < global_tempo * 0.9:
            segment += 1
            print(
                f"[{i}] Wolniejsze tempo: {bpm:.2f} BPM < {global_tempo:.2f} → +1dB")
        elif bpm > global_tempo * 1.05:
            segment += 10
            print(f"[{i}] Szybsze tempo: {bpm:.2f} BPM > {global_tempo:.2f} → +10dB")

        out += segment

    out.export(song_path, format="mp3")
    return global_tempo, local_tempi
