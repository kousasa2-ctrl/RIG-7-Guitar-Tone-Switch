"""
MIDIService
==============
Сервис управления MIDI.
"""

from typing import Optional, Callable
from midi.router import MIDIRouter
from core.state_manager import StateManager
from core.logger import Logger


class MIDIService:
    """Сервис управления MIDI"""

    def __init__(self, config, state_manager: StateManager, logger: Logger):
        self.config = config
        self.state_manager = state_manager
        self.logger = logger
        self.router: Optional[MIDIRouter] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Инициализация сервиса.

        Returns:
            bool: True если успешно
        """
        try:
            self.router = MIDIRouter(self.config, self.logger)

            if not self.router.initialize():
                self.state_manager.update_state(midi_active=False)
                return False

            self._initialized = True
            self.state_manager.update_state(midi_active=True)
            self.logger.log_midi("MIDIService инициализирован", "success")
            return True

        except Exception as e:
            self.logger.log_midi(f"Ошибка инициализации: {e}", "error")
            self.state_manager.update_state(midi_active=False)
            return False

    def send_program_change(self, program_id: int, channel: int = 0) -> bool:
        """
        Отправка Program Change.

        Args:
            program_id: ID пресета
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self._initialized or not self.router:
            self.logger.log_midi("MIDI не инициализирован", "error")
            return False

        return self.router.send_program_change(program_id, channel)

    def send_control_change(self, controller: int, value: int, channel: int = 0) -> bool:
        """
        Отправка Control Change.

        Args:
            controller: Номер контроллера
            value: Значение
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self._initialized or not self.router:
            return False

        return self.router.send_control_change(controller, value, channel)

    def send_note_on(self, note: int, velocity: int = 64, channel: int = 0) -> bool:
        """
        Отправка Note On.

        Args:
            note: Номер ноты
            velocity: Скорость
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self._initialized or not self.router:
            return False

        return self.router.send_note_on(note, velocity, channel)

    def send_note_off(self, note: int, channel: int = 0) -> bool:
        """
        Отправка Note Off.

        Args:
            note: Номер ноты
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self._initialized or not self.router:
            return False

        return self.router.send_note_off(note, channel)

    def get_status(self) -> dict:
        """Получение статуса"""
        if self.router:
            return self.router.get_status()
        return {'initialized': False, 'port_active': False}

    def shutdown(self) -> None:
        """Остановка сервиса"""
        if self.router:
            self.router.shutdown()
            self.router = None
        self._initialized = False
        self.logger.log_midi("MIDIService остановлен", "info")