import os
from tkinter import ttk

from . import playlists

PLAYING_BG = "#5e6268"
PLAYING_FG = "#ffffff"


class PlaybackHighlightMixin:
    def _fix_treeview_tag_colors(self):
        style = ttk.Style(self.root)
        for key in ("background", "foreground"):
            existing = style.map("Treeview", key)
            if existing:
                filtered = [
                    spec for spec in existing
                    if spec[0] != ("!disabled", "!selected") and spec[0] != "!selected"
                ]
                style.map("Treeview", **{key: filtered})

    def _get_active_track(self):
        panel = getattr(self, "player_panel", None)
        player = getattr(panel, "player", None)
        if not player:
            return None
        if not (getattr(player, "is_playing", False) or getattr(player, "is_paused", False)):
            return None
        queue = getattr(player, "play_queue", None)
        idx = getattr(player, "current_queue_index", -1)
        if isinstance(queue, list) and 0 <= idx < len(queue):
            return queue[idx]
        return None

    def _get_current_playing_info(self):
        track = self._get_active_track()
        if not isinstance(track, dict):
            return None
        panel = getattr(self, "player_panel", None)
        player = getattr(panel, "player", None)
        cur_path = getattr(player, "current_track_path", None) if player else None
        full_path = track.get("full_path") or cur_path
        norm_path = os.path.normcase(os.path.abspath(full_path)) if full_path else None
        link = track.get("link") or None
        artist = (track.get("artist") or "").strip().lower()
        title = (track.get("title") or "").strip().lower()
        return (link, norm_path, artist, title)

    def _is_song_dict_playing(self, song, playing_info, pl_name):
        if not playing_info:
            return False
        p_link, p_path, p_artist, p_title = playing_info

        if p_link and song.get("link") == p_link:
            return True

        song_file = song.get("file")
        if p_path and song_file and pl_name:
            song_path = os.path.normcase(os.path.abspath(os.path.join(playlists.BASE_DIR, pl_name, song_file)))
            if song_path == p_path:
                return True

        s_artist = (song.get("artist") or "").strip().lower()
        s_title = (song.get("title") or "").strip().lower()
        return bool(p_title and s_title == p_title and s_artist == p_artist)

    def _is_tuple_song_playing(self, song_tuple, playing_info):
        if not playing_info:
            return False
        p_link, _p_path, p_artist, p_title = playing_info
        link, artist, title, _genre = song_tuple

        if p_link and link == p_link:
            return True

        s_artist = (artist or "").strip().lower()
        s_title = (title or "").strip().lower()
        return bool(p_title and s_title == p_title and s_artist == p_artist)

    def _apply_playing_highlight(self):
        playing_info = self._get_current_playing_info()
        pl_name = self.playlist_var.get()

        for item, song in self.playlist_items_data.items():
            is_playing = self._is_song_dict_playing(song, playing_info, pl_name)
            self.playlist_tree.item(item, tags=("playing",) if is_playing else ())

        for item, song_tuple in self.right_songs.items():
            is_playing = self._is_tuple_song_playing(song_tuple, playing_info)
            self.right_tree.item(item, tags=("playing",) if is_playing else ())

    def _play_from_tree(self, tree, songs_map):
        if sel := tree.selection():
            q = [
                {"link": l, "artist": a, "title": t, "is_local": False}
                for i in tree.get_children()
                for l, a, t, _ in [songs_map[i]]
            ]
            self.player_panel.player.set_queue(q, tree.index(sel[0]))
            self._last_playing_state = self._get_current_playing_info()
            self._apply_playing_highlight()

    def play_from_playlist(self, _event=None):
        if not (sel := self.playlist_tree.selection()):
            return
        pl = self.playlist_var.get()
        ordered_songs = [
            self.playlist_items_data[item]
            for item in self.playlist_tree.get_children()
            if item in self.playlist_items_data
        ]
        q = [
            {
                "link": s["link"],
                "artist": s["artist"],
                "title": s["title"],
                "file": s.get("file"),
                "full_path": os.path.join(playlists.BASE_DIR, pl, s["file"]) if s.get("file") else None,
                "is_local": True,
            }
            for s in ordered_songs
        ]
        self.player_panel.player.set_queue(q, self.playlist_tree.index(sel[0]))
        self._last_playing_state = self._get_current_playing_info()
        self._apply_playing_highlight()

    def play_external_files(self, filepaths):
        valid = [p for p in filepaths if os.path.isfile(p) and p.lower().endswith(playlists.AUDIO_EXTENSIONS)]
        if not valid:
            return
        q = []
        for path in valid:
            artist, title = "", os.path.splitext(os.path.basename(path))[0]
            try:
                from tinytag import TinyTag
                tag = TinyTag.get(path)
                artist = (tag.artist or "").strip()
                if tag.title and tag.title.strip():
                    title = tag.title.strip()
            except Exception:
                pass
            q.append({
                "link": f"local:{os.path.basename(path)}",
                "artist": artist,
                "title": title,
                "file": os.path.basename(path),
                "full_path": os.path.abspath(path),
                "is_local": True,
            })
        self.player_panel.player.set_queue(q, 0)
        self._last_playing_state = self._get_current_playing_info()
        self._apply_playing_highlight()
