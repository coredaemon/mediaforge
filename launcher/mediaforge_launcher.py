from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import BOTH, DISABLED, NORMAL, Button, Label, StringVar, Tk, messagebox

from launcher.core import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    build_backend_command,
    configure_logger,
    detect_running_backend,
    find_free_port,
    find_project_root,
    log_path,
    start_backend,
    stop_process,
    ui_url,
    wait_for_health,
)


class MediaForgeLauncher:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("MediaForge")
        self.root.geometry("520x220")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status = StringVar(value="Статус: запускается...")
        self.backend = StringVar(value="Backend: ожидаем")
        self.address = StringVar(value=f"Адрес: http://{DEFAULT_HOST}:{DEFAULT_PORT}")
        self.log_file = log_path()
        self.logger = configure_logger(self.log_file)
        self.process = None
        self.running_url: str | None = None
        self.started_process = False

        Label(self.root, text="MediaForge", font=("Segoe UI", 16, "bold")).pack(pady=(16, 8))
        Label(self.root, textvariable=self.status, anchor="w").pack(fill=BOTH, padx=20)
        Label(self.root, textvariable=self.backend, anchor="w").pack(fill=BOTH, padx=20)
        Label(self.root, textvariable=self.address, anchor="w").pack(fill=BOTH, padx=20)
        Label(self.root, text=f"Лог: {self.log_file}", anchor="w").pack(fill=BOTH, padx=20, pady=(0, 12))

        self.open_button = Button(self.root, text="Открыть в браузере", command=self.open_browser, state=DISABLED)
        self.open_button.pack(side="left", padx=(20, 8), pady=10)
        self.stop_button = Button(self.root, text="Остановить", command=self.stop_backend, state=DISABLED)
        self.stop_button.pack(side="left", padx=8, pady=10)
        Button(self.root, text="Закрыть", command=self.on_close).pack(side="right", padx=(8, 20), pady=10)

    def run(self) -> None:
        threading.Thread(target=self.start, daemon=True).start()
        self.root.mainloop()

    def set_status(self, status: str, backend: str | None = None) -> None:
        self.root.after(0, lambda: self.status.set(f"Статус: {status}"))
        if backend is not None:
            self.root.after(0, lambda: self.backend.set(f"Backend: {backend}"))

    def start(self) -> None:
        self.logger.info("Launcher started")
        try:
            project_root = find_project_root()
            port = DEFAULT_PORT if detect_running_backend(DEFAULT_HOST, DEFAULT_PORT) else find_free_port(DEFAULT_HOST, DEFAULT_PORT)
            self.running_url = ui_url(DEFAULT_HOST, port)
            self.root.after(0, lambda: self.address.set(f"Адрес: {self.running_url}"))
            self.logger.info("Selected port: %s", port)

            if detect_running_backend(DEFAULT_HOST, port):
                self.set_status("MediaForge уже запущен", "запущен")
                self.logger.info("Detected existing backend on %s", self.running_url)
                self.enable_running_actions(stop_enabled=False)
                self.open_browser()
                return

            command = build_backend_command(project_root, DEFAULT_HOST, port)
            self.process = start_backend(command, self.log_file, self.logger)
            self.started_process = True
            self.enable_running_actions(stop_enabled=True)
            self.set_status("ожидаем backend...", "запускается")

            if not wait_for_health(DEFAULT_HOST, port, logger=self.logger):
                self.set_status("ошибка запуска", "не отвечает")
                self.logger.error("Backend health did not become ready")
                messagebox.showerror(
                    "MediaForge",
                    f"Не удалось запустить MediaForge.\nПроверьте лог: {self.log_file}",
                )
                return

            self.set_status("MediaForge работает", "запущен")
            self.logger.info("Backend is healthy")
            self.open_browser()
        except Exception as exc:  # noqa: BLE001 - launcher must surface startup errors
            self.logger.exception("Launcher startup failed")
            self.set_status("ошибка запуска", "ошибка")
            messagebox.showerror("MediaForge", f"Не удалось запустить MediaForge.\n{exc}\nЛог: {self.log_file}")

    def enable_running_actions(self, *, stop_enabled: bool) -> None:
        self.root.after(0, lambda: self.open_button.config(state=NORMAL))
        self.root.after(0, lambda: self.stop_button.config(state=NORMAL if stop_enabled else DISABLED))

    def open_browser(self) -> None:
        if not self.running_url:
            return
        self.logger.info("Opening browser: %s", self.running_url)
        self.set_status("открываю браузер")
        webbrowser.open(self.running_url)

    def stop_backend(self) -> None:
        if not self.started_process:
            return
        stop_process(self.process, self.logger)
        self.started_process = False
        self.set_status("остановлен", "остановлен")
        self.root.after(0, lambda: self.stop_button.config(state=DISABLED))

    def on_close(self) -> None:
        if self.started_process and self.process is not None and self.process.poll() is None:
            should_stop = messagebox.askyesno("MediaForge", "Остановить backend перед закрытием launcher?")
            if should_stop:
                self.stop_backend()
        self.root.destroy()


def main() -> None:
    MediaForgeLauncher().run()


if __name__ == "__main__":
    main()

