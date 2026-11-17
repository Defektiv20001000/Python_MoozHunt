import os
import queue
import random
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import DataBase
import Playlists
from dialogs import open_create_playlist_dialog, open_rename_playlist_dialog, open_report_dialog
from player import AudioPlayer
from theme import (
    ACCENT_BLUE, BG_HEADER, BG_MAIN, BG_PANEL, BORDER_COLOR,
    DOWNLOAD_POLL_MS, GENRE_PLACEHOLDER, RANDOM_SONGS_COUNT,
    SEARCH_DELAY_MS, TEXT_MAIN, TEXT_MUTED, TOP_LOGO_SIZE,
    create_scrollbar_tree, make_button, make_section_frame, setup_styles
)


def enable_high_dpi():
    if sys.platform == "win32":
        import ctypes
        for fn in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1), ctypes.windll.user32.SetProcessDPIAware):
            try:
                fn()
                break
            except Exception:
                pass


class MusicAppInterface:
    def __init__(self, root):
        self.root = root
        self.root.title("MuzHunt")
        try:
            self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0

        self.root.geometry(f"{self.s(1100)}x{self.s(730)}")
        self.root.minsize(self.s(920), self.s(620))
        self.root.configure(bg=BG_MAIN)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._search_job = self._random_songs = None
        self.right_songs, self.rec_songs_map, self.playlist_links, self.playlist_items_data = {}, {}, {}, {}
        self.rec_songs = []
        self._download_events = queue.Queue()
        self.volume_var = tk.DoubleVar(value=70)

        self.photo_icon = self.top_logo_img = None
        self._load_logos()
        setup_styles(self.root, self.s)

        self.title_var, self.artist_var, self.playlist_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.genre_var = tk.StringVar(value=GENRE_PLACEHOLDER)

        self.create_top_bar()
        self.create_context_menu()
        self.create_main_layout()

        self.player = AudioPlayer(
            root=self.root,
            temp_dir=os.path.join(self.base_dir, "songs_temporary"),
            on_status=self._on_player_status,
            on_play_state=lambda playing: self.play_btn.config(text="⏸ Пауза" if playing else "▶ Играть"),
            on_progress_setup=self._on_progress_setup,
            on_progress_tick=self.progress_var.set,
        )

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.refresh_playlists()
        self.refresh_right_list()
        self.poll_download_events()
        self.check_music_end()

    def s(self, val):
        return int(round(val * self.scale))

    def _load_logos(self):
        icon_path = os.path.join(self.base_dir, "logo.png")
        try:
            self.photo_icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(False, self.photo_icon)
        except Exception as e:
            print(f"Не удалось загрузить логотип: {e}")
            return

        target_px = self.s(TOP_LOGO_SIZE)
        try:
            from PIL import Image, ImageTk
            img = Image.open(icon_path).resize((target_px, target_px), Image.Resampling.LANCZOS)
            self.top_logo_img = ImageTk.PhotoImage(img)
        except Exception:
            factor = max(1, round(max(self.photo_icon.width(), self.photo_icon.height()) / max(1, target_px)))
            self.top_logo_img = self.photo_icon.subsample(factor, factor)

    def on_closing(self):
        self.player.shutdown()
        self.root.destroy()

    # --- ИНТЕРФЕЙС ---
    def create_context_menu(self):
        self.context_menu = tk.Menu(
            self.root, tearoff=0, bg=BG_HEADER, fg=TEXT_MAIN, activebackground=ACCENT_BLUE,
            activeforeground=TEXT_MAIN, bd=1, relief="solid", font=("Segoe UI", 9)
        )
        self.context_menu.add_command(label="Воспроизвести")
        self.context_menu.add_command(label="Добавить в плейлист")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Подать жалобу")

    def _show_tree_context_menu(self, event, tree, play_cmd, add_cmd, report_cmd):
        row = tree.identify_row(event.y)
        if not row:
            return
        if row not in tree.selection():
            tree.selection_set(row)
            tree.focus(row)
        self.context_menu.entryconfigure(0, command=play_cmd)
        self.context_menu.entryconfigure(1, command=add_cmd)
        self.context_menu.entryconfigure(3, command=report_cmd)
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def create_top_bar(self):
        top = tk.Frame(self.root, bg=BG_HEADER, padx=self.s(12), pady=self.s(8))
        top.pack(fill=tk.X)
        tk.Label(top, text="Поиск:", bg=BG_HEADER, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, self.s(5)))
        tk.Entry(
            top, width=28, textvariable=self.title_var, bg=BG_PANEL, fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN, relief="flat", highlightthickness=1,
            highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_BLUE, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=(0, self.s(15)), ipady=self.s(3))

        tk.Label(top, text="Жанр:", bg=BG_HEADER, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, self.s(5)))
        self.genre_combo = ttk.Combobox(
            top, width=22, state="readonly", textvariable=self.genre_var,
            values=[GENRE_PLACEHOLDER] + DataBase.GENRES, font=("Segoe UI", 9)
        )
        self.genre_combo.pack(side=tk.LEFT, ipady=self.s(2))
        self.genre_combo.bind("<<ComboboxSelected>>", self.on_genre_selected)

        if self.top_logo_img:
            tk.Label(top, image=self.top_logo_img, bg=BG_HEADER).pack(side=tk.RIGHT, padx=(self.s(10), 0))

        for v in (self.title_var, self.artist_var):
            v.trace_add("write", self.schedule_search)

    def create_main_layout(self):
        main = tk.Frame(self.root, bg=BG_MAIN, padx=self.s(10), pady=self.s(10))
        main.pack(fill=tk.BOTH, expand=True)

        # Левая колонка немного уже (weight=9), центральная и правая — шире (weight=11)
        main.grid_columnconfigure(0, weight=9, uniform="cols")
        main.grid_columnconfigure(1, weight=11, uniform="cols")
        main.grid_columnconfigure(2, weight=11, uniform="cols")
        main.grid_rowconfigure(0, weight=1)

        # Левая колонка
        left = tk.Frame(main, bg=BG_MAIN)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, self.s(6)))

        rec_frame = make_section_frame(left, "Рекомендуемые песни", self.s)
        rec_frame.pack(fill=tk.BOTH, expand=True, pady=(0, self.s(8)))
        self.rec_status = tk.Label(rec_frame, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED,
                                   font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.rec_status.pack(side=tk.BOTTOM, fill=tk.X)
        self.rec_tree = create_scrollbar_tree(
            rec_frame, (("Исполнитель", self.s(80)), ("Название", self.s(95)), ("Жанр", self.s(65))), self.s
        )
        self.rec_tree.bind("<Double-1>", self.play_from_recs)
        self.rec_tree.bind("<Button-3>", lambda e: self._show_tree_context_menu(
            e, self.rec_tree, self.play_from_recs, self.add_selected_rec_to_playlist, self.report_selected_rec))

        # Блок плеера
        player_box = make_section_frame(left, "Текущий трек", self.s)
        player_box.configure(bg=BG_PANEL)
        player_box.pack(fill=tk.X, side=tk.BOTTOM)
        self.track_info_label = tk.Label(
            player_box, text="Название песни:\nИсполнитель песни:\nПараметры: Выберите трек",
            bg=BG_PANEL, fg=TEXT_MAIN, justify=tk.LEFT, anchor="w", font=("Segoe UI", 9),
            padx=self.s(8), pady=self.s(6)
        )
        self.track_info_label.pack(fill=tk.X)

        self.progress_var = tk.DoubleVar()
        self.progress_slider = ttk.Scale(player_box, from_=0, to=100, variable=self.progress_var)
        self.progress_slider.pack(fill=tk.X, padx=self.s(8), pady=self.s(4))
        self.progress_slider.bind("<ButtonPress-1>", lambda e: setattr(self.player, "is_seeking", True))
        self.progress_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        vol = tk.Frame(player_box, bg=BG_PANEL)
        vol.pack(fill=tk.X, padx=self.s(8), pady=(0, self.s(4)))
        tk.Label(vol, text="🔈", bg=BG_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        ttk.Scale(vol, from_=0, to=100, variable=self.volume_var,
                  command=lambda v: self.player.set_volume(v)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=self.s(6))
        tk.Label(vol, text="🔊", bg=BG_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(side=tk.LEFT)

        ctrl = tk.Frame(player_box, bg=BG_PANEL)
        ctrl.pack(fill=tk.X, padx=self.s(6), pady=(self.s(2), self.s(8)))

        buttons_cfg = (
            ("⏮ Пред", lambda: self.player.prev_track(), False, None, 9),
            ("▶ Играть", lambda: self.player.toggle_pause(), True, "play_btn", 9),
            ("⏭ След", lambda: self.player.next_track(), False, None, 9),
            ("⏹", lambda: self.player.stop_track(), False, None, 4),
            ("-----", self.on_toggle_loop, False, "loop_btn", 9),
        )

        for col, (text, cmd, acc, attr, weight) in enumerate(buttons_cfg):
            ctrl.grid_columnconfigure(col, weight=weight, uniform="player_btns")
            btn = make_button(ctrl, text, cmd, self.s, accent=acc)
            btn.grid(row=0, column=col, sticky="ew", padx=2)
            if attr:
                setattr(self, attr, btn)

        # Центральная колонка
        center = make_section_frame(main, "Список песен в плейлисте", self.s)
        center.grid(row=0, column=1, sticky="nsew", padx=self.s(6))
        pl_bar = tk.Frame(center, bg=BG_PANEL, pady=self.s(5), padx=self.s(6))
        pl_bar.pack(fill=tk.X)
        self.playlist_combo = ttk.Combobox(pl_bar, state="readonly", textvariable=self.playlist_var, font=("Segoe UI", 9))
        self.playlist_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.playlist_combo.bind("<<ComboboxSelected>>", self.on_playlist_selected)
        make_button(pl_bar, "✎", self.rename_playlist, self.s).pack(side=tk.LEFT, padx=(self.s(4), 0))
        make_button(pl_bar, "+ Создать", self.create_playlist, self.s, accent=True).pack(side=tk.LEFT, padx=(self.s(4), 0))
        make_button(pl_bar, "Импорт MP3", self.import_local_files, self.s).pack(side=tk.LEFT, padx=(self.s(4), 0))

        self.playlist_status = tk.Label(center, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED,
                                        font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.playlist_status.pack(side=tk.BOTTOM, fill=tk.X)
        self.playlist_tree = create_scrollbar_tree(
            center, (("Исполнитель", self.s(85)), ("Название", self.s(100)), ("Жанр", self.s(65)), ("Удалить", self.s(58))), self.s
        )
        self.playlist_tree.column("Удалить", anchor="center", stretch=False, minwidth=self.s(54))
        self.playlist_tree.heading("Удалить", anchor="center")
        self.playlist_tree.bind("<Double-1>", self.play_from_playlist)
        self.playlist_tree.bind("<Button-1>", self.on_playlist_tree_click)

        # Правая колонка
        self.right_column = make_section_frame(main, "Поиск треков", self.s)
        self.right_column.grid(row=0, column=2, sticky="nsew", padx=(self.s(6), 0))
        self.search_status = tk.Label(self.right_column, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED,
                                      font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.search_status.pack(side=tk.BOTTOM, fill=tk.X)
        self.random_tree = create_scrollbar_tree(
            self.right_column, (("Исполнитель", self.s(95)), ("Название", self.s(110)), ("Жанр", self.s(80))), self.s
        )
        self.random_tree.bind("<Double-1>", self.play_from_random)
        self.random_tree.bind("<Button-3>", lambda e: self._show_tree_context_menu(
            e, self.random_tree, self.play_from_random, self.add_selected_right_to_playlist, self.report_selected_right))

    # --- КОЛЛБЭКИ ПЛЕЕРА ---
    def _on_player_status(self, track, status):
        if track:
            self.track_info_label.config(text=f"Название песни: {track['title']}\nИсполнитель песни: {track['artist']}\nПараметры: {status}")
        else:
            self.track_info_label.config(text=f"Название песни:\nИсполнитель песни:\nПараметры: {status}")

    def _on_progress_setup(self, max_val):
        self.progress_slider.config(to=max_val)
        self.progress_var.set(0)

    def on_slider_release(self, _event):
        self.player.is_seeking = False
        self.player.seek_to(self.progress_var.get())

    def on_toggle_loop(self):
        self.loop_btn.config(text=self.player.toggle_loop())

    def check_music_end(self):
        self.player.tick()
        self.root.after(100, self.check_music_end)

    # --- ЗАПУСК ТРЕКОВ ---
    def _play_from_tree(self, tree, songs_map):
        if sel := tree.selection():
            q = [{"link": l, "artist": a, "title": t, "is_local": False}
                 for i in tree.get_children() for l, a, t, _ in [songs_map[i]]]
            self.player.set_queue(q, tree.index(sel[0]))

    def play_from_playlist(self, event=None):
        if (event and self.playlist_tree.identify_column(event.x) == "#4") or not (sel := self.playlist_tree.selection()):
            return
        pl = self.playlist_var.get()
        q = [{"link": s["link"], "artist": s["artist"], "title": s["title"], "file": s.get("file"),
              "full_path": os.path.join(Playlists.BASE_DIR, pl, s["file"]) if s.get("file") else None,
              "is_local": True} for s in Playlists.load_songs(pl)]
        self.player.set_queue(q, self.playlist_tree.index(sel[0]))

    def play_from_recs(self, _event=None):
        self._play_from_tree(self.rec_tree, self.rec_songs_map)

    def play_from_random(self, _event=None):
        self._play_from_tree(self.random_tree, self.right_songs)

    # --- ДИАЛОГИ И ЖАЛОБЫ ---
    def report_selected_rec(self):
        if (sel := self.rec_tree.selection()) and sel[0] in self.rec_songs_map:
            open_report_dialog(self.root, self.s, self.photo_icon, self.rec_songs_map[sel[0]], source="Рекомендации")

    def report_selected_right(self):
        if (sel := self.random_tree.selection()) and sel[0] in self.right_songs:
            open_report_dialog(self.root, self.s, self.photo_icon, self.right_songs[sel[0]], source="Поиск треков")

    def create_playlist(self):
        open_create_playlist_dialog(self.root, self.s, self.photo_icon, lambda name: self.refresh_playlists(select=name))

    def rename_playlist(self):
        current = self.playlist_var.get()
        if not current:
            return messagebox.showinfo("Плейлист", "Нет выбранного плейлиста.", parent=self.root)
        if self.player.is_playing and self.player.current_track_path:
            pl_dir = os.path.abspath(os.path.join(Playlists.BASE_DIR, current))
            if os.path.abspath(self.player.current_track_path).startswith(pl_dir + os.sep):
                self.player.stop_track()
        open_rename_playlist_dialog(
            self.root, self.s, self.photo_icon, current,
            lambda new_name: self.refresh_playlists(select=new_name)
        )

    # --- ПЛЕЙЛИСТЫ, РЕКОМЕНДАЦИИ И ПОИСК ---
    def get_random_playlist_songs(self, count=5):
        songs = list(self.playlist_items_data.values())
        if not songs:
            return []
        return random.sample(songs, min(count, len(songs)))

    def _get_all_playlists_links(self):
        existing_links = set()
        try:
            for pl_name in Playlists.list_playlists():
                for song in Playlists.load_songs(pl_name):
                    if link := song.get("link"):
                        existing_links.add(link)
        except Exception as e:
            print(f"Ошибка при сборе треков из плейлистов: {e}")
        return existing_links

    def update_recommendations(self):
        sample_songs = self.get_random_playlist_songs(5)
        if not sample_songs:
            self.set_recommendations([])
            self.rec_status.config(text="Добавьте треки в плейлист")
            return

        try:
            avg_vector = DataBase.get_average_embedding(sample_songs)
            if avg_vector is None:
                self.set_recommendations([])
                self.rec_status.config(text="Нет данных для рекомендаций")
                return

            # Собираем ссылки на все песни во всех плейлистах пользователя
            existing_links = self._get_all_playlists_links()

            # Запрашиваем с запасом, чтобы после фильтрации осталось 15 новых треков
            fetch_count = 15 + len(existing_links)
            similar_songs = DataBase.find_similar_songs_db(avg_vector, fetch_count)

            formatted_songs = []
            for s in similar_songs:
                if isinstance(s, dict):
                    item = (
                        s.get("link", ""),
                        s.get("artist", ""),
                        s.get("title", ""),
                        s.get("genre", "")
                    )
                else:
                    item = s

                # Пропускаем песню, если она уже есть в любом из плейлистов
                if item[0] in existing_links:
                    continue

                formatted_songs.append(item)
                if len(formatted_songs) >= 15:
                    break

            self.set_recommendations(formatted_songs)
            self.rec_status.config(text=f"Подобрано треков: {len(formatted_songs)}")
        except Exception as e:
            print(f"Ошибка обновления рекомендаций: {e}")
            self.set_recommendations([])
            self.rec_status.config(text="Ошибка подбора")

    def on_playlist_tree_click(self, event):
        if self.playlist_tree.identify_region(event.x, event.y) == "cell" and self.playlist_tree.identify_column(event.x) == "#4":
            if item := self.playlist_tree.identify_row(event.y):
                self.delete_song_from_playlist(item)

    def _stop_if_current_file(self, filepath):
        if self.player.current_track_path and os.path.abspath(self.player.current_track_path) == os.path.abspath(filepath):
            self.player.stop_track()

    def delete_song_from_playlist(self, item):
        playlist, song = self.playlist_var.get(), self.playlist_items_data.get(item)
        if not playlist or not song:
            return
        try:
            Playlists.remove_song(playlist, song["link"], on_before_delete_file=self._stop_if_current_file)
            self.load_songs_to_playlist()
            self.update_recommendations()
        except Exception as e:
            messagebox.showerror("Удаление", f"Не удалось удалить песню: {e}", parent=self.root)

    def refresh_playlists(self, select=None):
        names = Playlists.list_playlists()
        self.playlist_combo["values"] = names
        current = select or self.playlist_var.get()
        self.playlist_var.set(current if current in names else (names[0] if names else ""))
        self.open_playlist()

    def import_local_files(self):
        if not (playlist := self.playlist_var.get()):
            return messagebox.showinfo("Плейлист", "Сначала создайте плейлист.", parent=self.root)
        if not (files := filedialog.askopenfilenames(parent=self.root, title="Выберите аудиофайлы",
            filetypes=[("Аудио", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("Все файлы", "*.*")])):
            return
        try:
            copied, added = Playlists.import_files(playlist, files)
            self.load_songs_to_playlist()
            self.update_recommendations()
            messagebox.showinfo("Импорт", f"Скопировано файлов: {copied}\nДобавлено в плейлист: {added}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Импорт", f"Ошибка импорта файлов: {e}", parent=self.root)

    def on_playlist_selected(self, _event=None):
        self.playlist_combo.selection_clear()
        self.open_playlist()

    def open_playlist(self):
        if playlist := self.playlist_var.get():
            try:
                Playlists.scan_local_files(playlist)
            except Exception as e:
                print(f"Ошибка сканирования папки плейлиста: {e}")
        self.load_songs_to_playlist()
        self.update_recommendations()
        if playlist:
            try:
                Playlists.download_missing(playlist, lambda p, l, err: self._download_events.put((p, l, err)))
            except Exception as e:
                print(f"Ошибка: {e}")

    def load_songs_to_playlist(self):
        self.playlist_tree.delete(*self.playlist_tree.get_children())
        self.playlist_links.clear()
        self.playlist_items_data.clear()
        if playlist := self.playlist_var.get():
            try:
                for song in Playlists.load_songs(playlist):
                    item = self.playlist_tree.insert("", tk.END, values=(song["artist"] or "—", song["title"] or "—", song["genre"] or "—", "✖"))
                    self.playlist_links[item], self.playlist_items_data[item] = song["link"], song
            except Exception as e:
                print(f"Ошибка: {e}")
        self.update_playlist_status()

    def update_playlist_status(self, note=""):
        if not (playlist := self.playlist_var.get()):
            text = "Плейлистов нет"
        else:
            try:
                total, done = Playlists.playlist_stats(playlist)
                text = f"Песен: {total} · скачано: {done}"
            except Exception:
                text = "Ошибка чтения"
        self.playlist_status.config(text=f"{note} · {text}" if note else text)

    def add_selected_right_to_playlist(self):
        self.add_to_playlist([self.right_songs[i] for i in self.random_tree.selection() if i in self.right_songs])

    def add_selected_rec_to_playlist(self):
        self.add_to_playlist([self.rec_songs_map[i] for i in self.rec_tree.selection() if i in self.rec_songs_map])

    def add_to_playlist(self, songs):
        if not (playlist := self.playlist_var.get()):
            return messagebox.showinfo("Плейлист", "Сначала создайте плейлист.", parent=self.root)
        if not songs:
            return
        for link, artist, title, genre in songs:
            Playlists.add_song(playlist, link, artist, title, genre, on_done=lambda p, l, err: self._download_events.put((p, l, err)))
        self.load_songs_to_playlist()
        self.update_recommendations()

    def poll_download_events(self):
        while True:
            try:
                if (err := self._download_events.get_nowait()[2]):
                    print(f"Ошибка скачивания: {err}")
            except queue.Empty:
                break
        self.update_playlist_status()
        self.root.after(DOWNLOAD_POLL_MS, self.poll_download_events)

    def schedule_search(self, *_):
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(SEARCH_DELAY_MS, self.refresh_right_list)

    def on_genre_selected(self, _event=None):
        self.genre_combo.selection_clear()
        self.refresh_right_list()

    def refresh_right_list(self):
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None
        genre = "" if self.genre_var.get() == GENRE_PLACEHOLDER else self.genre_var.get()
        query = self.title_var.get().strip()
        try:
            if query or genre:
                songs = DataBase.search_songs(query=query, genre=genre)
            else:
                if self._random_songs is None:
                    self._random_songs = DataBase.get_random_songs(RANDOM_SONGS_COUNT)
                songs = self._random_songs
        except Exception:
            songs = []
        self._fill_tree(self.random_tree, self.right_songs, songs)

    def _fill_tree(self, tree, target_map, songs):
        tree.delete(*tree.get_children())
        target_map.clear()
        for link, artist, title, genre in songs:
            item = tree.insert("", tk.END, values=(artist or "—", title or "—", genre or "—"))
            target_map[item] = (link, artist, title, genre)

    def fill_right_tree(self, songs):
        self._fill_tree(self.random_tree, self.right_songs, songs)

    def set_recommendations(self, songs):
        self.rec_songs = list(songs)
        self._fill_tree(self.rec_tree, self.rec_songs_map, self.rec_songs)


if __name__ == "__main__":
    enable_high_dpi()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("musicclean.app.v1")
    root = tk.Tk()
    MusicAppInterface(root)
    root.mainloop()
