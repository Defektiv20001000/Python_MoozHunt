import hashlib, os, shutil, threading, time, pygame
import tkinter as tk
from tkinter import ttk

from . import playlists
from .theme import (
    ACCENT_BLUE, AimpIconButton, BG_PANEL, CassetteWidget,
    TEXT_MAIN, TEXT_MUTED, make_section_frame
)


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
        name = playlists._safe_filename(" - ".join(p for p in (track.get("artist"), track.get("title")) if p)) or \
               "song_" + hashlib.md5(track["link"].encode()).hexdigest()[:8]
        filepath = None
        try:
            with playlists._slots:
                filepath = playlists._download_file(track["link"], os.path.join(self.temp_songs_dir, name))
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


class PlayerPanel:
    def __init__(self, parent, root, temp_dir, scale_fn, initial_volume, on_save_volume):
        self.root = root
        self.scale_fn = scale_fn
        self.on_save_volume = on_save_volume
        self.volume_var = tk.DoubleVar(value=initial_volume)
        self.progress_var = tk.DoubleVar()

        self.frame = make_section_frame(parent, "Текущий трек", scale_fn)
        self.frame.configure(bg=BG_PANEL)
        self.frame.pack(fill=tk.X, side=tk.BOTTOM)

        info_box = tk.Frame(self.frame, bg=BG_PANEL)
        info_box.pack(fill=tk.X, padx=scale_fn(8), pady=scale_fn(6))

        self.track_info_label = tk.Label(
            info_box, text="Название:\nИсполнитель:\nВыберите трек",
            bg=BG_PANEL, fg=TEXT_MAIN, justify=tk.LEFT, anchor="w", font=("Segoe UI", 9)
        )
        self.track_info_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cassette = CassetteWidget(info_box, scale_fn, width=116, height=68, bg=BG_PANEL)
        self.cassette.pack(side=tk.RIGHT, padx=(scale_fn(8), 0))

        self.progress_slider = ttk.Scale(self.frame, from_=0, to=100, variable=self.progress_var)
        self.progress_slider.pack(fill=tk.X, padx=scale_fn(8), pady=scale_fn(4))
        self.progress_slider.bind("<ButtonPress-1>", lambda _e: setattr(self.player, "is_seeking", True))
        self.progress_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        vol = tk.Frame(self.frame, bg=BG_PANEL)
        vol.pack(fill=tk.X, padx=scale_fn(8), pady=(0, scale_fn(4)))
        tk.Label(vol, text="🔈", bg=BG_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        vol_slider = ttk.Scale(vol, from_=0, to=100, variable=self.volume_var, command=self._on_volume_change)
        vol_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=scale_fn(6))
        vol_slider.bind("<ButtonRelease-1>", lambda _e: self.on_save_volume(self.volume_var.get()))
        tk.Label(vol, text="🔊", bg=BG_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT)

        ctrl = tk.Frame(self.frame, bg=BG_PANEL)
        ctrl.pack(fill=tk.X, padx=scale_fn(6), pady=(scale_fn(4), scale_fn(10)))

        center_box = tk.Frame(ctrl, bg=BG_PANEL)
        center_box.pack(anchor="center")

        self.prev_btn = AimpIconButton(center_box, "prev", lambda: self.player.prev_track(), scale_fn, size=34)
        self.prev_btn.pack(side=tk.LEFT, padx=scale_fn(5))

        self.stop_btn = AimpIconButton(center_box, "stop", lambda: self.player.stop_track(), scale_fn, size=34)
        self.stop_btn.pack(side=tk.LEFT, padx=scale_fn(5))

        self.play_btn = AimpIconButton(center_box, "play", lambda: self.player.toggle_pause(), scale_fn, size=44)
        self.play_btn.pack(side=tk.LEFT, padx=scale_fn(8))

        self.next_btn = AimpIconButton(center_box, "next", lambda: self.player.next_track(), scale_fn, size=34)
        self.next_btn.pack(side=tk.LEFT, padx=scale_fn(5))

        self.loop_btn = AimpIconButton(center_box, "loop", self._on_toggle_loop, scale_fn, size=34)
        self.loop_btn.pack(side=tk.LEFT, padx=scale_fn(5))

        self.player = AudioPlayer(
            root=root,
            temp_dir=temp_dir,
            on_status=self._on_player_status,
            on_play_state=self._on_play_state_changed,
            on_progress_setup=self._on_progress_setup,
            on_progress_tick=self.progress_var.set,
        )
        self.player.set_volume(initial_volume)

    def _on_play_state_changed(self, playing):
        self.play_btn.set_playing(playing)
        self.cassette.set_playing(playing)

    def _on_player_status(self, track, status):
        title = track["title"] if track else ""
        artist = track["artist"] if track else ""
        self.track_info_label.config(text=f"Название: {title}\nИсполнитель: {artist}\n{status}")

    def _on_progress_setup(self, max_val):
        self.progress_slider.config(to=max_val)
        self.progress_var.set(0)

    def _on_slider_release(self, _event):
        self.player.is_seeking = False
        self.player.seek_to(self.progress_var.get())

    def _on_volume_change(self, val):
        try:
            self.player.set_volume(float(val))
        except Exception:
            pass

    def _on_toggle_loop(self):
        state_str = self.player.toggle_loop()
        self.loop_btn.set_loop_state(state_str)

    def stop_if_in_dir(self, directory):
        if self.player.is_playing and self.player.current_track_path:
            pl_dir = os.path.abspath(directory)
            if os.path.abspath(self.player.current_track_path).startswith(pl_dir + os.sep):
                self.player.stop_track()

    def stop_if_file(self, filepath):
        if self.player.current_track_path and os.path.abspath(self.player.current_track_path) == os.path.abspath(filepath):
            self.player.stop_track()

    def tick(self):
        self.player.tick()

    def shutdown(self):
        self.player.shutdown()