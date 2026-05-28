#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GR7 Hub - Main Application
==========================
Guitar Rig 7 Hub с VST3 хостингом, MIDI управлением и WebRTC стримингом.
"""

import sys
import threading
from pathlib import Path

# PyQt6
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QFrame, QProgressBar, QTextEdit,
    QGroupBox, QGridLayout, QComboBox, QSpinBox, QCheckBox, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QBrush, QLinearGradient, QPainter,
    QPen, QCursor
)

# Модули приложения
from core import StateManager, ConfigLoader, Logger
from services import PluginService, AudioService, MIDIService, WebRTCService
from utils import QRGenerator


class CyberpunkStyle:
    """Стили для cyberpunk UI"""

    @staticmethod
    def apply_stylesheet(app):
        """Применение cyberpunk стиля"""
        app.setStyle("Fusion")

        # Цветовая палитра
        palette = QPalette()

        # Основные цвета
        palette.setColor(QPalette.ColorRole.Window, QColor(20, 20, 30))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 40))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 40, 50))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(40, 40, 50))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 255, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 200, 200))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

        app.setPalette(palette)

    @staticmethod
    def create_gradient_background(widget):
        """Создание градиентного фона"""
        widget.setAutoFillBackground(True)
        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(20, 20, 30))
        widget.setPalette(palette)


class LogWidget(QTextEdit):
    """Виджет логов"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0f;
                color: #00ff00;
                font-family: Consolas, monospace;
                font-size: 11px;
                border: 1px solid #00ffff;
                border-radius: 4px;
                padding: 8px;
            }
        """)

    def log(self, message: str, level: str = "info"):
        """Добавление сообщения в лог"""
        colors = {
            "info": "#00ff00",
            "success": "#00ffff",
            "error": "#ff0040",
            "warning": "#ffff00",
            "debug": "#0088ff"
        }

        color = colors.get(level, "#00ff00")
        self.append(f'<span style="color: {color}">[{level.upper()}] {message}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class DashboardTab(QWidget):
    """Вкладка Dashboard"""

    def __init__(self, state_manager, logger, parent=None):
        super().__init__(parent)
        self.state_manager = state_manager
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Заголовок
        title = QLabel("DASHBOARD")
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00ffff;
                text-align: center;
                padding: 10px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        layout.addWidget(title)

        # Статус плагина
        plugin_group = QGroupBox("VST3 Plugin")
        plugin_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        plugin_layout = QVBoxLayout()

        self.plugin_status = QLabel("Не загружен")
        self.plugin_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        plugin_layout.addWidget(self.plugin_status)

        self.plugin_info = QLabel("Плагин не загружен")
        self.plugin_info.setStyleSheet("color: #888888; font-size: 12px;")
        plugin_layout.addWidget(self.plugin_info)

        plugin_group.setLayout(plugin_layout)
        layout.addWidget(plugin_group)

        # Статус аудио
        audio_group = QGroupBox("Audio Engine")
        audio_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        audio_layout = QVBoxLayout()

        self.audio_status = QLabel("Остановлен")
        self.audio_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        audio_layout.addWidget(self.audio_status)

        self.audio_info = QLabel("Аудио движок не запущен")
        self.audio_info.setStyleSheet("color: #888888; font-size: 12px;")
        audio_layout.addWidget(self.audio_info)

        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)

        # Статус MIDI
        midi_group = QGroupBox("MIDI")
        midi_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        midi_layout = QVBoxLayout()

        self.midi_status = QLabel("Не инициализирован")
        self.midi_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        midi_layout.addWidget(self.midi_status)

        self.midi_info = QLabel("MIDI порт не создан")
        self.midi_info.setStyleSheet("color: #888888; font-size: 12px;")
        midi_layout.addWidget(self.midi_info)

        midi_group.setLayout(midi_layout)
        layout.addWidget(midi_group)

        # Текущий пресет
        preset_group = QGroupBox("Current Preset")
        preset_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        preset_layout = QVBoxLayout()

        self.preset_label = QLabel("ID: -")
        self.preset_label.setStyleSheet("color: #ffff00; font-size: 18px; font-weight: bold;")
        preset_layout.addWidget(self.preset_label)

        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        layout.addStretch()
        self.setLayout(layout)

    def update_status(self, state: dict):
        """Обновление статуса"""
        # Plugin
        if state.get('plugin_loaded'):
            self.plugin_status.setText("Загружен")
            self.plugin_status.setStyleSheet("color: #00ffff; font-size: 14px;")
            self.plugin_info.setText(f"Пресет: {state.get('current_preset', 'N/A')}")
        else:
            self.plugin_status.setText("Не загружен")
            self.plugin_status.setStyleSheet("color: #ff0040; font-size: 14px;")

        # Audio
        if state.get('audio_engine_active'):
            self.audio_status.setText("Активен")
            self.audio_status.setStyleSheet("color: #00ffff; font-size: 14px;")
        else:
            self.audio_status.setText("Остановлен")
            self.audio_status.setStyleSheet("color: #ff0040; font-size: 14px;")

        # MIDI
        if state.get('midi_active'):
            self.midi_status.setText("Активен")
            self.midi_status.setStyleSheet("color: #00ffff; font-size: 14px;")
        else:
            self.midi_status.setText("Не инициализирован")
            self.midi_status.setStyleSheet("color: #ff0040; font-size: 14px;")

        # Preset
        self.preset_label.setText(f"ID: {state.get('current_preset', 'N/A')}")


class MIDITab(QWidget):
    """Вкладка MIDI"""

    def __init__(self, midi_service, logger, parent=None):
        super().__init__(parent)
        self.midi_service = midi_service
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Заголовок
        title = QLabel("MIDI CONTROL")
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00ffff;
                text-align: center;
                padding: 10px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        layout.addWidget(title)

        # Статус
        status_group = QGroupBox("MIDI Status")
        status_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        status_layout = QVBoxLayout()

        self.midi_status = QLabel("Не инициализирован")
        self.midi_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        status_layout.addWidget(self.midi_status)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Program Change
        pc_group = QGroupBox("Program Change")
        pc_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        pc_layout = QGridLayout()

        pc_layout.addWidget(QLabel("Preset ID:"), 0, 0)
        self.preset_spin = QSpinBox()
        self.preset_spin.setRange(0, 127)
        self.preset_spin.setValue(0)
        pc_layout.addWidget(self.preset_spin, 0, 1)

        self.send_pc_btn = QPushButton("Send Program Change")
        self.send_pc_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ffff;
                color: #000000;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #00cccc;
            }
        """)
        self.send_pc_btn.clicked.connect(self._send_program_change)
        pc_layout.addWidget(self.send_pc_btn, 1, 0, 1, 2)

        pc_group.setLayout(pc_layout)
        layout.addWidget(pc_group)

        # Control Change
        cc_group = QGroupBox("Control Change")
        cc_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        cc_layout = QGridLayout()

        cc_layout.addWidget(QLabel("Controller:"), 0, 0)
        self.cc_controller = QSpinBox()
        self.cc_controller.setRange(0, 127)
        self.cc_controller.setValue(64)
        cc_layout.addWidget(self.cc_controller, 0, 1)

        cc_layout.addWidget(QLabel("Value:"), 1, 0)
        self.cc_value = QSpinBox()
        self.cc_value.setRange(0, 127)
        self.cc_value.setValue(64)
        cc_layout.addWidget(self.cc_value, 1, 1)

        self.send_cc_btn = QPushButton("Send CC")
        self.send_cc_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffff00;
                color: #000000;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #cccc00;
            }
        """)
        self.send_cc_btn.clicked.connect(self._send_control_change)
        cc_layout.addWidget(self.send_cc_btn, 2, 0, 1, 2)

        cc_group.setLayout(cc_layout)
        layout.addWidget(cc_group)

        # Test MIDI
        test_group = QGroupBox("Test MIDI")
        test_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        test_layout = QVBoxLayout()

        self.test_note_btn = QPushButton("Send Test Note")
        self.test_note_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff0040;
                color: #ffffff;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #cc0033;
            }
        """)
        self.test_note_btn.clicked.connect(self._send_test_note)
        test_layout.addWidget(self.test_note_btn)

        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

        layout.addStretch()
        self.setLayout(layout)

    def _send_program_change(self):
        """Отправка Program Change"""
        preset_id = self.preset_spin.value()
        if self.midi_service.send_program_change(preset_id):
            self.logger.log(f"Program Change {preset_id} отправлен", "success")
        else:
            self.logger.log(f"Ошибка отправки Program Change {preset_id}", "error")

    def _send_control_change(self):
        """Отправка Control Change"""
        controller = self.cc_controller.value()
        value = self.cc_value.value()
        if self.midi_service.send_control_change(controller, value):
            self.logger.log(f"CC {controller}={value} отправлен", "success")
        else:
            self.logger.log(f"Ошибка отправки CC {controller}={value}", "error")

    def _send_test_note(self):
        """Отправка тестовой ноты"""
        if self.midi_service.send_note_on(60, 100):
            self.logger.log("Test Note On отправлен", "success")
        else:
            self.logger.log("Ошибка отправки Test Note", "error")

    def update_status(self, status: dict):
        """Обновление статуса"""
        if status.get('port_active'):
            self.midi_status.setText("Активен")
            self.midi_status.setStyleSheet("color: #00ffff; font-size: 14px;")
        else:
            self.midi_status.setText("Не инициализирован")
            self.midi_status.setStyleSheet("color: #ff0040; font-size: 14px;")


class AudioTab(QWidget):
    """Вкладка Audio"""

    def __init__(self, audio_service, logger, parent=None):
        super().__init__(parent)
        self.audio_service = audio_service
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Заголовок
        title = QLabel("AUDIO ENGINE")
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00ffff;
                text-align: center;
                padding: 10px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        layout.addWidget(title)

        # Статус
        status_group = QGroupBox("Audio Status")
        status_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        status_layout = QVBoxLayout()

        self.audio_status = QLabel("Остановлен")
        self.audio_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        status_layout.addWidget(self.audio_status)

        self.audio_info = QLabel("Аудио движок не запущен")
        self.audio_info.setStyleSheet("color: #888888; font-size: 12px;")
        status_layout.addWidget(self.audio_info)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Настройки
        settings_group = QGroupBox("Settings")
        settings_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        settings_layout = QGridLayout()

        settings_layout.addWidget(QLabel("Sample Rate:"), 0, 0)
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["44100", "48000", "96000"])
        self.sample_rate.setCurrentText("44100")
        settings_layout.addWidget(self.sample_rate, 0, 1)

        settings_layout.addWidget(QLabel("Buffer Size:"), 1, 0)
        self.buffer_size = QSpinBox()
        self.buffer_size.setRange(64, 2048)
        self.buffer_size.setValue(256)
        self.buffer_size.setSingleStep(64)
        settings_layout.addWidget(self.buffer_size, 1, 1)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Кнопки
        button_layout = QHBoxLayout()

        self.start_audio_btn = QPushButton("Start Audio")
        self.start_audio_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ff00;
                color: #000000;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #00cc00;
            }
        """)
        self.start_audio_btn.clicked.connect(self._start_audio)
        button_layout.addWidget(self.start_audio_btn)

        self.stop_audio_btn = QPushButton("Stop Audio")
        self.stop_audio_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff0040;
                color: #ffffff;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #cc0033;
            }
        """)
        self.stop_audio_btn.clicked.connect(self._stop_audio)
        button_layout.addWidget(self.stop_audio_btn)

        layout.addLayout(button_layout)

        layout.addStretch()
        self.setLayout(layout)

    def _start_audio(self):
        """Запуск аудио"""
        if self.audio_service.start(self._audio_callback):
            self.logger.log("Аудио движок запущен", "success")
        else:
            self.logger.log("Ошибка запуска аудио", "error")

    def _stop_audio(self):
        """Остановка аудио"""
        self.audio_service.stop()
        self.logger.log("Аудио движок остановлен", "info")

    def _audio_callback(self, input_data):
        """Аудио callback"""
        # Обработка через VST3 плагин
        return input_data

    def update_status(self, status: dict):
        """Обновление статуса"""
        if status.get('running'):
            self.audio_status.setText("Активен")
            self.audio_status.setStyleSheet("color: #00ffff; font-size: 14px;")
            self.audio_info.setText(f"Sample Rate: {status.get('sample_rate', 'N/A')}")
        else:
            self.audio_status.setText("Остановлен")
            self.audio_status.setStyleSheet("color: #ff0040; font-size: 14px;")


class WebRTCTab(QWidget):
    """Вкладка WebRTC"""

    def __init__(self, webrtc_service, logger, parent=None):
        super().__init__(parent)
        self.webrtc_service = webrtc_service
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Заголовок
        title = QLabel("WEBRTC STREAM")
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00ffff;
                text-align: center;
                padding: 10px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        layout.addWidget(title)

        # Статус
        status_group = QGroupBox("Connection Status")
        status_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        status_layout = QVBoxLayout()

        self.connection_status = QLabel("Не подключен")
        self.connection_status.setStyleSheet("color: #ff0040; font-size: 14px;")
        status_layout.addWidget(self.connection_status)

        self.room_id_label = QLabel("Room ID: -")
        self.room_id_label.setStyleSheet("color: #888888; font-size: 12px;")
        status_layout.addWidget(self.room_id_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Создание комнаты
        create_group = QGroupBox("Create Room")
        create_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        create_layout = QVBoxLayout()

        self.create_room_btn = QPushButton("Create WebRTC Room")
        self.create_room_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: #ffffff;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.create_room_btn.clicked.connect(self._create_room)
        create_layout.addWidget(self.create_room_btn)

        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        # Очистка
        clear_group = QGroupBox("Room Management")
        clear_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        clear_layout = QVBoxLayout()

        self.clear_room_btn = QPushButton("Clear Room")
        self.clear_room_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: #000000;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d68910;
            }
        """)
        self.clear_room_btn.clicked.connect(self._clear_room)
        clear_layout.addWidget(self.clear_room_btn)

        clear_group.setLayout(clear_layout)
        layout.addWidget(clear_group)

        layout.addStretch()
        self.setLayout(layout)

    def _create_room(self):
        """Создание комнаты"""
        room_id = self.webrtc_service.create_room()
        if room_id:
            self.room_id_label.setText(f"Room ID: {room_id}")
            self.logger.log(f"Комната создана: {room_id}", "success")
        else:
            self.logger.log("Ошибка создания комнаты", "error")

    def _clear_room(self):
        """Очистка комнаты"""
        self.webrtc_service.stream.signaling.cleanup_room()
        self.room_id_label.setText("Room ID: -")
        self.logger.log("Комната очищена", "info")

    def update_status(self, status: dict):
        """Обновление статуса"""
        if status.get('ice_connected'):
            self.connection_status.setText("Подключено")
            self.connection_status.setStyleSheet("color: #00ffff; font-size: 14px;")
        else:
            self.connection_status.setText("Не подключен")
            self.connection_status.setStyleSheet("color: #ff0040; font-size: 14px;")


class SettingsTab(QWidget):
    """Вкладка Settings"""

    def __init__(self, config, logger, parent=None):
        super().__init__(parent)
        self.config = config
        self.logger = logger
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Заголовок
        title = QLabel("SETTINGS")
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00ffff;
                text-align: center;
                padding: 10px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        layout.addWidget(title)

        # VST3 Path
        vst3_group = QGroupBox("VST3 Plugin Path")
        vst3_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        vst3_layout = QVBoxLayout()

        self.vst3_path = self.config.get('vst3', 'path', '')
        self.vst3_entry = QLabel(self.vst3_path)
        self.vst3_entry.setStyleSheet("color: #888888; font-size: 12px; padding: 5px;")
        vst3_layout.addWidget(self.vst3_entry)

        vst3_group.setLayout(vst3_layout)
        layout.addWidget(vst3_group)

        # MIDI Port
        midi_group = QGroupBox("MIDI Port Name")
        midi_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        midi_layout = QVBoxLayout()

        self.midi_port = self.config.get('midi', 'virtual_port_name', 'GR7 Hub Control')
        self.midi_entry = QLabel(self.midi_port)
        self.midi_entry.setStyleSheet("color: #888888; font-size: 12px; padding: 5px;")
        midi_layout.addWidget(self.midi_entry)

        midi_group.setLayout(midi_layout)
        layout.addWidget(midi_group)

        # Debug
        debug_group = QGroupBox("Debug")
        debug_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        debug_layout = QVBoxLayout()

        self.debug_info = QLabel("GR7 Hub v2.0 - MIDI-first Architecture")
        self.debug_info.setStyleSheet("color: #0088ff; font-size: 12px;")
        debug_layout.addWidget(self.debug_info)

        debug_group.setLayout(debug_layout)
        layout.addWidget(debug_group)

        layout.addStretch()
        self.setLayout(layout)


class MainWindow(QMainWindow):
    """Главное окно"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GR7 Hub - Guitar Rig 7 Control Hub")
        self.setGeometry(100, 100, 1000, 700)

        # Инициализация компонентов
        self.config = ConfigLoader()
        self.logger = Logger("GR7Hub")
        self.state_manager = StateManager()

        # Сервисы
        self.plugin_service = PluginService(self.config, self.state_manager, self.logger)
        self.audio_service = AudioService(self.config, self.state_manager, self.logger)
        self.midi_service = MIDIService(self.config, self.state_manager, self.logger)
        self.webrtc_service = WebRTCService(self.config, self.state_manager, self.logger)

        # QR Generator
        self.qr_generator = QRGenerator()

        # Инициализация UI
        self._init_ui()

        # Запуск фоновых сервисов
        self._start_background_services()

    def _init_ui(self):
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Главный layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # Верхняя панель
        top_bar = QFrame()
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #1a1a2e;
                border-bottom: 2px solid #00ffff;
                padding: 10px;
            }
        """)
        top_layout = QHBoxLayout()

        title = QLabel("GR7 HUB")
        title.setStyleSheet("""
            QLabel {
                font-size: 28px;
                font-weight: bold;
                color: #00ffff;
            }
        """)
        top_layout.addWidget(title)

        top_layout.addStretch()

        # Статус системы
        self.system_status = QLabel("Initializing...")
        self.system_status.setStyleSheet("""
            QLabel {
                color: #0088ff;
                font-size: 12px;
            }
        """)
        top_layout.addWidget(self.system_status)

        top_bar.setLayout(top_layout)
        main_layout.addWidget(top_bar)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #00ffff;
                border-radius: 5px;
                background-color: #1a1a2e;
            }
            QTabBar::tab {
                background-color: #2a2a3e;
                color: #00ffff;
                padding: 10px 20px;
                margin-right: 2px;
                border-radius: 5px 5px 0 0;
            }
            QTabBar::tab:selected {
                background-color: #1a1a2e;
                border-bottom: 2px solid #00ffff;
            }
            QTabBar::tab:hover {
                background-color: #3a3a4e;
            }
        """)

        # Вкладки
        self.dashboard_tab = DashboardTab(self.state_manager, self.logger)
        self.midi_tab = MIDITab(self.midi_service, self.logger)
        self.audio_tab = AudioTab(self.audio_service, self.logger)
        self.webrtc_tab = WebRTCTab(self.webrtc_service, self.logger)
        self.settings_tab = SettingsTab(self.config, self.logger)

        self.tab_widget.addTab(self.dashboard_tab, "Dashboard")
        self.tab_widget.addTab(self.midi_tab, "MIDI")
        self.tab_widget.addTab(self.audio_tab, "Audio")
        self.tab_widget.addTab(self.webrtc_tab, "WebRTC")
        self.tab_widget.addTab(self.settings_tab, "Settings")

        main_layout.addWidget(self.tab_widget)

        # Лог
        log_label = QLabel("EVENT LOG:")
        log_label.setStyleSheet("""
            QLabel {
                color: #00ffff;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(log_label)

        self.log_widget = LogWidget()
        main_layout.addWidget(self.log_widget)

        central_widget.setLayout(main_layout)

        # Таймер обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)

    def _start_background_services(self):
        """Запуск всех сервисов в фоновом потоке"""
        self.logger.log("[BOOT] GUI created", "info")
        self.logger.log("[BOOT] Starting background services", "info")

        threading.Thread(
            target=self._init_services,
            daemon=True,
            name="BackgroundServices"
        ).start()

    def _init_services(self):
        """Инициализация всех сервисов в фоновом потоке"""
        try:
            # MIDI
            self.logger.log("[BOOT] MIDI init start", "info")
            if self.midi_service.initialize():
                self.logger.log("[BOOT] MIDI init complete", "success")
            else:
                self.logger.log("[BOOT] MIDI init failed", "error")

            # VST3
            self.logger.log("[BOOT] VST load start", "info")
            if self.plugin_service.initialize():
                self.logger.log("[BOOT] VST load complete", "success")
            else:
                self.logger.log("[BOOT] VST load failed", "error")

            # Audio
            self.logger.log("[BOOT] Audio init start", "info")
            if self.audio_service.initialize():
                self.logger.log("[BOOT] Audio init complete", "success")
            else:
                self.logger.log("[BOOT] Audio init failed", "error")

            # WebRTC
            self.logger.log("[BOOT] WebRTC init start", "info")
            if self.webrtc_service.initialize():
                self.logger.log("[BOOT] WebRTC init complete", "success")
            else:
                self.logger.log("[BOOT] WebRTC init failed", "error")

            self.logger.log("[BOOT] All services initialized", "success")

        except Exception as e:
            self.logger.log(f"[BOOT] Service initialization error: {e}", "error")
            import traceback
            self.logger.log(traceback.format_exc(), "error")

    def _update_status(self):
        """Обновление статуса"""
        state = self.state_manager.state.get_state_dict()

        # Обновление вкладок
        self.dashboard_tab.update_status(state)
        self.midi_tab.update_status(self.midi_service.get_status())
        self.audio_tab.update_status(self.audio_service.get_status())
        self.webrtc_tab.update_status(self.webrtc_service.get_status())

        # Обновление статуса системы
        status_text = f"Plugin: {'OK' if state.get('plugin_loaded') else 'NO'} | "
        status_text += f"Audio: {'OK' if state.get('audio_engine_active') else 'NO'} | "
        status_text += f"MIDI: {'OK' if state.get('midi_active') else 'NO'} | "
        status_text += f"WebRTC: {'OK' if state.get('webrtc_active') else 'NO'}"
        self.system_status.setText(status_text)

    def log(self, message: str, level: str = "info"):
        """Логирование"""
        self.log_widget.log(message, level)


def main():
    """Точка входа"""
    app = QApplication(sys.argv)

    # Применение cyberpunk стиля
    CyberpunkStyle.apply_stylesheet(app)

    # Создание и запуск окна
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()