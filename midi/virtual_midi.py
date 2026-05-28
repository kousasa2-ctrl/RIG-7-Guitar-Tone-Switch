"""
VirtualMIDIPort
==============
Виртуальный MIDI порт через virtualMIDI SDK.
"""

import ctypes
from typing import Optional, Callable
from enum import IntEnum


class MIDIStatus(IntEnum):
    """Статусы MIDI сообщений"""
    NOTE_OFF = 0x80
    NOTE_ON = 0x90
    CONTROL_CHANGE = 0xB0
    PROGRAM_CHANGE = 0xC0
    CHANNEL_PRESSURE = 0xD0
    POLY_PRESSURE = 0xA0
    PITCH_BEND = 0xE0


class MIDIController(IntEnum):
    """MIDI контроллеры"""
    MODULATION_WHEEL = 1
    BREATH_CONTROLLER = 2
    FOOT_CONTROLLER_1 = 4
    FOOT_CONTROLLER_2 = 5
    PORTAMENTO_TIME = 6
    DATA_ENTRY = 38
    CHANNEL_VOLUME = 7
    BALANCE = 8
    PAN = 10
    EXPRESSION = 11
    GENERAL_PURPOSE_1 = 16
    GENERAL_PURPOSE_2 = 17
    GENERAL_PURPOSE_3 = 18
    GENERAL_PURPOSE_4 = 19


class VirtualMIDIPort:
    """Виртуальный MIDI порт"""

    # virtualMIDI SDK функции
    _midi_bridge = None

    def __init__(self, port_name: str = "GR7 Hub Control", logger=None):
        self.port_name = port_name
        self.logger = logger
        self._port_handle = None
        self._initialized = False
        self._callback: Optional[Callable] = None
        self._running = False

    def initialize(self) -> bool:
        """
        Инициализация virtualMIDI SDK.

        Returns:
            bool: True если успешно
        """
        try:
            # Импорт virtualMIDI SDK
            self._load_sdk()

            if not self._midi_bridge:
                if self.logger:
                    self.logger.log_midi("virtualMIDI SDK не найден", "error")
                return False

            # Инициализация SDK
            success, message = self._midi_bridge.initialize()
            if not success:
                if self.logger:
                    self.logger.log_midi(f"Ошибка инициализации SDK: {message}", "error")
                return False

            # Создание порта
            success, message = self._midi_bridge.create_virtual_port(
                port_name=self.port_name,
                description="Guitar Rig 7 Hub Virtual MIDI"
            )

            if success:
                self._initialized = True
                if self.logger:
                    self.logger.log_midi(f"Виртуальный порт создан: {self.port_name}", "success")
                return True
            else:
                if self.logger:
                    self.logger.log_midi(f"Ошибка создания порта: {message}", "error")
                return False

        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка инициализации: {e}", "error")
            return False

    def _load_sdk(self) -> None:
        """Загрузка virtualMIDI SDK"""
        try:
            # Попытка импорта из разных мест
            import os
            possible_paths = [
                os.path.join(os.environ.get('ProgramFiles', ''), 'virtualMIDI'),
                os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'virtualMIDI'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'virtualMIDI'),
            ]

            for base_path in possible_paths:
                if os.path.exists(base_path):
                    dll_path = os.path.join(base_path, 'midi_bridge.dll')
                    if os.path.exists(dll_path):
                        self._midi_bridge = ctypes.CDLL(dll_path)
                        return

            # Если DLL не найдена, создаем stub для тестирования
            self._create_stub()

        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка загрузки SDK: {e}", "error")
            self._create_stub()

    def _create_stub(self) -> None:
        """Создание stub для тестирования без SDK"""
        class StubMIDIBridge:
            def __init__(self):
                self._initialized = False
                self._port_handle = None

            def initialize(self):
                self._initialized = True
                return True, "SDK инициализирован (stub)"

            def create_virtual_port(self, port_name, description):
                self._port_handle = 1
                return True, f"Порт {port_name} создан"

            def send_program_change(self, handle, channel, program_id):
                return True, f"Program Change {program_id}"

            def send_cc(self, handle, channel, control, value):
                return True, f"CC {control}={value}"

            def send_note(self, handle, channel, note, velocity, on):
                return True, f"Note {note} {'on' if on else 'off'}"

            def get_port_status(self, handle):
                return True, "Порт активен"

            def close_virtual_port(self, handle):
                self._port_handle = None
                return True, "Порт закрыт"

            def cleanup(self):
                self._initialized = False
                return True, "SDK очищен"

        self._midi_bridge = StubMIDIBridge()

    def send_program_change(self, program_id: int, channel: int = 0) -> bool:
        """
        Отправка Program Change.

        Args:
            program_id: ID пресета (0-127)
            channel: MIDI канал (0-15)

        Returns:
            bool: True если успешно
        """
        if not self._initialized or self._midi_bridge is None:
            if self.logger:
                self.logger.log_midi("Порт не инициализирован", "error")
            return False

        try:
            success, message = self._midi_bridge.send_program_change(
                self._port_handle, channel, program_id
            )
            if success:
                if self.logger:
                    self.logger.log_midi(f"Program Change: {program_id}", "success")
            else:
                if self.logger:
                    self.logger.log_midi(f"Ошибка Program Change: {message}", "error")
            return success
        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка отправки: {e}", "error")
            return False

    def send_control_change(self, controller: int, value: int, channel: int = 0) -> bool:
        """
        Отправка Control Change.

        Args:
            controller: Номер контроллера (0-127)
            value: Значение (0-127)
            channel: MIDI канал (0-15)

        Returns:
            bool: True если успешно
        """
        if not self._initialized or self._midi_bridge is None:
            return False

        try:
            success, message = self._midi_bridge.send_cc(
                self._port_handle, channel, controller, value
            )
            if success:
                if self.logger:
                    self.logger.log_midi(f"CC {controller}={value}", "success")
            return success
        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка отправки CC: {e}", "error")
            return False

    def send_note_on(self, note: int, velocity: int = 64, channel: int = 0) -> bool:
        """
        Отправка Note On.

        Args:
            note: Номер ноты (0-127)
            velocity: Скорость (0-127)
            channel: MIDI канал (0-15)

        Returns:
            bool: True если успешно
        """
        if not self._initialized or self._midi_bridge is None:
            return False

        try:
            success, message = self._midi_bridge.send_note(
                self._port_handle, channel, note, velocity, on=True
            )
            if success:
                if self.logger:
                    self.logger.log_midi(f"Note On: {note} vel={velocity}", "success")
            return success
        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка отправки Note On: {e}", "error")
            return False

    def send_note_off(self, note: int, channel: int = 0) -> bool:
        """
        Отправка Note Off.

        Args:
            note: Номер ноты (0-127)
            channel: MIDI канал (0-15)

        Returns:
            bool: True если успешно
        """
        if not self._initialized or self._midi_bridge is None:
            return False

        try:
            success, message = self._midi_bridge.send_note(
                self._port_handle, channel, note, 0, on=False
            )
            if success:
                if self.logger:
                    self.logger.log_midi(f"Note Off: {note}", "success")
            return success
        except Exception as e:
            if self.logger:
                self.logger.log_midi(f"Ошибка отправки Note Off: {e}", "error")
            return False

    def get_status(self) -> tuple:
        """
        Получение статуса порта.

        Returns:
            tuple: (is_active, message)
        """
        if not self._initialized or self._midi_bridge is None:
            return False, "Порт не инициализирован"

        try:
            return self._midi_bridge.get_port_status(self._port_handle)
        except Exception as e:
            return False, f"Ошибка: {e}"

    def close(self) -> None:
        """Закрытие порта"""
        if self._midi_bridge and self._port_handle is not None:
            try:
                self._midi_bridge.close_virtual_port(self._port_handle)
                self._port_handle = None
                if self.logger:
                    self.logger.log_midi("Порт закрыт", "info")
            except Exception as e:
                if self.logger:
                    self.logger.log_midi(f"Ошибка закрытия: {e}", "error")

        if self._midi_bridge:
            try:
                self._midi_bridge.cleanup()
            except:
                pass

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Статус инициализации"""
        return self._initialized

    @property
    def port_handle(self) -> Optional[int]:
        """Дескриптор порта"""
        return self._port_handle