import os, sqlite3, sys
import numpy as np

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
    results = [
        (song, float(
            np.dot(target_vector, song["vector"]) / (np.linalg.norm(target_vector) * np.linalg.norm(song["vector"]))))
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