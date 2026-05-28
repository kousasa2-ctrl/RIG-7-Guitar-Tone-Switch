"""
AudioUtils
==========
Утилиты для аудио обработки.
"""

import numpy as np
from typing import Tuple, Optional


class AudioUtils:
    """Утилиты для аудио"""

    @staticmethod
    def normalize_audio(data: np.ndarray, target_level: float = 0.9) -> np.ndarray:
        """
        Нормализация аудио.

        Args:
            data: Аудио данные
            target_level: Целевой уровень

        Returns:
            np.ndarray: Нормализованные данные
        """
        if data.size == 0:
            return data

        max_val = np.max(np.abs(data))
        if max_val > 0:
            data = data * (target_level / max_val)
        return data

    @staticmethod
    def apply_gain(data: np.ndarray, gain: float) -> np.ndarray:
        """
        Применение усиления.

        Args:
            data: Аудио данные
            gain: Коэффициент усиления

        Returns:
            np.ndarray: Усиленные данные
        """
        return data * gain

    @staticmethod
    def convert_to_float32(data: np.ndarray) -> np.ndarray:
        """
        Конвертация в float32.

        Args:
            data: Аудио данные

        Returns:
            np.ndarray: Данные в float32
        """
        if data.dtype != np.float32:
            data = data.astype(np.float32)
        return data

    @staticmethod
    def convert_to_int16(data: np.ndarray) -> np.ndarray:
        """
        Конвертация в int16.

        Args:
            data: Аудио данные

        Returns:
            np.ndarray: Данные в int16
        """
        if data.dtype != np.int16:
            data = (data * 32767).astype(np.int16)
        return data

    @staticmethod
    def mix_channels(data: np.ndarray, channels: int) -> np.ndarray:
        """
        Микширование каналов.

        Args:
            data: Аудио данные (channels, frames)
            channels: Количество каналов

        Returns:
            np.ndarray: Микшированные данные
        """
        if data.ndim == 1:
            return data

        if data.shape[0] > channels:
            # Усреднение каналов
            mixed = np.mean(data[:channels], axis=0)
        else:
            # Повторение каналов
            mixed = np.tile(data, (channels, 1))

        return mixed

    @staticmethod
    def split_channels(data: np.ndarray, channels: int) -> np.ndarray:
        """
        Разделение каналов.

        Args:
            data: Аудио данные (frames,)
            channels: Количество каналов

        Returns:
            np.ndarray: Данные (channels, frames)
        """
        if data.ndim == 2:
            return data

        frames = len(data)
        result = np.zeros((channels, frames), dtype=data.dtype)

        for i in range(channels):
            result[i, :] = data

        return result

    @staticmethod
    def get_rms(data: np.ndarray) -> float:
        """
        Получение RMS уровня.

        Args:
            data: Аудио данные

        Returns:
            float: RMS значение
        """
        if data.size == 0:
            return 0.0
        return np.sqrt(np.mean(data ** 2))

    @staticmethod
    def get_peak(data: np.ndarray) -> float:
        """
        Получение пикового значения.

        Args:
            data: Аудио данные

        Returns:
            float: Пиковое значение
        """
        if data.size == 0:
            return 0.0
        return np.max(np.abs(data))