"""
VST3 Plugin
===========
Управление VST3 плагином.
"""

import numpy as np
from typing import Optional, Dict, Any
from pedalboard import load_plugin, Plugin


class VST3Plugin:
    """Управление VST3 плагином"""

    def __init__(self, plugin_path: str, logger=None):
        self.plugin_path = plugin_path
        self.logger = logger
        self._plugin: Optional[Plugin] = None
        self._sample_rate = 44100
        self._is_loaded = False

    def load(self) -> bool:
        """
        Загрузка VST3 плагина.

        Returns:
            bool: True если успешно загружен
        """
        try:
            if self.logger:
                self.logger.log_vst(f"Загрузка плагина: {self.plugin_path}")

            self._plugin = load_plugin(self.plugin_path)
            self._is_loaded = True

            if self.logger:
                self.logger.log_vst("Плагин успешно загружен", "success")

            return True

        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка загрузки плагина: {e}", "error")
            self._is_loaded = False
            return False

    def unload(self) -> None:
        """Выгрузка плагина"""
        self._plugin = None
        self._is_loaded = False

    def process(self, input_data: np.ndarray) -> np.ndarray:
        """
        Обработка аудио через плагин.

        Args:
            input_data: Входные данные (channels, frames)

        Returns:
            np.ndarray: Выходные данные
        """
        if not self._is_loaded or self._plugin is None:
            if self.logger:
                self.logger.log_vst("Плагин не загружен", "error")
            return input_data

        try:
            # Транспонируем для pedalboard: (frames, channels)
            input_channels = input_data.T.astype(np.float32)
            output_channels = self._plugin(input_channels, sample_rate=self._sample_rate, reset=False)
            return output_channels.T

        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка обработки: {e}", "error")
            return input_data

    def set_parameter(self, param_name: str, value: float) -> bool:
        """
        Установка параметра плагина.

        Args:
            param_name: Имя параметра
            value: Значение (0.0 - 1.0)

        Returns:
            bool: True если успешно
        """
        if not self._is_loaded or self._plugin is None:
            return False

        try:
            if hasattr(self._plugin, param_name):
                setattr(self._plugin, param_name, value)
                return True
            return False
        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка установки параметра {param_name}: {e}", "error")
            return False

    def get_parameter(self, param_name: str) -> Optional[float]:
        """
        Получение значения параметра плагина.

        Args:
            param_name: Имя параметра

        Returns:
            float: Значение параметра или None
        """
        if not self._is_loaded or self._plugin is None:
            return None

        try:
            if hasattr(self._plugin, param_name):
                return getattr(self._plugin, param_name)
            return None
        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка получения параметра {param_name}: {e}", "error")
            return None

    def get_parameters(self) -> Dict[str, float]:
        """
        Получение всех параметров плагина.

        Returns:
            Dict[str, float]: Словарь параметров
        """
        if not self._is_loaded or self._plugin is None:
            return {}

        params = {}
        try:
            for attr in dir(self._plugin):
                if not attr.startswith('_') and not callable(getattr(self._plugin, attr)):
                    try:
                        value = getattr(self._plugin, attr)
                        if isinstance(value, (int, float)):
                            params[attr] = float(value)
                    except:
                        pass
        except Exception as e:
            if self.logger:
                self.logger.log_vst(f"Ошибка получения параметров: {e}", "error")

        return params

    def get_info(self) -> Dict[str, Any]:
        """
        Получение информации о плагине.

        Returns:
            Dict[str, Any]: Информация о плагине
        """
        info = {
            'path': self.plugin_path,
            'loaded': self._is_loaded,
            'sample_rate': self._sample_rate
        }

        if self._is_loaded and self._plugin:
            info['name'] = getattr(self._plugin, 'name', 'Unknown')
            info['parameters'] = self.get_parameters()

        return info

    @property
    def is_loaded(self) -> bool:
        """Статус загрузки плагина"""
        return self._is_loaded

    @property
    def plugin(self) -> Optional[Plugin]:
        """Ссылка на плагин"""
        return self._plugin