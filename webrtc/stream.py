"""
WebRTCStream
============
WebRTC поток для стриминга аудио.
"""

import asyncio
import numpy as np
from typing import Optional, Callable
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from .signaling import WebRTCSignaling


class WebRTCStream:
    """WebRTC поток"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.signaling = WebRTCSignaling(config, logger)
        self._pc: Optional[RTCPeerConnection] = None
        self._audio_track = None
        self._running = False
        self._ice_connected = False
        self._latency = 0

    def initialize(self) -> bool:
        """
        Инициализация WebRTC потока.

        Returns:
            bool: True если успешно
        """
        if not self.signaling.initialize():
            if self.logger:
                self.logger.log_webrtc("Ошибка инициализации signaling", "error")
            return False

        if self.logger:
            self.logger.log_webrtc("WebRTC поток инициализирован", "success")

        return True

    async def create_offer(self) -> str:
        """
        Создание SDP offer.

        Returns:
            str: SDP offer
        """
        self._pc = RTCPeerConnection()

        # Создание аудио track
        self._audio_track = self._create_audio_track()

        @self._pc.on('track')
        def on_track(track):
            if track.kind == 'audio':
                self._audio_track = track
                if self.logger:
                    self.logger.log_webrtc("Аудио track получен", "info")

        # Создание offer
        offer = await self._pc.create_offer()
        await self._pc.setLocalDescription(offer)

        # Ожидание ICE candidates
        ice_candidates = []
        @self._pc.on('icecandidate')
        def on_ice_candidate(candidate):
            if candidate:
                ice_candidates.append({
                    'candidate': candidate.candidate,
                    'sdpMid': candidate.sdpMid,
                    'sdpMLineIndex': candidate.sdpMLineIndex
                })

        # Ожидание ICE connected
        @self._pc.on('connectionstatechange')
        def on_connection_state_change(state):
            if state == 'connected':
                self._ice_connected = True
                if self.logger:
                    self.logger.log_webrtc("ICE connected", "success")
            elif state == 'disconnected':
                self._ice_connected = False
                if self.logger:
                    self.logger.log_webrtc("ICE disconnected", "error")

        return self._pc.localDescription.sdp

    async def set_remote_description(self, sdp: str) -> bool:
        """
        Установка remote description.

        Args:
            sdp: SDP description

        Returns:
            bool: True если успешно
        """
        if not self._pc:
            return False

        try:
            await self._pc.setRemoteDescription(RTCSessionDescription(sdp, 'answer'))
            if self.logger:
                self.logger.log_webrtc("Remote description установлен", "success")
            return True
        except Exception as e:
            if self.logger:
                self.logger.log_webrtc(f"Ошибка установки remote description: {e}", "error")
            return False

    def _create_audio_track(self):
        """Создание аудио track"""
        # В реальном приложении здесь будет MediaStreamTrack
        # Для тестирования создаем заглушку
        class AudioTrack:
            kind = 'audio'
            def __init__(self):
                self._data = np.zeros((2, 1024), dtype=np.float32)

            def read(self, frames):
                return self._data

            def stop(self):
                pass

        return AudioTrack()

    def send_audio(self, audio_data: np.ndarray) -> None:
        """
        Отправка аудио данных.

        Args:
            audio_data: Аудио данные (channels, frames)
        """
        if self._audio_track and self._ice_connected:
            try:
                # В реальном приложении здесь будет отправка через WebRTC
                pass
            except Exception as e:
                if self.logger:
                    self.logger.log_webrtc(f"Ошибка отправки аудио: {e}", "error")

    def get_status(self) -> dict:
        """
        Получение статуса потока.

        Returns:
            dict: Статус
        """
        return {
            'running': self._running,
            'ice_connected': self._ice_connected,
            'latency': self._latency,
            'room_id': self.signaling.get_room_id()
        }

    def start(self) -> bool:
        """Запуск потока"""
        if not self.signaling.is_running():
            return False

        self._running = True
        if self.logger:
            self.logger.log_webrtc("WebRTC поток запущен", "success")
        return True

    def stop(self) -> None:
        """Остановка потока"""
        self._running = False
        self._ice_connected = False
        if self._pc:
            self._pc.close()
            self._pc = None

        if self.logger:
            self.logger.log_webrtc("WebRTC поток остановлен", "info")

    def shutdown(self) -> None:
        """Остановка и очистка"""
        self.stop()
        self.signaling.shutdown()