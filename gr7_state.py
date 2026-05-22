"""
GR7 State Management
Централизованное управление состоянием приложения
"""
import customtkinter as ctk


class GR7State:
    """State class для управления UI переменными"""
    
    def __init__(self):
        # Config paths
        self.exe_path = ctk.StringVar(value='')
        self.songs_path = ctk.StringVar(value='')
        self.phone_ip = ctk.StringVar(value='')
        
        # Status variables
        self.gr7_status = ctk.StringVar(value='Остановлен')
        self.bt_status = ctk.StringVar(value='ОЖИДАНИЕ')
        self.cloud_status = ctk.StringVar(value='ОЖИДАНИЕ')
        self.webrtc_status = ctk.StringVar(value='ОЖИДАНИЕ')
        self.connection_status = ctk.StringVar(value='Не подключено')
        self.stream_status = ctk.StringVar(value='Остановлен')
        
        # WebRTC specific
        self.room_id = ctk.StringVar(value='')
        self.room_id_display = ctk.StringVar(value='')
        self.ice_status = ctk.StringVar(value='Не инициализирован')
        self.latency = ctk.StringVar(value='0 ms')
        self.current_room_id = ''

        # Aliases / compatibility names required by UI
        # Provide the alternative names expected by the refactor
        self.connection_state = self.connection_status
        self.ice_state = self.ice_status
        self.peer_status = self.webrtc_status
        self.automation_status = ctk.StringVar(value='Остановлен')
        self.bluetooth_status = self.bt_status
        self.lan_status = self.cloud_status
        
        # Debug
        self.debug_results = None
        
        # Backend references
        self.webrtc_peer_connection = None
        self.webrtc_running = False
        self.automation_running = False
        
        # Validation
        self._validate_state()
    
    def _validate_state(self):
        """Проверяет наличие всех обязательных state variables"""
        required_vars = [
            'exe_path', 'songs_path', 'phone_ip',
            'gr7_status', 'bt_status', 'cloud_status', 'webrtc_status',
            'connection_status', 'stream_status',
            'room_id', 'room_id_display', 'ice_status', 'latency'
        ]
        # Also accept the new compatibility names
        required_vars += [
            'connection_state', 'ice_state', 'peer_status', 'automation_status',
            'bluetooth_status', 'lan_status'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not hasattr(self, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise RuntimeError(f"Missing state variables: {', '.join(missing_vars)}")
    
    def get_safe(self, attr_name, default_value=''):
        """Безопасное получение state variable с fallback значением"""
        try:
            return getattr(self, attr_name).get()
        except AttributeError:
            return default_value