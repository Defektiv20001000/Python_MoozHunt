import hashlib
import os
import shutil
import threading
import time
import pygame
import Playlists


class AudioPlayer:
    def __init__(self, root, temp_dir, on_status, on_play_state, on_progress_setup, on_progress_tick):
        self.root = root
        self.temp_songs_dir = temp_dir
        self.on_status = on_status
        self.on_play_state = on_play_state
        self.on_progress_setup = on_progress_setup
        self.on_progress_tick = on_progress_tick

        self.temp_cache = {}
        self.play_queue = []
        self.current_queue_index = 0
        self.current_track_path = None
        self._current_token = None

        self.is_playing = False
        self.is_paused = False
        self.is_seeking = False
        self.track_duration = 0
        self.play_start_time = 0
        self.paused_time = 0
        self.loop_mode = 0

        pygame.mixer.init()
        pygame.mixer.music.set_volume(0.7)
        self.cleanup_temp_folder()

    def set_volume(self, val):
        pygame.mixer.music.set_volume(float(val) / 100.0)

    def cleanup_temp_folder(self):
        self.temp_cache.clear()
        os.makedirs(self.temp_songs_dir, exist_ok=True)
        for name in os.listdir(self.temp_songs_dir):
            path = os.path.join(self.temp_songs_dir, name)
            try:
                (shutil.rmtree if os.path.isdir(path) and not os.path.islink(path) else os.unlink)(path)
            except Exception as e:
                print(f"Не удалось удалить временный файл {path}: {e}")

    def shutdown(self):
        for fn in (pygame.mixer.music.stop, pygame.mixer.music.unload, pygame.mixer.quit):
            try:
                fn()
            except Exception:
                pass
        self.cleanup_temp_folder()

    def set_queue(self, queue_list, start_index):
        self.play_queue = queue_list
        self.current_queue_index = start_index
        self.load_and_play_current()

    def load_and_play_current(self):
        if not self.play_queue or self.current_queue_index >= len(self.play_queue):
            return
        pygame.mixer.music.stop()
        self.is_playing = self.is_paused = False
        track = self.play_queue[self.current_queue_index]
        self.on_status(track, "Загрузка...")
        self._current_token = id(track)

        if track.get("is_local") and track.get("file"):
            return self.play_file(track["full_path"], track)

        cached = track.get("cached_filepath") or self.temp_cache.get(track["link"])
        if cached and os.path.exists(cached):
            track["cached_filepath"] = cached
            self.play_file(cached, track)
        else:
            self.on_status(track, "Скачивание в кэш...")
            threading.Thread(target=self._download_worker, args=(track, self._current_token), daemon=True).start()

    def _download_worker(self, track, token):
        os.makedirs(self.temp_songs_dir, exist_ok=True)
        name = Playlists._safe_filename(" - ".join(p for p in (track.get("artist"), track.get("title")) if p)) or \
               "song_" + hashlib.md5(track["link"].encode()).hexdigest()[:8]
        filepath = None
        try:
            with Playlists._slots:
                filepath = Playlists._download_file(track["link"], os.path.join(self.temp_songs_dir, name))
        except Exception as e:
            print(f"Ошибка скачивания трека в кэш: {e}")

        if self._current_token != token:
            return
        if filepath and os.path.exists(filepath):
            track["cached_filepath"] = self.temp_cache[track["link"]] = filepath
        self.root.after(0, self.play_file, filepath, track)

    def _get_duration(self, filepath):
        try:
            from tinytag import TinyTag
            if d := TinyTag.get(filepath).duration:
                return d
        except Exception:
            pass
        try:
            return pygame.mixer.Sound(filepath).get_length()
        except Exception:
            return 0

    def play_file(self, filepath, track):
        if not filepath or not os.path.exists(filepath):
            self.on_status(track, "Ошибка воспроизведения")
            self.is_playing = self.is_paused = False
            self.on_play_state(False)
            return
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.is_playing, self.is_paused, self.is_seeking = True, False, False
            self.on_play_state(True)
            self.on_status(track, "Играет")
            self.current_track_path = filepath
            self.track_duration = self._get_duration(filepath)
            self.on_progress_setup(self.track_duration if self.track_duration > 0 else 100)
            self.paused_time = 0
            self.play_start_time = time.time()
        except Exception as e:
            print(f"Ошибка воспроизведения: {e}")
            self.on_status(track, "Ошибка воспроизведения файла")
            self.is_playing = self.is_paused = False
            self.on_play_state(False)

    def toggle_pause(self):
        if not self.is_playing:
            return self.load_and_play_current()
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.on_play_state(True)
            self.play_start_time = time.time()
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.on_play_state(False)
            self.paused_time += time.time() - self.play_start_time

    def seek_to(self, position):
        if not self.is_playing:
            return
        position = max(0, min(position, self.track_duration - 0.5)) if self.track_duration > 0 else max(0, position)
        self.paused_time, self.play_start_time = position, time.time()
        try:
            was_paused = self.is_paused
            pygame.mixer.music.play(start=position)
            if was_paused:
                pygame.mixer.music.pause()
        except Exception as e:
            print(f"Ошибка перемотки: {e}")

    def stop_track(self):
        pygame.mixer.music.stop()
        self.is_playing = self.is_paused = False
        self.on_play_state(False)
        self.on_status(None, "Остановлено")
        self.on_progress_tick(0)
        self.paused_time = 0

    def next_track(self):
        if self.play_queue:
            self.current_queue_index = (self.current_queue_index + 1) % len(self.play_queue)
            self.load_and_play_current()

    def prev_track(self):
        if self.play_queue:
            self.current_queue_index = (self.current_queue_index - 1) % len(self.play_queue)
            self.load_and_play_current()

    def toggle_loop(self):
        self.loop_mode = (self.loop_mode + 1) % 3
        return ("-----", "🔁 Плейлист", "🔂 Трек")[self.loop_mode]

    def tick(self):
        if self.is_playing and not self.is_paused:
            elapsed = self.paused_time + (time.time() - self.play_start_time)
            if (elapsed >= self.track_duration) if self.track_duration > 0 else (not pygame.mixer.music.get_busy()):
                if self.loop_mode == 2:
                    self.load_and_play_current()
                elif self.loop_mode == 1 or self.current_queue_index < len(self.play_queue) - 1:
                    self.next_track()
                else:
                    self.stop_track()
            elif not self.is_seeking:
                self.on_progress_tick(elapsed)
