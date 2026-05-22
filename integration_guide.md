# Интеграция нового automation engine в существующий GUI

## 1. Обзор архитектуры интеграции

### 1.1 Текущая архитектура
```
gr7_hub.py (GUI)
├── keyboard_automation.py (старый automation)
└── image_utils.py (утилиты)
```

### 1.2 Новая архитектура
```
gr7_hub.py (GUI)
├── gr7_automation_v2.py (новый automation engine)
├── gr7_state_machine.py (state machine)
├── gr7_ui_validator.py (UI валидация)
├── gr7_focus_tracker.py (tracking фокуса)
├── gr7_watchdog.py (мониторинг)
├── gr7_recovery.py (self-recovery)
├── gr7_retry_manager.py (retry logic)
├── gr7_event_logger.py (event logging)
└── gr7_polling_system.py (polling вместо sleeps)
```

## 2. План миграции

### 2.1 Фаза 1: Подготовка
1. Создать резервную копию текущей системы
2. Установить все новые зависимости
3. Настроить структуру проекта

### 2.2 Фаза 2: Реализация компонентов
1. Реализовать каждый новый компонент
2. Протестировать компоненты по отдельности
3. Интегрировать с существующим GUI

### 2.3 Фаза 3: Тестирование
1. Функциональное тестирование
2. Нагрузочное тестирование
3. Тестирование восстановления

### 2.4 Фаза 4: Развертывание
1. Параллельное старте старой и новой системы
2. Сравнение результатов
3. Полный переход на новую систему

## 3. Детальная интеграция

### 3.1 Обновление gr7_hub.py

```python
# Старый код
from keyboard_automation import GR7Automation

# Новый код
from gr7_automation_v2 import GR7AutomationV2
from gr7_event_logger import EventLogger
from gr7_polling_system import PollingSystem

class GR7Hub(ctk.CTk):
    def __init__(self):
        super().__init__()
        # ... существующий код ...
        
        # --- ИНИЦИАЛИЗАЦИЯ НОВОГО AUTOMATION ENGINE ---
        self.event_logger = EventLogger(logger_func=self.log)
        self.polling_system = PollingSystem()
        self.gr7_auto = GR7AutomationV2(
            logger_func=self.log,
            event_logger=self.event_logger,
            polling_system=self.polling_system
        )
```

### 3.2 Обновление метода импорта песни

```python
# Старый метод
def _auto_switch_logic(self):
    songs_folder = self.songs_path.get()
    # ... проверка папки ...
    
    next_song = songs[0]
    song_full_path = os.path.join(songs_folder, next_song)
    
    # Используем старый automation
    success = self.gr7_auto.import_song(song_full_path)
    
    if success:
        self.log("✅ [Auto] Импорт песни выполнен успешно!")
    else:
        self.log("[ERROR] Импорт не удался. Используем fallback...")
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'right')
        self.log("✅ Fallback выполнен (Ctrl+Right)")

# Новый метод
def _auto_switch_logic(self):
    songs_folder = self.songs_path.get()
    # ... проверка папки ...
    
    next_song = songs[0]
    song_full_path = os.path.join(songs_folder, next_song)
    
    # Используем новый automation с полной трассировкой
    with self.event_logger.trace_context("song_import"):
        success = self.gr7_auto.import_song_with_retry(song_full_path)
        
        if success:
            self.log("✅ [Auto] Импорт песни выполнен успешно!")
        else:
            self.log("[ERROR] Импорт не удался даже с retry и fallback")
```

### 3.3 Новый automation engine

```python
# gr7_automation_v2.py
import threading
import time
from typing import Dict, Any, Optional
from gr7_state_machine import GR7StateMachine
from gr7_ui_validator import UIValidator
from gr7_focus_tracker import FocusAwareAutomation
from gr7_recovery import SelfRecoveryEngine
from gr7_retry_manager import GR7AutomationWithRetry
from gr7_watchdog import WatchdogStateMachine

class GR7AutomationV2:
    def __init__(self, logger_func=None, event_logger=None, polling_system=None):
        self.logger = logger_func or print
        self.event_logger = event_logger
        self.polling_system = polling_system
        
        # Инициализация всех компонентов
        self.focus_automation = FocusAwareAutomation(logger_func)
        self.ui_validator = UIValidator(logger_func)
        self.recovery_engine = SelfRecoveryEngine(logger_func)
        self.retry_manager = GR7AutomationWithRetry(logger_func)
        
        # State machine с watchdog
        self.state_machine = GR7StateMachine(
            self.focus_automation,
            self.ui_validator,
            self.recovery_engine,
            logger_func
        )
        
        # Watchdog для мониторинга
        self.watchdog = WatchdogStateMachine(self.state_machine, logger_func)
        
        # Запускаем мониторинг
        self.watchdog.start_monitoring()
    
    def import_song_with_retry(self, song_path: str) -> bool:
        """Импорт песни с полной обработкой ошибок и восстановлением"""
        
        def import_operation():
            """Основная операция импорта"""
            
            # Шаг 1: Обеспечиваем фокус
            if not self.focus_automation.ensure_focus("import_song"):
                raise Exception("Failed to ensure focus")
            
            # Шаг 2: Открываем диалог импорта
            if not self.state_machine.transition_to_state(
                "focused", "import_dialog", 
                self._open_import_dialog
            ):
                raise Exception("Failed to open import dialog")
            
            # Шаг 3: Вставляем путь
            if not self.state_machine.transition_to_state(
                "import_dialog", "path_pasted",
                lambda: self._paste_path(song_path)
            ):
                raise Exception("Failed to paste path")
            
            # Шаг 4: Подтверждаем импорт
            if not self.state_machine.transition_to_state(
                "path_pasted", "import_success",
                lambda: self._confirm_import()
            ):
                raise Exception("Failed to confirm import")
            
            return True
        
        # Fallback стратегия
        def fallback_import(context, error):
            """Fallback импорт"""
            self.logger("[FALLBACK] Using alternative import method")
            
            # Альтернативные методы
            import pyautogui
            
            # Ctrl+Right как fallback
            pyautogui.hotkey('ctrl', 'right')
            time.sleep(0.5)
            
            return {'success': True, 'fallback_used': True}
        
        # Выполняем с retry и fallback
        try:
            result = self.retry_manager.import_song_with_retry(song_path)
            
            if result and result.get('success'):
                if result.get('fallback_used'):
                    self.logger("[RETRY] Import completed using fallback method")
                else:
                    self.logger("[RETRY] Import completed successfully")
                return True
            else:
                self.logger("[RETRY] Import failed")
                return False
                
        except Exception as e:
            self.logger(f"[RETRY] Import error: {e}")
            return False
    
    def _open_import_dialog(self):
        """Открытие диалога импорта"""
        import pyautogui
        
        # Пробуем разные методы
        methods = [
            lambda: pyautogui.hotkey('ctrl', 'o'),
            lambda: pyautogui.hotkey('alt', 'f') or pyautogui.press('o'),
            lambda: self._click_menu_item()
        ]
        
        for method in methods:
            try:
                method()
                # Ждем открытия диалога
                if self.polling_system.wait_until(
                    lambda: self.ui_validator.validate_dialog_opened(),
                    timeout=3.0,
                    description="Dialog open"
                ):
                    return True
            except:
                continue
        
        return False
    
    def _paste_path(self, song_path: str):
        """Вставка пути в диалог"""
        import pyautogui
        import pyperclip
        
        # Копируем путь
        pyperclip.copy(song_path)
        
        # Вставляем
        pyautogui.hotkey('ctrl', 'v')
        
        # Ждем вставки
        if self.polling_system.wait_until(
            lambda: pyperclip.paste() == song_path,
            timeout=1.0,
            description="Path paste"
        ):
            return True
        
        return False
    
    def _confirm_import(self):
        """Подтверждение импорта"""
        import pyautogui
        
        pyautogui.press('enter')
        
        # Ждем закрытия диалога
        if self.polling_system.wait_until(
            lambda: self.ui_validator.validate_dialog_closed(),
            timeout=5.0,
            description="Dialog close"
        ):
            return True
        
        return False
    
    def _click_menu_item(self):
        """Клик по пункту меню"""
        from image_utils import locate_image_on_screen
        
        menu_pos = locate_image_on_screen("file_menu.png", confidence=0.8)
        if menu_pos:
            pyautogui.click(menu_pos[0], menu_pos[1])
            time.sleep(0.3)
            open_pos = locate_image_on_screen("open_menu_item.png", confidence=0.8)
            if open_pos:
                pyautogui.click(open_pos[0], open_pos[1])
                return True
        
        return False
    
    def get_system_status(self) -> Dict:
        """Получение статуса системы"""
        return {
            'focus_status': self.focus_automation.get_focus_status(),
            'retry_stats': self.retry_manager.get_retry_statistics(),
            'watchdog_state': self.watchdog.get_state(),
            'performance_report': self.event_logger.get_performance_report()
        }
    
    def stop(self):
        """Остановка системы"""
        self.watchdog.stop_monitoring()
        self.focus_automation.stop()
```

### 3.4 Обновление GUI с новыми возможностями

```python
# Обновление gr7_hub.py с новыми элементами интерфейса
class GR7Hub(ctk.CTk):
    def __init__(self):
        super().__init__()
        # ... существующий код ...
        
        # --- НОВЫЕ ЭЛЕМЕНТЫ ИНТЕРФЕЙСА ---
        self.setup_debug_tab()
        self.setup_status_display()
        
    def setup_debug_tab(self):
        """Создание вкладки отладки"""
        self.tab_debug = self.tabview.add("Отладка")
        
        # Кнопка для просмотра статуса системы
        ctk.CTkButton(self.tab_debug, text="ПОКАЗАТЬ СТАТУС СИСТЕМЫ",
                     command=self.show_system_status).pack(pady=10)
        
        # Кнопка для просмотра логов
        ctk.CTkButton(self.tab_debug, text="ПОКАЗАТЬ ЛОГИ",
                     command=self.show_event_logs).pack(pady=10)
        
        # Кнопка для тестирования компонентов
        ctk.CTkButton(self.tab_debug, text="ТЕСТ КОМПОНЕНТОВ",
                     command=self.test_components).pack(pady=10)
    
    def setup_status_display(self):
        """Создание отображения статуса"""
        self.status_frame = ctk.CTkFrame(self.tab_local, fg_color="#111111")
        self.status_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(self.status_frame, text="СТАТУС СИСТЕМЫ:",
                    font=("Consolas", 10, "bold")).pack(anchor="w")
        
        self.status_text = ctk.CTkTextbox(self.status_frame, height=60,
                                          font=("Consolas", 9))
        self.status_text.pack(fill="x", padx=5, pady=5)
        
        # Обновляем статус периодически
        self.update_status()
    
    def update_status(self):
        """Обновление статуса системы"""
        try:
            status = self.gr7_auto.get_system_status()
            
            status_text = f"Фокус: {'✅' if status['focus_status']['focused'] else '❌'}\n"
            status_text += f"Retry: {status['retry_stats']['total_attempts']} попыток\n"
            status_text += f"Watchdog: {'🟢' if status['watchdog_state']['state'] == 'closed' else '🔴'}\n"
            
            self.status_text.delete("1.0", "end")
            self.status_text.insert("1.0", status_text)
            
        except Exception as e:
            self.status_text.delete("1.0", "end")
            self.status_text.insert("1.0", f"Ошибка статуса: {e}")
        
        # Следующее обновление через 5 секунд
        self.after(5000, self.update_status)
    
    def show_system_status(self):
        """Показать детальный статус системы"""
        try:
            status = self.gr7_auto.get_system_status()
            
            # Форматируем статус для отображения
            status_info = f"""
СИСТЕМНЫЙ СТАТУС
================

Фокус:
  - Активен: {'✅' if status['focus_status']['focused'] else '❌'}
  - Видим: {'✅' if status['focus_status']['visible'] else '❌'}
  - Ответчив: {'✅' if status['focus_status']['responsive'] else '❌'}

Статистика Retry:
  - Всего попыток: {status['retry_stats']['total_attempts']}
  - Успешных: {status['retry_stats']['successful_retries']}
  - Неудачных: {status['retry_stats']['failed_retries']}
  - Rate: {status['retry_stats']['success_rate']:.1f}%

Watchdog:
  - Состояние: {status['watchdog_state']['state']}
  - Ошибок: {status['watchdog_state']['failure_count']}

Производительность:
  - Uptime: {status['performance_report']['uptime_seconds']:.1f}s
  - Событий: {status['performance_report']['total_events']}
"""
            
            # Показываем в модальном окне
            self.show_info_dialog("Системный статус", status_info)
            
        except Exception as e:
            self.show_error_dialog("Ошибка", f"Не удалось получить статус: {e}")
    
    def show_event_logs(self):
        """Показать логи событий"""
        try:
            logs = self.gr7_auto.event_logger.get_event_trace(
                session_id=self.gr7_auto.event_logger.session_id
            )
            
            # Форматируем логи
            log_text = "ЛОГИ СОБЫТИЙ\n" + "="*50 + "\n\n"
            
            for event in logs[-20:]:  # Последние 20 событий
                timestamp = event.get('timestamp', 'N/A')
                level = event.get('level', 'N/A')
                message = event.get('message', 'N/A')
                event_type = event.get('event_type', 'N/A')
                
                log_text += f"[{timestamp}] {level} | {event_type}\n"
                log_text += f"  {message}\n\n"
            
            # Показываем в модальном окне
            self.show_info_dialog("Логи событий", log_text)
            
        except Exception as e:
            self.show_error_dialog("Ошибка", f"Не удалось получить логи: {e}")
    
    def test_components(self):
        """Тестирование компонентов системы"""
        test_results = []
        
        # Тест фокуса
        try:
            focus_result = self.gr7_auto.focus_automation.ensure_focus("test")
            test_results.append(f"Фокус: {'✅' if focus_result else '❌'}")
        except Exception as e:
            test_results.append(f"Фокус: ❌ ({e})")
        
        # Тест UI валидации
        try:
            ui_result = self.gr7_auto.ui_validator.validate_gr7_focused()
            test_results.append(f"UI Валидация: {'✅' if ui_result else '❌'}")
        except Exception as e:
            test_results.append(f"UI Валидация: ❌ ({e})")
        
        # Тест retry
        try:
            retry_result = self.gr7_auto.retry_manager.import_song_with_retry("test.mp3")
            test_results.append(f"Retry: {'✅' if retry_result else '❌'}")
        except Exception as e:
            test_results.append(f"Retry: ❌ ({e})")
        
        # Показываем результаты
        result_text = "РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ\n" + "="*30 + "\n\n"
        result_text += "\n".join(test_results)
        
        self.show_info_dialog("Тестирование компонентов", result_text)
```

## 4. Конфигурация и настройки

### 4.1 Файл конфигурации
```ini
# config.ini
[automation]
# Настройки polling
polling_interval = 0.1
polling_timeout = 10.0
max_retries = 3
backoff_multiplier = 2.0

# Настройки валидации UI
ui_confidence_high = 0.95
ui_confidence_medium = 0.85
ui_confidence_low = 0.75

# Настройки восстановления
max_recovery_attempts = 5
recovery_delay = 0.3

# Настройки логирования
log_level = INFO
log_file = automation_events.log
max_log_size = 10485760  # 10MB

[ui_templates]
# Пути к шаблонам для валидации
import_dialog = templates/import_dialog.png
file_menu = templates/file_menu.png
open_menu_item = templates/open_menu_item.png
input_field = templates/input_field.png
confirm_button = templates/confirm_button.png
```

### 4.2 Управление конфигурацией
```python
class AutomationConfig:
    def __init__(self, config_file="config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """Загрузка конфигурации"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """Создание конфигурации по умолчанию"""
        self.config['automation'] = {
            'polling_interval': '0.1',
            'polling_timeout': '10.0',
            'max_retries': '3',
            'backoff_multiplier': '2.0'
        }
        
        self.config['ui_templates'] = {
            'import_dialog': 'templates/import_dialog.png',
            'file_menu': 'templates/file_menu.png',
            'open_menu_item': 'templates/open_menu_item.png'
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def get_polling_config(self):
        """Получение конфигурации polling"""
        return PollingConfig(
            default_interval=float(self.config.get('automation', 'polling_interval', fallback=0.1)),
            timeout=float(self.config.get('automation', 'polling_timeout', fallback=10.0)),
            max_retries=int(self.config.get('automation', 'max_retries', fallback=3)),
            backoff_multiplier=float(self.config.get('automation', 'backoff_multiplier', fallback=2.0))
        )
    
    def get_ui_confidence(self, level):
        """Получение уровня уверенности для UI валидации"""
        return float(self.config.get('automation', f'ui_confidence_{level}', fallback=0.85))
```

## 5. Тестирование и валидация

### 5.1 Тестовые сценарии
```python
# test_automation.py
import unittest
from gr7_automation_v2 import GR7AutomationV2
from gr7_event_logger import EventLogger

class TestGR7Automation(unittest.TestCase):
    def setUp(self):
        self.event_logger = EventLogger()
        self.automation = GR7AutomationV2(event_logger=self.event_logger)
    
    def test_focus_automation(self):
        """Тестирование фокусировки"""
        result = self.automation.focus_automation.ensure_focus("test")
        self.assertTrue(result)
    
    def test_ui_validation(self):
        """Тестирование UI валидации"""
        result = self.automation.ui_validator.validate_gr7_focused()
        # Может быть False если GR7 не запущен
        self.assertIsInstance(result, bool)
    
    def test_retry_mechanism(self):
        """Тестирование retry механизма"""
        # Тест с несуществующим файлом
        result = self.automation.retry_manager.import_song_with_retry("nonexistent.mp3")
        self.assertFalse(result)  # Должен вернуть False, но не упасть
    
    def test_event_logging(self):
        """Тестирование логирования событий"""
        self.automation.event_logger.log_event(
            "test_event", "INFO", "Test message"
        )
        
        trace = self.automation.event_logger.get_event_trace()
        self.assertGreater(len(trace), 0)
    
    def tearDown(self):
        self.automation.stop()

if __name__ == '__main__':
    unittest.main()
```

### 5.2 Интеграционное тестирование
```python
def test_full_import_workflow():
    """Тестирование полного workflow импорта"""
    
    # Создаем тестовый файл
    test_file = "test_song.mp3"
    with open(test_file, 'w') as f:
        f.write("test content")
    
    try:
        # Инициализируем систему
        event_logger = EventLogger()
        automation = GR7AutomationV2(event_logger=event_logger)
        
        # Запускаем импорт
        result = automation.import_song_with_retry(test_file)
        
        # Проверяем результат
        print(f"Import result: {result}")
        
        # Получаем статистику
        stats = automation.get_system_status()
        print(f"System stats: {stats}")
        
    finally:
        # Очистка
        if os.path.exists(test_file):
            os.remove(test_file)
        automation.stop()

if __name__ == '__main__':
    test_full_import_workflow()
```

## 6. Развертывание и мониторинг

### 6.1 Пошаговая миграция
1. **Резервное копирование**: Создать полную копию текущей системы
2. **Тестовая среда**: Развернуть новую систему в тестовой среде
3. **Параллельное выполнение**: Запустить старую и новую системы одновременно
4. **Сравнение результатов**: Сравнить результаты работы обеих систем
5. **Поэтапный переход**: Постепенно переводить пользователей на новую систему
6. **Мониторинг**: Следить за производительностью и стабильностью

### 6.2 Мониторинг производительности
```python
class PerformanceMonitor:
    def __init__(self, automation_system):
        self.automation = automation_system
        self.metrics = {
            'import_times': [],
            'success_rates': [],
            'error_counts': [],
            'recovery_attempts': []
        }
    
    def record_import(self, success: bool, duration: float, recovery_attempts: int):
        """Запись метрик импорта"""
        self.metrics['import_times'].append(duration)
        self.metrics['success_rates'].append(success)
        self.metrics['error_counts'].append(1 if not success else 0)
        self.metrics['recovery_attempts'].append(recovery_attempts)
    
    def get_performance_report(self):
        """Получение отчета о производительности"""
        if not self.metrics['import_times']:
            return {}
        
        avg_import_time = sum(self.metrics['import_times']) / len(self.metrics['import_times'])
        success_rate = sum(self.metrics['success_rates']) / len(self.metrics['success_rates'])
        avg_recovery_attempts = sum(self.metrics['recovery_attempts']) / len(self.metrics['recovery_attempts'])
        
        return {
            'average_import_time': avg_import_time,
            'success_rate': success_rate,
            'total_imports': len(self.metrics['import_times']),
            'total_errors': sum(self.metrics['error_counts']),
            'average_recovery_attempts': avg_recovery_attempts
        }
```

Эта интеграция обеспечит плавный переход на новую систему automation с сохранением обратной совместимости и возможностью отладки.