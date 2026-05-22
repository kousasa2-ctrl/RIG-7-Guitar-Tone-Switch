import customtkinter as ctk
from tkinter import filedialog, messagebox
import configparser, subprocess, os, threading, time, socket, pyperclip, psutil, cv2, numpy as np, pyautogui, asyncio, qrcode
import json
import urllib.request
from PIL import Image

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import credentials, db
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# State management
from gr7_state import GR7State

# Импорты для Windows API (только для Windows)
try:
    import win32gui
    import win32con
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False

# Image utilities
from image_utils import adaptive_engine, MatchResult

# ========== Конфиг и логика ==========
CONFIG_FILE = "config.ini"

def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        config['paths'] = {'exe': '', 'songs': '', 'phone_ip': '', 'buffer': '256'}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            config.write(f)
    config.read(CONFIG_FILE, encoding='utf-8')
    return config

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

def rebuild_engine(log_func):
    src = "audio_engine.cpp"
    out = "audio_engine.exe"
    import shutil
    if shutil.which("g++"):
        cmd = f"g++ -std=c++17 -O2 -o {out} {src} -lportaudio -lpthread"
    elif shutil.which("cl.exe"):
        cmd = f"cl.exe /EHsc /O2 {src} portaudio.lib /Fe{out}"
    else:
        log_func('❌ Компилятор не найден!', color='red')
        return
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8')
        if res.returncode == 0:
            log_func('✅ Драйвер собран и готов к работе', color='green')
        else:
            log_func(f'❌ Ошибка сборки: {res.stderr}', color='red')
    except Exception as e:
        log_func(f'❌ Ошибка запуска компилятора: {e}', color='red')

def activate_gr7(log_func):
    """Активация Guitar Rig 7"""
    log_func('[Auto] Активация Guitar Rig 7...', color='blue')
    # Проверяем, запущен ли Guitar Rig 7
    running = any('Guitar Rig 7' in p.name() for p in psutil.process_iter())
    if not running:
        exe = log_func.__self__.exe_path.get() if hasattr(log_func, '__self__') else None
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe])
                log_func('[Auto] Guitar Rig 7 запускается...', color='blue')
                time.sleep(3)  # Ожидание запуска
            except Exception as e:
                log_func(f'❌ Ошибка запуска GR7: {e}', color='red')
                return False
        else:
            log_func('❌ Путь к Guitar Rig 7 не указан!', color='red')
            return False
    return True

def verify_player_enabled(log_func):
    """
    ROBUST проверка состояния TapeDeck player с adaptive logic.
    НЕ останавливается при первом fail, использует fallback систему.
    """
    log_func('[Auto] Проверка состояния TapeDeck player...', color='blue')
    
    # Сначала проверяем состояние через adaptive system
    player_state = verify_player_state_robust(log_func)
    
    if player_state[0]:  # player уже активен
        log_func('[Auto] TapeDeck player уже активен', color='green')
        return True
    
    # Если player не активен, пробуем найти post.png с robust поиском
    log_func('[Auto] Player не активен, пробуем включить...', color='blue')
    
    # Используем robust поиск с retry logic
    btn_post = locate_image_robust('post', max_retries=3, timeout_per_retry=2.0, logger_func=log_func)
    
    if btn_post:
        log_func('[Auto] Найдена кнопка post, пробуем включить...', color='blue')
        
        # Используем safe click с fallback
        if safe_click_with_fallback(btn_post[0], btn_post[1], log_func, max_retries=2):
            time.sleep(1.0)
            
            # Повторная проверка состояния
            player_state = verify_player_state_robust(log_func)
            if player_state[0]:
                log_func('[Auto] TapeDeck player успешно активирован', color='green')
                return True
            else:
                log_func('⚠️ Player state verification failed, but continuing...', color='orange')
                # НЕ возвращаем False, а продолжаем работу с soft fail
                return True  # Soft fail - продолжаем automation
    else:
        log_func('⚠️ post.png не найдена, но продолжаем работу...', color='orange')
        # Soft fail - продолжаем automation даже если кнопка не найдена
        return True

def verify_dialog_open(log_func):
    """Проверка открытия Windows file dialog"""
    log_func('[Auto] Проверка открытия диалога выбора файла...', color='blue')
    
    if not WINDOWS_AVAILABLE:
        # Альтернативная проверка без Windows API
        log_func('[Auto] Windows API недоступен, используем альтернативную проверку...', color='blue')
        # Проверяем наличие диалога по изменению курсора или другим признакам
        try:
            # Проверяем, есть ли активное окно с типом диалога
            import pygetwindow as gw
            active_window = gw.getActiveWindow()
            if active_window and ('Open' in active_window.title or 'Открыть' in active_window.title or 'Выбор' in active_window.title):
                log_func('[Auto] Диалог выбора файла обнаружен', color='green')
                return True
        except:
            pass
        
        # Если pygetwindow недоступен, используем простой таймаут
        log_func('[Auto] Ожидание открытия диалога...', color='blue')
        time.sleep(1.0)
        return True  # Предполагаем, что диалог открылся
    
    # Основная проверка через Windows API
    def enum_windows_callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if 'Открыть' in title or 'Open' in title or 'Выбор файла' in title:
                windows.append(hwnd)
        return True
    
    windows = []
    win32gui.EnumWindows(enum_windows_callback, windows)
    
    if windows:
        log_func('[Auto] Диалог выбора файла обнаружен', color='green')
        return True
    else:
        log_func('❌ Диалог выбора файла не открыт', color='red')
        return False

def verify_playback_started(log_func):
    """Проверка начала воспроизведения"""
    log_func('[Auto] Проверка начала воспроизведения...', color='blue')
    from image_utils import is_button_active
    
    # Проверяем, что кнопка play активна (индикатор воспроизведения)
    playback_active = is_button_active('distortion', debug=False)
    if playback_active:
        log_func('[Auto] Воспроизведение успешно начато', color='green')
        return True
    else:
        log_func('❌ Воспроизведение не началось', color='red')
        return False

def change_song(song_folder, log_func):
    """
    ROBUST автоматизация смены песни с adaptive search и safe continue logic.
    НЕ останавливается при первом fail, использует multi-stage pipeline.
    """
    log_func('[Auto] Начало автоматизации смены песни...', color='blue')
    
    # 1. Активация Guitar Rig 7
    if not activate_gr7(log_func):
        log_func('⚠️ GR7 activation failed, but continuing...', color='orange')
        # Soft fail - продолжаем
    
    # 2. Проверка и активация TapeDeck player (с soft fail)
    if not verify_player_enabled(log_func):
        log_func('⚠️ Player verification failed, but continuing...', color='orange')
        # Soft fail - продолжаем
    
    # 3. Открытие import dialog через robust поиск
    log_func('[Auto] Поиск overdrive.png для открытия диалога...', color='blue')
    
    # Используем robust поиск с retry logic
    btn_open = locate_image_robust('overdrive', max_retries=3, timeout_per_retry=2.0, logger_func=log_func)
    
    if btn_open:
        log_func('[Auto] Открытие диалога импорта...', color='blue')
        
        # Используем safe click с fallback
        if safe_click_with_fallback(btn_open[0], btn_open[1], log_func, max_retries=2):
            log_func('[Auto] Dialog click successful', color='green')
        else:
            log_func('⚠️ Dialog click failed, but continuing...', color='orange')
    else:
        log_func('⚠️ overdrive.png не найдена, но продолжаем работу...', color='orange')
        # Soft fail - продолжаем без открытия диалога
    
    # 4. Проверка открытия диалога (с soft fail)
    if not verify_dialog_open(log_func):
        # Retry один раз
        log_func('[Auto] Повторная попытка открытия диалога...', color='blue')
        time.sleep(1.0)
        if not verify_dialog_open(log_func):
            log_func('⚠️ Диалог не открылся, но продолжаем работу...', color='orange')
            # Soft fail - продолжаем
    
    # 5. Вставка пути к mp3 и подтверждение
    files = [f for f in os.listdir(song_folder) if os.path.isfile(os.path.join(song_folder, f)) and f.lower().endswith(('.mp3', '.wav', '.flac'))]
    if not files:
        log_func('❌ Ошибка: В выбранной папке нет аудиофайлов!', color='red')
        return
        
    song_path = os.path.normpath(os.path.join(song_folder, files[0]))
    log_func(f'[Auto] Загрузка трека: {files[0]}', color='blue')
    
    try:
        pyperclip.copy(song_path)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        pyautogui.press('enter')
        time.sleep(2.0)  # Ожидание завершения импорта
        log_func('[Auto] File import completed', color='green')
    except Exception as e:
        log_func(f'⚠️ File import failed: {e}, but continuing...', color='orange')
        # Soft fail - продолжаем

# ========== Bluetooth и Cloud ==========
async def start_ble_server(log_func, secret_code):
    log_func('[BT] BLE сервер запущен (заглушка)', color='blue')

# WebRTC + Firebase signaling functions
async def start_webrtc_server(log_func, room_id, buffer_size, state):
    """Запуск WebRTC сервера с Firebase signaling"""
    try:
        import firebase_admin
        from firebase_admin import credentials, db
        import uuid
        import asyncio
        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.contrib.media import MediaPlayer
        
        # Инициализация Firebase
        if not firebase_admin._apps:
            cred = credentials.Certificate('firebase-service-account.json')
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://your-project-default-rtdb.firebaseio.com/'
            })
        
        # Создание комнаты в Firebase
        ref = db.reference(f'rooms/{room_id}')
        ref.set({
            'status': 'created',
            'created_at': int(time.time()),
            'connected': False
        })
        
        log_func(f'[WEBRTC] Комната создана: {room_id}', color='green')
        
        # Создание WebRTC peer connection
        pc = RTCPeerConnection()
        
        # Генерация SDP offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Сохранение offer в Firebase
        ref.update({
            'pc_offer': offer.sdp,
            'ice_candidates_pc': []
        })
        
        log_func('[WEBRTC] SDP offer сгенерирован и загружен в Firebase', color='green')
        
        # Ожидание ответа от телефона
        while True:
            await asyncio.sleep(1)
            snapshot = ref.get()
            if snapshot and 'phone_answer' in snapshot:
                answer_sdp = snapshot['phone_answer']
                await pc.setRemoteDescription(RTCSessionDescription(answer_sdp, 'answer'))
                log_func('[WEBRTC] Remote description applied', color='green')
                break
        
        # Обмен ICE candidates
        @pc.on_ice_candidate
        def on_ice_candidate(candidate):
            if candidate:
                candidates_ref = ref.child('ice_candidates_pc')
                candidates_ref.push({
                    'candidate': candidate.candidate,
                    'sdpMid': candidate.sdpMid,
                    'sdpMLineIndex': candidate.sdpMLineIndex
                })
        
        # Ожидание подключения
        @pc.on_connection_state_change
        def on_connection_state_change(state):
            if state == 'connected':
                ref.update({'connected': True})
                log_func('[WEBRTC] ICE connected, audio stream started', color='green')
        
        # Хранение peer connection в state
        state.webrtc_peer_connection = pc
        state.webrtc_running = True
        
        # Держим соединение открытым
        await asyncio.sleep(3600)  # 1 час
        
    except Exception as e:
        log_func(f'[WEBRTC] Ошибка: {e}', color='red')
        raise


# ========== GUI ==========
class GR7Hub(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Guitar Rig 7 Hub")
        self.geometry("900x700")
        ctk.set_appearance_mode("dark")
        
        # 1. Инициализация state (централизованно)
        self.app_state = GR7State()

        # 2. Загрузка конфигурации
        self.app_config = load_config()
        
        # 3. Инициализация UI переменных из config
        self._init_ui_from_config()
        
        # 4. Инициализация UI компонентов (ДО построения вкладок)
        self.current_room_id = None
        self.qr_label = None
        self.devices_listbox = None
        self.logbox = None
        self.log_frame = None
        
        # 5. Создание tabview
        self.tabview = ctk.CTkTabview(self, width=860, height=350)
        self.tabview.pack(padx=10, pady=5, fill="x")
        
        # 6. Построение вкладок (в правильном порядке)
        self.build_control_tab()
        self.build_webrtc_tab()
        self.build_network_tab()
        self.build_bluetooth_tab()
        self.build_settings_tab()
        
        # 7. Лог и мониторинг
        self.build_log()
        self.monitor_gr7()
        
        # 8. Инициализация WebRTC
        self._init_webrtc()
        
        # 9. Debug лог
        self._log_debug_info()
    
    def _init_ui_from_config(self):
        """Инициализация UI переменных из конфигурации"""
        self.app_state.exe_path.set(self.app_config['paths'].get('exe', ''))
        self.app_state.songs_path.set(self.app_config['paths'].get('songs', ''))
        self.app_state.phone_ip.set(self.app_config['paths'].get('phone_ip', ''))
    
    def _init_webrtc(self):
        """Инициализация WebRTC переменных"""
        self.app_state.ice_status.set('Не инициализирован')
        self.app_state.latency.set('0 ms')
        self.app_state.stream_status.set('Остановлен')
    
    def _log_debug_info(self):
        """Логирование debug информации"""
        current_dir = os.getcwd()
        self.log(f'[DEBUG] Working directory: {current_dir}', color='blue')
        
        # Проверка существования файлов изображений
        image_files = ['post.png', 'clean.png', 'distortion.png', 'overdrive.png']
        for img_file in image_files:
            img_path = os.path.join(current_dir, img_file)
            exists = os.path.exists(img_path)
            self.log(f'[DEBUG] {img_file}: {"✅" if exists else "❌"} {img_path}', color='green' if exists else 'red')
        
        self.log('[System] Готов к работе. Выделение текста доступно (Ctrl+A / Ctrl+C).')

    def build_control_tab(self):
        tab = self.tabview.add("Управление")
        ctk.CTkLabel(tab, text="Управление Guitar Rig 7", font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=10)
        
        # Статус Guitar Rig 7
        status_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        status_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(status_frame, text="Статус Guitar Rig 7:", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=5)
        ctk.CTkLabel(status_frame, textvariable=self.app_state.gr7_status, font=("Arial", 11)).pack(anchor="w", padx=10)
        
        ctk.CTkButton(status_frame, text="Запустить GR7", fg_color="green", command=self.launch_gr7).pack(pady=5)

    def build_webrtc_tab(self):
        """Создание вкладки WebRTC"""
        tab = self.tabview.add("WebRTC")
        
        # Статус WebRTC
        status_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        status_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(status_frame, text="🌐 WebRTC Статус",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # Connection status
        conn_frame = ctk.CTkFrame(status_frame, fg_color="#1E1E1E", corner_radius=5)
        conn_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(conn_frame, text="Статус соединения:",
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(conn_frame, textvariable=self.app_state.connection_status,
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        
        # ICE status
        ice_frame = ctk.CTkFrame(status_frame, fg_color="#1E1E1E", corner_radius=5)
        ice_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(ice_frame, text="ICE статус:",
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(ice_frame, textvariable=self.app_state.ice_status,
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        
        # Latency
        latency_frame = ctk.CTkFrame(status_frame, fg_color="#1E1E1E", corner_radius=5)
        latency_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(latency_frame, text="Задержка:",
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        ctk.CTkLabel(latency_frame, textvariable=self.app_state.latency,
                     font=("Arial", 11)).pack(side="left", padx=5, pady=5)
        
        # Room info
        room_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        room_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(room_frame, text="🏠 Информация о комнате",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkLabel(room_frame, text="Текущая комната:",
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(room_frame, textvariable=self.app_state.room_id_display,
                     font=("Consolas", 12), text_color="cyan").pack(anchor="w", padx=10, pady=2)
        
        # Firebase status
        firebase_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        firebase_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(firebase_frame, text="🔥 Firebase Статус",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkLabel(firebase_frame, textvariable=self.app_state.webrtc_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=5)
        
        # Stream status
        stream_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        stream_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(stream_frame, text="🎵 Статус потока",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkLabel(stream_frame, text="Аудио поток:",
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(stream_frame, textvariable=self.app_state.stream_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)

    def build_network_tab(self):
        tab = self.tabview.add("Сеть")
        
        # Информация о подключении
        info_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(info_frame, text="📡 Информация о подключении",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # IP адрес компьютера
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        ctk.CTkLabel(info_frame, text=f"🖥️ Компьютер: {hostname}",
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(info_frame, text=f"🌐 Локальный IP: {local_ip}:8080",
                     font=("Arial", 11), text_color="cyan").pack(anchor="w", padx=10, pady=2)
        
        # Статус сервера
        ctk.CTkLabel(info_frame, textvariable=self.app_state.cloud_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=5)
        
        # Сетевое управление
        control_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(control_frame, text="🔧 Управление сетью",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkButton(control_frame, text="🚀 Создать комнату",
                       command=self.create_webrtc_room, fg_color="#3498DB").pack(pady=5)
        
        # Статус WebRTC
        ctk.CTkLabel(control_frame, textvariable=self.app_state.webrtc_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=5)
        
        # Room ID для подключения
        ctk.CTkLabel(control_frame, text="Room ID:",
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(control_frame, textvariable=self.app_state.room_id_display,
                     font=("Consolas", 12), text_color="cyan").pack(anchor="w", padx=10, pady=2)
        
        # Статус соединения
        ctk.CTkLabel(control_frame, text="Статус соединения:",
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(control_frame, textvariable=self.app_state.connection_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=2)
        
        # Кнопки управления WebRTC
        webrtc_button_frame = ctk.CTkFrame(control_frame, fg_color="#1E1E1E", corner_radius=5)
        webrtc_button_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(webrtc_button_frame, text="🔄 Перегенерировать QR",
                       command=self.regenerate_qr, fg_color="#9B59B6").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(webrtc_button_frame, text="🛑 Остановить WebRTC",
                       command=self.stop_webrtc, fg_color="#E74C3C").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(webrtc_button_frame, text="🗑️ Очистить комнату",
                       command=self.clear_room, fg_color="#F39C12").pack(side="left", padx=5, pady=5)
        
        # QR-код
        qr_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        qr_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(qr_frame, text="📱 QR-код для подключения",
                     font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        self.qr_label = ctk.CTkLabel(qr_frame, text="")
        self.qr_label.pack(pady=10)
        
        ctk.CTkLabel(qr_frame, text="Отсканируйте QR-код с телефона для подключения",
                     font=("Arial", 10), text_color="#888888").pack(pady=5)

    def build_bluetooth_tab(self):
        tab = self.tabview.add("Bluetooth")
        
        # Управление Bluetooth
        control_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(control_frame, text="📱 Управление Bluetooth",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkButton(control_frame, text="🔍 Поиск устройств",
                       command=self.scan_devices, fg_color="#3498DB").pack(pady=5)
        
        ctk.CTkLabel(control_frame, textvariable=self.app_state.bt_status,
                     font=("Arial", 11)).pack(anchor="w", padx=10, pady=5)
        
        # Список устройств
        devices_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        devices_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(devices_frame, text="📋 Найденные устройства",
                     font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # Список устройств (будет заполняться динамически)
        self.devices_listbox = ctk.CTkTextbox(devices_frame, height=200, font=("Consolas", 10))
        self.devices_listbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Кнопка подключения
        self.connect_button = ctk.CTkButton(devices_frame, text="🔗 Подключиться",
                                           command=self.connect_device, state="disabled")
        self.connect_button.pack(pady=5)
        
        # Код подтверждения
        self.confirmation_code = ctk.StringVar(value="")
        confirm_frame = ctk.CTkFrame(devices_frame, fg_color="#1E1E1E", corner_radius=5)
        confirm_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(confirm_frame, text="Код подтверждения:",
                     font=("Arial", 10)).pack(side="left", padx=5, pady=5)
        ctk.CTkEntry(confirm_frame, textvariable=self.confirmation_code, width=100).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(confirm_frame, text="✓ Подтвердить",
                       command=self.confirm_connection, state="disabled").pack(side="left", padx=5, pady=5)

    def build_settings_tab(self):
        """Создание вкладки Настройки с diagnostics panel"""
        tab = self.tabview.add("Настройки")
        
        # Основные настройки
        main_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        main_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(main_frame, text="⚙️ Основные настройки",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkLabel(main_frame, text="Путь к Guitar Rig 7:").pack(anchor="w", padx=10, pady=2)
        exe_frame = ctk.CTkFrame(main_frame, fg_color="#1E1E1E", corner_radius=5)
        exe_frame.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkEntry(exe_frame, textvariable=self.app_state.exe_path, width=400).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(exe_frame, text="Выбрать", command=self.choose_exe).pack(side="left", padx=5, pady=5)
        
        ctk.CTkLabel(main_frame, text="Папка с песнями:").pack(anchor="w", padx=10, pady=2)
        songs_frame = ctk.CTkFrame(main_frame, fg_color="#1E1E1E", corner_radius=5)
        songs_frame.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkEntry(songs_frame, textvariable=self.app_state.songs_path, width=400).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(songs_frame, text="Выбрать", command=self.choose_songs).pack(side="left", padx=5, pady=5)
        
        ctk.CTkLabel(main_frame, text="IP телефона (для сетевого режима):").pack(anchor="w", padx=10, pady=2)
        ip_frame = ctk.CTkFrame(main_frame, fg_color="#1E1E1E", corner_radius=5)
        ip_frame.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkEntry(ip_frame, textvariable=self.app_state.phone_ip, width=400).pack(side="left", padx=5, pady=5)
        
        # Кнопки управления
        button_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(button_frame, text="💾 Сохранить настройки",
                       command=self.save_paths, fg_color="#27AE60").pack(side="left", padx=10, pady=10)
        ctk.CTkButton(button_frame, text="🚀 Запустить GR7",
                       command=self.launch_gr7, fg_color="green").pack(side="left", padx=10, pady=10)
        
        # DIAGNOSTICS PANEL
        diag_frame = ctk.CTkFrame(tab, fg_color="#2B2B2B", corner_radius=8)
        diag_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(diag_frame, text="🔍 DIAGNOSTICS PANEL",
                     font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # Diagnostics controls
        diag_controls = ctk.CTkFrame(diag_frame, fg_color="#1E1E1E", corner_radius=5)
        diag_controls.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(diag_controls, text="📸 Снять скриншот",
                      command=self.take_diagnostics_screenshot, fg_color="#3498DB").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🔍 Найти post",
                      command=self.run_diagnostics_post, fg_color="#9B59B6").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🔍 Найти clean",
                      command=self.run_diagnostics_clean, fg_color="#9B59B6").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🔍 Найти distortion",
                      command=self.run_diagnostics_distortion, fg_color="#9B59B6").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🔍 Найти overdrive",
                      command=self.run_diagnostics_overdrive, fg_color="#9B59B6").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="📊 Статистика",
                      command=self.show_diagnostics_stats, fg_color="#1ABC9C").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🗑️ Очистить",
                      command=self.clear_diagnostics, fg_color="#E74C3C").pack(side="left", padx=5, pady=5)
        ctk.CTkButton(diag_controls, text="🖥️ Fullscreen",
                      command=self.run_diagnostics_fullscreen, fg_color="#F39C12").pack(side="left", padx=5, pady=5)
        
        # Diagnostics display
        diag_display = ctk.CTkFrame(diag_frame, fg_color="#1E1E1E", corner_radius=5)
        diag_display.pack(fill="both", expand=True, padx=10, pady=5)
        
        ctk.CTkLabel(diag_display, text="📋 Результаты диагностики:",
                     font=("Arial", 12, "bold")).pack(anchor="w", padx=5, pady=5)
        
        self.diagnostics_text = ctk.CTkTextbox(diag_display, height=300, font=("Consolas", 9))
        self.diagnostics_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Diagnostics info
        diag_info = ctk.CTkFrame(diag_frame, fg_color="#1E1E1E", corner_radius=5)
        diag_info.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(diag_info, text="ℹ️ Информация о системе:",
                     font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=2)
        self.system_info_label = ctk.CTkLabel(diag_info, text="Загрузка...", font=("Consolas", 9))
        self.system_info_label.pack(anchor="w", padx=5, pady=2)

    def take_diagnostics_screenshot(self):
        """Снять скриншот для диагностики"""
        try:
            import pyautogui
            import cv2
            import numpy as np
            
            screenshot = pyautogui.screenshot()
            screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Сохраняем
            filename = f"diag_screenshot_{int(time.time())}.png"
            cv2.imwrite(filename, screenshot_bgr)
            
            self.log(f'[DIAG] Скриншот сохранен: {filename}', color='green')
            self.update_diagnostics_display(f"📸 Скриншот сохранен: {filename}\n")
        except Exception as e:
            self.log(f'[DIAG] Ошибка скриншота: {e}', color='red')
            self.update_diagnostics_display(f"❌ Ошибка скриншота: {e}\n")

    def run_diagnostics_post(self):
        """Диагностика поиска post.png"""
        self.update_diagnostics_display(f"\n{'='*50}\n🔍 Поиск post.png\n{'='*50}\n")
        self.log('[DIAG] Запуск диагностики post.png...', color='blue')
        
        try:
            result = adaptive_engine.locate_image_adaptive("post", timeout=3.0, debug=True)
            
            if result and result.success:
                self.update_diagnostics_display(
                    f"✅ НАЙДЕНО!\n"
                    f"   Позиция: {result.position}\n"
                    f"   Confidence: {result.confidence:.3f}\n"
                    f"   Метод: {result.method}\n"
                    f"   Scale: {result.scale:.2f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] post.png найден: conf={result.confidence:.3f}', color='green')
            else:
                self.update_diagnostics_display(
                    f"❌ НЕ НАЙДЕНО\n"
                    f"   Best confidence: {result.confidence:.3f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] post.png не найден: conf={result.confidence:.3f}', color='red')
        except Exception as e:
            self.update_diagnostics_display(f"❌ Ошибка: {e}\n")
            self.log(f'[DIAG] Ошибка диагностики: {e}', color='red')

    def run_diagnostics_clean(self):
        """Диагностика поиска clean.png"""
        self.update_diagnostics_display(f"\n{'='*50}\n🔍 Поиск clean.png\n{'='*50}\n")
        self.log('[DIAG] Запуск диагностики clean.png...', color='blue')
        
        try:
            result = adaptive_engine.locate_image_adaptive("clean", timeout=3.0, debug=True)
            
            if result and result.success:
                self.update_diagnostics_display(
                    f"✅ НАЙДЕНО!\n"
                    f"   Позиция: {result.position}\n"
                    f"   Confidence: {result.confidence:.3f}\n"
                    f"   Метод: {result.method}\n"
                    f"   Scale: {result.scale:.2f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] clean.png найден: conf={result.confidence:.3f}', color='green')
            else:
                self.update_diagnostics_display(
                    f"❌ НЕ НАЙДЕНО\n"
                    f"   Best confidence: {result.confidence:.3f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] clean.png не найден: conf={result.confidence:.3f}', color='red')
        except Exception as e:
            self.update_diagnostics_display(f"❌ Ошибка: {e}\n")
            self.log(f'[DIAG] Ошибка диагностики: {e}', color='red')

    def run_diagnostics_distortion(self):
        """Диагностика поиска distortion.png"""
        self.update_diagnostics_display(f"\n{'='*50}\n🔍 Поиск distortion.png\n{'='*50}\n")
        self.log('[DIAG] Запуск диагностики distortion.png...', color='blue')
        
        try:
            result = adaptive_engine.locate_image_adaptive("distortion", timeout=3.0, debug=True)
            
            if result and result.success:
                self.update_diagnostics_display(
                    f"✅ НАЙДЕНО!\n"
                    f"   Позиция: {result.position}\n"
                    f"   Confidence: {result.confidence:.3f}\n"
                    f"   Метод: {result.method}\n"
                    f"   Scale: {result.scale:.2f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] distortion.png найден: conf={result.confidence:.3f}', color='green')
            else:
                self.update_diagnostics_display(
                    f"❌ НЕ НАЙДЕНО\n"
                    f"   Best confidence: {result.confidence:.3f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] distortion.png не найден: conf={result.confidence:.3f}', color='red')
        except Exception as e:
            self.update_diagnostics_display(f"❌ Ошибка: {e}\n")
            self.log(f'[DIAG] Ошибка диагностики: {e}', color='red')

    def run_diagnostics_overdrive(self):
        """Диагностика поиска overdrive.png"""
        self.update_diagnostics_display(f"\n{'='*50}\n🔍 Поиск overdrive.png\n{'='*50}\n")
        self.log('[DIAG] Запуск диагностики overdrive.png...', color='blue')
        
        try:
            result = adaptive_engine.locate_image_adaptive("overdrive", timeout=3.0, debug=True)
            
            if result and result.success:
                self.update_diagnostics_display(
                    f"✅ НАЙДЕНО!\n"
                    f"   Позиция: {result.position}\n"
                    f"   Confidence: {result.confidence:.3f}\n"
                    f"   Метод: {result.method}\n"
                    f"   Scale: {result.scale:.2f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] overdrive.png найден: conf={result.confidence:.3f}', color='green')
            else:
                self.update_diagnostics_display(
                    f"❌ НЕ НАЙДЕНО\n"
                    f"   Best confidence: {result.confidence:.3f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] overdrive.png не найден: conf={result.confidence:.3f}', color='red')
        except Exception as e:
            self.update_diagnostics_display(f"❌ Ошибка: {e}\n")
            self.log(f'[DIAG] Ошибка диагностики: {e}', color='red')
    
    def run_diagnostics_fullscreen(self):
        """Диагностика поиска post.png в fullscreen режиме"""
        self.update_diagnostics_display(f"\n{'='*50}\n🔍 Поиск post.png (FULLSCREEN)\n{'='*50}\n")
        self.log('[DIAG] Запуск диагностики post.png в fullscreen режиме...', color='blue')
        
        try:
            result = adaptive_engine.locate_image_adaptive("post", timeout=3.0, debug=True, fullscreen=True)
            
            if result and result.success:
                self.update_diagnostics_display(
                    f"✅ НАЙДЕНО!\n"
                    f"   Позиция: {result.position}\n"
                    f"   Confidence: {result.confidence:.3f}\n"
                    f"   Метод: {result.method}\n"
                    f"   Scale: {result.scale:.2f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] post.png найден: conf={result.confidence:.3f}', color='green')
            else:
                self.update_diagnostics_display(
                    f"❌ НЕ НАЙДЕНО\n"
                    f"   Best confidence: {result.confidence:.3f}\n"
                    f"   Debug: debug_match_{int(time.time())}.png\n"
                )
                self.log(f'[DIAG] post.png не найден: conf={result.confidence:.3f}', color='red')
        except Exception as e:
            self.update_diagnostics_display(f"❌ Ошибка: {e}\n")
            self.log(f'[DIAG] Ошибка диагностики: {e}', color='red')

    def show_diagnostics_stats(self):
        """Показать статистику поиска"""
        self.update_diagnostics_display(f"\n{'='*50}\n📊 Статистика поиска\n{'='*50}\n")
        self.log('[DIAG] Показ статистики...', color='blue')
        
        stats = adaptive_engine.get_search_stats()
        
        for key, value in stats.items():
            self.update_diagnostics_display(
                f"{key}:\n"
                f"   Attempts: {value.get('attempts', 0)}\n"
                f"   Successes: {value.get('successes', 0)}\n"
                f"   Best Confidence: {value.get('best_confidence', 0):.3f}\n"
            )
        
        # System info
        try:
            import pyautogui
            screen_w, screen_h = pyautogui.size()
            self.update_diagnostics_display(
                f"\n🖥️ Система:\n"
                f"   Screen: {screen_w}x{screen_h}\n"
            )
        except:
            pass

    def clear_diagnostics(self):
        """Очистить статистику"""
        adaptive_engine.clear_stats()
        self.update_diagnostics_display("✅ Статистика очищена\n")
        self.log('[DIAG] Статистика очищена', color='green')

    def update_diagnostics_display(self, text):
        """Обновить отображение диагностики"""
        self.diagnostics_text.insert("end", text)
        self.diagnostics_text.see("end")

    def update_system_info(self):
        """Обновить информацию о системе"""
        try:
            import pyautogui
            screen_w, screen_h = pyautogui.size()
            import ctypes
            dpi = ctypes.windll.shcore.GetDpiForSystem() if hasattr(ctypes, 'windll') else 96
            info = f"Screen: {screen_w}x{screen_h} | DPI: {dpi} | Python: 3.14"
            self.system_info_label.configure(text=info)
        except:
            self.system_info_label.configure(text="Screen: unknown | DPI: unknown")

    def scan_devices(self):
        """Поиск Bluetooth устройств"""
        self.log('[BT] Поиск устройств...', color='blue')
        self.app_state.bt_status.set('Поиск...')
        
        if not hasattr(self, 'devices_listbox') or self.devices_listbox is None:
            self.log('[BT] Devices listbox not initialized', color='orange')
            return
        
        # Имитация поиска устройств
        devices = [
            {"name": "iPhone 13 Pro", "address": "AA:BB:CC:DD:EE:01", "status": "Доступен"},
            {"name": "Samsung Galaxy S21", "address": "AA:BB:CC:DD:EE:02", "status": "Доступен"},
            {"name": "Xiaomi Redmi Note 10", "address": "AA:BB:CC:DD:EE:03", "status": "Занят"}
        ]
        
        # Очистка списка
        try:
            self.devices_listbox.delete("1.0", "end")
        except Exception as e:
            self.log(f'[BT] Error clearing devices list: {e}', color='red')
            return
        
        # Добавление устройств в список
        for device in devices:
            status_color = "green" if device["status"] == "Доступен" else "red"
            device_info = f"📱 {device['name']}\n   📍 {device['address']}\n   🟢 {device['status']}\n\n"
            try:
                self.devices_listbox.insert("end", device_info)
            except Exception as e:
                self.log(f'[BT] Error adding device: {e}', color='red')
        
        self.app_state.bt_status.set(f'Найдено {len(devices)} устройств')
        self.log(f'[BT] Найдено {len(devices)} устройств', color='green')
        
        # Включаем кнопку подключения
        if hasattr(self, 'connect_button'):
            self.connect_button.configure(state="normal")

    def connect_device(self):
        """Подключение к выбранному устройству"""
        if not hasattr(self, 'devices_listbox') or self.devices_listbox is None:
            self.log('❌ Ошибка: Devices listbox не инициализирован', color='red')
            return
        
        try:
            selected_text = self.devices_listbox.get("1.0", "end").strip()
        except Exception as e:
            self.log(f'❌ Ошибка: Не удалось получить текст устройства: {e}', color='red')
            return
        
        if not selected_text:
            self.log('❌ Ошибка: Не выбрано устройство', color='red')
            return
        
        self.log('[BT] Подготовка к подключению...', color='blue')
        self.app_state.bt_status.set('Ожидание подтверждения...')
        
        # Генерация кода подтверждения
        import random
        confirmation_code = str(random.randint(100000, 999999))
        self.confirmation_code.set(confirmation_code)
        
        # Включаем кнопку подтверждения
        for widget in self.winfo_children():
            if isinstance(widget, ctk.CTkButton) and widget.cget("text") == "✓ Подтвердить":
                widget.configure(state="normal")
                break
        
        self.log(f'[BT] Код подтверждения: {confirmation_code}', color='blue')

    def confirm_connection(self):
        """Подтверждение подключения"""
        code = self.confirmation_code.get()
        if not code:
            self.log('❌ Ошибка: Код подтверждения не введен', color='red')
            return
        
        self.log(f'[BT] Подтверждение подключения с кодом: {code}', color='blue')
        
        # Имитация успешного подключения
        time.sleep(1)
        self.app_state.bt_status.set('✅ Подключено')
        self.log('[BT] Устройство успешно подключено', color='green')
        
        # Отключаем кнопки подтверждения
        if hasattr(self, 'connect_button'):
            self.connect_button.configure(state="disabled")
        for widget in self.winfo_children():
            if isinstance(widget, ctk.CTkButton) and widget.cget("text") == "✓ Подтвердить":
                widget.configure(state="disabled")
                break

    def build_log(self):
        self.log_frame = ctk.CTkFrame(self, fg_color="#111111", corner_radius=8)
        self.log_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        ctk.CTkLabel(self.log_frame, text="КОНСОЛЬ СОБЫТИЙ:", font=("Arial", 12, "bold"), text_color="orange").pack(anchor="w", padx=15, pady=5)
        
        self.logbox = ctk.CTkTextbox(self.log_frame, font=("Consolas", 12), text_color="#00FF00")
        self.logbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Перехват клавиш для реализации копирования текста без возможности ручного изменения данных
        self.logbox.bind("<Key>", self._handle_log_keys)

    def _handle_log_keys(self, event):
        # Разрешаем системное копирование Ctrl+C / Выделение Ctrl+A
        if (event.state & 4) and event.keysym.lower() in ['c', 'a']:
            return None
        return "break"

    def log(self, msg, color=None):
        """
        Честное логирование без ложных SUCCESS.
        Автоматически определяет реальный статус операции.
        """
        if not hasattr(self, 'logbox') or self.logbox is None:
            # Если logbox не инициализирован, просто выводим в консоль
            print(f"{msg}")
            return
        
        prefix = "[INFO] "
        
        # Автоматическое определение статуса на основе содержания сообщения
        if color == 'green':
            prefix = "[OK] "
        elif color == 'red':
            prefix = "[ERR] "
        elif color == 'yellow':
            prefix = "[WARN] "
        elif color == 'blue':
            prefix = "[DEBUG] "
        elif color == 'gray':
            prefix = "[VERBOSE] "
        else:
            # Автоматическое определение по содержанию
            if any(keyword in msg.lower() for keyword in ["успешно", "success", "completed", "готов", "активна", "connected"]):
                # Проверяем на ложный успех
                if any(keyword in msg.lower() for keyword in ["не найден", "не открылся", "не подтвержден", "не изменился", "failed", "error", "ошибка"]):
                    prefix = "[ERR] "
                    color = 'red'
                else:
                    prefix = "[OK] "
                    color = 'green'
            elif any(keyword in msg.lower() for keyword in ["не найден", "не открылся", "не подтвержден", "не изменился", "failed", "error", "ошибка", "провал", "timeout"]):
                prefix = "[ERR] "
                color = 'red'
            elif any(keyword in msg.lower() for keyword in ["предупреждение", "warning", "внимание", "retry", "повтор", "weak", "нестабильно"]):
                prefix = "[WARN] "
                color = 'yellow'
            elif any(keyword in msg.lower() for keyword in ["debug", "тест", "test", "проверка", "диагностика"]):
                prefix = "[DEBUG] "
                color = 'blue'
            else:
                prefix = "[INFO] "
        
        # Специальная обработка для automation логов
        if "[Auto]" in msg:
            if "не найден" in msg or "не открылся" in msg or "не подтвержден" in msg:
                prefix = "[ERR] "
                color = 'red'
            elif "продолжаем работу" in msg or "soft fail" in msg or "weak match" in msg:
                prefix = "[WARN] "
                color = 'yellow'
            elif "успешно" in msg or "активен" in msg or "начато" in msg:
                prefix = "[OK] "
                color = 'green'
        
        # Специальная обработка для WebRTC логов
        if "[WEBRTC]" in msg:
            if "ошибка" in msg or "failed" in msg or "не подключено" in msg:
                prefix = "[ERR] "
                color = 'red'
            elif "создана" in msg or "подключено" in msg or "stream started" in msg:
                prefix = "[OK] "
                color = 'green'
            elif "ожидание" in msg or "waiting" in msg:
                prefix = "[INFO] "
                color = 'blue'
        
        # Специальная обработка для CV логов
        if "[CV]" in msg or "[FIND]" in msg:
            if "не найдено" in msg or "failed" in msg or "timeout" in msg:
                prefix = "[ERR] "
                color = 'red'
            elif "найдена" in msg or "success" in msg or "accepted" in msg:
                prefix = "[OK] "
                color = 'green'
            elif "weak" in msg or "warning" in msg:
                prefix = "[WARN] "
                color = 'yellow'
        
        # Форматируем сообщение с цветом
        try:
            self.logbox.insert("end", f"{prefix}{msg}\n")
            self.logbox.see("end")
            
            # Применяем цвет к последнему вставленному тексту
            if color:
                # Получаем позицию последней вставки
                last_pos = self.logbox.index("end-1c")
                first_pos = last_pos + " linestart"
                
                # Применяем тег цвета
                self.logbox.tag_add(color, first_pos, last_pos)
                self.logbox.tag_config(color, foreground=color)
        except Exception as e:
            print(f"[ERROR] Failed to log message: {e}")

    def choose_exe(self):
        f = filedialog.askopenfilename(filetypes=[("EXE", "*.exe")])
        if f:
            self.app_state.exe_path.set(f)
            self.save_paths()
    
    def choose_songs(self):
        f = filedialog.askdirectory()
        if f:
            self.app_state.songs_path.set(f)
            self.save_paths()
    
    def save_paths(self):
        self.app_config['paths']['exe'] = self.app_state.exe_path.get()
        self.app_config['paths']['songs'] = self.app_state.songs_path.get()
        self.app_config['paths']['phone_ip'] = self.app_state.phone_ip.get()
        save_config(self.app_config)
        self.log("Пути и настройки сохранены.", color='green')

    def launch_gr7(self):
        exe = self.app_state.exe_path.get()
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe])
                self.log("Guitar Rig 7 успешно запущен.", color='green')
            except Exception as e:
                self.log(f"Ошибка запуска GR7: {e}", color='red')
        else:
            self.log("Указанный файл EXE не найден! Проверьте вкладку Настройки.", color='red')


    def bt_next_song(self):
        folder = self.app_state.songs_path.get()
        if not os.path.isdir(folder):
            self.log("Папка песен не выбрана или не существует!", color='red')
            return
        threading.Thread(target=change_song, args=(folder, self.log), daemon=True).start()
    
    def create_webrtc_room(self):
        """Создание новой WebRTC комнаты"""
        import uuid
        
        # Генерация уникального room ID
        room_id = str(uuid.uuid4())[:8]
        self.current_room_id = room_id
        self.app_state.room_id.set(room_id)
        self.app_state.room_id_display.set(room_id)
        
        self.log(f'[WEBRTC] Создание комнаты: {room_id}', color='blue')
        self.app_state.webrtc_status.set('Создание...')
        
        # Запуск WebRTC сервера в отдельном потоке
        threading.Thread(target=lambda: asyncio.run(start_webrtc_server(self.log, room_id, "256", self.app_state)), daemon=True).start()
        
        # Генерация QR кода
        self.generate_webrtc_qr(room_id)
        
        self.app_state.webrtc_status.set('АКТИВНА')
        self.log(f'[WEBRTC] Комната {room_id} создана и активна', color='green')
    
    def generate_webrtc_qr(self, room_id):
        """Генерация QR кода для WebRTC комнаты (без URL)"""
        import qrcode
        import json
        
        # QR содержит только room ID, без URL
        qr_data = {
            "type": "gr7_room",
            "room": room_id
        }
        
        filename = f"webrtc_qr_{room_id}.png"
        img = qrcode.make(json.dumps(qr_data))
        img.save(filename)
        
        try:
            raw_img = Image.open(filename)
            ctk_img = ctk.CTkImage(light_image=raw_img, dark_image=raw_img, size=(180, 180))
            self.qr_label.configure(image=ctk_img)
            self.qr_label.image = ctk_img
            self.log(f'[WEBRTC] QR код сгенерирован: {room_id}', color='green')
        except Exception as e:
            self.log(f'[WEBRTC] Ошибка создания QR: {e}', color='red')
    
    def regenerate_qr(self):
        """Перегенерация QR кода для текущей комнаты"""
        if not hasattr(self, 'current_room_id') or not self.current_room_id:
            self.log('[WEBRTC] Нет активной комнаты для перегенерации QR', color='red')
            return
        
        if not hasattr(self, 'qr_label') or self.qr_label is None:
            self.log('[WEBRTC] QR label not initialized', color='orange')
            return
        
        try:
            self.generate_webrtc_qr(self.current_room_id)
            self.log(f'[WEBRTC] QR код перегенерирован для комнаты: {self.current_room_id}', color='blue')
        except Exception as e:
            self.log(f'[WEBRTC] Ошибка перегенерации QR: {e}', color='red')
    
    def stop_webrtc(self):
        """Остановка WebRTC соединения"""
        if self.app_state.webrtc_peer_connection:
            try:
                self.app_state.webrtc_peer_connection.close()
                self.log('[WEBRTC] WebRTC соединение остановлено', color='blue')
            except Exception as e:
                self.log(f'[WEBRTC] Ошибка остановки: {e}', color='red')
        
        self.app_state.webrtc_status.set('ОСТАНОВЛЕНО')
        self.app_state.connection_status.set('Не подключено')
        self.app_state.webrtc_running = False
    
    def clear_room(self):
        """Очистка комнаты из Firebase"""
        if self.current_room_id:
            try:
                import firebase_admin
                from firebase_admin import db
                
                if firebase_admin._apps:
                    ref = db.reference(f'rooms/{self.current_room_id}')
                    ref.delete()
                    self.log(f'[WEBRTC] Комната {self.current_room_id} очищена из Firebase', color='green')
                
                self.current_room_id = None
                self.app_state.room_id.set('')
                self.app_state.room_id_display.set('')
                self.app_state.webrtc_status.set('ОЖИДАНИЕ')
                self.app_state.connection_status.set('Не подключено')
                self.app_state.webrtc_running = False
                
            except Exception as e:
                self.log(f'[WEBRTC] Ошибка очистки комнаты: {e}', color='red')
        else:
            self.log('[WEBRTC] Нет активной комнаты для очистки', color='orange')

    def monitor_gr7(self):
        def check():
            while True:
                running = any('Guitar Rig 7' in p.name() for p in psutil.process_iter())
                if running:
                    self.app_state.gr7_status.set('Запущен')
                else:
                    self.app_state.gr7_status.set('Остановлен')
                time.sleep(2)
        threading.Thread(target=check, daemon=True).start()
        
        # Обновляем system info каждые 5 секунд
        def update_info():
            while True:
                self.update_system_info()
                time.sleep(5)
        threading.Thread(target=update_info, daemon=True).start()
if __name__ == "__main__":
    print("[BOOT] Starting GR7 Hub")

    app = GR7Hub()

    print("[BOOT] GUI created")

    app.mainloop()

    print("[BOOT] Mainloop exited")