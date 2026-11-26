import math
import os
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

RANDOM_SONGS_COUNT = 20
SEARCH_DELAY_MS = 150
DOWNLOAD_POLL_MS = 400
GENRE_PLACEHOLDER = "Жанр на выбор"
TOP_LOGO_SIZE = 50
REPORT_API_URL = "https://example.com"

BG_MAIN, BG_PANEL, BG_HEADER, BG_HOVER = "#2b2b2b", "#333333", "#3c3f41", "#45494a"
ACCENT_BLUE, ACCENT_HOVER = "#1f6aa5", "#144870"
TEXT_MAIN, TEXT_MUTED, BORDER_COLOR = "#ffffff", "#aaaaaa", "#444444"


def setup_styles(root, scale_fn):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview", background=BG_MAIN, foreground=TEXT_MAIN, fieldbackground=BG_MAIN,
                    rowheight=scale_fn(28), borderwidth=0, font=("Segoe UI", 9))
    style.map("Treeview", background=[("selected", ACCENT_BLUE)], foreground=[("selected", TEXT_MAIN)])
    style.configure("Treeview.Heading", background=BG_HEADER, foreground=TEXT_MAIN, relief="flat",
                    borderwidth=0, font=("Segoe UI", 9, "bold"), padding=(scale_fn(6), scale_fn(5)))
    style.map("Treeview.Heading", background=[("active", BG_HOVER)])
    style.configure("Vertical.TScrollbar", background=BG_HEADER, troughcolor=BG_MAIN, borderwidth=0, arrowcolor=TEXT_MUTED)
    style.map("Vertical.TScrollbar", background=[("active", BG_HOVER)])
    style.configure("TCombobox", fieldbackground=BG_PANEL, background=BG_HEADER, foreground=TEXT_MAIN,
                    arrowcolor=TEXT_MAIN, borderwidth=1, relief="flat")
    style.map("TCombobox", fieldbackground=[("readonly", BG_PANEL)],
              selectbackground=[("readonly", BG_PANEL)], selectforeground=[("readonly", TEXT_MAIN)])
    for opt, val in (("background", BG_PANEL), ("foreground", TEXT_MAIN),
                     ("selectBackground", ACCENT_BLUE), ("selectForeground", TEXT_MAIN)):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)
    style.configure("TScale", background=BG_PANEL, troughcolor="#1e1e1e", sliderthickness=scale_fn(14))


class AimpIconButton(tk.Canvas):
    """Векторная кнопка управления в стиле AIMP."""
    def __init__(self, parent, kind, command, scale_fn, size=34, bg=BG_PANEL):
        px = scale_fn(size)
        super().__init__(
            parent, width=px, height=px, bg=bg,
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self.kind = kind
        self.command = command
        self.px = px
        self.scale_fn = scale_fn
        self.is_playing = False
        self.loop_state = "off"  # "off", "all", "one"
        self.hovered = False
        self.pressed = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.draw()

    def _on_enter(self, _e):
        self.hovered = True
        self.draw()

    def _on_leave(self, _e):
        self.hovered = False
        self.pressed = False
        self.draw()

    def _on_press(self, _e):
        self.pressed = True
        self.draw()

    def _on_release(self, event):
        was_pressed = self.pressed
        self.pressed = False
        self.draw()
        if was_pressed and 0 <= event.x <= self.px and 0 <= event.y <= self.px:
            if self.command:
                self.command()

    def set_playing(self, playing):
        self.is_playing = bool(playing)
        self.draw()

    def set_loop_state(self, state_str):
        """Определяет состояние повтора по возвращаемой строке из player.toggle_loop()."""
        s = str(state_str).strip().lower()
        if "1" in s or "one" in s or "трек" in s or "один" in s:
            self.loop_state = "one"
        elif any(ch.isalnum() for ch in s) and s not in ("off", "нет", "выкл", "none"):
            self.loop_state = "all"
        else:
            self.loop_state = "off"
        self.draw()

    def draw(self):
        self.delete("all")
        c = self.px / 2.0
        offset = 1 if self.pressed else 0

        if self.kind == "play":
            r = self.px * 0.43
            fill_bg = "#3b8eed" if self.hovered else ACCENT_BLUE
            if self.pressed:
                fill_bg = "#1f6bc4"
            self.create_oval(
                c - r, c - r + offset, c + r, c + r + offset,
                fill=fill_bg, outline="#5ba4fc" if self.hovered else "", width=1
            )
            fg = "#ffffff"
            if self.is_playing:
                bw = max(2, self.px * 0.08)
                bh = self.px * 0.34
                gap = self.px * 0.07
                self.create_rectangle(c - gap - bw, c - bh / 2 + offset, c - gap, c + bh / 2 + offset, fill=fg, outline="")
                self.create_rectangle(c + gap, c - bh / 2 + offset, c + gap + bw, c + bh / 2 + offset, fill=fg, outline="")
            else:
                s = self.px * 0.19
                shift = self.px * 0.03
                self.create_polygon(
                    c - s * 0.75 + shift, c - s + offset,
                    c - s * 0.75 + shift, c + s + offset,
                    c + s * 1.05 + shift, c + offset,
                    fill=fg, outline=""
                )
            return

        if self.hovered:
            r_bg = self.px * 0.42
            self.create_oval(
                c - r_bg, c - r_bg, c + r_bg, c + r_bg,
                fill="#2d323b" if not self.pressed else "#22262d", outline=""
            )

        fg = "#ffffff" if self.hovered else "#cfd6e0"

        if self.kind == "prev":
            s = self.px * 0.16
            bar_w = max(2, self.px * 0.065)
            x_bar = c - s - bar_w * 0.5
            self.create_rectangle(x_bar, c - s + offset, x_bar + bar_w, c + s + offset, fill=fg, outline="")
            self.create_polygon(
                c + s, c - s + offset,
                c + s, c + s + offset,
                c - s * 0.35, c + offset,
                fill=fg, outline=""
            )
        elif self.kind == "next":
            s = self.px * 0.16
            bar_w = max(2, self.px * 0.065)
            x_bar = c + s - bar_w * 0.5
            self.create_rectangle(x_bar, c - s + offset, x_bar + bar_w, c + s + offset, fill=fg, outline="")
            self.create_polygon(
                c - s, c - s + offset,
                c - s, c + s + offset,
                c + s * 0.35, c + offset,
                fill=fg, outline=""
            )
        elif self.kind == "stop":
            s = self.px * 0.15
            self.create_rectangle(c - s, c - s + offset, c + s, c + s + offset, fill=fg, outline="")
        elif self.kind == "loop":
            if self.loop_state == "off":
                loop_fg = "#8b949e" if not self.hovered else "#cfd6e0"
            else:
                loop_fg = "#5ba4fc" if self.hovered else ACCENT_BLUE

            w = self.px * 0.24
            h = self.px * 0.17
            lw = max(1.6, self.px * 0.055)
            arr = self.px * 0.085

            x1, y1 = c - w, c - h + offset
            x2, y2 = c + w, c + h + offset

            self.create_line(x1, c + h * 0.15 + offset, x1, y1, x2 - arr * 0.4, y1, fill=loop_fg, width=lw)
            self.create_polygon(
                x2 + arr * 0.4, y1,
                x2 - arr * 0.7, y1 - arr * 0.75,
                x2 - arr * 0.7, y1 + arr * 0.75,
                fill=loop_fg, outline=""
            )

            self.create_line(x2, c - h * 0.15 + offset, x2, y2, x1 + arr * 0.4, y2, fill=loop_fg, width=lw)
            self.create_polygon(
                x1 - arr * 0.4, y2,
                x1 + arr * 0.7, y2 - arr * 0.75,
                x1 + arr * 0.7, y2 + arr * 0.75,
                fill=loop_fg, outline=""
            )

            if self.loop_state == "one":
                font_sz = max(7, int(round(self.px * 0.22)))
                self.create_text(c - 1, c + offset - 1, text="1", fill=loop_fg, font=("Segoe UI", font_sz, "bold"))
        elif self.kind == "edit":
            s = self.px * 0.20
            lw = max(1.5, self.px * 0.055)
            self.create_line(
                c - s * 0.75, c + s * 0.75 + offset,
                c + s * 0.55, c - s * 0.55 + offset,
                fill=fg, width=lw * 1.6
            )
            self.create_line(
                c + s * 0.65, c - s * 0.65 + offset,
                c + s * 0.90, c - s * 0.90 + offset,
                fill=fg, width=lw * 1.6
            )
            self.create_polygon(
                c - s * 0.98, c + s * 0.98 + offset,
                c - s * 0.92, c + s * 0.48 + offset,
                c - s * 0.48, c + s * 0.92 + offset,
                fill=fg, outline=""
            )


def make_button(parent, text, command, scale_fn, accent=False, width=None):
    btn = tk.Button(
        parent, text=text, command=command, bg=ACCENT_BLUE if accent else BG_HEADER, fg=TEXT_MAIN,
        activebackground=ACCENT_HOVER if accent else BG_HOVER, activeforeground=TEXT_MAIN,
        relief="flat", bd=0, font=("Segoe UI", 9, "bold" if accent else "normal"),
        cursor="hand2", padx=scale_fn(8), pady=scale_fn(5)
    )
    if width:
        btn.config(width=width)
    return btn


def make_section_frame(parent, title, scale_fn):
    outer = tk.Frame(parent, bg=BG_MAIN, highlightbackground=BORDER_COLOR, highlightthickness=1)
    tk.Label(outer, text=title, bg=BG_HEADER, fg=TEXT_MAIN, font=("Segoe UI", 9, "bold"),
             anchor="w", padx=scale_fn(8), pady=scale_fn(5)).pack(fill=tk.X)
    return outer


def create_scrollbar_tree(parent, columns, scale_fn):
    frame = tk.Frame(parent, bg=BG_MAIN)
    frame.pack(fill=tk.BOTH, expand=True)
    sb = ttk.Scrollbar(frame)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", yscrollcommand=sb.set)
    for name, width in columns:
        tree.heading(name, text=name, anchor="w")
        tree.column(name, width=width, minwidth=scale_fn(45), anchor="w")
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.config(command=tree.yview)
    return tree


class CassetteWidget(tk.Label):
    """Гладкая векторная аудиокассета с суперсэмплингом (антиалиасингом)."""
    def __init__(self, parent, scale_fn, width=116, height=68, bg=BG_PANEL):
        w, h = scale_fn(width), scale_fn(height)
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.w = w
        self.h = h
        self.bg = bg
        self.angle = 0.0
        self.is_playing = False
        self._job = None
        self._photo = None
        self.draw()

    def set_playing(self, playing):
        playing = bool(playing)
        if self.is_playing == playing:
            return
        self.is_playing = playing
        if self.is_playing:
            self._animate()
        elif self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _animate(self):
        if not self.is_playing:
            self._job = None
            return
        self.angle = (self.angle + 8.0) % 360.0
        self.draw()
        self._job = self.after(45, self._animate)

    def draw(self):
        ss = 4
        W, H = self.w * ss, self.h * ss
        img = Image.new("RGBA", (W, H), self.bg)
        d = ImageDraw.Draw(img)

        pad = 3 * ss
        d.rounded_rectangle([pad, pad, W - pad, H - pad], radius=5 * ss, fill="#22252a", outline="#555b65", width=ss)
        d.rounded_rectangle([pad + 5 * ss, pad + 4 * ss, W - pad - 5 * ss, int(H * 0.30)], radius=2 * ss, fill=ACCENT_BLUE)
        wx1, wy1 = int(W * 0.16), int(H * 0.36)
        wx2, wy2 = int(W * 0.84), int(H * 0.72)
        d.rounded_rectangle([wx1, wy1, wx2, wy2], radius=3 * ss, fill="#16181c", outline="#444952", width=ss)

        cy = (wy1 + wy2) / 2.0
        reels = [(W * 0.33, 0.96), (W * 0.67, 0.82)]
        r_tape = (wy2 - wy1) * 0.43
        r_hub = r_tape * 0.50

        for cx, tape_scale in reels:
            rt = r_tape * tape_scale
            d.ellipse([cx - rt, cy - rt, cx + rt, cy + rt], fill="#3b2f2f", outline="#281e1e", width=ss)
            d.ellipse([cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub], fill="#cfd6e0", outline="#8b949e", width=ss)
            for i in range(6):
                rad = math.radians(self.angle + i * 60.0)
                x1 = cx + math.cos(rad) * (r_hub * 0.42)
                y1 = cy + math.sin(rad) * (r_hub * 0.42)
                x2 = cx + math.cos(rad) * (r_hub * 0.86)
                y2 = cy + math.sin(rad) * (r_hub * 0.86)
                d.line([x1, y1, x2, y2], fill="#22252a", width=max(2, int(1.6 * ss)))
            r_in = r_hub * 0.36
            d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill="#16181c")

        d.polygon(
            [(W * 0.24, H - pad), (W * 0.30, H * 0.78), (W * 0.70, H * 0.78), (W * 0.76, H - pad)],
            fill="#2c3038", outline="#555b65"
        )

        smooth_img = img.resize((self.w, self.h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(smooth_img)
        self.config(image=self._photo)


class AudioVisualizerWidget(tk.Label):
    """Гладкий визуализатор звуковых волн в стиле AIMP со сглаживанием (суперсэмплинг)."""
    def __init__(self, parent, scale_fn, bars=11, width=56, height=24, bg=BG_HEADER):
        w, h = scale_fn(width), scale_fn(height)
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.w = w
        self.h = h
        self.bg = bg
        self.bars_count = bars
        self.levels = [0.06] * bars
        self.target_levels = [0.06] * bars
        self.is_playing = False
        self._running = True
        self._photo = None
        self._has_loopback = False

        self._cached_filepath = None
        self._envelope = None
        self._envelope_step = 0.05

        threading.Thread(target=self._wasapi_loopback_worker, daemon=True).start()
        self.draw()
        self._animate()

    def set_playing(self, playing):
        self.is_playing = bool(playing)

    def destroy(self):
        self._running = False
        super().destroy()

    def _wasapi_loopback_worker(self):
        try:
            import numpy as np
            import pyaudiowpatch as pyaudio
        except ImportError:
            return

        p = pyaudio.PyAudio()
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers.get("isLoopbackDevice"):
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            rate = int(default_speakers["defaultSampleRate"])
            channels = int(default_speakers["maxInputChannels"])
            chunk = 1024

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                frames_per_buffer=chunk,
                input=True,
                input_device_index=default_speakers["index"],
            )
            self._has_loopback = True

            while self._running:
                data = stream.read(chunk, exception_on_overflow=False)
                if not self.is_playing:
                    self.target_levels = [0.06] * self.bars_count
                    continue

                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1)

                fft = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
                fft = fft[2: max(self.bars_count + 3, len(fft) // 3)]
                chunks = np.array_split(fft, self.bars_count)
                raw = [float(np.mean(c)) / 16000.0 for c in chunks]
                self.target_levels = [min(1.0, max(0.06, v)) for v in raw]

            stream.stop_stream()
            stream.close()
        except Exception:
            self._has_loopback = False
        finally:
            p.terminate()

    def _load_file_envelope(self, filepath):
        if filepath == self._cached_filepath:
            return
        self._cached_filepath = filepath
        self._envelope = None
        if not filepath or not os.path.exists(filepath):
            return

        def worker():
            try:
                import numpy as np
                import pygame
                snd = pygame.mixer.Sound(filepath)
                arr = pygame.sndarray.array(snd)
                if arr.ndim > 1:
                    arr = arr.mean(axis=1)
                init_info = pygame.mixer.get_init()
                freq = init_info[0] if isinstance(init_info, tuple) else (init_info or 44100)
                step_samples = max(1, int(freq * self._envelope_step))
                usable = (len(arr) // step_samples) * step_samples
                if usable <= 0:
                    return
                frames = np.abs(arr[:usable].reshape(-1, step_samples)).mean(axis=1)
                peak = float(np.percentile(frames, 98)) or 1.0
                self._envelope = np.clip(frames / peak, 0.08, 1.0).tolist()
            except Exception:
                self._envelope = None

        threading.Thread(target=worker, daemon=True).start()

    def update_from_player(self, player):
        playing = bool(player.is_playing and not player.is_paused)
        self.set_playing(playing)
        if self._has_loopback:
            return

        if not playing:
            self.target_levels = [0.06] * self.bars_count
            return

        self._load_file_envelope(player.current_track_path)
        elapsed = player.paused_time + (time.time() - player.play_start_time)

        energy = 0.55
        if self._envelope:
            idx = int(elapsed / self._envelope_step)
            if 0 <= idx < len(self._envelope):
                energy = self._envelope[idx]

        center = (self.bars_count - 1) / 2.0
        new_targets = []
        for i in range(self.bars_count):
            dist_factor = 1.0 - 0.35 * (abs(i - center) / max(1.0, center))
            wave = 0.65 + 0.35 * math.sin(elapsed * (9.0 + i * 1.7) + i * 1.1)
            val = energy * dist_factor * wave
            new_targets.append(min(1.0, max(0.08, val)))
        self.target_levels = new_targets

    def _animate(self):
        if not self._running:
            return
        changed = False
        for i in range(self.bars_count):
            target = self.target_levels[i] if self.is_playing else 0.06
            cur = self.levels[i]
            speed = 0.55 if target > cur else 0.25
            nxt = cur + (target - cur) * speed
            if abs(nxt - cur) > 0.004:
                self.levels[i] = nxt
                changed = True

        if changed or self.is_playing:
            self.draw()

        self.after(35, self._animate)

    def draw(self):
        ss = 4
        W, H = self.w * ss, self.h * ss
        img = Image.new("RGBA", (W, H), self.bg)
        d = ImageDraw.Draw(img)

        gap = 2 * ss
        bar_w = max(2 * ss, (W - gap * (self.bars_count - 1)) // self.bars_count)
        total_w = self.bars_count * bar_w + (self.bars_count - 1) * gap
        start_x = (W - total_w) // 2
        cy = H / 2.0
        max_half_h = (H / 2.0) - 2 * ss

        for i, lvl in enumerate(self.levels):
            x0 = start_x + i * (bar_w + gap)
            x1 = x0 + bar_w
            half_h = max(1.5 * ss, lvl * max_half_h)
            color = "#4fa3f7" if (self.is_playing and lvl > 0.65) else (ACCENT_BLUE if self.is_playing else "#555b65")
            d.rounded_rectangle(
                [x0, cy - half_h, x1, cy + half_h],
                radius=bar_w // 2,
                fill=color,
            )

        smooth_img = img.resize((self.w, self.h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(smooth_img)
        self.config(image=self._photo)
