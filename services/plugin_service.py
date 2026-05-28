"""
PluginService
==============
Сервис управления VST3 плагином.
"""

from typing import Optional, Dict, Any
from vst3.host import VST3Host
from core.state_manager import StateManager
from core.logger import Logger


class PluginService:
    """Сервис управления VST3 плагином"""

    def __init__(self, config, state_manager: StateManager, logger: Logger):
        self.config = config
        self.state_manager = state_manager
        self.logger = logger
        self.host: Optional[VST3Host] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Инициализация сервиса.

        Returns:
            bool: True если успешно
        """
        try:
            self.host = VST3Host(self.config, self.logger)

            if not self.host.initialize():
                self.state_manager.update_state(plugin_loaded=False)
                return False

            self._initialized = True
            self.state_manager.update_state(plugin_loaded=True, current_preset=0)
            self.logger.log_plugin("PluginService инициализирован", "success")
            return True

        except Exception as e:
            self.logger.log_plugin(f"Ошибка инициализации: {e}", "error")
            self.state_manager.update_state(plugin_loaded=False)
            return False

    def switch_preset(self, preset_id: int) -> bool:
        """
        Переключение пресета.

        Args:
            preset_id: ID пресета

        Returns:
            bool: True если успешно
        """
        if not self._initialized or not self.host:
            self.logger.log_plugin("Плагин не загружен", "error")
            return False

        try:
            success = self.host.send_program_change(preset_id)
            if success:
                self.state_manager.update_state(current_preset=preset_id)
            return success
        except Exception as e:
            self.logger.log_plugin(f"Ошибка переключения: {e}", "error")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Получение статуса"""
        if self.host:
            return self.host.get_status()
        return {'initialized': False, 'plugin_loaded': False}

    def shutdown(self) -> None:
        """Остановка сервиса"""
        if self.host:
            self.host.shutdown()
            self.host = None
        self._initialized = False
        self.logger.log_plugin("PluginService остановлен", "info")