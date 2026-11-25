import os, queue, sqlite3, sys
from concurrent.futures import ThreadPoolExecutor

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "music_vault.db")
STORAGE_DIR = os.path.join(BASE_DIR, "songs")

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

def clean_title(title_text):
    text = title_text or ""
    for sep in ("[", "(", "{"):
        if sep in text:
            text = text.split(sep, 1)[0]
    return text.strip()

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

if __name__ == "__main__":
    load_database(4000)
