import hashlib, json, os, random, re, shutil, threading, sys
from urllib.parse import urlparse

if getattr(sys, "frozen", False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.join(PROJECT_ROOT, "plays")
os.makedirs(BASE_DIR, exist_ok=True)

MANIFEST_NAME = "playlist.json"
MAX_PARALLEL_DOWNLOADS = 2
DOWNLOAD_TIMEOUT = 30
AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_FIELDS = {"url": "link", "title": "title", "artist": "artist", "genre": "genre"}

_lock = threading.RLock()
_slots = threading.Semaphore(MAX_PARALLEL_DOWNLOADS)
_in_progress = set()


class AppStorage:
    def __init__(self, base_dir=BASE_DIR):
        self.bad_songs_file = os.path.join(base_dir, "bad_songs.json")
        self.settings_file = os.path.join(base_dir, "app_settings.json")
        self.bad_songs = self._load_json(self.bad_songs_file, {})
        self.settings = self._load_settings()

    def _load_json(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, type(default)):
                        return data
            except Exception as e:
                print(f"Ошибка загрузки {os.path.basename(path)}: {e}")
        return default

    def _save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения {os.path.basename(path)}: {e}")

    def _load_settings(self):
        data = self._load_json(self.settings_file, {"volume": 70.0})
        try:
            vol = float(data.get("volume", 70.0))
        except Exception:
            vol = 70.0
        data["volume"] = max(0.0, min(100.0, vol))
        return data

    def save_settings(self, volume=None):
        if volume is not None:
            self.settings["volume"] = round(float(volume), 2)
        self._save_json(self.settings_file, self.settings)

    def save_bad_songs(self):
        self._save_json(self.bad_songs_file, self.bad_songs)

    def add_bad_songs(self, songs):
        changed = False
        for link, artist, title, genre in songs:
            if link and link not in self.bad_songs:
                self.bad_songs[link] = {
                    "link": link, "artist": artist or "", "title": title or "", "genre": genre or ""
                }
                changed = True
        if changed:
            self.save_bad_songs()
        return changed


def _safe_filename(text):
    return " ".join(_INVALID_CHARS.sub("", text or "").split()).strip(". ")


def normalize_name(name):
    name = _safe_filename(name).upper()
    if not name:
        raise ValueError("Название плейлиста пустое.")
    if not any(ch.isalpha() for ch in name):
        raise ValueError("В названии должна быть хотя бы одна буква.")
    if name in _WINDOWS_RESERVED:
        raise ValueError(f"Имя «{name}» зарезервировано системой, выберите другое.")
    return name


def list_playlists():
    return sorted(
        entry for entry in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, entry))
        and not entry.startswith((".", "_"))
        and any(ch.isalpha() for ch in entry)
        and entry == entry.upper()
    )


def create_playlist(name):
    name = normalize_name(name)
    for entry in os.listdir(BASE_DIR):
        if entry.lower() == name.lower():
            raise FileExistsError(f"Плейлист «{name}» уже существует.")
    os.makedirs(os.path.join(BASE_DIR, name))
    return name


def rename_playlist(old_name, new_name):
    old_dir = _playlist_dir(old_name)
    new_name = normalize_name(new_name)
    if old_name == new_name:
        return new_name
    for entry in os.listdir(BASE_DIR):
        if entry.lower() == new_name.lower() and entry != old_name:
            raise FileExistsError(f"Плейлист «{new_name}» уже существует.")
    with _lock:
        if any(pl == old_name for pl, _ in _in_progress):
            raise RuntimeError("Дождитесь окончания скачивания треков в этот плейлист перед переименованием.")
        os.rename(old_dir, os.path.join(BASE_DIR, new_name))
    return new_name


def _playlist_dir(name):
    if name not in list_playlists():
        raise FileNotFoundError(f"Плейлист «{name}» не найден.")
    return os.path.join(BASE_DIR, name)


def load_songs(playlist):
    with _lock:
        try:
            with open(os.path.join(_playlist_dir(playlist), MANIFEST_NAME), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            if playlist in list_playlists():
                return []
            raise


def _save_songs(playlist, songs):
    path = os.path.join(_playlist_dir(playlist), MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_songs(playlist, n=None, what="url", shuffle=False):
    if what != "full" and what not in _FIELDS:
        raise ValueError(f"what должно быть одним из: full, {', '.join(_FIELDS)}")
    songs = load_songs(playlist)
    if shuffle:
        random.shuffle(songs)
    if n is not None:
        songs = songs[:max(0, n)]
    return songs if what == "full" else [song[_FIELDS[what]] for song in songs]


def add_song(playlist, link, artist, title, genre, on_done=None):
    artist, title, genre = artist or "", title or "", genre or ""
    with _lock:
        songs = load_songs(playlist)
        if any(
            s["link"] == link or (title and s["title"].lower() == title.lower() and s["artist"].lower() == artist.lower())
            for s in songs
        ):
            return False
        songs.append({"link": link, "artist": artist, "title": title, "genre": genre, "file": ""})
        _save_songs(playlist, songs)
    _start_download(playlist, link, on_done)
    return True


def remove_song(playlist, link, on_before_delete_file=None):
    with _lock:
        folder = _playlist_dir(playlist)
        songs = load_songs(playlist)
        target = next((s for s in songs if s.get("link") == link), None)
        if not target:
            return False
        if target.get("file"):
            filepath = os.path.join(folder, target["file"])
            if os.path.exists(filepath):
                if on_before_delete_file:
                    on_before_delete_file(filepath)
                os.remove(filepath)
        updated = [s for s in songs if s.get("link") != link]
        _save_songs(playlist, updated)
        return True


def import_files(playlist, filepaths):
    folder = _playlist_dir(playlist)
    copied = 0
    for src in filepaths:
        dst = os.path.join(folder, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            copied += 1
    added = scan_local_files(playlist)
    return copied, added


def playlist_stats(playlist):
    folder = _playlist_dir(playlist)
    songs = load_songs(playlist)
    done = sum(1 for s in songs if s.get("file") and os.path.isfile(os.path.join(folder, s["file"])))
    return len(songs), done


def download_missing(playlist, on_done=None):
    folder = _playlist_dir(playlist)
    for s in load_songs(playlist):
        if not s.get("link", "").startswith("local:") and not (s.get("file") and os.path.isfile(os.path.join(folder, s["file"]))):
            _start_download(playlist, s["link"], on_done)


def _start_download(playlist, link, on_done):
    key = (playlist, link)
    with _lock:
        if key in _in_progress:
            return
        _in_progress.add(key)
    threading.Thread(target=_download_worker, args=(playlist, link, on_done), daemon=True).start()


def _download_worker(playlist, link, on_done):
    error = None
    try:
        with _lock:
            song = next(s for s in load_songs(playlist) if s["link"] == link)
        name = _safe_filename(" - ".join(p for p in (song["artist"], song["title"]) if p)) or "song_" + hashlib.md5(link.encode()).hexdigest()[:8]
        target_base = os.path.join(_playlist_dir(playlist), name)

        with _slots:
            filename = os.path.basename(_download_file(link, target_base))

        with _lock:
            songs = load_songs(playlist)
            for s in songs:
                if s["link"] == link:
                    s["file"] = filename
            _save_songs(playlist, songs)
    except Exception as e:
        error = e
    finally:
        with _lock:
            _in_progress.discard((playlist, link))
        if on_done:
            on_done(playlist, link, error)


def _download_file(url, target_base):
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"Ссылка не http/https: {url}")
    import yt_dlp

    final_path = target_base + ".mp3"
    options = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "outtmpl": target_base.replace("%", "%%") + ".%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": DOWNLOAD_TIMEOUT,
    }
    if any(os.path.isfile(os.path.join(PROJECT_ROOT, n)) for n in ("ffmpeg.exe", "ffmpeg")):
        options["ffmpeg_location"] = PROJECT_ROOT

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
    if not os.path.isfile(final_path):
        raise RuntimeError("yt-dlp не создал mp3-файл")
    return final_path


def scan_local_files(playlist):
    from tinytag import TinyTag
    folder = _playlist_dir(playlist)
    with _lock:
        songs = load_songs(playlist)
        known = {s["file"] for s in songs if s.get("file")}
        added = 0
        for entry in os.listdir(folder):
            if not entry.lower().endswith(AUDIO_EXTENSIONS) or entry in known:
                continue
            artist, title = "", ""
            try:
                tag = TinyTag.get(os.path.join(folder, entry))
                artist, title = (tag.artist or "").strip(), (tag.title or "").strip()
            except Exception:
                pass
            songs.append({
                "link": f"local:{entry}",
                "artist": artist,
                "title": title or os.path.splitext(entry)[0],
                "genre": "",
                "file": entry,
            })
            added += 1
        if added:
            _save_songs(playlist, songs)
        return added
