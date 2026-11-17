import json
import threading
import time
import tkinter as tk
from tkinter import messagebox
import urllib.request

import Playlists
from theme import (
    ACCENT_BLUE, BG_MAIN, BG_PANEL, BORDER_COLOR,
    REPORT_API_URL, TEXT_MAIN, TEXT_MUTED, make_button
)


def _open_playlist_name_dialog(root, scale_fn, photo_icon, title, label_text, initial_value, submit_fn, on_success):
    dialog = tk.Toplevel(root)
    dialog.title(title)
    if photo_icon:
        dialog.iconphoto(False, photo_icon)
    dialog.configure(bg=BG_MAIN)
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    root.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - scale_fn(300)) // 2
    y = root.winfo_y() + (root.winfo_height() - scale_fn(130)) // 2
    dialog.geometry(f"{scale_fn(300)}x{scale_fn(130)}+{x}+{y}")

    tk.Label(dialog, text=label_text, bg=BG_MAIN, fg=TEXT_MAIN, font=("Segoe UI", 9)).pack(
        anchor="w", padx=scale_fn(15), pady=(scale_fn(12), scale_fn(4)))
    name_var = tk.StringVar(value=initial_value)
    entry = tk.Entry(dialog, textvariable=name_var, bg=BG_PANEL, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                     relief="flat", highlightthickness=1, highlightbackground=BORDER_COLOR,
                     highlightcolor=ACCENT_BLUE, font=("Segoe UI", 9))
    entry.pack(fill=tk.X, padx=scale_fn(15), ipady=scale_fn(4))
    entry.focus_set()
    entry.icursor(tk.END)
    entry.selection_range(0, tk.END)

    def to_upper(*_):
        if (val := name_var.get()) != val.upper():
            pos = entry.index(tk.INSERT)
            name_var.set(val.upper())
            entry.icursor(pos)

    name_var.trace_add("write", to_upper)

    def on_ok(event=None):
        if not (name := name_var.get().strip()):
            return dialog.destroy()
        try:
            result = submit_fn(name)
            dialog.destroy()
            on_success(result)
        except Exception as e:
            messagebox.showerror("Плейлист", str(e), parent=dialog)

    btns = tk.Frame(dialog, bg=BG_MAIN)
    btns.pack(fill=tk.X, padx=scale_fn(15), pady=scale_fn(12))
    make_button(btns, "OK", on_ok, scale_fn, accent=True, width=10).pack(side=tk.LEFT, expand=True, padx=(0, scale_fn(5)))
    make_button(btns, "Cancel", dialog.destroy, scale_fn, width=10).pack(side=tk.RIGHT, expand=True, padx=(scale_fn(5), 0))
    dialog.bind("<Return>", on_ok)
    dialog.bind("<Escape>", lambda e: dialog.destroy())


def open_create_playlist_dialog(root, scale_fn, photo_icon, on_created):
    _open_playlist_name_dialog(
        root, scale_fn, photo_icon,
        title="Новый плейлист",
        label_text="Название плейлиста:",
        initial_value="",
        submit_fn=Playlists.create_playlist,
        on_success=on_created,
    )


def open_rename_playlist_dialog(root, scale_fn, photo_icon, current_name, on_renamed):
    _open_playlist_name_dialog(
        root, scale_fn, photo_icon,
        title="Переименовать плейлист",
        label_text="Новое название плейлиста:",
        initial_value=current_name,
        submit_fn=lambda new_name: Playlists.rename_playlist(current_name, new_name),
        on_success=on_renamed,
    )


def open_report_dialog(root, scale_fn, photo_icon, song_tuple, source=""):
    link, artist, title, genre = song_tuple
    dialog = tk.Toplevel(root)
    dialog.title("Подать жалобу")
    if photo_icon:
        dialog.iconphoto(False, photo_icon)
    dialog.configure(bg=BG_MAIN)
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    root.update_idletasks()
    w, h = scale_fn(380), scale_fn(250)
    x = root.winfo_x() + (root.winfo_width() - w) // 2
    y = root.winfo_y() + (root.winfo_height() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    track_name = f"{artist or '—'} — {title or '—'}"
    tk.Label(dialog, text=f"Трек: {track_name}", bg=BG_MAIN, fg=TEXT_MAIN,
             font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, padx=scale_fn(15), pady=(scale_fn(12), scale_fn(4)))
    tk.Label(dialog, text="Опишите суть проблемы:", bg=BG_MAIN, fg=TEXT_MUTED,
             font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=scale_fn(15), pady=(0, scale_fn(4)))

    text_box = tk.Text(
        dialog, height=5, bg=BG_PANEL, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
        relief="flat", highlightthickness=1, highlightbackground=BORDER_COLOR,
        highlightcolor=ACCENT_BLUE, font=("Segoe UI", 9), wrap=tk.WORD
    )
    text_box.pack(fill=tk.BOTH, expand=True, padx=scale_fn(15))
    text_box.focus_set()

    def on_send():
        reason = text_box.get("1.0", tk.END).strip()
        if not reason:
            return messagebox.showwarning("Жалоба", "Пожалуйста, опишите суть проблемы.", parent=dialog)
        payload = {
            "link": link,
            "artist": artist or "",
            "title": title or "",
            "genre": genre or "",
            "source": source,
            "reason": reason,
            "timestamp": int(time.time()),
        }
        dialog.destroy()
        threading.Thread(target=_send_report_worker, args=(root, payload), daemon=True).start()

    btns = tk.Frame(dialog, bg=BG_MAIN)
    btns.pack(fill=tk.X, padx=scale_fn(15), pady=scale_fn(12))
    make_button(btns, "Отправить", on_send, scale_fn, accent=True, width=12).pack(side=tk.LEFT, expand=True, padx=(0, scale_fn(5)))
    make_button(btns, "Отмена", dialog.destroy, scale_fn, width=12).pack(side=tk.RIGHT, expand=True, padx=(scale_fn(5), 0))
    dialog.bind("<Escape>", lambda e: dialog.destroy())


def _send_report_worker(root, payload):
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            REPORT_API_URL,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                root.after(0, lambda: messagebox.showinfo("Жалоба", "Жалоба успешно отправлена.", parent=root))
            else:
                root.after(0, lambda: messagebox.showwarning("Жалоба", f"Сервер вернул статус: {resp.status}", parent=root))
    except Exception as e:
        print(f"[REPORT] Ошибка отправки на {REPORT_API_URL}: {e} | Данные: {payload}")
        root.after(0, lambda: messagebox.showinfo(
            "Жалоба", "Запрос сформирован, но сервер недоступен (подробности в консоли).", parent=root
        ))
