"""
Logger
======
Честное логирование без ложных SUCCESS сообщений.
"""

import logging
import sys
from typing import Optional, Callable
from datetime import datetime


class Logger:
    """Модуль логирования"""

    def __init__(self, name: str = "GR7Hub", log_file: Optional[str] = None):
        self.name = name
        self.log_file = log_file
        self._setup_logger()

    def _setup_logger(self) -> None:
        """Настройка логгера"""
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)

        # Очистка существующих handlers
        self.logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '[%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

        # File handler
        if self.log_file:
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)

    def debug(self, message: str) -> None:
        """DEBUG уровень"""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """INFO уровень"""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """WARNING уровень"""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """ERROR уровень"""
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """CRITICAL уровень"""
        self.logger.critical(message)

    def success(self, message: str) -> None:
        """SUCCESS уровень"""
        self.logger.info(message)

    def log(self, message: str, level: str = "info") -> None:
        """Обратная совместимость - универсальный метод логирования"""
        level = level.lower()

        if level == "info":
            return self.info(message)
        elif level == "warning":
            return self.warning(message)
        elif level == "error":
            return self.error(message)
        elif level == "success":
            return self.success(message)
        elif level == "debug":
            return self.debug(message)
        else:
            return self.info(message)

    def log_midi(self, message: str, status: str = "info") -> None:
        """Логирование MIDI событий"""
        prefix = "[MIDI]"
        if status == "error":
            self.error(f"{prefix} {message}")
        elif status == "success":
            self.info(f"{prefix} {message}")
        else:
            self.info(f"{prefix} {message}")

    def log_audio(self, message: str, status: str = "info") -> None:
        """Логирование аудио событий"""
        prefix = "[AUDIO]"
        if status == "error":
            self.error(f"{prefix} {message}")
        elif status == "success":
            self.info(f"{prefix} {message}")
        else:
            self.info(f"{prefix} {message}")

    def log_vst(self, message: str, status: str = "info") -> None:
        """Логирование VST событий"""
        prefix = "[VST3]"
        if status == "error":
            self.error(f"{prefix} {message}")
        elif status == "success":
            self.info(f"{prefix} {message}")
        else:
            self.info(f"{prefix} {message}")

    def log_webrtc(self, message: str, status: str = "info") -> None:
        """Логирование WebRTC событий"""
        prefix = "[WEBRTC]"
        if status == "error":
            self.error(f"{prefix} {message}")
        elif status == "success":
            self.info(f"{prefix} {message}")
        else:
            self.info(f"{prefix} {message}")

    def log_plugin(self, message: str, status: str = "info") -> None:
        """Логирование событий плагина"""
        prefix = "[PLUGIN]"
        if status == "error":
            self.error(f"{prefix} {message}")
        elif status == "success":
            self.info(f"{prefix} {message}")
        else:
            self.info(f"{prefix} {message}")