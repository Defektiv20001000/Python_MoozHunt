import json, threading, time, urllib.request
import tkinter as tk
from tkinter import messagebox

from . import playlists
from .theme import (
    ACCENT_BLUE, BG_HEADER, BG_MAIN, BG_PANEL, BORDER_COLOR,
    REPORT_API_URL, TEXT_MAIN, TEXT_MUTED, create_scrollbar_tree, make_button
)

def _init_modal(root, scale_fn, photo_icon, title, width, height, resizable=False):
    dialog = tk.Toplevel(root)
    dialog.title(title)
    if photo_icon:
        try:
            dialog.iconphoto(False, photo_icon)
        except Exception:
            pass
    dialog.configure(bg=BG_MAIN)
    dialog.resizable(resizable, resizable)
    dialog.transient(root)
    dialog.grab_set()

    root.update_idletasks()
    w, h = scale_fn(width), scale_fn(height)
    x = root.winfo_x() + (root.winfo_width() - w) // 2
    y = root.winfo_y() + (root.winfo_height() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    return dialog


def _open_playlist_name_dialog(
    root, scale_fn, photo_icon, title, label_text, initial_value, submit_fn, on_success, on_delete=None
):
    width = 340 if on_delete else 300
    dialog = _init_modal(root, scale_fn, photo_icon, title, width, 130)

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

    def on_ok(_event=None):
        if not (name := name_var.get().strip()):
            return dialog.destroy()
        try:
            result = submit_fn(name)
            dialog.destroy()
            on_success(result)
        except Exception as e:
            messagebox.showerror("Плейлист", str(e), parent=dialog)

    def handle_delete():
        if messagebox.askyesno(
            "Удаление плейлиста",
            f"Удалить плейлист «{initial_value}» и все его файлы?",
            parent=dialog
        ):
            try:
                on_delete(initial_value)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Плейлист", f"Не удалось удалить плейлист: {e}", parent=dialog)

    btns = tk.Frame(dialog, bg=BG_MAIN)
    btns.pack(fill=tk.X, padx=scale_fn(15), pady=scale_fn(12))

    if on_delete:
        btns.grid_columnconfigure((0, 1, 2), weight=1, uniform="pl_btns")
        make_button(btns, "OK", on_ok, scale_fn, accent=True).grid(row=0, column=0, sticky="ew", padx=(0, scale_fn(4)))
        make_button(btns, "Удалить", handle_delete, scale_fn).grid(row=0, column=1, sticky="ew", padx=scale_fn(2))
        make_button(btns, "Отмена", dialog.destroy, scale_fn).grid(row=0, column=2, sticky="ew", padx=(scale_fn(4), 0))
    else:
        make_button(btns, "OK", on_ok, scale_fn, accent=True, width=10).pack(
            side=tk.LEFT, expand=True, padx=(0, scale_fn(5))
        )
        make_button(btns, "Отмена", dialog.destroy, scale_fn, width=10).pack(
            side=tk.RIGHT, expand=True, padx=(scale_fn(5), 0)
        )

    dialog.bind("<Return>", on_ok)


def open_create_playlist_dialog(root, scale_fn, photo_icon, on_created):
    _open_playlist_name_dialog(
        root, scale_fn, photo_icon,
        title="Новый плейлист",
        label_text="Название плейлиста:",
        initial_value="",
        submit_fn=playlists.create_playlist,
        on_success=on_created,
    )


def open_rename_playlist_dialog(root, scale_fn, photo_icon, current_name, on_renamed, on_deleted=None):
    _open_playlist_name_dialog(
        root, scale_fn, photo_icon,
        title="Переименовать плейлист",
        label_text="Новое название плейлиста:",
        initial_value=current_name,
        submit_fn=lambda new_name: playlists.rename_playlist(current_name, new_name),
        on_success=on_renamed,
        on_delete=on_deleted,
    )


def open_report_dialog(root, scale_fn, photo_icon, song_tuple, source=""):
    link, artist, title, genre = song_tuple
    dialog = _init_modal(root, scale_fn, photo_icon, "Подать жалобу", 380, 250)

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


def open_bad_songs_dialog(root, scale_fn, photo_icon, bad_songs, on_changed):
    win = _init_modal(root, scale_fn, photo_icon, "Плохой список треков", 640, 440, resizable=True)
    win.minsize(scale_fn(480), scale_fn(340))

    header = tk.Frame(win, bg=BG_HEADER, padx=scale_fn(12), pady=scale_fn(8))
    header.pack(fill=tk.X)
    tk.Label(
        header, text="Треки, исключённые из рекомендаций и поиска",
        bg=BG_HEADER, fg=TEXT_MAIN, font=("Segoe UI", 10, "bold")
    ).pack(side=tk.LEFT)

    body = tk.Frame(win, bg=BG_MAIN, padx=scale_fn(10), pady=scale_fn(10))
    body.pack(fill=tk.BOTH, expand=True)

    bad_tree = create_scrollbar_tree(
        body, (("Исполнитель", scale_fn(170)), ("Название", scale_fn(220)), ("Жанр", scale_fn(130))), scale_fn
    )
    bad_map = {}

    def populate():
        bad_tree.delete(*bad_tree.get_children())
        bad_map.clear()
        for link, info in bad_songs.items():
            item = bad_tree.insert(
                "", tk.END,
                values=(info.get("artist") or "—", info.get("title") or "—", info.get("genre") or "—")
            )
            bad_map[item] = link

    def restore_selected(_event=None):
        removed = [bad_map[i] for i in bad_tree.selection() if bad_map.get(i) in bad_songs]
        if removed:
            for link in removed:
                del bad_songs[link]
            populate()
            on_changed()

    def clear_all():
        if bad_songs and messagebox.askyesno("Очистка", "Вернуть все треки из плохого списка?", parent=win):
            bad_songs.clear()
            populate()
            on_changed()

    bad_menu = tk.Menu(
        win, tearoff=0, bg=BG_HEADER, fg=TEXT_MAIN, activebackground=ACCENT_BLUE,
        activeforeground=TEXT_MAIN, bd=1, relief="solid", font=("Segoe UI", 9)
    )
    bad_menu.add_command(label="Вернуть из плохого списка", command=restore_selected)

    def on_right_click(event):
        if row := bad_tree.identify_row(event.y):
            if row not in bad_tree.selection():
                bad_tree.selection_set(row)
                bad_tree.focus(row)
            bad_menu.tk_popup(event.x_root, event.y_root)

    bad_tree.bind("<Double-1>", restore_selected)
    bad_tree.bind("<Button-3>", on_right_click)
    populate()

    footer = tk.Frame(win, bg=BG_HEADER, padx=scale_fn(12), pady=scale_fn(8))
    footer.pack(fill=tk.X)
    make_button(footer, "Вернуть выбранные", restore_selected, scale_fn, accent=True).pack(side=tk.LEFT)
    make_button(footer, "Очистить весь список", clear_all, scale_fn).pack(side=tk.LEFT, padx=(scale_fn(8), 0))
    make_button(footer, "Закрыть", win.destroy, scale_fn).pack(side=tk.RIGHT)
