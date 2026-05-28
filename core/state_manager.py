"""
State Manager
==============
Централизованное управление состоянием приложения.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import threading


class SystemState(Enum):
    """Состояния системы"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class SystemState:
    """Состояние системы"""
    state: SystemState = SystemState.IDLE
    plugin_loaded: bool = False
    audio_engine_active: bool = False
    midi_active: bool = False
    webrtc_active: bool = False
    current_preset: Optional[int] = None
    active_device: Optional[str] = None
    error_message: Optional[str] = None
    _lock = threading.Lock()

    def set_state(self, new_state: SystemState) -> None:
        """Установка нового состояния"""
        with self._lock:
            self.state = new_state

    def set_plugin_loaded(self, loaded: bool) -> None:
        """Установка статуса загрузки плагина"""
        with self._lock:
            self.plugin_loaded = loaded

    def set_audio_active(self, active: bool) -> None:
        """Установка статуса аудио движка"""
        with self._lock:
            self.audio_engine_active = active

    def set_midi_active(self, active: bool) -> None:
        """Установка статуса MIDI"""
        with self._lock:
            self.midi_active = active

    def set_webrtc_active(self, active: bool) -> None:
        """Установка статуса WebRTC"""
        with self._lock:
            self.webrtc_active = active

    def set_preset(self, preset_id: int) -> None:
        """Установка текущего пресета"""
        with self._lock:
            self.current_preset = preset_id

    def set_error(self, message: str) -> None:
        """Установка сообщения об ошибке"""
        with self._lock:
            self.state = SystemState.ERROR
            self.error_message = message

    def get_state_dict(self) -> Dict[str, Any]:
        """Получение словаря состояния"""
        with self._lock:
            return {
                'state': self.state.value,
                'plugin_loaded': self.plugin_loaded,
                'audio_engine_active': self.audio_engine_active,
                'midi_active': self.midi_active,
                'webrtc_active': self.webrtc_active,
                'current_preset': self.current_preset,
                'active_device': self.active_device,
                'error_message': self.error_message
            }


class StateManager:
    """Менеджер состояния приложения"""

    def __init__(self):
        self.state = SystemState()
        self.listeners = []
        self._lock = threading.Lock()

    def add_listener(self, callback) -> None:
        """Добавление слушателя изменений состояния"""
        with self._lock:
            self.listeners.append(callback)

    def remove_listener(self, callback) -> None:
        """Удаление слушателя"""
        with self._lock:
            if callback in self.listeners:
                self.listeners.remove(callback)

    def notify_listeners(self) -> None:
        """Уведомление всех слушателей"""
        with self._lock:
            state_dict = self.state.get_state_dict()
            for callback in self.listeners:
                try:
                    callback(state_dict)
                except Exception:
                    pass

    def update_state(self, **kwargs) -> None:
        """Обновление состояния"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)
            self.notify_listeners()