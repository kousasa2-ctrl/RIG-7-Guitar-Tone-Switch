"""
AudioEngine
===========
Аудио движок с поддержкой ASIO и WASAPI.
"""

import threading
import numpy as np
from typing import Optional, Callable, Dict, Any
from .device import AudioDevice


class AudioEngine:
    """Аудио движок"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.device = AudioDevice(logger)
        self._audio_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._callback: Optional[Callable] = None
        self._input_device_id = None
        self._output_device_id = None
        self._input_channels = 2
        self._output_channels = 2

    def initialize(self) -> bool:
        """
        Инициализация аудио движка.

        Returns:
            bool: True если успешно
        """
        try:
            # Получение настроек из конфигурации
            self._input_device_id = self.config.get('audio', 'device_input', '')
            self._output_device_id = self.config.get('audio', 'device_output', '')
            self._sample_rate = int(self.config.get('audio', 'sample_rate', '44100'))
            self._buffer_size = int(self.config.get('audio', 'buffer_size', '256'))

            # Установка параметров
            self.device.set_sample_rate(self._sample_rate)
            self.device.set_buffer_size(self._buffer_size)

            if self.logger:
                self.logger.log_audio("Аудио движок инициализирован", "success")

            return True

        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка инициализации: {e}", "error")
            return False

    def start(self, callback: Callable) -> None:
        """
        Запуск аудио потока.

        Args:
            callback: Функция обратного вызова (input_data) -> output_data
        """
        with self._lock:
            if self._running:
                return

            self._callback = callback
            self._running = True
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()

            if self.logger:
                self.logger.log_audio("Аудио поток запущен", "success")

    def stop(self) -> None:
        """Остановка аудио потока"""
        with self._lock:
            self._running = False
            if self._audio_thread:
                self._audio_thread.join(timeout=1.0)
                self._audio_thread = None

            if self.logger:
                self.logger.log_audio("Аудио поток остановлен", "info")

    def _audio_loop(self) -> None:
        """Цикл аудио обработки"""
        while self._running:
            try:
                if self._callback:
                    self._callback()
            except Exception as e:
                if self.logger:
                    self.logger.log_audio(f"Ошибка в аудио цикле: {e}", "error")
                break

    def process_audio(self, input_data: np.ndarray) -> np.ndarray:
        """
        Обработка аудио.

        Args:
            input_data: Входные данные (channels, frames)

        Returns:
            np.ndarray: Выходные данные
        """
        if self._callback:
            try:
                return self._callback(input_data)
            except Exception as e:
                if self.logger:
                    self.logger.log_audio(f"Ошибка обработки: {e}", "error")
        return input_data

    def get_status(self) -> Dict[str, Any]:
        """
        Получение статуса движка.

        Returns:
            Dict: Статус
        """
        status = {
            'running': self._running,
            'sample_rate': self._sample_rate,
            'buffer_size': self._buffer_size,
            'input_device': self._input_device_id,
            'output_device': self._output_device_id,
            'devices': self.device.get_devices()
        }
        return status

    def shutdown(self) -> None:
        """Остановка и очистка"""
        self.stop()
        if self.logger:
            self.logger.log_audio("Аудио движок остановлен", "info")