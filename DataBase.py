import os, queue, sqlite3, sys
import numpy as np
from concurrent.futures import ThreadPoolExecutor

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "music_vault.db")
STORAGE_DIR = os.path.join(BASE_DIR, "songs")

GENRES = [
    "Pop", "Rock", "Metal", "Hip-Hop", "Electronic", "Indie",
    "Disco", "Eurodance/Dance-Pop", "Classical", "Soundtrack/Instrumental",
]

def _connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT,
            title TEXT,
            link TEXT,
            genre TEXT DEFAULT 'Не определен',
            embedding BLOB
        )
    """)
    return conn

def _norm(value):
    return (value or "").strip().casefold()

def clean_title(title_text):
    text = title_text or ""
    for sep in ("[", "(", "{"):
        if sep in text:
            text = text.split(sep, 1)[0]
    return text.strip()


def get_all_songs():
    with _connect() as conn:
        return conn.execute("SELECT link, artist, title, genre FROM songs").fetchall()

def get_random_songs(count=20):
    with _connect() as conn:
        return conn.execute(
            "SELECT link, artist, title, genre FROM songs ORDER BY RANDOM() LIMIT ?",
            (int(count),),
        ).fetchall()

def search_songs(title="", artist="", genre="", query="", limit=None):
    query = _norm(query)
    title, artist, genre = _norm(title), _norm(artist), _norm(genre)
    result = []
    for link, song_artist, song_title, song_genre in get_all_songs():
        norm_artist, norm_title = _norm(song_artist), _norm(song_title)
        if query:
            if query not in f"{norm_artist} {norm_title}":
                continue
        else:
            if (title and title not in norm_title) or (artist and artist not in norm_artist):
                continue
        if genre and genre != _norm(song_genre):
            continue
        result.append((link, song_artist, song_title, song_genre))
        if limit is not None and len(result) >= limit:
            break
    return result


def find_similar_songs_db(target_vector, top_n=3):
    from scipy.spatial.distance import cosine
    results = [
        (song, 1 - cosine(target_vector, song["vector"]))
        for song in load_embeddings()
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return [song for song, _ in results[:top_n]]

def get_average_embedding(songs, db_path="music_vault.db"):
    if not songs:
        return None

    # Собираем ссылки на песни (игнорируем локальные файлы без ссылок)
    links = [s.get("link") for s in songs if s.get("link")]
    if not links:
        return None

    vectors = []
    placeholders = ",".join("?" for _ in links)
    query = f"SELECT embedding FROM songs WHERE link IN ({placeholders})"

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, links)
            for (emb_data,) in cursor.fetchall():
                if not emb_data:
                    continue
                # Преобразуем данные из БД в массив чисел
                if isinstance(emb_data, str):
                    vec = json.loads(emb_data)
                elif isinstance(emb_data, bytes):
                    vec = np.frombuffer(emb_data, dtype=np.float32)
                else:
                    vec = emb_data
                vectors.append(vec)
    except Exception as e:
        print(f"Ошибка при чтении эмбеддингов из БД: {e}")
        return None

    if not vectors:
        return None

    # Вычисляем средний вектор по всем найденным песням
    avg_vector = np.mean(vectors, axis=0)
    return avg_vector

def load_embeddings():
    with _connect() as conn:
        rows = conn.execute("SELECT link, artist, title, genre, embedding FROM songs").fetchall()
    return [
        {
            "link": link,
            "artist": artist,
            "title": title,
            "genre": genre,
            "vector": np.frombuffer(embedding_bytes, dtype=np.float32),
        }
        for link, artist, title, genre, embedding_bytes in rows
    ]


def load_database(count_songs=1, max_workers=4):
    import numpy as np
    from tinytag import TinyTag
    import AIAnalyzer
    import Download

    os.makedirs(STORAGE_DIR, exist_ok=True)
    ready_queue = queue.Queue()
    workers = max(1, min(max_workers, count_songs))

    def download_task():
        item = Download.download_random_song(output_dir=STORAGE_DIR)
        ready_queue.put(item)

    with ThreadPoolExecutor(max_workers=workers) as pool, _connect() as conn:
        for _ in range(count_songs):
            pool.submit(download_task)

        for loop in range(count_songs):
            filepath, youtube_link, genre = ready_queue.get()
            if not filepath or not youtube_link or not os.path.isfile(filepath):
                print(f"[{loop + 1}/{count_songs}] Не удалось скачать трек. Пропуск...")
                continue

            try:
                tag = TinyTag.get(filepath)
                clean_track_title = clean_title(tag.title)
                vector = AIAnalyzer.get_audio_embedding(filepath)

                if vector is None:
                    print(f"Пропуск {os.path.basename(filepath)}: не удалось получить эмбеддинг.")
                    continue

                embedding_bytes = vector.astype(np.float32).tobytes()
                conn.execute(
                    "INSERT INTO songs (artist, title, link, genre, embedding) VALUES (?, ?, ?, ?, ?)",
                    (tag.artist, clean_track_title, youtube_link, genre, embedding_bytes),
                )
                conn.commit()
                print(f"[{loop + 1}/{count_songs}] Сохранено: {tag.artist} — {clean_track_title}")
            except Exception as e:
                print(f"Ошибка при обработке файла {os.path.basename(filepath)}: {e}")
            finally:
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"Не удалось удалить временный файл {filepath}: {e}")


def download_byUrl(url):
    import yt_dlp
    output_folder = os.path.join(BASE_DIR, "songs_temporary")
    os.makedirs(output_folder, exist_ok=True)

    ffmpeg_dir = BASE_DIR if any(os.path.isfile(os.path.join(BASE_DIR, n)) for n in ("ffmpeg.exe", "ffmpeg")) else None
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "MetadataFromTitle", "titleformat": "%(artist)s - %(title)s"},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
        "outtmpl": os.path.join(output_folder, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "force_ipv4": True,
        "source_address": "0.0.0.0",
        "proxy": "socks5h://127.0.0.1:10808",
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloads = info.get("requested_downloads") or []
            if downloads and downloads[0].get("filepath") and os.path.exists(downloads[0]["filepath"]):
                return downloads[0]["filepath"]
            final_path = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            return final_path if os.path.exists(final_path) else None
    except Exception as e:
        print(f"\n[ОШИБКА] Не удалось скачать: {e}")
        return None


if __name__ == "__main__":
    load_database(12000)
