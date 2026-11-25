import os, queue, random, shutil
import tkinter as tk
from tkinter import filedialog, messagebox

import DataBase
from . import playlists
from .dialogs import (
    open_bad_songs_dialog,
    open_create_playlist_dialog,
    open_rename_playlist_dialog,
)
from .theme import DOWNLOAD_POLL_MS, GENRE_PLACEHOLDER, SEARCH_DELAY_MS


class AppActionsMixin:
    def import_local_songs(self):
        playlist = self.playlist_var.get()
        if not playlist:
            return messagebox.showinfo("Плейлист", "Сначала создайте или выберите плейлист.", parent=self.root)
        filepaths = filedialog.askopenfilenames(
            parent=self.root,
            title="Добавить аудиофайлы в плейлист",
            filetypes=[
                ("Аудиофайлы", "*.mp3 *.wav *.flac *.ogg *.m4a"),
                ("Все файлы", "*.*"),
            ],
        )
        if not filepaths:
            return
        try:
            playlists.import_files(playlist, filepaths)
            self.load_songs_to_playlist()
            self._save_playlist_order()
            self.update_recommendations()
        except Exception as e:
            messagebox.showerror("Импорт", f"Не удалось добавить файлы: {e}", parent=self.root)

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

    def create_playlist(self):
        open_create_playlist_dialog(self.root, self.s, self.photo_icon, lambda name: self.refresh_playlists(select=name))

    def _delete_playlist_files(self, name):
        pl_dir = os.path.join(playlists.BASE_DIR, name)
        self.player_panel.stop_if_in_dir(pl_dir)
        if hasattr(playlists, "delete_playlist"):
            playlists.delete_playlist(name)
        elif os.path.isdir(pl_dir):
            shutil.rmtree(pl_dir)

        orders = self.storage.settings.get("playlist_orders", {})
        if name in orders:
            del orders[name]
            self.storage.save_settings(self.player_panel.volume_var.get())

        self.refresh_playlists()

    def rename_playlist(self):
        current = self.playlist_var.get()
        if not current:
            return messagebox.showinfo("Плейлист", "Нет выбранного плейлиста.", parent=self.root)
        self.player_panel.stop_if_in_dir(os.path.join(playlists.BASE_DIR, current))

        def handle_renamed(new_name):
            orders = self.storage.settings.get("playlist_orders", {})
            if current in orders:
                orders[new_name] = orders.pop(current)
                self.storage.save_settings(self.player_panel.volume_var.get())
            self.refresh_playlists(select=new_name)

        open_rename_playlist_dialog(
            self.root, self.s, self.photo_icon, current,
            on_renamed=handle_renamed,
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
            self.right_status.config(text=f"Ошибка: {e}")

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
            self._save_playlist_order()
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
                raw_songs = playlists.load_songs(playlist)
                sorted_songs = self._sort_songs_by_saved_order(playlist, raw_songs)
                for song in sorted_songs:
                    item = self.playlist_tree.insert("", tk.END, values=(song["artist"] or "—", song["title"] or "—", song["genre"] or "—"))
                    self.playlist_items_data[item] = song
            except Exception as e:
                print(f"Ошибка: {e}")
        self.update_playlist_status()
        self._apply_playing_highlight()

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
        self._save_playlist_order()
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
