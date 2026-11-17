import tkinter as tk
from tkinter import ttk

RANDOM_SONGS_COUNT = 20
SEARCH_DELAY_MS = 150
DOWNLOAD_POLL_MS = 400
GENRE_PLACEHOLDER = "Жанр на выбор"
TOP_LOGO_SIZE = 50
REPORT_API_URL = "https://example.com/api/reports"

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
