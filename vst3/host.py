"""
VST3 Host
=========
Основной класс для управления VST3 хостингом.
"""

import threading
import numpy as np
from typing import Optional, Callable, List
from .plugin import VST3Plugin


class VST3Host:
    """VST3 хостинг движок"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.plugin: Optional[VST3Plugin] = None
        self._audio_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._callback: Optional[Callable] = None

    def initialize(self) -> bool:
        """
        Инициализация VST3 хоста.

        Returns:
            bool: True если успешно
        """
        try:
            plugin_path = self.config.get('vst3', 'path')
            if not plugin_path:
                if self.logger:
                    self.logger.log_vst("Путь к VST3 плагину не указан", "error")
                return False

            self.plugin = VST3Plugin(plugin_path, self.logger)

            if not self.plugin.load():
                return False

            if self.logger:
                self.logger.log_vst("VST3 хост инициализирован", "success")

            return True

        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка инициализации VST3 хоста: {e}", "error")
            return False

    def start_audio_thread(self, callback: Callable) -> None:
        """
        Запуск аудио потока.

        Args:
            callback: Функция обратного вызова для обработки аудио
        """
        with self._lock:
            if self._running:
                return

            self._callback = callback
            self._running = True
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()

            if self.logger:
                self.logger.log_vst("Аудио поток запущен", "success")

    def stop_audio_thread(self) -> None:
        """Остановка аудио потока"""
        with self._lock:
            self._running = False
            if self._audio_thread:
                self._audio_thread.join(timeout=1.0)
                self._audio_thread = None

            if self.logger:
                self.logger.log_vst("Аудио поток остановлен", "info")

    def _audio_loop(self) -> None:
        """Цикл аудио обработки"""
        while self._running:
            try:
                if self._callback:
                    self._callback()
            except Exception as e:
                if self.logger:
                    self.logger.log_vst(f"Ошибка в аудио цикле: {e}", "error")
                break

    def process_audio(self, input_data: np.ndarray) -> np.ndarray:
        """
        Обработка аудио через плагин.

        Args:
            input_data: Входные данные

        Returns:
            np.ndarray: Выходные данные
        """
        if self.plugin:
            return self.plugin.process(input_data)
        return input_data

    def send_program_change(self, program_id: int) -> bool:
        """
        Отправка Program Change (перезагрузка плагина с новым preset).

        Args:
            program_id: ID пресета

        Returns:
            bool: True если успешно
        """
        if not self.plugin or not self.plugin.is_loaded:
            if self.logger:
                self.logger.log_vst("Плагин не загружен", "error")
            return False

        try:
            # Перезагрузка плагина для смены preset
            self.plugin.unload()
            if self.plugin.load():
                if self.logger:
                    self.logger.log_vst(f"Пресет переключен: {program_id}", "success")
                return True
            return False
        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка переключения пресета: {e}", "error")
            return False

    def send_control_change(self, controller: int, value: int) -> bool:
        """
        Отправка Control Change.

        Args:
            controller: Номер контроллера
            value: Значение (0-127)

        Returns:
            bool: True если успешно
        """
        if not self.plugin or not self.plugin.is_loaded:
            if self.logger:
                self.logger.log_vst("Плагин не загружен", "error")
            return False

        try:
            # Получаем параметры плагина и пытаемся найти соответствующий
            params = self.plugin.get_parameters()
            for param_name, param_value in params.items():
                if controller == int(param_value * 127):
                    self.plugin.set_parameter(param_name, value / 127.0)
                    if self.logger:
                        self.logger.log_vst(f"CC {controller} -> {param_name}", "success")
                    return True
            return False
        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка отправки CC: {e}", "error")
            return False

    def get_status(self) -> dict:
        """
        Получение статуса хоста.

        Returns:
            dict: Статус
        """
        status = {
            'initialized': self.plugin is not None,
            'plugin_loaded': self.plugin.is_loaded if self.plugin else False,
            'audio_running': self._running,
            'info': self.plugin.get_info() if self.plugin else {}
        }
        return status

    def shutdown(self) -> None:
        """Остановка и очистка"""
        self.stop_audio_thread()
        if self.plugin:
            self.plugin.unload()
            self.plugin = None

        if self.logger:
            self.logger.log_vst("VST3 хост остановлен", "info")