import os, random, sqlite3, uuid, yt_dlp, sys
from list import artists_and_genres

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "music_vault.db")
STORAGE_DIR = os.path.join(BASE_DIR, "songs")

def download_random_song(count=1, output_dir=None):
    downloaded_url = None
    downloaded_path = None
    target_dir = output_dir or STORAGE_DIR
    os.makedirs(target_dir, exist_ok=True)
    file_prefix = uuid.uuid4().hex[:8]

    def strict_duration_filter(info_dict, *, incomplete):
        duration = info_dict.get("duration")
        if duration:
            if duration > 360:
                return "Пропускаем: слишком длинный микс или клип."
            if duration < 80:
                return "Пропускаем: слишком короткое превью или shorts."

        url = info_dict.get("webpage_url")
        if url and os.path.exists(DB_NAME):
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    if conn.execute("SELECT 1 FROM songs WHERE link = ?", (url,)).fetchone():
                        return "Пропускаем: песня уже есть в базе данных."
            except sqlite3.Error as e:
                print(f"[БД Предупреждение] Ошибка при проверке URL: {e}")
        return None

    def postprocessor_hook(d):
        nonlocal downloaded_url, downloaded_path
        if d["status"] == "finished":
            info = d.get("info_dict", {})
            downloaded_url = info.get("webpage_url") or downloaded_url
            filepath = info.get("filepath")
            if filepath and os.path.isfile(filepath):
                downloaded_path = filepath

    selected_genre = random.choice(list(artists_and_genres.keys()))
    selected_artist = random.choice(artists_and_genres[selected_genre])
    yt_search_string = f"ytsearch{25}:{selected_artist} songs"

    ffmpeg_dir = BASE_DIR if any(os.path.isfile(os.path.join(BASE_DIR, n)) for n in ("ffmpeg.exe", "ffmpeg")) else None
    ydl_opts = {
        "format": "bestaudio/best",
        "match_filter": strict_duration_filter,
        "max_downloads": count,
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "MetadataFromTitle", "titleformat": "%(artist)s - %(title)s"},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
        "outtmpl": os.path.join(target_dir, f"{file_prefix}_%(title)s.%(ext)s"),
        "noplaylist": True,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([yt_search_string])
    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка при скачивании: {e}")

    if not downloaded_path:
        for fname in os.listdir(target_dir):
            if fname.startswith(f"{file_prefix}_") and fname.endswith(".mp3"):
                downloaded_path = os.path.join(target_dir, fname)
                break

    return downloaded_path, downloaded_url, selected_genre
