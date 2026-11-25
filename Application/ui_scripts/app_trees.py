import tkinter as tk

from .dialogs import open_report_dialog
from .theme import create_scrollbar_tree
from .app_playback import PLAYING_BG, PLAYING_FG


class TreeMixin:
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

    def _on_tree_select(self, event):
        source = event.widget
        sel = source.selection()
        if not sel:
            return
        if len(sel) > 1:
            source.selection_set(sel[-1])
        other = self.right_tree if source is self.playlist_tree else self.playlist_tree
        if other.selection():
            other.selection_remove(other.selection())

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
        tree.bind(
            "<ButtonPress-1>",
            lambda e: tree.selection_remove(tree.selection()) if not tree.identify_row(e.y) else None,
        )

    def _make_equal_tree(self, parent):
        tree = create_scrollbar_tree(
            parent,
            (("Исполнитель", self.s(120)), ("Название", self.s(120)), ("Жанр", self.s(120))),
            self.s,
        )
        tree.configure(selectmode="browse")
        tree.tag_configure("playing", background=PLAYING_BG, foreground=PLAYING_FG)

        for col in ("#1", "#2", "#3"):
            tree.column(col, stretch=True, minwidth=self.s(60))

        def on_resize(event):
            col_w = max(self.s(60), (event.width - 2) // 3)
            for col in ("#1", "#2", "#3"):
                tree.column(col, width=col_w)

        tree.bind("<Configure>", on_resize)
        tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        return tree

    def _fill_tree(self, tree, target_map, songs):
        tree.delete(*tree.get_children())
        target_map.clear()
        for link, artist, title, genre in songs:
            item = tree.insert("", tk.END, values=(artist or "—", title or "—", genre or "—"))
            target_map[item] = (link, artist, title, genre)
        self._apply_playing_highlight()

    def _on_playlist_drag_start(self, event):
        item = self.playlist_tree.identify_row(event.y)
        if not item:
            self.playlist_tree.selection_remove(self.playlist_tree.selection())
            self._drag_item = None
            return
        self._drag_item = item

    def _on_playlist_drag_motion(self, event):
        if not self._drag_item:
            return
        target = self.playlist_tree.identify_row(event.y)
        if target and target != self._drag_item:
            target_idx = self.playlist_tree.index(target)
            self.playlist_tree.move(self._drag_item, "", target_idx)

    def _on_playlist_drag_drop(self, _event):
        if not self._drag_item:
            return
        self._drag_item = None
        self._save_playlist_order()

    def _save_playlist_order(self):
        pl = self.playlist_var.get()
        if not pl:
            return
        ordered_links = [
            self.playlist_items_data[item]["link"]
            for item in self.playlist_tree.get_children()
            if item in self.playlist_items_data
        ]
        orders = self.storage.settings.setdefault("playlist_orders", {})
        orders[pl] = ordered_links
        self.storage.save_settings(self.player_panel.volume_var.get())

    def _sort_songs_by_saved_order(self, playlist_name, songs):
        orders = self.storage.settings.get("playlist_orders", {})
        saved_links = orders.get(playlist_name)
        if not saved_links:
            return songs
        order_map = {link: idx for idx, link in enumerate(saved_links)}
        return sorted(songs, key=lambda s: order_map.get(s.get("link"), len(saved_links)))
