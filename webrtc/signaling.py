"""
WebRTCSignaling
==============
Firebase signaling для WebRTC соединения.
"""

import asyncio
import time
import uuid
from typing import Optional, Dict, Any
from datetime import datetime


class WebRTCSignaling:
    """WebRTC signaling через Firebase"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self._firebase_available = False
        self._firebase_app = None
        self._db_ref = None
        self._room_id = None
        self._pc = None
        self._running = False

    def initialize(self) -> bool:
        """
        Инициализация Firebase.

        Returns:
            bool: True если успешно
        """
        try:
            # Проверка доступности Firebase
            try:
                import firebase_admin
                from firebase_admin import credentials, db
                self._firebase_available = True
            except ImportError:
                if self.logger:
                    self.logger.log_webrtc("Firebase не установлен", "error")
                return False

            # Инициализация Firebase
            firebase_project = self.config.get('webrtc', 'firebase_project', '')
            firebase_key = self.config.get('webrtc', 'firebase_key', '')

            if not firebase_project or not firebase_key:
                if self.logger:
                    self.logger.log_webrtc("Firebase credentials не настроены", "error")
                return False

            # Создание credentials
            cred = credentials.Certificate(firebase_key)
            self._firebase_app = firebase_admin.initialize_app(cred, {
                'databaseURL': f'https://{firebase_project}.firebaseio.com/'
            })

            if self.logger:
                self.logger.log_webrtc("Firebase инициализирован", "success")

            return True

        except Exception as e:
            if self.logger:
                self.logger.log_webrtc(f"Ошибка инициализации Firebase: {e}", "error")
            return False

    def create_room(self) -> str:
        """
        Создание новой комнаты.

        Returns:
            str: ID комнаты
        """
        self._room_id = str(uuid.uuid4())[:8]
        self._running = True

        if self._firebase_available and self._firebase_app:
            try:
                from firebase_admin import db
                ref = db.reference(f'rooms/{self._room_id}')
                ref.set({
                    'status': 'created',
                    'created_at': int(time.time()),
                    'connected': False
                })
                if self.logger:
                    self.logger.log_webrtc(f"Комната создана: {self._room_id}", "success")
            except Exception as e:
                if self.logger:
                    self.logger.log_webrtc(f"Ошибка создания комнаты: {e}", "error")

        return self._room_id

    def get_room_id(self) -> Optional[str]:
        """Получение ID текущей комнаты"""
        return self._room_id

    def cleanup_room(self) -> None:
        """Очистка комнаты"""
        if self._room_id and self._firebase_available:
            try:
                from firebase_admin import db
                ref = db.reference(f'rooms/{self._room_id}')
                ref.delete()
                if self.logger:
                    self.logger.log_webrtc(f"Комната {self._room_id} очищена", "info")
            except Exception as e:
                if self.logger:
                    self.logger.log_webrtc(f"Ошибка очистки комнаты: {e}", "error")

        self._room_id = None
        self._running = False

    def is_running(self) -> bool:
        """Статус работы"""
        return self._running

    def shutdown(self) -> None:
        """Остановка"""
        self.cleanup_room()
        if self._firebase_app:
            try:
                firebase_admin.delete_app(self._firebase_app)
            except:
                pass
        if self.logger:
            self.logger.log_webrtc("WebRTC signaling остановлен", "info")