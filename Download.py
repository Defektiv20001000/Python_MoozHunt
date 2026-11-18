import os, random, sqlite3, uuid, yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "music_vault.db")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "songs")

artists_and_genres = {
    "Pop": [
        "The Weeknd", "Billie Eilish", "Dua Lipa", "Harry Styles", "Bruno Mars",
        "Ed Sheeran", "Taylor Swift", "Ariana Grande", "Justin Bieber", "Sia",
        "Sam Smith", "Doja Cat", "Olivia Rodrigo", "Miley Cyrus", "Halsey",
        "Khalid", "Shawn Mendes", "Camila Cabello", "Lana Del Rey", "Michael Jackson",
        "Lady Gaga", "Michael Buble", "George Michael", "Ricky Martin",
        "Beyonce", "Rihanna", "Adele", "Justin Timberlake", "Katy Perry",
        "Selena Gomez", "Britney Spears", "Pink",
        "Zivert", "Полина Гагарина", "Дима Билан", "Сергей Лазарев",
        "Ёлка", "JONY", "ANIKV", "Elton John", "Gotye"
    ],
    "Rock": [
        "Linkin Park", "Coldplay", "Arctic Monkeys", "Green Day", "Foo Fighters",
        "Muse", "The Killers", "Radiohead", "Red Hot Chili Peppers", "Thirty Seconds to Mars",
        "Bring Me The Horizon", "Fall Out Boy", "Panic! At The Disco", "Imagine Dragons", "OneRepublic",
        "Evanescence", "Nickelback", "Paramore", "Royal Blood", "Deftones",
        "Король и Шут", "KISS", "Skip The Use",
        "Queen", "Nirvana", "AC/DC", "Metallica", "Pink Floyd",
        "The Rolling Stones", "Led Zeppelin", "Guns N' Roses", "U2",
        "Кино", "Сплин", "Би-2", "Земфира",
        "Мумий Тролль", "Агата Кристи", "Порнофильмы"
    ],
    "Metal": [
        "Rammstein", "Powerwolf", "Sabaton", "Eisbrecher",
        "Slipknot", "System of a Down", "Iron Maiden", "Judas Priest", "Nightwish",
        "Disturbed", "Korn", "Avenged Sevenfold", "Megadeth", "Slayer",
        "Black Sabbath", "Pantera", "Gojira", "Tool", "In Flames",
        "Children of Bodom", "Amon Amarth", "Arch Enemy", "Lamb of God", "Meshuggah",
        "Trivium", "Opeth", "Blind Guardian", "Helloween", "Sepultura",
        "Ария", "Кипелов", "Эпидемия", "Слот",
        "Louna", "Stigmata", "Amatory"
    ],
    "Hip-Hop": [
        "Drake", "Kendrick Lamar", "Eminem", "Travis Scott", "J. Cole",
        "Asap Rocky", "Kid Cudi", "Mac Miller", "Tyler, The Creator", "Childish Gambino",
        "The Notorious B.I.G.", "Juice WRLD", "Lil Peep", "XXXTentacion", "Post Malone",
        "Frank Ocean", "The Internet", "Anderson .Paak", "Leon Bridges", "Miguel",
        "Tupac Shakur", "Kanye West", "Jay-Z", "Snoop Dogg", "Lil Wayne",
        "50 Cent", "Dr. Dre", "A$AP Rocky",
        "Баста", "Oxxxymiron", "Скриптонит", "Miyagi & Эндшпиль",
        "Каста", "Noize MC", "PHARAOH"
    ],
    "Electronic": [
        "Daft Punk", "Kavinsky", "M83", "The Prodigy", "The Chemical Brothers",
        "Skrillex", "Deadmau5", "Avicii", "Calvin Harris", "Zedd",
        "Marshmello", "Flume", "Disclosure", "Kaytranada", "Justice",
        "Gesaﬀelstein", "Perturbator", "Carpenter Brut", "The Midnight", "FM-84",
        "Mr. Kitty", "Modjo", "INTERWORLD", "Kordhell",
        "Martin Garrix", "David Guetta", "Tiësto", "Armin van Buuren", "The Chainsmokers",
        "Swedish House Mafia", "Pendulum", "Fatboy Slim",
        "IC3PEAK", "Cream Soda", "ЛСП", "Mujuice",
        "Нейромонах Феофан", "Swanky Tunes", "Pendulum (RU) / Teddy Killerz"
    ],
    "Indie": [
        "Tame Impala", "Gorillaz", "Mac DeMarco", "Boy Pablo", "Cigarettes After Sex",
        "The Neighborhood", "Foster The People", "MGMT", "Phoenix", "Alt-J",
        "Beach House", "Chvrches", "Glass Animals", "Khruangbin", "Thundercat",
        "FKJ", "Tom Misch", "Joji", "Cuco", "Clairo", "Мы",
        "Florence + The Machine", "Bon Iver", "Thexx", "Vampire Weekend",
        "Local Natives", "Iron & Wine", "Sufjan Stevens", "Fleet Foxes",
        "Монеточка", "Сироткин", "Дайте танк (!)", "Буерак",
        "СБПЧ", "Пошлая Молли", "kedr livanskiy"
    ],
    "Disco": [
        "Modern Talking", "ABBA", "Boney M.", "Sandy Marton", "Scissors Sisters",
        "Bee Gees", "Donna Summer", "Earth, Wind & Fire", "Chic", "KC and the Sunshine Band",
        "Kool & The Gang", "Gloria Gaynor", "Village People", "Baccara", "Arabesque",
        "C.C. Catch", "Ottawan", "Eruption", "Dschinghis Khan", "bad Boys Blue",
        "Ricchi e Poveri", "Gazebo", "Lipps Inc.", "Sister Sledge", "Sylvester",
        "Bananarama", "Pet Shop Boys", "Jamiroquai", "Kylie Minogue", "Daft Punk (Random Access)",
        "Мираж", "Ласковый май", "Кар-Мэн", "Форум",
        "Комбинация", "Технология", "Анжелика Варум"
    ],
    "Eurodance/Dance-Pop": [
        "Stormae", "Shaggy", "Dave Rogers", "THE ROOP", "Holly Dolly", "Little Big",
        "4Wheel", "Tako",
        "Aqua", "Vengaboys", "2 Unlimited", "Haddaway", "E-Type",
        "Corona", "Culture Beat", "Ace of Base", "Dr. Alban", "Scooter",
        "Руки Вверх!", "Demo", "Вирус!", "Краски",
        "Hi-Fi", "Дискотека Авария", "Отпетые мошенники"
    ],
    "Classical": [
        "Бетховен", "Zaz", "Aron Wright",
        "Моцарт", "Бах", "Вивальди", "Шопен", "Чайковский",
        "Людовико Эйнауди", "Ян Тирсен", "Yiruma", "Ханс Циммер", "Макс Рихтер"
    ],
    "Soundtrack/Instrumental": [
        "The Living Tombstone", "C418", "Kevin MacLeod", "Спектакль Джо",
        "Christopher Larkin", "Lena Reine",
        "John Williams", "Hans Zimmer", "Jeremy Soule", "Nobuo Uematsu", "Martin O'Donnell",
        "Gustavo Santaolalla", "Danny Elfman", "Ennio Morricone", "Howard Shore", "Michael Giacchino",
        "Эдуард Артемьев", "Алексей Рыбников", "Микаэл Таривердиев", "Игорь Корнелюк",
        "Евгений Дога", "Кирилл Рихтер", "Илья Бешевли"
    ]
}



def download_random_song(count=1, output_dir=None):
    downloaded_url = None
    downloaded_path = None
    target_dir = output_dir or DEFAULT_OUTPUT_DIR
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
        if url and os.path.exists(DB_PATH):
            try:
                with sqlite3.connect(DB_PATH) as conn:
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
