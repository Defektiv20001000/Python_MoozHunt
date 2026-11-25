import os, queue, sys
import tkinter as tk
from tkinter import ttk

import DataBase
from ui_scripts import (
    ACCENT_BLUE, AimpIconButton, AppActionsMixin, AppStorage,
    BG_HEADER, BG_MAIN, BG_PANEL, BORDER_COLOR, DOWNLOAD_POLL_MS,
    GENRE_PLACEHOLDER, PlaybackHighlightMixin, PlayerPanel,
    TEXT_MAIN, TEXT_MUTED, TOP_LOGO_SIZE, TreeMixin,
    make_button, make_section_frame, setup_styles,
)


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class MusicAppInterface(PlaybackHighlightMixin, TreeMixin, AppActionsMixin):
    def __init__(self, root, startup_files=None):
        self.root = root
        self.root.title("MuzHunt")
        try:
            self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0

        self.root.geometry(f"{self.s(700)}x{self.s(720)}")
        self.root.minsize(self.s(700), self.s(720))
        self.root.configure(bg=BG_MAIN)

        self.base_dir = get_app_dir()
        self.storage = AppStorage(self.base_dir)

        self._search_job = None
        self.right_songs, self.playlist_items_data = {}, {}
        self.is_search_mode = False
        self._download_events = queue.Queue()
        self._last_playing_state = None
        self._drag_item = None

        self.mini_win = None
        self.mini_play_btn = None
        self.mini_title_lbl = None

        self.photo_icon = self.top_logo_img = None
        self._load_logos()
        setup_styles(self.root, self.s)
        self._fix_treeview_tag_colors()

        self.title_var = tk.StringVar()
        self.playlist_var = tk.StringVar()
        self.genre_var = tk.StringVar(value=GENRE_PLACEHOLDER)

        self.create_top_bar()
        self.create_context_menu()
        self.create_main_layout()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind("<Unmap>", self._on_minimize)

        self.refresh_playlists()
        self.poll_download_events()
        self.check_music_end()

        if startup_files:
            self.root.after(150, lambda: self.play_external_files(startup_files))

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
        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.destroy()
        self.storage.save_settings(self.player_panel.volume_var.get())
        self.player_panel.shutdown()
        self.root.destroy()

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

        main.grid_columnconfigure(0, weight=1, uniform="cols")
        main.grid_columnconfigure(1, weight=1, uniform="cols")
        main.grid_rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG_MAIN)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, self.s(6)))

        center = make_section_frame(left, "Список песен в плейлисте", self.s)
        center.pack(fill=tk.BOTH, expand=True, pady=(0, self.s(8)))

        pl_bar = tk.Frame(center, bg=BG_PANEL, pady=self.s(5), padx=self.s(6))
        pl_bar.pack(fill=tk.X)
        self.playlist_combo = ttk.Combobox(pl_bar, state="readonly", textvariable=self.playlist_var, font=("Segoe UI", 9))
        self.playlist_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.playlist_combo.bind("<<ComboboxSelected>>", lambda _e: (self.playlist_combo.selection_clear(), self.open_playlist()))

        add_song_btn = make_button(pl_bar, "+", self.import_local_songs, self.s, width=2)
        add_song_btn.configure(highlightthickness=1, highlightbackground=BORDER_COLOR, pady=self.s(3))
        add_song_btn.pack(side=tk.LEFT, padx=(self.s(5), 0))

        edit_btn = AimpIconButton(pl_bar, "edit", self.rename_playlist, self.s, size=26, bg=BG_HEADER)
        edit_btn.configure(highlightthickness=1, highlightbackground=BORDER_COLOR)
        edit_btn.pack(side=tk.LEFT, padx=(self.s(5), 0))

        make_button(pl_bar, "+ Создать", self.create_playlist, self.s, accent=True).pack(side=tk.LEFT, padx=(self.s(5), 0))

        self.playlist_status = tk.Label(center, text="", anchor="w", bg=BG_HEADER, fg=TEXT_MUTED, font=("Segoe UI", 8), padx=self.s(8), pady=self.s(3))
        self.playlist_status.pack(side=tk.BOTTOM, fill=tk.X)
        self.playlist_tree = self._make_equal_tree(center)
        self.playlist_tree.bind("<Double-1>", self.play_from_playlist)
        self.playlist_tree.bind("<Button-3>", lambda e: self._popup_on_row(e, self.playlist_tree, self.playlist_context_menu))

        self.playlist_tree.bind("<ButtonPress-1>", self._on_playlist_drag_start)
        self.playlist_tree.bind("<B1-Motion>", self._on_playlist_drag_motion)
        self.playlist_tree.bind("<ButtonRelease-1>", self._on_playlist_drag_drop)

        self.player_panel = PlayerPanel(
            parent=left,
            root=self.root,
            temp_dir=os.path.join(self.base_dir, "songs_temporary"),
            scale_fn=self.s,
            initial_volume=self.storage.settings["volume"],
            on_save_volume=self.storage.save_settings,
        )

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

    # --- Мини-плеер в стиле AIMP (слева снизу поверх всех окон) ---

    def _get_work_area_bottom(self):
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
                return rect.bottom
            except Exception:
                pass
        return self.root.winfo_screenheight() - self.s(48)

    def _on_minimize(self, event):
        if event.widget is self.root and self.root.state() == "iconic":
            self.root.withdraw()
            self._show_mini_player()

    def _show_mini_player(self):
        if self.mini_win and self.mini_win.winfo_exists():
            return

        self.mini_win = tk.Toplevel(self.root)
        self.mini_win.overrideredirect(True)
        self.mini_win.attributes("-topmost", True)
        self.mini_win.configure(bg=BG_HEADER, highlightbackground=ACCENT_BLUE, highlightthickness=1)

        w, h = self.s(340), self.s(42)
        x = self.s(8)
        y = self._get_work_area_bottom() - h - self.s(8)
        self.mini_win.geometry(f"{w}x{h}+{x}+{y}")

        player = self.player_panel.player

        btn_prev = AimpIconButton(self.mini_win, "prev", player.prev_track, self.s, size=28, bg=BG_HEADER)
        btn_prev.pack(side=tk.LEFT, padx=(self.s(6), self.s(2)), pady=self.s(7))

        self.mini_play_btn = AimpIconButton(self.mini_win, "play", player.toggle_pause, self.s, size=32, bg=BG_HEADER)
        self.mini_play_btn.set_playing(player.is_playing and not player.is_paused)
        self.mini_play_btn.pack(side=tk.LEFT, padx=self.s(2), pady=self.s(5))

        btn_next = AimpIconButton(self.mini_win, "next", player.next_track, self.s, size=28, bg=BG_HEADER)
        btn_next.pack(side=tk.LEFT, padx=(self.s(2), self.s(6)), pady=self.s(7))

        restore_btn = make_button(self.mini_win, "🗖", self._restore_from_mini, self.s, accent=True)
        restore_btn.configure(padx=self.s(7), pady=self.s(2))
        restore_btn.pack(side=tk.RIGHT, padx=(self.s(4), self.s(6)), pady=self.s(6))

        self.mini_title_lbl = tk.Label(
            self.mini_win, text=self._get_mini_track_title(),
            bg=BG_HEADER, fg=TEXT_MAIN, font=("Segoe UI", 9), anchor="w"
        )
        self.mini_title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=self.s(4))
        self.mini_title_lbl.bind("<Double-1>", lambda _e: self._restore_from_mini())

    def _restore_from_mini(self):
        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.destroy()
        self.mini_win = None
        self.mini_play_btn = None
        self.mini_title_lbl = None
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()

    def _get_mini_track_title(self):
        track = self._get_active_track()
        if isinstance(track, dict):
            title = (track.get("title") or "").strip()
            if title:
                return title
        return "MuzHunt"

    def _sync_mini_player(self):
        if not (self.mini_win and self.mini_win.winfo_exists()):
            return
        if self.mini_title_lbl:
            new_title = self._get_mini_track_title()
            if self.mini_title_lbl.cget("text") != new_title:
                self.mini_title_lbl.config(text=new_title)
        if self.mini_play_btn:
            player = self.player_panel.player
            is_actually_playing = bool(player.is_playing and not player.is_paused)
            if self.mini_play_btn.is_playing != is_actually_playing:
                self.mini_play_btn.set_playing(is_actually_playing)

    # -------------------------------------------------------------

    def check_music_end(self):
        self.player_panel.tick()
        current_state = self._get_current_playing_info()
        if current_state != self._last_playing_state:
            self._last_playing_state = current_state
            self._apply_playing_highlight()
        self._sync_mini_player()
        self.root.after(100, self.check_music_end)


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

    startup_audio = [arg for arg in sys.argv[1:] if os.path.isfile(arg)]
    root = tk.Tk()
    MusicAppInterface(root, startup_files=startup_audio)
    root.mainloop()
