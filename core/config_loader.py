"""
Config Loader
==============
Загрузка и сохранение конфигурации.
"""

import configparser
import os
from typing import Dict, Any


class ConfigLoader:
    """Загрузчик конфигурации"""

    DEFAULT_CONFIG = {
        'vst3': {
            'path': r'C:\Program Files\Common Files\VST3\Native Instruments\Guitar Rig 7.vst3',
            'auto_load': 'true'
        },
        'midi': {
            'virtual_port_name': 'GR7 Hub Control',
            'channel': '0',
            'auto_create': 'true'
        },
        'audio': {
            'device_input': '',
            'device_output': '',
            'sample_rate': '44100',
            'buffer_size': '256',
            'asio_driver': ''
        },
        'webrtc': {
            'enabled': 'true',
            'firebase_project': '',
            'firebase_key': ''
        },
        'network': {
            'api_port': '5000',
            'lan_mode': 'true'
        }
    }

    def __init__(self, config_path: str = "config.ini"):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._load()

    def _load(self) -> None:
        """Загрузка конфигурации"""
        if not os.path.exists(self.config_path):
            self._create_default_config()
        self.config.read(self.config_path, encoding='utf-8')

    def _create_default_config(self) -> None:
        """Создание конфигурации по умолчанию"""
        for section, options in self.DEFAULT_CONFIG.items():
            if section not in self.config:
                self.config[section] = {}
            for key, value in options.items():
                self.config[section][key] = value
        self._save()

    def _save(self) -> None:
        """Сохранение конфигурации"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """Получение значения из конфигурации"""
        if section in self.config and key in self.config[section]:
            return self.config[section][key]
        return fallback

    def set(self, section: str, key: str, value: str) -> None:
        """Установка значения в конфигурацию"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        self._save()

    def get_section(self, section: str) -> Dict[str, str]:
        """Получение всей секции"""
        if section in self.config:
            return dict(self.config[section])
        return {}

    def get_all(self) -> Dict[str, Dict[str, str]]:
        """Получение всех секций"""
        return {section: dict(self.config[section]) for section in self.config}