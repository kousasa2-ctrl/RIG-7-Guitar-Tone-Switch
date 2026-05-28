"""
AudioService
==============
Сервис управления аудио движком.
"""

from typing import Optional, Callable
import numpy as np
from audio.engine import AudioEngine
from core.state_manager import StateManager
from core.logger import Logger


class AudioService:
    """Сервис управления аудио движком"""

    def __init__(self, config, state_manager: StateManager, logger: Logger):
        self.config = config
        self.state_manager = state_manager
        self.logger = logger
        self.engine: Optional[AudioEngine] = None
        self._initialized = False
        self._callback: Optional[Callable] = None

    def initialize(self) -> bool:
        """
        Инициализация сервиса.

        Returns:
            bool: True если успешно
        """
        try:
            self.engine = AudioEngine(self.config, self.logger)

            if not self.engine.initialize():
                self.state_manager.update_state(audio_engine_active=False)
                return False

            self._initialized = True
            self.state_manager.update_state(audio_engine_active=True)
            self.logger.log_audio("AudioService инициализирован", "success")
            return True

        except Exception as e:
            self.logger.log_audio(f"Ошибка инициализации: {e}", "error")
            self.state_manager.update_state(audio_engine_active=False)
            return False

    def start(self, callback: Callable) -> None:
        """
        Запуск аудио потока.

        Args:
            callback: Функция обратного вызова
        """
        if self._initialized and self.engine:
            self._callback = callback
            self.engine.start(callback)
            self.state_manager.update_state(audio_engine_active=True)
            self.logger.log_audio("Аудио поток запущен", "success")

    def stop(self) -> None:
        """Остановка аудио потока"""
        if self.engine:
            self.engine.stop()
            self.state_manager.update_state(audio_engine_active=False)
            self.logger.log_audio("Аудио поток остановлен", "info")

    def process_audio(self, input_data: np.ndarray) -> np.ndarray:
        """
        Обработка аудио.

        Args:
            input_data: Входные данные

        Returns:
            np.ndarray: Выходные данные
        """
        if self.engine:
            return self.engine.process_audio(input_data)
        return input_data

    def get_status(self) -> dict:
        """Получение статуса"""
        if self.engine:
            return self.engine.get_status()
        return {'initialized': False, 'running': False}

    def shutdown(self) -> None:
        """Остановка сервиса"""
        self.stop()
        if self.engine:
            self.engine.shutdown()
            self.engine = None
        self._initialized = False
        self.logger.log_audio("AudioService остановлен", "info")