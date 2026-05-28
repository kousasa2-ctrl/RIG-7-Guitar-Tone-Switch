"""
WebRTCService
==============
Сервис управления WebRTC.
"""

from typing import Optional
from webrtc.stream import WebRTCStream
from core.state_manager import StateManager
from core.logger import Logger


class WebRTCService:
    """Сервис управления WebRTC"""

    def __init__(self, config, state_manager: StateManager, logger: Logger):
        self.config = config
        self.state_manager = state_manager
        self.logger = logger
        self.stream: Optional[WebRTCStream] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Инициализация сервиса.

        Returns:
            bool: True если успешно
        """
        try:
            self.stream = WebRTCStream(self.config, self.logger)

            if not self.stream.initialize():
                self.state_manager.update_state(webrtc_active=False)
                return False

            self._initialized = True
            self.state_manager.update_state(webrtc_active=True)
            self.logger.log_webrtc("WebRTCService инициализирован", "success")
            return True

        except Exception as e:
            self.logger.log_webrtc(f"Ошибка инициализации: {e}", "error")
            self.state_manager.update_state(webrtc_active=False)
            return False

    def create_room(self) -> str:
        """
        Создание комнаты.

        Returns:
            str: ID комнаты
        """
        if not self._initialized or not self.stream:
            self.logger.log_webrtc("WebRTC не инициализирован", "error")
            return ""

        room_id = self.stream.signaling.create_room()
        return room_id

    def get_status(self) -> dict:
        """Получение статуса"""
        if self.stream:
            return self.stream.get_status()
        return {'initialized': False, 'running': False}

    def shutdown(self) -> None:
        """Остановка сервиса"""
        if self.stream:
            self.stream.shutdown()
            self.stream = None
        self._initialized = False
        self.logger.log_webrtc("WebRTCService остановлен", "info")