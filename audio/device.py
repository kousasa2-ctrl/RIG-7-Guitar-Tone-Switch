"""
AudioDevice
===========
Управление аудио устройствами.
"""

import sounddevice as sd
from typing import List, Dict, Any, Optional
import numpy as np


class AudioDevice:
    """Управление аудио устройством"""

    def __init__(self, logger=None):
        self.logger = logger
        self._devices = None
        self._input_device = None
        self._output_device = None
        self._sample_rate = 44100
        self._buffer_size = 256

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Получение списка аудио устройств.

        Returns:
            List[Dict]: Список устройств
        """
        try:
            self._devices = sd.query_devices()
            return self._devices
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка получения устройств: {e}", "error")
            return []

    def get_default_input_device(self) -> Optional[Dict[str, Any]]:
        """Получение устройства по умолчанию для ввода"""
        try:
            return sd.query_devices(sd.default.device[0], 'input')
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка получения входного устройства: {e}", "error")
            return None

    def get_default_output_device(self) -> Optional[Dict[str, Any]]:
        """Получение устройства по умолчанию для вывода"""
        try:
            return sd.query_devices(sd.default.device[1], 'output')
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка получения выходного устройства: {e}", "error")
            return None

    def get_device_info(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение информации об устройстве.

        Args:
            device_id: ID устройства

        Returns:
            Dict: Информация об устройстве
        """
        try:
            return sd.query_devices(device_id)
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка получения информации: {e}", "error")
            return None

    def is_asio_device(self, device_id: int) -> bool:
        """
        Проверка, является ли устройство ASIO.

        Args:
            device_id: ID устройства

        Returns:
            bool: True если ASIO
        """
        try:
            device = self.get_device_info(device_id)
            if device:
                return 'ASIO' in device['name'].upper()
            return False
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка проверки ASIO: {e}", "error")
            return False

    def get_asio_devices(self) -> List[Dict[str, Any]]:
        """
        Получение списка ASIO устройств.

        Returns:
            List[Dict]: Список ASIO устройств
        """
        devices = self.get_devices()
        return [d for d in devices if self.is_asio_device(d['index'])]

    def get_low_latency_devices(self) -> List[Dict[str, Any]]:
        """
        Получение устройств с низкой задержкой.

        Returns:
            List[Dict]: Список устройств с низкой задержкой
        """
        devices = self.get_devices()
        low_latency = []

        for device in devices:
            if device['max_output_channels'] > 0:
                latency = device['default_low_output_latency']
                if latency < 0.1:  # Менее 100мс
                    low_latency.append(device)

        return low_latency

    def get_buffer_size_info(self, device_id: int) -> Dict[str, Any]:
        """
        Получение информации о размерах буфера для устройства.

        Args:
            device_id: ID устройства

        Returns:
            Dict: Информация о буферах
        """
        try:
            device = self.get_device_info(device_id)
            if device:
                return {
                    'default_low': device['default_low_output_latency'],
                    'default_high': device['default_high_output_latency'],
                    'default': device['default_samplerate'],
                    'max': device['default_high_output_latency']
                }
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка получения информации о буфере: {e}", "error")

        return {}

    @property
    def sample_rate(self) -> int:
        """Текущая частота дискретизации"""
        return self._sample_rate

    @property
    def buffer_size(self) -> int:
        """Текущий размер буфера"""
        return self._buffer_size

    def set_sample_rate(self, sample_rate: int) -> bool:
        """Установка частоты дискретизации"""
        try:
            self._sample_rate = sample_rate
            return True
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка установки частоты: {e}", "error")
            return False

    def set_buffer_size(self, buffer_size: int) -> bool:
        """Установка размера буфера"""
        try:
            self._buffer_size = buffer_size
            return True
        except Exception as e:
            if self.logger:
                self.logger.log_audio(f"Ошибка установки буфера: {e}", "error")
            return False