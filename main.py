import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import pygame
import pystray
from PIL import Image, ImageDraw, ImageFont
from pynput import mouse

try:
    import winreg
except ImportError:
    winreg = None


APP_NAME = "TykClicker"
APP_TITLE = "Тык-кликер"
BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
SOUND_FILE = BASE_DIR / "sounds" / "click.mp3"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULT_SETTINGS = {
    "volume": 35,
    "sound_enabled": True,
    "text_enabled": True,
    "autostart": False,
}


class TykClickerApp:
    def __init__(self):
        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("380x250")
        self.root.resizable(False, False)

        self.sound_ready = False
        self.click_sound = None
        self.tray_icon = None
        self.mouse_listener = None
        self.running = True
        self.last_click_time = 0.0

        self.volume_var = tk.IntVar(value=self.settings["volume"])
        self.sound_var = tk.BooleanVar(value=self.settings["sound_enabled"])
        self.text_var = tk.BooleanVar(value=self.settings["text_enabled"])
        self.autostart_var = tk.BooleanVar(value=self.settings["autostart"])

        self._init_sound()
        self._build_ui()
        self._sync_autostart_state()
        self._start_tray()
        self._start_mouse_listener()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def _init_sound(self):
        if not SOUND_FILE.exists() or SOUND_FILE.stat().st_size == 0:
            return

        try:
            pygame.mixer.init()
            self.click_sound = pygame.mixer.Sound(str(SOUND_FILE))
            self.click_sound.set_volume(self.settings["volume"] / 100)
            self.sound_ready = True
        except pygame.error:
            self.sound_ready = False
            self.click_sound = None

    def _build_ui(self):
        self.root.configure(bg="#f4f4f4")

        main = tk.Frame(self.root, bg="#f4f4f4", padx=22, pady=18)
        main.pack(fill="both", expand=True)

        title = tk.Label(
            main,
            text="🔊 Громкость клика:",
            font=("Segoe UI", 11),
            bg="#f4f4f4",
            anchor="w",
        )
        title.pack(fill="x")

        volume_row = tk.Frame(main, bg="#f4f4f4")
        volume_row.pack(fill="x", pady=(6, 18))

        volume_slider = tk.Scale(
            volume_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self.on_volume_change,
            length=240,
            showvalue=False,
            bg="#f4f4f4",
            highlightthickness=0,
        )
        volume_slider.pack(side="left")

        self.volume_label = tk.Label(
            volume_row,
            text=f"{self.volume_var.get()}%",
            width=5,
            font=("Segoe UI", 10),
            bg="#f4f4f4",
            anchor="e",
        )
        self.volume_label.pack(side="left", padx=(12, 0))

        buttons = tk.Frame(main, bg="#f4f4f4")
        buttons.pack(fill="x", pady=(0, 16))

        self.sound_button = tk.Button(
            buttons,
            width=15,
            command=self.toggle_sound,
            font=("Segoe UI", 10),
        )
        self.sound_button.pack(side="left")

        self.text_button = tk.Button(
            buttons,
            width=15,
            command=self.toggle_text,
            font=("Segoe UI", 10),
        )
        self.text_button.pack(side="left", padx=(12, 0))

        self.autostart_checkbox = tk.Checkbutton(
            main,
            text="🚀 Запускать при старте Windows",
            variable=self.autostart_var,
            command=self.on_autostart_change,
            bg="#f4f4f4",
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.autostart_checkbox.pack(fill="x", pady=(0, 18))

        hide_button = tk.Button(
            main,
            text="Скрыть в трей",
            command=self.hide_window,
            font=("Segoe UI", 10),
            width=18,
        )
        hide_button.pack()

        self._refresh_toggle_buttons()

    def _sync_autostart_state(self):
        current_state = is_autostart_enabled()
        if current_state != self.settings["autostart"]:
            self.settings["autostart"] = current_state
            self.autostart_var.set(current_state)
            save_settings(self.settings)

    def _start_tray(self):
        self.tray_icon = pystray.Icon(
            APP_NAME,
            create_tray_image(),
            APP_TITLE,
            menu=pystray.Menu(
                pystray.MenuItem("Показать окно", self.show_window, default=True),
                pystray.MenuItem("Выход", self.exit_app),
            ),
        )
        self.tray_icon.run_detached()

    def _start_mouse_listener(self):
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        self.mouse_listener.daemon = True
        self.mouse_listener.start()

    def on_mouse_click(self, x, y, button, pressed):
        if not pressed or button != mouse.Button.left or not self.running:
            return

        # Prevent immediate double handling from some touchpads and virtual devices.
        now = time.monotonic()
        if now - self.last_click_time < 0.03:
            return
        self.last_click_time = now

        if self.sound_var.get():
            self.play_click_sound()
        if self.text_var.get():
            self.root.after(0, lambda: self.show_tyk_text(x, y))

    def play_click_sound(self):
        if not self.sound_ready or self.click_sound is None:
            return

        try:
            self.click_sound.set_volume(self.volume_var.get() / 100)
            self.click_sound.play()
        except pygame.error:
            self.sound_ready = False

    def show_tyk_text(self, x, y):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg="#ffffff")

        try:
            popup.attributes("-transparentcolor", "#ffffff")
        except tk.TclError:
            pass

        label = tk.Label(
            popup,
            text="тык",
            fg="#808080",
            bg="#ffffff",
            font=("Segoe UI", 14),
            padx=0,
            pady=0,
        )
        label.pack()
        popup.geometry(f"+{int(x) + 15}+{int(y) - 20}")
        popup.after(400, popup.destroy)

    def on_volume_change(self, value):
        volume = int(float(value))
        self.volume_label.config(text=f"{volume}%")
        self.settings["volume"] = volume
        if self.click_sound is not None:
            self.click_sound.set_volume(volume / 100)
        save_settings(self.settings)

    def toggle_sound(self):
        self.sound_var.set(not self.sound_var.get())
        self.settings["sound_enabled"] = self.sound_var.get()
        self._refresh_toggle_buttons()
        save_settings(self.settings)

    def toggle_text(self):
        self.text_var.set(not self.text_var.get())
        self.settings["text_enabled"] = self.text_var.get()
        self._refresh_toggle_buttons()
        save_settings(self.settings)

    def on_autostart_change(self):
        enabled = self.autostart_var.get()

        try:
            if enabled:
                enable_autostart()
            else:
                disable_autostart()
        except OSError as exc:
            self.autostart_var.set(not enabled)
            messagebox.showwarning(
                APP_TITLE,
                f"Не удалось изменить автозагрузку Windows:\n{exc}",
            )
            return

        self.settings["autostart"] = enabled
        save_settings(self.settings)

    def _refresh_toggle_buttons(self):
        sound_text = "🔊 Звук: ВКЛ" if self.sound_var.get() else "🔇 Звук: ВЫКЛ"
        text_text = "📝 Текст: ВКЛ" if self.text_var.get() else "📝 Текст: ВЫКЛ"
        self.sound_button.config(text=sound_text)
        self.text_button.config(text=text_text)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._show_window_from_main_thread)

    def _show_window_from_main_thread(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self, icon=None, item=None):
        self.running = False
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        try:
            pygame.mixer.quit()
        except pygame.error:
            pass
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    settings_exists = SETTINGS_FILE.exists()

    if settings_exists:
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    settings["volume"] = max(0, min(100, int(settings.get("volume", 35))))
    settings["sound_enabled"] = bool(settings.get("sound_enabled", True))
    settings["text_enabled"] = bool(settings.get("text_enabled", True))
    settings["autostart"] = bool(settings.get("autostart", False))
    if not settings_exists:
        save_settings(settings)
    return settings


def save_settings(settings):
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_pythonw_path():
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw
    return executable


def get_autostart_command():
    pythonw_path = get_pythonw_path()
    script_path = Path(__file__).resolve()
    return f'"{pythonw_path}" "{script_path}"'


def enable_autostart():
    if winreg is None:
        raise OSError("Автозагрузка через реестр доступна только в Windows.")

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_autostart_command())


def disable_autostart():
    if winreg is None:
        raise OSError("Автозагрузка через реестр доступна только в Windows.")

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass


def is_autostart_enabled():
    if winreg is None:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return value == get_autostart_command()
    except OSError:
        return False


def create_tray_image():
    image = Image.new("RGBA", (64, 64), "#808080")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 38)
    except OSError:
        font = ImageFont.load_default()

    text = "Т"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (64 - text_width) / 2
    y = (64 - text_height) / 2 - 3
    draw.text((x, y), text, fill="#ffffff", font=font)
    return image


def main():
    app = TykClickerApp()
    app.run()


if __name__ == "__main__":
    main()
