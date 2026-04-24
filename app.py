import configparser
import logging
import os
import queue
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
import numpy as np
import pyautogui
import pygame
import serial
from flask import Flask, jsonify
from werkzeug.serving import make_server

try:
    import sounddevice as sd
except Exception:
    sd = None


APP_PORT = 5000
CONFIG_FILE = "config.ini"
FOLDER_BUTTON_IMAGE = "folder_btn.png"
VALID_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg"}


class TkTextHandler(logging.Handler):
    """Logging handler that routes logs to the GUI queue."""

    def __init__(self, ui_queue: queue.Queue):
        super().__init__()
        self.ui_queue = ui_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.ui_queue.put(message)
        except Exception:
            self.handleError(record)


class FlaskThread(threading.Thread):
    def __init__(self, app: Flask, host: str, port: int, logger: logging.Logger):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.logger = logger
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self) -> None:
        self.logger.info("Flask server started on http://%s:%s", self.host, self.port)
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.logger.info("Flask server is shutting down")
        self.server.shutdown()


class GuitarRigControllerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Guitar Rig 7 Tone Switch")
        self.geometry("980x680")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.logger = self._setup_logger()

        self.config = configparser.ConfigParser()
        self.music_folder = ""
        self.audio_files: List[str] = []
        self.current_track_index = -1

        self.flask_thread: Optional[FlaskThread] = None
        self.serial_thread: Optional[threading.Thread] = None
        self.serial_connection: Optional[serial.Serial] = None
        self.serial_stop_event = threading.Event()
        self.server_started = False
        self.host_ip = self._resolve_local_ip()

        self.bt_status_var = ctk.StringVar(value="Disabled")
        self.ip_status_var = ctk.StringVar(value=f"{self.host_ip}:{APP_PORT}")
        self.folder_status_var = ctk.StringVar(value="Checking startup requirement...")

        self._load_config()
        self._build_ui()
        self._check_folder_button_image(show_success=False)
        self._poll_log_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("guitar_rig_switch")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

        file_handler = logging.FileHandler("app_debug.log", mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        gui_handler = TkTextHandler(self.log_queue)
        gui_handler.setFormatter(formatter)
        gui_handler.setLevel(logging.INFO)

        logger.addHandler(file_handler)
        logger.addHandler(gui_handler)
        logger.propagate = False
        return logger

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")
        status_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(status_frame, text="Flask IP:Port:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=8, pady=8, sticky="w"
        )
        ctk.CTkLabel(status_frame, textvariable=self.ip_status_var).grid(row=0, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(status_frame, text="Bluetooth COM:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=2, padx=8, pady=8, sticky="w"
        )
        ctk.CTkLabel(status_frame, textvariable=self.bt_status_var).grid(row=0, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(status_frame, text="Startup Check:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=8, pady=8, sticky="w"
        )
        self.startup_check_label = ctk.CTkLabel(status_frame, textvariable=self.folder_status_var, text_color="orange")
        self.startup_check_label.grid(row=1, column=1, columnspan=2, padx=8, pady=8, sticky="w")

        self.refresh_button = ctk.CTkButton(status_frame, text="Refresh", width=90, command=self._refresh_startup_check)
        self.refresh_button.grid(row=1, column=3, padx=8, pady=8, sticky="e")

        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=1, column=0, padx=14, pady=8, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(action_frame, text="Music Folder:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.music_folder_entry = ctk.CTkEntry(action_frame)
        self.music_folder_entry.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.music_folder_entry.insert(0, self.music_folder)

        ctk.CTkButton(action_frame, text="Browse", command=self._browse_music_folder, width=100).grid(
            row=0, column=2, padx=8, pady=8
        )
        ctk.CTkButton(action_frame, text="Start Services", command=self._start_services).grid(
            row=1, column=0, padx=8, pady=8, sticky="w"
        )
        ctk.CTkButton(action_frame, text="Launch Visualizer", command=self._launch_visualizer_thread).grid(
            row=1, column=1, padx=8, pady=8, sticky="w"
        )

        self.com_entry = ctk.CTkEntry(action_frame, placeholder_text="COM Port e.g. COM5")
        self.com_entry.grid(row=1, column=2, padx=8, pady=8, sticky="ew")

        self.log_box = ctk.CTkTextbox(self, wrap="word")
        self.log_box.grid(row=2, column=0, padx=14, pady=(8, 14), sticky="nsew")
        self.log_box.insert("end", "Console Log initialized...\n")
        self.log_box.configure(state="disabled")

    def _append_gui_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        while not self.log_queue.empty():
            self._append_gui_log(self.log_queue.get())
        self.after(120, self._poll_log_queue)

    def _resolve_local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def _load_config(self) -> None:
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE)
            self.music_folder = self.config.get("paths", "music_folder", fallback="")

    def _save_config(self) -> None:
        if "paths" not in self.config:
            self.config["paths"] = {}
        self.config["paths"]["music_folder"] = self.music_folder
        with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
            self.config.write(config_file)
        self.logger.info("Saved music folder to config.ini: %s", self.music_folder)

    def _check_folder_button_image(self, show_success: bool = True) -> bool:
        exists = Path(FOLDER_BUTTON_IMAGE).exists()
        if exists:
            self.folder_status_var.set("'folder_btn.png' found. Ready.")
            self.startup_check_label.configure(text_color="green")
            if show_success:
                self.logger.info("Startup check passed: folder_btn.png found")
            return True

        error_msg = (
            "Error: 'folder_btn.png' not found. Please take a small screenshot of the "
            "'Open Folder' icon in Guitar Rig 7 and place it in the app folder."
        )
        self.folder_status_var.set(error_msg)
        self.startup_check_label.configure(text_color="red")
        self.logger.error(error_msg)
        return False

    def _refresh_startup_check(self) -> None:
        self._check_folder_button_image(show_success=True)

    def _browse_music_folder(self) -> None:
        from tkinter import filedialog

        folder = filedialog.askdirectory()
        if not folder:
            return
        self.music_folder = folder
        self.music_folder_entry.delete(0, "end")
        self.music_folder_entry.insert(0, folder)
        self._save_config()
        self._refresh_audio_file_cache()

    def _refresh_audio_file_cache(self) -> None:
        selected_folder = self.music_folder_entry.get().strip()
        if selected_folder:
            self.music_folder = selected_folder

        if not self.music_folder or not Path(self.music_folder).is_dir():
            self.audio_files = []
            self.logger.error("Music folder invalid or missing: %s", self.music_folder)
            return

        files = []
        for item in Path(self.music_folder).iterdir():
            if item.is_file() and item.suffix.lower() in VALID_AUDIO_EXTENSIONS:
                files.append(item.name)

        self.audio_files = sorted(files, key=str.lower)
        self.logger.info("Scanned %d valid audio files from: %s", len(self.audio_files), self.music_folder)

    def _build_flask_app(self) -> Flask:
        app = Flask(__name__)

        @app.route("/list", methods=["GET"])
        def list_tracks():
            self._refresh_audio_file_cache()
            self.logger.info("HTTP /list requested (%d files)", len(self.audio_files))
            return jsonify(self.audio_files)

        @app.route("/play/<path:filename>", methods=["GET"])
        def play_track(filename: str):
            self._refresh_audio_file_cache()
            if filename not in self.audio_files:
                self.logger.error("HTTP /play rejected. File not found in allowed list: %s", filename)
                return jsonify({"success": False, "error": "file not found"}), 404

            full_path = str(Path(self.music_folder) / filename)
            ok = self.load_track(full_path)
            return jsonify({"success": ok, "filename": filename})

        return app

    def _start_services(self) -> None:
        if not self._check_folder_button_image(show_success=True):
            return

        self._refresh_audio_file_cache()
        if not self.music_folder:
            self.logger.error("Cannot start services: set a music folder first")
            return

        if not self.server_started:
            flask_app = self._build_flask_app()
            self.flask_thread = FlaskThread(flask_app, "0.0.0.0", APP_PORT, self.logger)
            self.flask_thread.start()
            self.server_started = True

        com_port = self.com_entry.get().strip()
        if com_port:
            self._start_serial_listener(com_port)
        else:
            self.bt_status_var.set("Disabled")
            self.logger.info("Bluetooth serial listener disabled (no COM port specified)")

    def _start_serial_listener(self, com_port: str) -> None:
        if self.serial_thread and self.serial_thread.is_alive():
            self.logger.info("Serial listener already running")
            return

        try:
            self.serial_connection = serial.Serial(com_port, 9600, timeout=0.2)
            self.serial_stop_event.clear()
            self.serial_thread = threading.Thread(target=self._serial_loop, daemon=True)
            self.serial_thread.start()
            self.bt_status_var.set(f"Active ({com_port})")
            self.logger.info("Bluetooth serial listener started on %s", com_port)
        except Exception as exc:
            self.bt_status_var.set("Disabled")
            self.logger.error("Failed to open COM port %s: %s", com_port, exc)

    def _serial_loop(self) -> None:
        while not self.serial_stop_event.is_set() and self.serial_connection:
            try:
                incoming = self.serial_connection.read(1)
                if incoming == b"1":
                    self.logger.info("Bluetooth command '1' received: loading next track")
                    self._load_next_track()
            except Exception as exc:
                self.logger.error("Serial listener error: %s", exc)
                break

    def _load_next_track(self) -> None:
        self._refresh_audio_file_cache()
        if not self.audio_files:
            self.logger.error("No valid audio files available to load")
            return

        self.current_track_index = (self.current_track_index + 1) % len(self.audio_files)
        filename = self.audio_files[self.current_track_index]
        full_path = str(Path(self.music_folder) / filename)
        self.load_track(full_path)

    def load_track(self, file_path: str) -> bool:
        try:
            self.logger.info("Automation step 1: finding folder button image on screen")
            location = pyautogui.locateOnScreen(FOLDER_BUTTON_IMAGE, confidence=0.8)
            if location is None:
                self.logger.error("Automation failed: folder button image was not found on screen")
                return False

            self.logger.info("Automation step 2: clicking folder button center")
            center = pyautogui.center(location)
            pyautogui.click(center)

            time.sleep(0.8)

            self.logger.info("Automation step 3: typing full file path")
            pyautogui.write(file_path)

            self.logger.info("Automation step 4: pressing Enter")
            pyautogui.press("enter")

            self.logger.info("Track loaded successfully: %s", file_path)
            return True
        except Exception as exc:
            self.logger.error("Automation error while loading '%s': %s", file_path, exc)
            return False

    def _launch_visualizer_thread(self) -> None:
        thread = threading.Thread(target=self._run_visualizer, daemon=True)
        thread.start()
        self.logger.info("Visualizer launched")

    def _run_visualizer(self) -> None:
        pygame.init()
        width, height = 1000, 700
        screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        pygame.display.set_caption("Guitar Rig 7 Visualizer")
        clock = pygame.time.Clock()

        fft_bins = 256
        ring_points = 96
        phase = 0.0

        audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        stop_audio = threading.Event()

        def audio_callback(indata, frames, _time_info, _status):
            if stop_audio.is_set():
                return
            channel_data = np.mean(indata, axis=1)
            try:
                audio_queue.put_nowait(channel_data.copy())
            except queue.Full:
                pass

        stream = None
        if sd:
            try:
                stream = sd.InputStream(channels=2, callback=audio_callback, samplerate=44100, blocksize=1024)
                stream.start()
            except Exception as exc:
                self.logger.error("Visualizer audio input unavailable: %s", exc)
        else:
            self.logger.error("Visualizer audio backend not available. Install sounddevice.")

        waveform = np.zeros(1024, dtype=np.float32)

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    width, height = max(640, event.w), max(420, event.h)
                    screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)

            while not audio_queue.empty():
                waveform = audio_queue.get()

            if len(waveform) < 2:
                spectrum = np.zeros(fft_bins)
            else:
                windowed = waveform * np.hanning(len(waveform))
                fft_vals = np.abs(np.fft.rfft(windowed))
                spectrum = np.interp(
                    np.linspace(0, len(fft_vals) - 1, fft_bins),
                    np.arange(len(fft_vals)),
                    fft_vals,
                )

            bass_energy = float(np.mean(spectrum[:16])) if spectrum.size else 0.0
            high_energy = float(np.mean(spectrum[80:200])) if spectrum.size else 0.0

            bass_scale = min(2.8, 1.0 + bass_energy / 150.0)
            ray_boost = min(240.0, 20.0 + high_energy / 6.0)

            center = (width // 2, height // 2)
            base_radius = int(min(width, height) * 0.14 * bass_scale)
            phase += 0.018

            screen.fill((6, 8, 18))

            points = []
            for i in range(ring_points):
                angle = 2 * np.pi * i / ring_points
                freq_idx = int(i / ring_points * min(fft_bins - 1, 220))
                amp = spectrum[freq_idx] if spectrum.size else 0.0
                ray_length = base_radius + min(ray_boost, amp / 2.2)
                wobble = 8.0 * np.sin(phase * 4 + i * 0.8)
                px = center[0] + (ray_length + wobble) * np.cos(angle)
                py = center[1] + (ray_length + wobble) * np.sin(angle)
                points.append((px, py))

            pygame.draw.polygon(screen, (30, 110, 200), points, width=2)
            pygame.draw.circle(screen, (130, 200, 255), center, base_radius, width=3)
            pygame.draw.circle(screen, (80, 150, 255), center, int(base_radius * 0.62))

            timestamp = datetime.now().strftime("%H:%M:%S")
            caption = f"Stereo Mix / Mic FFT Visualizer  |  {timestamp}"
            pygame.display.set_caption(caption)
            pygame.display.flip()
            clock.tick(60)

        stop_audio.set()
        if stream:
            stream.stop()
            stream.close()
        pygame.quit()

    def _on_close(self) -> None:
        try:
            if self.flask_thread:
                self.flask_thread.shutdown()
            self.serial_stop_event.set()
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
        finally:
            self.destroy()


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = GuitarRigControllerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
