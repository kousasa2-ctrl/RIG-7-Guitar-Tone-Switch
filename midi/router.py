"""
MIDIRouter
==========
Маршрутизация MIDI сообщений.
"""

from typing import Optional, Callable, List
from .virtual_midi import VirtualMIDIPort


class MIDIRouter:
    """Маршрутизатор MIDI сообщений"""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.virtual_port: Optional[VirtualMIDIPort] = None
        self._listeners: List[Callable] = []
        self._running = False

    def initialize(self) -> bool:
        """
        Инициализация MIDI маршрутизатора.

        Returns:
            bool: True если успешно
        """
        try:
            port_name = self.config.get('midi', 'virtual_port_name', 'GR7 Hub Control')
            self.virtual_port = VirtualMIDIPort(port_name, self.logger)

            if not self.virtual_port.initialize():
                if self.logger:
                    self.logger.log_midi("Ошибка инициализации виртуального порта", "error")
                return False

            if self.logger:
                self.logger.log_midi("MIDI маршрутизатор инициализирован", "success")

            return True

        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка инициализации: {e}", "error")
            return False

    def add_listener(self, callback: Callable) -> None:
        """
        Добавление слушателя MIDI сообщений.

        Args:
            callback: Функция обратного вызова (message_dict)
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Удаление слушателя"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def send_program_change(self, program_id: int, channel: int = 0) -> bool:
        """
        Отправка Program Change.

        Args:
            program_id: ID пресета
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self.virtual_port:
            if self.logger:
                self.logger.log_midi("MIDI порт не инициализирован", "error")
            return False

        return self.virtual_port.send_program_change(program_id, channel)

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
        if not self.virtual_port:
            return False

        return self.virtual_port.send_control_change(controller, value, channel)

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
        if not self.virtual_port:
            return False

        return self.virtual_port.send_note_on(note, velocity, channel)

    def send_note_off(self, note: int, channel: int = 0) -> bool:
        """
        Отправка Note Off.

        Args:
            note: Номер ноты
            channel: MIDI канал

        Returns:
            bool: True если успешно
        """
        if not self.virtual_port:
            return False

        return self.virtual_port.send_note_off(note, channel)

    def get_status(self) -> dict:
        """
        Получение статуса маршрутизатора.

        Returns:
            dict: Статус
        """
        status = {
            'initialized': self.virtual_port is not None,
            'port_active': self.virtual_port.is_initialized if self.virtual_port else False,
            'listeners_count': len(self._listeners)
        }
        return status

    def shutdown(self) -> None:
        """Остановка маршрутизатора"""
        if self.virtual_port:
            self.virtual_port.close()
            self.virtual_port = None

        if self.logger:
            self.logger.log_midi("MIDI маршрутизатор остановлен", "info")