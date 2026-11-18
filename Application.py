import os, queue, random, shutil, sys
import tkinter as tk
from tkinter import messagebox, ttk

import DataBase
from ui_scripts import (
    ACCENT_BLUE, AimpIconButton, AppStorage, AudioPlayer, BG_HEADER, BG_MAIN,
    BG_PANEL, BORDER_COLOR, DOWNLOAD_POLL_MS, GENRE_PLACEHOLDER, PlayerPanel,
    SEARCH_DELAY_MS, TEXT_MAIN, TEXT_MUTED, TOP_LOGO_SIZE,
    create_scrollbar_tree, make_button, make_section_frame,
    open_bad_songs_dialog, open_create_playlist_dialog,
    open_rename_playlist_dialog, open_report_dialog, playlists, setup_styles
)



class MusicAppInterface:
    def __init__(self, root):
        self.root = root
        self.root.title("MuzHunt")
        try:
            self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0

        self.root.geometry(f"{self.s(700)}x{self.s(700)}")
        self.root.minsize(self.s(700), self.s(700))
        self.root.configure(bg=BG_MAIN)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.storage = AppStorage(self.base_dir)

        self._search_job = None
        self.right_songs, self.playlist_items_data = {}, {}
        self.is_search_mode = False
        self._download_events = queue.Queue()

        self.photo_icon = self.top_logo_img = None
        self._load_logos()
        setup_styles(self.root, self.s)

        self.title_var = tk.StringVar()
        self.playlist_var = tk.StringVar()
        self.genre_var = tk.StringVar(value=GENRE_PLACEHOLDER)

        self.create_top_bar()
        self.create_context_menu()
        self.create_main_layout()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.refresh_playlists()
        self.poll_download_events()
        self.check_music_end()

    def s(self, val):
        return int(round(val * self.scale))

    def _make_menu(self):
        return tk.Menu(
            self.root, tearoff=0, bg=BG_HEADER, fg=TEXT_MAIN, activebackground=ACCENT_BLUE,
            activeforeground=TEXT_MAIN, bd=1, relief="solid", font=("Segoe UI", 9)
        )

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
        self.storage.save_settings(self.player_panel.volume_var.get())
        self.player_panel.shutdown()
        self.root.destroy()

    # --- ПЛОХОЙ СПИСОК ---
    def _update_bad_list_btn_text(self):
        if hasattr(self, "bad_list_btn"):
            count = len(self.storage.bad_songs)
            self.bad_list_btn.config(text=f"🚫 Плохой список ({count})" if count else "🚫 Плохой список")

    def _on_bad_songs_updated(self):
        self._update_bad_list_btn_text()
        self.refresh_right_list()

    def add_to_bad_songs(self, songs):
        if self.storage.add_bad_songs(songs):
            self._on_bad_songs_updated()

    def _on_bad_songs_dialog_changed(self):
        self.storage.save_bad_songs()
        self._on_bad_songs_updated()

    def open_bad_songs_dialog(self):
        open_bad_songs_dialog(
            self.root, self.s, self.photo_icon, self.storage.bad_songs, self._on_bad_songs_dialog_changed
        )

    # --- ИНТЕРФЕЙС И КОНТЕКСТНЫЕ МЕНЮ ---
    def create_context_menu(self):
        self.context_menu = self._make_menu()
        self.context_menu.add_command(label="Воспроизвести")
        self.context_menu.add_command(label="Добавить в плейлист")
        self.context_menu.add_command(label="В плохой список")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Подать жалобу")

        self.playlist_context_menu = self._make_menu()
        self.playlist_context_menu.add_command(label="Удалить", command=self.delete_selected_from_playlist)

    def _popup_on_row(self, event, tree, menu, before_popup=None):
        row = tree.identify_row(event.y)
        if not row:
            return
        if row not in tree.selection():
            tree.selection_set(row)
            tree.focus(row)
        if before_popup:
            before_popup()
        menu.tk_popup(event.x_root, event.y_root)

    def _get_selected(self, tree, songs_map):
        return [songs_map[i] for i in tree.selection() if i in songs_map]

    def _bind_song_tree(self, tree, songs_map):
        play_cmd = lambda: self._play_from_tree(tree, songs_map)
        add_cmd = lambda: self.add_to_playlist(self._get_selected(tree, songs_map))
        bad_cmd = lambda: self.add_to_bad_songs(self._get_selected(tree, songs_map))
        report_cmd = lambda: (sel := self._get_selected(tree, songs_map)) and open_report_dialog(
            self.root, self.s, self.photo_icon, sel[0],
            source="Поиск треков" if self.is_search_mode else "Рекомендации"
        )

        def configure_menu():
            self.context_menu.entryconfigure(0, command=play_cmd)
            self.context_menu.entryconfigure(1, command=add_cmd)
            self.context_menu.entryconfigure(2, command=bad_cmd)
            self.context_menu.entryconfigure(4, command=report_cmd)

        tree.bind("<Double-1>", lambda _e: play_cmd())
        tree.bind("<Button-3>", lambda e: self._popup_on_row(e, tree, self.context_menu, configure_menu))

    def _make_equal_tree(self, parent):
        tree = create_scrollbar_tree(
            parent,
            (("Исполнитель", self.s(120)), ("Название", self.s(120)), ("Жанр", self.s(120))),
            self.s
        )
        for col in ("#1", "#2", "#3"):
            tree.column(col, stretch=True, minwidth=self.s(60))

        def on_resize(event):
            col_w = max(self.s(60), (event.width - 2) // 3)
            for col in ("#1", "#2", "#3"):
                tree.column(col, width=col_w)

        tree.bind("<Configure>", on_resize)
        return tree

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
        self.genre_combo.bind("<<ComboboxSelected>>", lambda _e: (self.genre_combo.selection_clear(), self.refresh_right_list()))

        if self.top_logo_img:
            tk.Label(top, image=self.top_logo_img, bg=BG_HEADER).pack(side=tk.RIGHT, padx=(self.s(10), 0))

        self.bad_list_btn = make_button(top, "🚫 Плохой список", self.open_bad_songs_dialog, self.s)
        self.bad_list_btn.configure(
            relief="solid", bd=1, highlightthickness=1,
            highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_BLUE,
            padx=self.s(10), pady=self.s(4),
        )
        self.bad_list_btn.pack(side=tk.RIGHT)
        self._update_bad_list_btn_text()

        self.title_var.trace_add("write", self.schedule_search)

    def create_main_layout(self):
        main = tk.Frame(self.root, bg=BG_MAIN, padx=self.s(10), pady=self.s(10))
        main.pack(fill=tk.BOTH, expand=True)

        # Две колонки: слева плейлист + плеер, справа рекомендации / поиск
        main.grid_columnconfigure(0, weight=1, uniform="cols")
        main.grid_columnconfigure(1, weight=1, uniform="cols")
        main.grid_rowconfigure(0, weight=1)

        # Левая колонка
        left = tk.Frame(main, bg=BG_MAIN)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, self.s(6)))

        center = make_section_frame(left, "Список песен в плейлисте", self.s)
        center.pack(fill=tk.BOTH, expand=True, pady=(0, self.s(8)))

        pl_bar = tk.Frame(center, bg=BG_PANEL, pady=self.s(5), padx=self.s(6))
        pl_bar.pack(fill=tk.X)
        self.playlist_combo = ttk.Combobox(pl_bar, state="readonly", textvariable=self.playlist_var, font=("Segoe UI", 9))
        self.playlist_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.playlist_combo.bind("<<ComboboxSelected>>", lambda _e: (self.playlist_combo.selection_clear(), self.open_playlist()))

        # Векторная кнопка редактирования плейлиста (вместо расплывчатого символа шрифта)
        edit_btn = AimpIconButton(pl_bar, "edit", self.rename_playlist, self.s, size=26, bg=BG_HEADER)
        edit_btn.configure(highlightthickness=1, highlightbackground=BORDER_COLOR)
        edit_btn.pack(side=tk.LEFT, padx=(self.s(5), 0))

        make_button(pl_bar, "+ Создать", self.create_playlist, self.s, accent=True).pack(side=tk.LEFT, padx=(self.s(5), 0))

        self.playlist_status = tk.Label(center, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED, font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.playlist_status.pack(side=tk.BOTTOM, fill=tk.X)
        self.playlist_tree = self._make_equal_tree(center)
        self.playlist_tree.bind("<Double-1>", self.play_from_playlist)
        self.playlist_tree.bind("<Button-3>", lambda e: self._popup_on_row(e, self.playlist_tree, self.playlist_context_menu))

        self.player_panel = PlayerPanel(
            parent=left,
            root=self.root,
            temp_dir=os.path.join(self.base_dir, "songs_temporary"),
            scale_fn=self.s,
            initial_volume=self.storage.settings["volume"],
            on_save_volume=self.storage.save_settings,
        )

        # Правая колонка (Рекомендации + Результаты поиска)
        self.right_column = make_section_frame(main, "Рекомендации", self.s)
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(self.s(6), 0))

        right_footer = tk.Frame(self.right_column, bg=BG_HEADER)
        right_footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.right_status = tk.Label(right_footer, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED, font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.right_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.rec_refresh_btn = make_button(right_footer, "↻ Обновить", self.update_recommendations, self.s)
        self.rec_refresh_btn.pack(side=tk.RIGHT, padx=self.s(4), pady=self.s(2))

        self.right_tree = self._make_equal_tree(self.right_column)
        self._bind_song_tree(self.right_tree, self.right_songs)

    def _set_right_header(self, title):
        def find_and_set(parent):
            for w in parent.winfo_children():
                if isinstance(w, tk.Label) and w is not self.right_status:
                    w.config(text=title)
                    return True
                if find_and_set(w):
                    return True
            return False
        find_and_set(self.right_column)

    def check_music_end(self):
        self.player_panel.tick()
        self.root.after(100, self.check_music_end)

    # --- ЗАПУСК ТРЕКОВ ---
    def _play_from_tree(self, tree, songs_map):
        if sel := tree.selection():
            q = [{"link": l, "artist": a, "title": t, "is_local": False}
                 for i in tree.get_children() for l, a, t, _ in [songs_map[i]]]
            self.player_panel.player.set_queue(q, tree.index(sel[0]))

    def play_from_playlist(self, _event=None):
        if not (sel := self.playlist_tree.selection()):
            return
        pl = self.playlist_var.get()
        q = [{"link": s["link"], "artist": s["artist"], "title": s["title"], "file": s.get("file"),
              "full_path": os.path.join(playlists.BASE_DIR, pl, s["file"]) if s.get("file") else None,
              "is_local": True} for s in playlists.load_songs(pl)]
        self.player_panel.player.set_queue(q, self.playlist_tree.index(sel[0]))

    # --- УПРАВЛЕНИЕ ПЛЕЙЛИСТАМИ ---
    def create_playlist(self):
        open_create_playlist_dialog(self.root, self.s, self.photo_icon, lambda name: self.refresh_playlists(select=name))

    def _delete_playlist_files(self, name):
        pl_dir = os.path.join(playlists.BASE_DIR, name)
        self.player_panel.stop_if_in_dir(pl_dir)
        if hasattr(playlists, "delete_playlist"):
            playlists.delete_playlist(name)
        elif os.path.isdir(pl_dir):
            shutil.rmtree(pl_dir)
        self.refresh_playlists()

    def rename_playlist(self):
        current = self.playlist_var.get()
        if not current:
            return messagebox.showinfo("Плейлист", "Нет выбранного плейлиста.", parent=self.root)
        self.player_panel.stop_if_in_dir(os.path.join(playlists.BASE_DIR, current))
        open_rename_playlist_dialog(
            self.root, self.s, self.photo_icon, current,
            on_renamed=lambda new_name: self.refresh_playlists(select=new_name),
            on_deleted=self._delete_playlist_files,
        )

    def _get_all_playlists_links(self):
        existing_links = set()
        try:
            for pl_name in playlists.list_playlists():
                for song in playlists.load_songs(pl_name):
                    if link := song.get("link"):
                        existing_links.add(link)
        except Exception as e:
            print(f"Ошибка при сборе треков из плейлистов: {e}")
        return existing_links

    def _filter_rec_candidates(self, candidates, excluded_links, limit=15):
        result = []
        for s in candidates:
            item = (s.get("link", ""), s.get("artist", ""), s.get("title", ""), s.get("genre", "")) if isinstance(s, dict) else s
            if item[0] not in excluded_links:
                result.append(item)
                if len(result) >= limit:
                    break
        return result

    # --- ОБНОВЛЕНИЕ ПРАВОЙ КОЛОНКИ (ПОИСК / РЕКОМЕНДАЦИИ) ---
    def update_recommendations(self):
        if self.is_search_mode:
            return

        self._set_right_header("Рекомендации")
        if not self.rec_refresh_btn.winfo_ismapped():
            self.rec_refresh_btn.pack(side=tk.RIGHT, padx=self.s(4), pady=self.s(2))

        excluded_links = self._get_all_playlists_links() | set(self.storage.bad_songs.keys())
        songs = list(self.playlist_items_data.values())
        sample_songs = random.sample(songs, min(5, len(songs))) if songs else []
        fetch_count = 15 + len(excluded_links)

        try:
            avg_vector = DataBase.get_average_embedding(sample_songs) if sample_songs else None
            if avg_vector is not None:
                candidates = DataBase.find_similar_songs_db(avg_vector, fetch_count)
                label_prefix = "Подобрано треков"
            else:
                candidates = DataBase.get_random_songs(fetch_count)
                label_prefix = "Случайная подборка"

            formatted = self._filter_rec_candidates(candidates, excluded_links)
            self._fill_tree(self.right_tree, self.right_songs, formatted)
            self.right_status.config(text=f"{label_prefix}: {len(formatted)}")
        except Exception as e:
            print(f"Ошибка обновления рекомендаций: {e}")
            self._fill_tree(self.right_tree, self.right_songs, [])
            self.right_status.config(text="Ошибка подбора")

    def delete_selected_from_playlist(self):
        playlist = self.playlist_var.get()
        selected = self.playlist_tree.selection()
        if not playlist or not selected:
            return
        try:
            for item in selected:
                if song := self.playlist_items_data.get(item):
                    playlists.remove_song(playlist, song["link"], on_before_delete_file=self.player_panel.stop_if_file)
            self.load_songs_to_playlist()
            self.update_recommendations()
        except Exception as e:
            messagebox.showerror("Удаление", f"Не удалось удалить песню: {e}", parent=self.root)

    def refresh_playlists(self, select=None):
        names = playlists.list_playlists()
        self.playlist_combo["values"] = names
        current = select or self.playlist_var.get()
        self.playlist_var.set(current if current in names else (names[0] if names else ""))
        self.open_playlist()

    def open_playlist(self):
        if playlist := self.playlist_var.get():
            try:
                playlists.scan_local_files(playlist)
            except Exception as e:
                print(f"Ошибка сканирования папки плейлиста: {e}")
        self.load_songs_to_playlist()
        self.update_recommendations()
        if playlist:
            try:
                playlists.download_missing(playlist, lambda p, l, err: self._download_events.put((p, l, err)))
            except Exception as e:
                print(f"Ошибка: {e}")

    def load_songs_to_playlist(self):
        self.playlist_tree.delete(*self.playlist_tree.get_children())
        self.playlist_items_data.clear()
        if playlist := self.playlist_var.get():
            try:
                for song in playlists.load_songs(playlist):
                    item = self.playlist_tree.insert("", tk.END, values=(song["artist"] or "—", song["title"] or "—", song["genre"] or "—"))
                    self.playlist_items_data[item] = song
            except Exception as e:
                print(f"Ошибка: {e}")
        self.update_playlist_status()

    def update_playlist_status(self, note=""):
        if not (playlist := self.playlist_var.get()):
            text = "Плейлистов нет"
        else:
            try:
                total, done = playlists.playlist_stats(playlist)
                text = f"Песен: {total} · скачано: {done}"
            except Exception:
                text = "Ошибка чтения"
        self.playlist_status.config(text=f"{note} · {text}" if note else text)

    def add_to_playlist(self, songs):
        if not (playlist := self.playlist_var.get()):
            return messagebox.showinfo("Плейлист", "Сначала создайте плейлист.", parent=self.root)
        if not songs:
            return
        for link, artist, title, genre in songs:
            playlists.add_song(playlist, link, artist, title, genre, on_done=lambda p, l, err: self._download_events.put((p, l, err)))
        self.load_songs_to_playlist()
        self.update_recommendations()

    def poll_download_events(self):
        while True:
            try:
                if err := self._download_events.get_nowait()[2]:
                    print(f"Ошибка скачивания: {err}")
            except queue.Empty:
                break
        self.update_playlist_status()
        self.root.after(DOWNLOAD_POLL_MS, self.poll_download_events)

    def schedule_search(self, *_):
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(SEARCH_DELAY_MS, self.refresh_right_list)

    def refresh_right_list(self):
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None

        genre = "" if self.genre_var.get() == GENRE_PLACEHOLDER else self.genre_var.get()
        query = self.title_var.get().strip()

        # Если строка поиска и жанр пусты — возвращаем рекомендации
        if not query and not genre:
            self.is_search_mode = False
            self.update_recommendations()
            return

        self.is_search_mode = True
        self._set_right_header("Результаты поиска")
        self.rec_refresh_btn.pack_forget()

        try:
            songs = [s for s in DataBase.search_songs(query=query, genre=genre) if s[0] not in self.storage.bad_songs]
            random.shuffle(songs)
        except Exception:
            songs = []

        self._fill_tree(self.right_tree, self.right_songs, songs)
        self.right_status.config(text=f"Найдено треков: {len(songs)}")

    def _fill_tree(self, tree, target_map, songs):
        tree.delete(*tree.get_children())
        target_map.clear()
        for link, artist, title, genre in songs:
            item = tree.insert("", tk.END, values=(artist or "—", title or "—", genre or "—"))
            target_map[item] = (link, artist, title, genre)


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        for fn in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1), ctypes.windll.user32.SetProcessDPIAware):
            try:
                fn()
                break
            except Exception:
                pass
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("musicclean.app.v1")

    root = tk.Tk()
    MusicAppInterface(root)
    root.mainloop()
