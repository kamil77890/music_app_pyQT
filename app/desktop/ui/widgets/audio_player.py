import os
import random
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from app.desktop.assets import assets


class AudioPlayerWidget(QFrame):
    
    playback_state_changed = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_song_path = None
        self.current_playlist = [] 
        self.shuffle_mode = False
        self.repeat_mode = 0  
        self.previous_volume = 70  
        self.is_muted = False
        self.playlist = []  
        self.current_index = -1
        self.random_history = []  # Track recently played random songs
        
        self.setup_ui()
        self.setup_player()
        
    def setup_ui(self):
        """Setup player UI"""
        self.setFixedHeight(140)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)
        
        # Song info
        info_layout = QHBoxLayout()
        
        # Album art placeholder
        self.album_art = QLabel()
        self.album_art.setFixedSize(70, 70)
        self.album_art.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(139, 92, 246, 0.3),
                    stop:1 rgba(6, 182, 212, 0.3));
                border: 2px solid rgba(138, 43, 226, 0.4);
                border-radius: 12px;
            }
        """)
        info_layout.addWidget(self.album_art)
        
        # Song details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)
        
        self.song_title = QLabel("No song playing")
        self.song_title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        self.song_artist = QLabel("")
        self.song_artist.setStyleSheet("""
            QLabel {
                color: #8a9bb0;
                font-size: 13px;
            }
        """)
        
        details_layout.addWidget(self.song_title)
        details_layout.addWidget(self.song_artist)
        details_layout.addStretch()
        info_layout.addLayout(details_layout, 1)
        layout.addLayout(info_layout)
        
        # Progress bar
        progress_layout = QHBoxLayout()
        
        self.time_current = QLabel("0:00")
        self.time_current.setFixedWidth(45)
        self.time_current.setAlignment(Qt.AlignCenter)
        self.time_current.setStyleSheet("""
            QLabel {
                color: #b8c5d6;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(1000)
        self.progress_slider.sliderMoved.connect(self.seek_position)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.12);
                height: 5px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #c4b5fd);
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: none;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8b5cf6, stop:1 #06b6d4);
                border-radius: 2px;
            }
        """)
        
        self.time_total = QLabel("0:00")
        self.time_total.setFixedWidth(45)
        self.time_total.setAlignment(Qt.AlignCenter)
        self.time_total.setStyleSheet("""
            QLabel {
                color: #b8c5d6;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        
        progress_layout.addWidget(self.time_current)
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.time_total)
        layout.addLayout(progress_layout)
        
        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)
        
        # Load icons
        shuffle_icon = "🔀"
        repeat_icon = "🔁"
        prev_icon = "⏮"
        play_icon = "▶"
        next_icon = "⏭"
        volume_icon = "🔊"
        
        # Shuffle Button
        self.shuffle_btn = QPushButton(shuffle_icon)
        self.shuffle_btn.setFixedSize(36, 36)
        self.shuffle_btn.setProperty("player", True)
        self.shuffle_btn.setToolTip("Toggle Shuffle")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        
        # Repeat Button
        self.repeat_btn = QPushButton(repeat_icon)
        self.repeat_btn.setFixedSize(36, 36)
        self.repeat_btn.setProperty("player", True)
        self.repeat_btn.setToolTip("Toggle Repeat")
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        
        # Previous button
        self.prev_btn = QPushButton(prev_icon)
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.setProperty("player", True)
        self.prev_btn.clicked.connect(self.previous_song)
        
        # Play/pause button
        self.play_btn = QPushButton(play_icon)
        self.play_btn.setFixedSize(56, 56)
        self.play_btn.setProperty("player", "play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8b5cf6, stop:1 #06b6d4);
                border: none;
                border-radius: 28px;
                color: white;
                font-size: 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a78bfa, stop:1 #22d3ee);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:1 #0891b2);
            }
        """)
        
        # Next button
        self.next_btn = QPushButton(next_icon)
        self.next_btn.setFixedSize(40, 40)
        self.next_btn.setProperty("player", True)
        self.next_btn.clicked.connect(self.next_song)
        
        # Volume
        self.volume_btn = QPushButton(volume_icon)
        self.volume_btn.setFixedSize(36, 36)
        self.volume_btn.setProperty("player", True)
        self.volume_btn.clicked.connect(self.toggle_mute)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.12);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #8b5cf6;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8b5cf6, stop:1 #06b6d4);
                border-radius: 2px;
            }
        """)
        
        controls_layout.addStretch()
        controls_layout.addWidget(self.shuffle_btn)
        controls_layout.addWidget(self.repeat_btn)
        controls_layout.addWidget(self.prev_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.volume_btn)
        controls_layout.addWidget(self.volume_slider)

        layout.addLayout(controls_layout)
        
        self.update_shuffle_button_style()
        self.update_repeat_button_style()
    
    def setup_player(self):
        self.player = QMediaPlayer()
        self.player.setVolume(70)
        
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.stateChanged.connect(self.update_play_button)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress)
        self.update_timer.start(100)
    
    def seek_position(self, value):
        if self.player.duration() > 0:
            position = int((value / 1000) * self.player.duration())
            self.player.setPosition(position)
    
    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        self.update_shuffle_button_style()
        print(f"[DEBUG] Shuffle mode: {'ON' if self.shuffle_mode else 'OFF'}")
    
    def update_shuffle_button_style(self):
        if self.shuffle_mode:
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8b5cf6, stop:1 #06b6d4);
                    color: #ffffff;
                    border: none;
                    border-radius: 18px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #a78bfa, stop:1 #22d3ee);
                }
            """)
        else:
            self.shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    color: #b8c5d6;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 18px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                    border: 1px solid rgba(138, 43, 226, 0.3);
                }
            """)
    
    def toggle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        self.update_repeat_button_style()
        print(f"[DEBUG] Repeat mode: {self.repeat_mode}")
    
    def update_repeat_button_style(self):
        if self.repeat_mode == 0: 
            self.repeat_btn.setText("🔁")
            self.repeat_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    color: #b8c5d6;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 18px;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                    border: 1px solid rgba(138, 43, 226, 0.3);
                }
            """)
        elif self.repeat_mode == 1:  
            self.repeat_btn.setText("🔁")
            self.repeat_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8b5cf6, stop:1 #06b6d4);
                    color: #ffffff;
                    border: none;
                    border-radius: 18px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #a78bfa, stop:1 #22d3ee);
                }
            """)
        else:  
            self.repeat_btn.setText("🔂")
            self.repeat_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #8b5cf6, stop:1 #06b6d4);
                    color: #ffffff;
                    border: none;
                    border-radius: 18px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #a78bfa, stop:1 #22d3ee);
                }
            """)
    
    def play_song(self, file_path, metadata=None):
        """Play a song file"""
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            self.playback_state_changed.emit(False)
            return False
            
        try:
            self.current_song_path = file_path
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            self.player.play()
            
            if metadata:
                self.song_title.setText(metadata.get('title', os.path.basename(file_path)))
                self.song_artist.setText(metadata.get('artist', 'Unknown Artist'))
            else:
                filename = os.path.basename(file_path).replace('.mp3', '')
                self.song_title.setText(filename)
                self.song_artist.setText("")

            # Track random history for better random selection
            if self.shuffle_mode and file_path not in self.random_history:
                self.random_history.append(file_path)
                # Keep history reasonable size
                if len(self.random_history) > 50:
                    self.random_history.pop(0)
            
            for i, (fp, _) in enumerate(self.playlist):
                if fp == file_path:
                    self.current_index = i
                    break
            
            self.playback_state_changed.emit(True)
            return True
            
        except Exception as e:
            print(f"Error playing song: {e}")
            self.playback_state_changed.emit(False)
            return False
    
    def set_current_playlist(self, playlist):
        self.current_playlist = playlist.copy()
        self.random_history = []  # Clear history when playlist changes
    
    def get_next_random_song(self):
        if not self.current_playlist:
            return None
        
        available_songs = []
        current_song = self.current_song_path
        
        # Get all songs except current and recently played
        for file_path, metadata in self.current_playlist:
            if file_path != current_song and file_path not in self.random_history[-5:]:
                available_songs.append((file_path, metadata))
        
        # If we've played most songs recently, expand selection
        if not available_songs:
            for file_path, metadata in self.current_playlist:
                if file_path != current_song:
                    available_songs.append((file_path, metadata))
        
        # If still no songs, play current song again (for single song playlists)
        if not available_songs:
            for file_path, metadata in self.current_playlist:
                if file_path == current_song:
                    return (file_path, metadata)
            return None
        
        # Select random song
        return random.choice(available_songs)
    
    def on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            print(f"[DEBUG] Song ended, repeat mode: {self.repeat_mode}, shuffle: {self.shuffle_mode}")
            
            if self.repeat_mode == 2:  # Repeat one
                self.player.setPosition(0)
                self.player.play()
                self.playback_state_changed.emit(True)
            elif self.shuffle_mode and self.current_playlist:
                # Play random song with improved random selection
                next_song = self.get_next_random_song()
                if next_song:
                    file_path, metadata = next_song
                    self.play_song(file_path, metadata)
                    print(f"[DEBUG] Playing random song: {os.path.basename(file_path)}")
                else:
                    self.playback_state_changed.emit(False)
            elif self.repeat_mode == 1:  # Repeat all
                self.next_song()
            else:
                self.next_song()
        elif status == QMediaPlayer.LoadedMedia:
            pass
        elif status == QMediaPlayer.InvalidMedia:
            print("Invalid media")
            self.playback_state_changed.emit(False)
    
    def stop_playback(self):
        self.player.stop()
        self.song_title.setText("No song playing")
        self.song_artist.setText("")
        self.play_btn.setText("▶")
        self.playback_state_changed.emit(False)
    
    def update_position(self, position):
        duration = self.player.duration()
        if duration > 0:
            self.progress_slider.setValue(int((position / duration) * 1000))
        
        self.time_current.setText(self.format_time(position))
    
    def update_duration(self, duration):
        self.time_total.setText(self.format_time(duration))
    
    def format_time(self, ms):
        seconds = int(ms / 1000)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def update_progress(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            position = self.player.position()
            duration = self.player.duration()
            if duration > 0:
                self.progress_slider.setValue(int((position / duration) * 1000))
                self.time_current.setText(self.format_time(position))
    
    def update_play_button(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")
    
    def clear_playlist(self):
        self.playlist = []
        self.current_index = -1
        self.random_history = []
    
    def add_to_playlist(self, file_path, metadata):
        self.playlist.append((file_path, metadata))
    
    def toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def previous_song(self):
        if not self.shuffle_mode and self.current_index > 0:
            self.current_index -= 1
            file_path, metadata = self.playlist[self.current_index]
            self.play_song(file_path, metadata)
    
    def next_song(self):
        if self.shuffle_mode and self.current_playlist:
            # Get next random song
            next_song = self.get_next_random_song()
            if next_song:
                file_path, metadata = next_song
                self.play_song(file_path, metadata)
        else:
            if self.current_index < len(self.playlist) - 1:
                self.current_index += 1
                file_path, metadata = self.playlist[self.current_index]
                self.play_song(file_path, metadata)
    
    def set_volume(self, value):
        self.player.setVolume(value)
        if not self.is_muted:
            self.previous_volume = value
    
    def toggle_mute(self):
        if self.is_muted:
            self.player.setVolume(self.previous_volume)
            self.volume_slider.setValue(self.previous_volume)
            self.is_muted = False
            self.volume_btn.setText("🔊")
        else:
            self.previous_volume = self.player.volume()
            self.player.setVolume(0)
            self.volume_slider.setValue(0)
            self.is_muted = True
            self.volume_btn.setText("🔇")