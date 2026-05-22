import cv2
import numpy as np
import pyautogui
import os
import time
from typing import Optional, Tuple, Dict, List, Any
import logging
import ctypes

# DPI awareness для Windows (исправляет проблемы с масштабированием)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

# Конфигурация поиска
VALID_ASSETS = {
    "post": "post.png",
    "clean": "clean.png", 
    "distortion": "distortion.png",
    "overdrive": "overdrive.png"
}

# Expected zones для разных кнопок (относительные координаты экрана)
EXPECTED_ZONES = {
    "post": (0.15, 0.60, 0.85, 0.92),      # Нижняя область
    "clean": (0.15, 0.60, 0.85, 0.92),     # Нижняя область  
    "distortion": (0.15, 0.60, 0.85, 0.92), # Нижняя область
    "overdrive": (0.15, 0.60, 0.85, 0.92)   # Нижняя область
}

# Multi-scale параметры для обработки DPI и масштабирования
SEARCH_SCALES = [0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30]

# Confidence уровни для разных стадий
STAGE_CONFIDENCES = {
    "fast_match": 0.88,
    "color_match": 0.82,
    "edge_match": 0.78,
    "relaxed_match": 0.80
}

# Retry параметры
MAX_RETRIES = 3
RETRY_DELAYS = [0.5, 1.0, 1.5]

# Fallback detection methods
FALLBACK_METHODS = ['orb', 'sift', 'contours']

# Global logger
logger = logging.getLogger('gr7_hub')

class MatchResult:
    """Результат поиска с детальной информацией"""
    def __init__(self, success: bool, position: Optional[Tuple[int, int]] = None, 
                 confidence: float = 0.0, method: str = "", scale: float = 1.0,
                 debug_info: Dict = None):
        self.success = success
        self.position = position
        self.confidence = confidence
        self.method = method
        self.scale = scale
        self.debug_info = debug_info or {}
    
    def __repr__(self):
        return f"MatchResult(success={self.success}, pos={self.position}, conf={self.confidence:.3f}, method={self.method})"


class AdaptiveSearchEngine:
    def __init__(self, logger_func=None):
        self.logger = logger_func or print
        self.last_known_positions = {}
        self.search_stats = {}
        self.diagnostics_log = []
        
    def _log(self, message: str, level: str = "INFO"):
        """Честное логирование с указанием стадии"""
        prefix = f"[{level}] "
        if level == "WARNING":
            prefix = "[WARNING] "
        elif level == "ERROR":
            prefix = "[ERROR] "
        elif level == "SEARCH":
            prefix = "[SEARCH] "
        elif level == "STATE":
            prefix = "[STATE] "
        elif level == "CONTINUE":
            prefix = "[CONTINUE] "
        
        self.logger(f"{prefix}{message}")
        
        # Добавляем в diagnostics log
        self.diagnostics_log.append({
            'timestamp': time.time(),
            'level': level,
            'message': message
        })
    
    def _resolve_asset_path(self, image_path: str) -> str:
        """Получение пути к активу с валидацией"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        basename = os.path.basename(image_path)
        if basename in VALID_ASSETS.values():
            asset_path = os.path.join(current_dir, basename)
        elif image_path in VALID_ASSETS:
            asset_path = os.path.join(current_dir, VALID_ASSETS[image_path])
        else:
            raise ValueError(f"[CV] Asset '{image_path}' is not allowed. Use only: {list(VALID_ASSETS.keys())}")
        
        self._log(f"Loading asset: {asset_path}", "DEBUG")
        self._log(f"File exists: {os.path.exists(asset_path)}", "DEBUG")
        
        if os.path.exists(asset_path):
            try:
                img = cv2.imread(asset_path, cv2.IMREAD_COLOR)
                if img is not None:
                    self._log(f"Image loaded: True", "DEBUG")
                    self._log(f"Shape: {img.shape}", "DEBUG")
                else:
                    self._log(f"Image loaded: False (cv2.imread returned None)", "DEBUG")
            except Exception as e:
                self._log(f"Error loading image: {e}", "DEBUG")
        else:
            self._log(f"File missing: {asset_path}", "DEBUG")
        
        return asset_path
    
    def _get_expected_zone(self, screen_w: int, screen_h: int, image_key: str) -> Tuple[int, int, int, int]:
        """Получение ожидаемой зоны поиска для конкретной кнопки"""
        if image_key in EXPECTED_ZONES:
            ratio = EXPECTED_ZONES[image_key]
        else:
            ratio = EXPECTED_ZONES["post"]  # Default
        
        left = int(screen_w * ratio[0])
        top = int(screen_h * ratio[1])
        right = int(screen_w * ratio[2])
        bottom = int(screen_h * ratio[3])
        return left, top, right, bottom
    
    def _save_debug_overlay(self, screenshot_bgr, top_left, bottom_right, 
                           template_w, template_h, match_info: Dict = None):
        """Сохранение debug overlay с детальной информацией"""
        debug_img = screenshot_bgr.copy()
        
        # Рисуем прямоугольник вокруг матча
        cv2.rectangle(debug_img, top_left, bottom_right, (0, 255, 0), 3)
        
        # Добавляем информацию о матче
        info_text = []
        if match_info:
            info_text.append(f"Conf: {match_info.get('confidence', 0):.3f}")
            info_text.append(f"Method: {match_info.get('method', 'unknown')}")
            info_text.append(f"Scale: {match_info.get('scale', 1.0):.2f}")
        
        # Добавляем координаты
        x, y = top_left
        w, h = bottom_right[0] - x, bottom_right[1] - y
        info_text.append(f"Pos: ({x}, {y})")
        info_text.append(f"Size: {w}x{h}")
        
        # Добавляем временную метку
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        info_text.append(f"Time: {timestamp}")
        
        # Рисуем текст
        for i, text in enumerate(info_text):
            cv2.putText(debug_img, text, (x, y - 10 - i * 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Сохраняем
        filename = f"debug_match_{int(time.time())}.png"
        cv2.imwrite(filename, debug_img)
        self._log(f"Debug overlay saved: {filename}", "DEBUG")
    
    def _validate_match_region(self, region_bgr, template_bgr) -> Tuple[bool, str]:
        """Валидация найденного региона"""
        if region_bgr.size == 0 or template_bgr.size == 0:
            return False, "empty region or template"
        
        region_gray = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        
        # Проверка яркости
        mean_region = np.mean(region_gray)
        mean_template = np.mean(template_gray)
        if abs(mean_region - mean_template) > 35:
            return False, "brightness/color mismatch"
        
        # Проверка гистограммы
        hist_region = cv2.calcHist([region_gray], [0], None, [16], [0, 256])
        hist_template = cv2.calcHist([template_gray], [0], None, [16], [0, 256])
        cv2.normalize(hist_region, hist_region)
        cv2.normalize(hist_template, hist_template)
        hist_corr = cv2.compareHist(hist_template, hist_region, cv2.HISTCMP_CORREL)
        if hist_corr < 0.80:
            return False, "histogram mismatch"
        
        # Проверка свечения
        region_hsv = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2HSV)
        bright_ratio = np.mean(region_hsv[:, :, 2] > 210)
        if bright_ratio > 0.30 and mean_template < 150:
            return False, "unexpected glow/overlay"
        
        return True, None
    
    def _resize_template(self, template: np.ndarray, scale: float) -> np.ndarray:
        """Изменение размера шаблона для multi-scale поиска"""
        if abs(scale - 1.0) < 0.01:
            return template
        
        new_width = int(template.shape[1] * scale)
        new_height = int(template.shape[0] * scale)
        
        if new_width <= 0 or new_height <= 0:
            return template
        
        return cv2.resize(template, (new_width, new_height))
    
    def _detect_dpi_scaling(self) -> float:
        """Detect real DPI scaling factor"""
        try:
            import ctypes
            # Get system DPI
            dpi = ctypes.windll.shcore.GetDpiForSystem()
            # Convert to scaling factor (96 DPI = 1.0)
            scaling = dpi / 96.0
            self._log(f"DPI detected: {dpi}, scaling factor: {scaling:.2f}", "DEBUG")
            return scaling
        except:
            self._log("DPI detection failed, using default scaling 1.0", "WARNING")
            return 1.0
    
    def _stage_fast_match(self, zone_gray: np.ndarray, template_gray: np.ndarray, 
                         confidence: float) -> Optional[MatchResult]:
        """STAGE 1: Быстрый grayscale поиск"""
        self._log("Trying grayscale match...", "SEARCH")
        
        res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Fast match found: {max_val:.3f} >= {confidence:.3f}", "SEARCH")
            return MatchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                method="grayscale",
                scale=1.0
            )
        
        return None
    
    def _stage_multi_scale_search(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                 confidence: float) -> Optional[MatchResult]:
        """STAGE 2: Multi-scale поиск для обработки DPI и масштабирования"""
        self._log("Trying multi-scale search...", "SEARCH")
        
        best_scale_result = None
        best_scale_confidence = 0
        
        for scale in SEARCH_SCALES:
            if abs(scale - 1.0) < 0.01:
                continue  # Пропускаем оригинальный размер, т.к. он уже проверен
            
            self._log(f"scale={scale:.2f} confidence={confidence:.2f}", "SEARCH")
            
            scaled_template = self._resize_template(template_gray, scale)
            if scaled_template.shape != template_gray.shape:
                res = cv2.matchTemplate(zone_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                
                if max_val > best_scale_confidence:
                    best_scale_confidence = max_val
                    best_scale_result = MatchResult(
                        success=True,
                        position=max_loc,
                        confidence=max_val,
                        method=f"grayscale_scale_{scale:.2f}",
                        scale=scale
                    )
        
        if best_scale_result and best_scale_result.confidence >= confidence:
            self._log(f"Multi-scale match found: {best_scale_result.confidence:.3f}", "SEARCH")
            return best_scale_result
        
        return None
    
    def _stage_color_match(self, zone_bgr: np.ndarray, template_bgr: np.ndarray,
                           confidence: float) -> Optional[MatchResult]:
        """STAGE 3: Color matching"""
        self._log("Trying color matching...", "SEARCH")
        
        res = cv2.matchTemplate(zone_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Color match found: {max_val:.3f} >= {confidence:.2f}", "SEARCH")
            return MatchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                method="color",
                scale=1.0
            )
        
        return None
    
    def _stage_edge_match(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                         confidence: float) -> Optional[MatchResult]:
        """STAGE 4: Edge detection с Canny"""
        self._log("Trying edge detection...", "SEARCH")
        
        # Canny edge detection
        zone_edges = cv2.Canny(zone_gray, 50, 150)
        template_edges = cv2.Canny(template_gray, 50, 150)
        
        res = cv2.matchTemplate(zone_edges, template_edges, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Edge match found: {max_val:.3f} >= {confidence:.2f}", "SEARCH")
            return MatchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                method="edge",
                scale=1.0
            )
        
        return None
    
    def _stage_last_known_position(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                   image_key: str, confidence: float) -> Optional[MatchResult]:
        """STAGE 5: Поиск вокруг последней известной позиции"""
        if image_key not in self.last_known_positions:
            return None
        
        last_pos = self.last_known_positions[image_key]
        self._log(f"Searching around last known position: {last_pos}", "SEARCH")
        
        # Определяем область вокруг последней позиции
        search_radius = 50
        template_h, template_w = template_gray.shape
        
        # Границы зоны
        zone_h, zone_w = zone_gray.shape
        left_bound = max(0, last_pos[0] - search_radius)
        right_bound = min(zone_w - template_w, last_pos[0] + search_radius)
        top_bound = max(0, last_pos[1] - search_radius)
        bottom_bound = min(zone_h - template_h, last_pos[1] + search_radius)
        
        if left_bound >= right_bound or top_bound >= bottom_bound:
            return None
        
        # Ищем только в указанной области
        search_area = zone_gray[top_bound:bottom_bound, left_bound:right_bound]
        res = cv2.matchTemplate(search_area, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            # Корректируем позицию относительно всей зоны
            adjusted_pos = (left_bound + max_loc[0], top_bound + max_loc[1])
            self._log(f"Last known position match found: {max_val:.3f}", "SEARCH")
            return MatchResult(
                success=True,
                position=adjusted_pos,
                confidence=max_val,
                method="last_known",
                scale=1.0
            )
        
        return None
    
    def _stage_relaxed_confidence(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                 confidence_levels: List[float]) -> Optional[MatchResult]:
        """STAGE 6: Поиск с пониженным confidence"""
        self._log("Trying relaxed confidence search...", "SEARCH")
        
        best_relaxed_result = None
        best_relaxed_confidence = 0
        
        for confidence in confidence_levels:
            self._log(f"confidence={confidence:.2f}", "SEARCH")
            
            res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            if max_val > best_relaxed_confidence:
                best_relaxed_confidence = max_val
                best_relaxed_result = MatchResult(
                    success=True,
                    position=max_loc,
                    confidence=max_val,
                    method=f"relaxed_{confidence:.2f}",
                    scale=1.0
                )
        
        if best_relaxed_result and best_relaxed_result.confidence >= 0.70:
            self._log(f"Relaxed match found: {best_relaxed_result.confidence:.3f}", "SEARCH")
            return best_relaxed_result
        
        return None
    
    def _stage_orb_match(self, zone_gray: np.ndarray, template_gray: np.ndarray) -> Optional[MatchResult]:
        """STAGE 7: ORB feature matching fallback"""
        try:
            self._log("Trying ORB feature matching...", "SEARCH")
            
            orb = cv2.ORB_create()
            kp1, des1 = orb.detectAndCompute(template_gray, None)
            kp2, des2 = orb.detectAndCompute(zone_gray, None)
            
            if des1 is None or des2 is None or des1 is None or des2 is None:
                return None
            
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)
            
            if len(matches) > 5:
                matches = sorted(matches, key=lambda x: x.distance)
                good_matches = matches[:10]
                confidence = len(good_matches) / 10.0
                
                self._log(f"ORB match found: {confidence:.3f} ({len(good_matches)}/10 matches)", "SEARCH")
                return MatchResult(
                    success=True,
                    confidence=confidence,
                    method="orb",
                    scale=1.0
                )
        except Exception as e:
            self._log(f"ORB matching failed: {e}", "WARNING")
        
        return None
    
    def _stage_sift_match(self, zone_gray: np.ndarray, template_gray: np.ndarray) -> Optional[MatchResult]:
        """STAGE 8: SIFT feature matching fallback"""
        try:
            self._log("Trying SIFT feature matching...", "SEARCH")
            
            sift = cv2.SIFT_create()
            kp1, des1 = sift.detectAndCompute(template_gray, None)
            kp2, des2 = sift.detectAndCompute(zone_gray, None)
            
            if des1 is None or des2 is None or des1 is None or des2 is None:
                return None
            
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
            matches = bf.match(des1, des2)
            
            if len(matches) > 5:
                matches = sorted(matches, key=lambda x: x.distance)
                good_matches = matches[:10]
                confidence = len(good_matches) / 10.0
                
                self._log(f"SIFT match found: {confidence:.3f} ({len(good_matches)}/10 matches)", "SEARCH")
                return MatchResult(
                    success=True,
                    confidence=confidence,
                    method="sift",
                    scale=1.0
                )
        except Exception as e:
            self._log(f"SIFT matching failed: {e}", "WARNING")
        
        return None
    
    def _stage_contour_match(self, zone_gray: np.ndarray, template_gray: np.ndarray) -> Optional[MatchResult]:
        """STAGE 9: Contour detection fallback"""
        try:
            self._log("Trying contour detection...", "SEARCH")
            
            # Find contours in template
            template_contours, _ = cv2.findContours(template_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(template_contours) == 0:
                return None
            
            # Find contours in zone
            zone_contours, _ = cv2.findContours(zone_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(zone_contours) == 0:
                return None
            
            # Find best matching contour
            best_match = None
            best_match_score = 0
            
            for tc in template_contours:
                if cv2.contourArea(tc) < 10:
                    continue
                
                for zc in zone_contours:
                    if cv2.contourArea(zc) < 10:
                        continue
                    
                    # Calculate similarity
                    area_ratio = min(cv2.contourArea(tc), cv2.contourArea(zc)) / max(cv2.contourArea(tc), cv2.contourArea(zc))
                    if area_ratio > best_match_score:
                        best_match_score = area_ratio
                        best_match = zc
            
            if best_match and best_match_score > 0.5:
                self._log(f"Contour match found: {best_match_score:.3f}", "SEARCH")
                return MatchResult(
                    success=True,
                    confidence=best_match_score,
                    method="contour",
                    scale=1.0
                )
        except Exception as e:
            self._log(f"Contour matching failed: {e}", "WARNING")
        
        return None
    
    def _perform_single_search(self, image_key: str, zone_gray: np.ndarray, zone_bgr: np.ndarray,
                              template_gray: np.ndarray, template_bgr: np.ndarray,
                              screen_w: int, screen_h: int) -> Optional[MatchResult]:
        """Выполнение одного прохода поиска через все стадии с глобальным best match selection"""
        
        # STAGE 1: Fast grayscale match
        result = self._stage_fast_match(zone_gray, template_gray, STAGE_CONFIDENCES["fast_match"])
        if result:
            return result
        
        # STAGE 2: Multi-scale search
        result = self._stage_multi_scale_search(zone_gray, template_gray, STAGE_CONFIDENCES["fast_match"])
        if result:
            return result
        
        # STAGE 3: Color matching
        result = self._stage_color_match(zone_bgr, template_bgr, STAGE_CONFIDENCES["color_match"])
        if result:
            return result
        
        # STAGE 4: Edge detection
        result = self._stage_edge_match(zone_gray, template_gray, STAGE_CONFIDENCES["edge_match"])
        if result:
            return result
        
        # STAGE 5: Last known position
        result = self._stage_last_known_position(zone_gray, template_gray, image_key, STAGE_CONFIDENCES["relaxed_match"])
        if result:
            return result
        
        # STAGE 6: Relaxed confidence
        result = self._stage_relaxed_confidence(zone_gray, template_gray, [0.88, 0.84, 0.80])
        if result:
            return result
        
        # STAGE 7-9: Fallback methods
        for method in ['orb', 'sift', 'contours']:
            if method == 'orb':
                result = self._stage_orb_match(zone_gray, template_gray)
            elif method == 'sift':
                result = self._stage_sift_match(zone_gray, template_gray)
            elif method == 'contours':
                result = self._stage_contour_match(zone_gray, template_gray)
            
            if result and result.confidence >= 0.60:
                return result
        
        return None
    
    def locate_image_adaptive(self, image_key: str, timeout: float = 5.0,
                            debug: bool = False, max_retries: int = 3,
                            fullscreen: bool = False) -> Optional[MatchResult]:
        """
        Адаптивный поиск изображения с multi-stage pipeline
        
        Args:
            image_key: Ключ или имя файла из VALID_ASSETS
            timeout: Максимальное время поиска
            debug: Сохранять debug overlay при ошибке
            max_retries: Максимальное количество повторных попыток
            fullscreen: Если True, искать по всему экрану (для диагностики)
            
        Returns:
            MatchResult с информацией о результате
        """
        start_time = time.time()
        
        try:
            asset_path = self._resolve_asset_path(image_key)
        except ValueError as exc:
            self._log(str(exc), "ERROR")
            return MatchResult(success=False, debug_info={"error": str(exc)})
        
        template_bgr = cv2.imread(asset_path, cv2.IMREAD_COLOR)
        if template_bgr is None:
            self._log(f"[CV] ОШИБКА: Не удалось загрузить шаблон '{asset_path}'", "ERROR")
            return MatchResult(success=False, debug_info={"error": "template_load_failed"})
        
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        template_h, template_w = template_gray.shape
        
        # Инициализация статистики
        if image_key not in self.search_stats:
            self.search_stats[image_key] = {"attempts": 0, "successes": 0, "best_confidence": 0.0}
        
        self.search_stats[image_key]["attempts"] += 1
        
        deadline = time.time() + timeout
        best_result = None
        best_confidence = 0.0
        
        # Screenshot verification
        screenshot = pyautogui.screenshot()
        screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
        screen_h, screen_w = screenshot_gray.shape
        
        # Check if screen is valid
        if screen_w < 100 or screen_h < 100:
            self._log(f"Invalid screen size: {screen_w}x{screen_h}", "ERROR")
            return MatchResult(success=False, debug_info={"error": "invalid_screen_size"})
        
        # Check if Guitar Rig is visible (basic check)
        if not self._verify_window_visible(screenshot_bgr):
            self._log("Guitar Rig window not visible or minimized", "WARNING")
        
        # Определяем зону поиска
        if fullscreen:
            self._log(f"Fullscreen search mode enabled for {image_key}", "DEBUG")
            left, top, right, bottom = 0, 0, screen_w, screen_h
        else:
            left, top, right, bottom = self._get_expected_zone(screen_w, screen_h, image_key)
        
        zone_gray = screenshot_gray[top:bottom, left:right]
        zone_bgr = screenshot_bgr[top:bottom, left:right]
        
        if zone_gray.size == 0:
            self._log("Expected search zone is empty", "ERROR")
            return MatchResult(success=False, debug_info={"error": "empty_search_zone"})
        
        retry_count = 0
        while time.time() < deadline and retry_count < max_retries:
            try:
                # Выполняем multi-stage поиск
                result = self._perform_single_search(image_key, zone_gray, zone_bgr,
                                                   template_gray, template_bgr, screen_w, screen_h)
                
                if result and result.success:
                    # DEBUG вывод координат
                    if result.position:
                        self._log(f"[MATCH] x={result.position[0]} y={result.position[1]} conf={result.confidence:.3f}", "DEBUG")
                    
                    # Корректируем позицию относительно всего экрана
                    if result.position:
                        corrected_x = left + result.position[0] + template_w // 2
                        corrected_y = top + result.position[1] + template_h // 2
                        result.position = (corrected_x, corrected_y)
                    
                    # Обновляем последнюю известную позицию
                    self.last_known_positions[image_key] = result.position
                    
                    # Обновляем статистику
                    self.search_stats[image_key]["successes"] += 1
                    self.search_stats[image_key]["best_confidence"] = max(
                        self.search_stats[image_key]["best_confidence"], result.confidence
                    )
                    
                    self._log(f"Image found at stage: {result.method}, confidence: {result.confidence:.3f}", "SEARCH")
                    
                    if debug:
                        self._save_debug_overlay(
                            screenshot_bgr,
                            (result.position[0] - template_w // 2, result.position[1] - template_h // 2),
                            (result.position[0] + template_w // 2, result.position[1] + template_h // 2),
                            template_w, template_h,
                            {"confidence": result.confidence, "method": result.method, "scale": result.scale}
                        )
                    
                    return result
                
                # Сохраняем лучший результат для отчета
                if result and result.confidence > best_confidence:
                    best_result = result
                    best_confidence = result.confidence
                
                retry_count += 1
                if retry_count < max_retries:
                    self._log(f"Retry {retry_count}/{max_retries}...", "SEARCH")
                    time.sleep(0.2)
                
            except Exception as exc:
                self._log(f"Error during search: {exc}", "ERROR")
                if debug:
                    try:
                        cv2.imwrite(f"debug_screen_{int(time.time())}.png", screenshot_bgr)
                    except:
                        pass
                retry_count += 1
                time.sleep(0.2)
                continue
        
        # Поиск не удался, но был найден слабый матч
        if best_result and best_confidence > 0.0:
            self._log(f"Weak match accepted: {best_confidence:.3f} < required confidence", "WARNING")
            self._log("Continuing with fallback logic", "CONTINUE")
            
            # Корректируем позицию для слабого матча
            if best_result.position:
                corrected_x = left + best_result.position[0] + template_w // 2
                corrected_y = top + best_result.position[1] + template_h // 2
                best_result.position = (corrected_x, corrected_y)
                best_result.success = True  # Принимаем слабый матч
            
            if debug:
                self._save_debug_overlay(
                    screenshot_bgr,
                    (best_result.position[0] - template_w // 2, best_result.position[1] - template_h // 2),
                    (best_result.position[0] + template_w // 2, best_result.position[1] + template_h // 2),
                    template_w, template_h,
                    {"confidence": best_result.confidence, "method": best_result.method, "scale": best_result.scale}
                )
            
            return best_result
        
        # Полный провал - логируем детальную информацию
        self._log(f"Image '{image_key}' not found within {timeout} seconds", "ERROR")
        self._log(f"Best confidence: {best_confidence:.3f}", "ERROR")
        self._log(f"Template size: {template_w}x{template_h}", "ERROR")
        self._log(f"Screen size: {screen_w}x{screen_h}", "ERROR")
        self._log(f"Search zone: ({left}, {top}) - ({right}, {bottom})", "ERROR")
        
        if debug:
            self._save_debug_overlay(
                screenshot_bgr,
                (left, top),
                (right, bottom),
                template_w, template_h,
                {"confidence": best_confidence, "method": "none", "scale": 1.0}
            )
        
        return MatchResult(success=False, debug_info={"timeout": True, "best_confidence": best_confidence})
    
    def _verify_window_visible(self, screenshot_bgr: np.ndarray) -> bool:
        """Проверка, что Guitar Rig окно видно"""
        try:
            # Проверяем, что скриншот не пустой
            if screenshot_bgr.size == 0:
                return False
            
            # Проверяем, что есть значимая яркость
            gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
            mean_brightness = np.mean(gray)
            
            if mean_brightness < 20:
                return False
            
            return True
        except:
            return True  # Если проверка не удалась, считаем что окно видно
    
    def get_search_stats(self, image_key: str = None) -> Dict:
        """Получение статистики поиска"""
        if image_key:
            return self.search_stats.get(image_key, {})
        return self.search_stats
    
    def clear_stats(self):
        """Очистка статистики"""
        self.search_stats.clear()
        self.last_known_positions.clear()
        self.diagnostics_log.clear()


# Global instance
adaptive_engine = AdaptiveSearchEngine()


def locate_image_on_screen(image_path, confidence=0.92, timeout=5, debug=False):
    """
    УЛУЧШЕННЫЙ поиск изображения с multi-scale pipeline.
    Использует multi-scale matching, adaptive search и robust fallback.

    Args:
        image_path: Ключ или имя файла из VALID_ASSETS
        confidence: Порог совпадения (для обратной совместимости)
        timeout: Максимальное время поиска
        debug: Сохранять debug overlay при ошибке

    Returns:
        (x, y, confidence) или None
    """
    try:
        # 1. Сначала пробуем adaptive search (основной метод)
        result = adaptive_engine.locate_image_adaptive(image_path, timeout=timeout//2, debug=debug)
        
        if result and result.success:
            # Возвращаем формат совместимый со старым API
            return (result.position[0], result.position[1], result.confidence)
        
        # 2. Если adaptive search не сработал, пробуем multi-scale matching
        asset_path = adaptive_engine._resolve_asset_path(image_path)
        template_bgr = cv2.imread(asset_path, cv2.IMREAD_COLOR)
        
        if template_bgr is not None:
            # Захватываем скриншот
            screenshot = pyautogui.screenshot()
            screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Multi-scale matching
            best_match, best_confidence, best_scale = multi_scale_template_matching(
                screenshot_bgr, template_bgr, SEARCH_SCALES
            )
            
            if best_match and best_confidence >= 0.70:
                # Конвертируем координаты в глобальные
                left, top, right, bottom = _expected_zone_bbox(screenshot_bgr.shape[1], screenshot_bgr.shape[0])
                global_x = left + best_match[0]
                global_y = top + best_match[1]
                
                if debug:
                    # Сохраняем debug overlay
                    debug_img = screenshot_bgr.copy()
                    cv2.rectangle(debug_img, (global_x, global_y),
                                 (global_x + int(template_bgr.shape[1] * best_scale),
                                  global_y + int(template_bgr.shape[0] * best_scale)),
                                 (0, 255, 0), 2)
                    cv2.imwrite("debug_match.png", debug_img)
                
                return (global_x, global_y, best_confidence)
        
        # 3. Для обратной совместимости возвращаем None при полном провале
        if debug:
            print(f"[CV] Изображение '{image_path}' не найдено за {timeout} сек")
        return None
        
    except Exception as e:
        if debug:
            print(f"[CV] Ошибка при поиске {image_path}: {e}")
        return None


def locate_image_robust(image_path, max_retries=3, timeout_per_retry=3.0,
                        logger_func=None) -> Optional[Tuple[int, int, float]]:
    """
    УЛУЧШЕННЫЙ ROBUST поиск с retry logic, soft fail и thread safety.
    
    Args:
        image_path: Ключ или имя файла из VALID_ASSETS
        max_retries: Максимальное количество попыток
        timeout_per_retry: Время на каждую попытку
        logger_func: Функция для логирования
        
    Returns:
        (x, y, confidence) или None (но не останавливает automation)
    """
    import threading
    import queue
    
    if logger_func:
        adaptive_engine.logger = logger_func
    
    # Thread-safe queue для результатов
    result_queue = queue.Queue()
    
    def search_worker():
        """Worker thread для поиска изображения"""
        try:
            result = adaptive_engine.locate_image_adaptive(image_path, timeout=timeout_per_retry, debug=True)
            if result and result.success:
                result_queue.put(('success', result))
            else:
                result_queue.put(('fail', None))
        except Exception as e:
            result_queue.put(('error', e))
    
    for attempt in range(max_retries):
        if attempt > 0:
            adaptive_engine._log(f"Retry attempt {attempt + 1}/{max_retries}", "SEARCH")
            # Используем RETRY_DELAYS для стабильной паузы
            delay_index = min(attempt-1, len(RETRY_DELAYS)-1)
            time.sleep(RETRY_DELAYS[delay_index])
        
        # Запускаем поиск в отдельном потоке для thread safety
        search_thread = threading.Thread(target=search_worker, daemon=True)
        search_thread.start()
        
        # Ожидаем результата с таймаутом
        try:
            status, result = result_queue.get(timeout=timeout_per_retry + 1)
            
            if status == 'success':
                adaptive_engine._log(f"Image found after {attempt + 1} attempts", "SEARCH")
                return (result.position[0], result.position[1], result.confidence)
            elif status == 'error':
                adaptive_engine._log(f"Search error: {result}", "ERROR")
            else:
                adaptive_engine._log(f"Search failed, retrying...", "SEARCH")
                
        except queue.Empty:
            adaptive_engine._log(f"Search timeout for {image_path}", "WARNING")
            # Принудительно останавливаем поток
            if search_thread.is_alive():
                search_thread.join(timeout=0.1)
    
    # Soft fail - возвращаем None, но не останавливает automation
    adaptive_engine._log(f"Weak search result for {image_path}, continuing with fallback", "WARNING")
    
    # Проверяем, может быть weak match все же найден
    try:
        weak_result = adaptive_engine.locate_image_adaptive(image_path, timeout=1.0, debug=False)
        if weak_result and weak_result.success and weak_result.confidence >= 0.70:
            adaptive_engine._log(f"Weak match accepted: confidence={weak_result.confidence:.3f}", "WARNING")
            return (weak_result.position[0], weak_result.position[1], weak_result.confidence)
    except:
        pass
    
    return None


def verify_player_state_robust(logger_func=None) -> Tuple[bool, str]:
    """
    ROBUST проверка состояния player с adaptive logic.
    
    Returns:
        (is_active, status_message)
    """
    if logger_func:
        adaptive_engine.logger = logger_func
    
    adaptive_engine._log("Verifying player state...", "STATE")
    
    # Сначала проверяем состояние кнопки через adaptive search
    result = adaptive_engine.locate_image_adaptive("post", timeout=2.0, debug=True)
    
    if result and result.success:
        confidence = result.confidence
        if confidence >= 0.85:
            adaptive_engine._log("Player probably enabled already (high confidence)", "STATE")
            return True, "enabled_high_confidence"
        elif confidence >= 0.70:
            adaptive_engine._log("Player probably enabled already (medium confidence)", "STATE")
            return True, "enabled_medium_confidence"
        else:
            adaptive_engine._log("Player state unknown - weak match found", "STATE")
            return False, "unknown_weak_match"
    else:
        adaptive_engine._log("Player not detected, will try to enable", "STATE")
        return False, "not_detected"


def safe_click_with_fallback(x, y, logger_func=None, max_retries=2):
    """
    УЛУЧШЕННЫЙ ROBUST клик с fallback logic, retry и enhanced verification.
    
    Args:
        x, y: Координаты клика
        logger_func: Функция для логирования
        max_retries: Максимальное количество повторных попыток
        
    Returns:
        True если клик успешен, False при soft fail
    """
    import threading
    import queue
    
    if logger_func:
        adaptive_engine.logger = logger_func
    
    def click_worker():
        """Worker thread для безопасного клика"""
        try:
            # moveTo()
            pyautogui.moveTo(x, y, duration=0.25)
            
            # pause 0.3
            time.sleep(0.3)
            
            # verify cursor position
            current_x, current_y = pyautogui.position()
            distance = abs(current_x - x) + abs(current_y - y)
            
            if distance > MAX_MOVE_DISTANCE:
                result_queue.put(('fail', f"Position verification failed: distance={distance}"))
                return
            
            # click()
            pyautogui.click()
            
            # Небольшая пауза после клика
            time.sleep(0.25)
            
            # Final verification - проверяем, что UI изменился
            final_x, final_y = pyautogui.position()
            if abs(final_x - x) > MAX_MOVE_DISTANCE or abs(final_y - y) > MAX_MOVE_DISTANCE:
                result_queue.put(('fail', "UI change verification failed"))
                return
            
            result_queue.put(('success', None))
            
        except Exception as exc:
            result_queue.put(('error', str(exc)))
    
    for attempt in range(max_retries):
        if attempt > 0:
            adaptive_engine._log(f"Click retry {attempt + 1}/{max_retries}", "SEARCH")
            # Используем RETRY_DELAYS для стабильной паузы
            delay_index = min(attempt-1, len(RETRY_DELAYS)-1)
            time.sleep(RETRY_DELAYS[delay_index])
        
        # Thread-safe queue для результатов
        result_queue = queue.Queue()
        
        # Запускаем клик в отдельном потоке
        click_thread = threading.Thread(target=click_worker, daemon=True)
        click_thread.start()
        
        # Ожидаем результата с таймаутом
        try:
            status, message = result_queue.get(timeout=2.0)
            
            if status == 'success':
                adaptive_engine._log("Click successful", "SEARCH")
                return True
            elif status == 'error':
                adaptive_engine._log(f"Click error: {message}", "ERROR")
            else:
                adaptive_engine._log(f"Click verification failed: {message}", "WARNING")
                
        except queue.Empty:
            adaptive_engine._log("Click timeout", "WARNING")
            # Принудительно останавливаем поток
            if click_thread.is_alive():
                click_thread.join(timeout=0.1)
    
    adaptive_engine._log("Click failed, but continuing with automation", "WARNING")
    return False


def get_search_diagnostics(image_key="post") -> Dict:
    """
    Получение детальной статистики поиска для диагностики.
    
    Args:
        image_key: Ключ изображения для статистики
        
    Returns:
        Словарь с статистикой поиска
    """
    return adaptive_engine.get_search_stats(image_key)


def clear_search_diagnostics():
    """Очистка статистики поиска"""
    adaptive_engine.clear_stats()


def safe_click(x, y, logger_func=None):
    """Выполняет безопасный клик через moveTo -> pause 0.3 -> verify -> click."""
    log = logger_func or print
    try:
        # moveTo()
        pyautogui.moveTo(x, y, duration=0.25)
        
        # pause 0.3
        time.sleep(0.3)
        
        # verify cursor position
        current_x, current_y = pyautogui.position()
        distance = abs(current_x - x) + abs(current_y - y)
        if distance > MAX_MOVE_DISTANCE:
            log(f"[WARNING] Неверная позиция перед кликом: ожидается ({x}, {y}), текущее ({current_x}, {current_y})")
            return False
        
        # click()
        pyautogui.click()
        
        # Небольшая пауза после клика
        time.sleep(0.25)
        return True
    except Exception as exc:
        log(f"[ERROR] safe_click failed: {exc}")
        return False


def is_button_active(image_key="post", debug=False):
    """Проверяет состояние кнопки по активному/pressed/overlay/glow/иконке."""
    try:
        asset_path = adaptive_engine._resolve_asset_path(image_key)
    except ValueError as exc:
        print(exc)
        return False

    template_bgr = cv2.imread(asset_path, cv2.IMREAD_COLOR)
    if template_bgr is None:
        print(f"[CV] ОШИБКА: Не удалось загрузить шаблон '{asset_path}'")
        print(f"[CV] Причина: file missing, cv2.imread failed, invalid image, or wrong path")
        return False

    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    screenshot = pyautogui.screenshot()
    screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    screen_h, screen_w = screenshot_gray.shape

    left, top, right, bottom = _expected_zone_bbox(screen_w, screen_h)
    zone_gray = screenshot_gray[top:bottom, left:right]
    zone_bgr = screenshot_bgr[top:bottom, left:right]

    if zone_gray.size == 0:
        return False

    res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val < 0.70:
        return False

    match_x = left + max_loc[0]
    match_y = top + max_loc[1]
    region_bgr = screenshot_bgr[match_y:match_y + template_gray.shape[0], match_x:match_x + template_gray.shape[1]]
    if region_bgr.size == 0:
        return False

    region_hsv = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2HSV)
    region_gray = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2GRAY)
    mean_v = np.mean(region_hsv[:, :, 2])
    mean_s = np.mean(region_hsv[:, :, 1])
    glow_ratio = float(np.mean(region_hsv[:, :, 2] > 220))
    dark_ratio = float(np.mean(region_gray < 50))

    hist_region = cv2.calcHist([region_gray], [0], None, [16], [0, 256])
    hist_template = cv2.calcHist([template_gray], [0], None, [16], [0, 256])
    cv2.normalize(hist_region, hist_region)
    cv2.normalize(hist_template, hist_template)
    hist_corr = cv2.compareHist(hist_template, hist_region, cv2.HISTCMP_CORREL)

    active_signals = 0
    if mean_v > 180:
        active_signals += 1
    if glow_ratio > 0.06:
        active_signals += 1
    if hist_corr < 0.85:
        active_signals += 1
    if dark_ratio > 0.08:
        active_signals += 1

    if debug:
        _save_debug_overlay(screenshot_bgr, (match_x, match_y), (match_x + template_gray.shape[1], match_y + template_gray.shape[0]))

    return active_signals >= 2


def verify_button_state_adaptive(image_key="post", logger_func=None) -> Dict:
    """
    АДАПТИВНАЯ верификация состояния кнопки с detailed analysis.
    
    Args:
        image_key: Ключ кнопки для проверки
        logger_func: Функция для логирования
        
    Returns:
        Словарь с детальной информацией о состоянии
    """
    if logger_func:
        adaptive_engine.logger = logger_func
    
    adaptive_engine._log(f"Adaptive button state verification for {image_key}...", "STATE")
    
    # Проверяем наличие кнопки
    result = adaptive_engine.locate_image_adaptive(image_key, timeout=2.0, debug=True)
    
    if not result or not result.success:
        return {
            "detected": False,
            "confidence": 0.0,
            "stage": "not_found",
            "status": "button_not_detected",
            "recommendation": "search_fallback"
        }
    
    # Проверяем активное состояние
    is_active = is_button_active(image_key, debug=True)
    
    # Дополнительный анализ
    template_bgr = cv2.imread(adaptive_engine._resolve_asset_path(image_key), cv2.IMREAD_COLOR)
    if template_bgr is not None:
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        screenshot = pyautogui.screenshot()
        screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
        
        left, top, right, bottom = _expected_zone_bbox(screenshot_bgr.shape[1], screenshot_bgr.shape[0])
        zone_gray = screenshot_gray[top:bottom, left:right]
        
        # Анализ качества match
        res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        quality_score = max_val
        state_quality = "high" if quality_score > 0.85 else "medium" if quality_score > 0.70 else "low"
        
        adaptive_engine._log(f"Button state: {'active' if is_active else 'inactive'}, "
                           f"quality: {state_quality} ({quality_score:.3f})", "STATE")
        
        return {
            "detected": True,
            "active": is_active,
            "confidence": result.confidence,
            "quality_score": quality_score,
            "stage": result.stage,
            "state_quality": state_quality,
            "status": "button_detected" if is_active else "button_inactive",
            "recommendation": "proceed" if is_active else "activate"
        }
    
    return {
        "detected": True,
        "active": is_active,
        "confidence": result.confidence,
        "stage": result.stage,
        "status": "button_detected" if is_active else "button_inactive",
        "recommendation": "proceed" if is_active else "activate"
    }


def _expected_zone_bbox(screen_w, screen_h):
    left = int(screen_w * EXPECTED_ZONES["post"][0])
    top = int(screen_h * EXPECTED_ZONES["post"][1])
    right = int(screen_w * EXPECTED_ZONES["post"][2])
    bottom = int(screen_h * EXPECTED_ZONES["post"][3])
    return left, top, right, bottom


def _save_debug_overlay(screenshot_bgr, top_left, bottom_right):
    debug_img = screenshot_bgr.copy()
    cv2.rectangle(debug_img, top_left, bottom_right, (0, 255, 0), 3)
    cv2.imwrite("debug_match.png", debug_img)


def multi_scale_template_matching(screenshot_bgr, template_bgr, scales=SEARCH_SCALES):
    """
    Multi-scale template matching с улучшенной логикой.
    
    Args:
        screenshot_bgr: Скриншот в BGR формате
        template_bgr: Шаблон в BGR формате
        scales: Список масштабов для поиска
        
    Returns:
        (best_match, best_confidence, best_scale) или (None, 0, 0)
    """
    best_match = None
    best_confidence = 0
    best_scale = 1.0
    
    template_h, template_w = template_bgr.shape[:2]
    screen_h, screen_w = screenshot_bgr.shape[:2]
    
    for scale in scales:
        # Пропускаем масштабы, которые слишком большие для экрана
        scaled_w = int(template_w * scale)
        scaled_h = int(template_h * scale)
        
        if scaled_w > screen_w or scaled_h > screen_h:
            continue
        
        if scaled_w < 5 or scaled_h < 5:  # Слишком маленькие
            continue
        
        try:
            # Масштабирование шаблона
            scaled_template = cv2.resize(template_bgr, (scaled_w, scaled_h))
            
            # Grayscale matching
            screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
            scaled_template_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
            
            # Template matching
            result = cv2.matchTemplate(screenshot_gray, scaled_template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # Color matching
            result_color = cv2.matchTemplate(screenshot_bgr, scaled_template, cv2.TM_CCOEFF_NORMED)
            min_val_color, max_val_color, min_loc_color, max_loc_color = cv2.minMaxLoc(result_color)
            
            # Edge matching
            screenshot_edges = cv2.Canny(screenshot_gray, 50, 150)
            template_edges = cv2.Canny(scaled_template_gray, 50, 150)
            result_edges = cv2.matchTemplate(screenshot_edges, template_edges, cv2.TM_CCOEFF_NORMED)
            min_val_edges, max_val_edges, min_loc_edges, max_loc_edges = cv2.minMaxLoc(result_edges)
            
            # Комбинированный confidence
            combined_confidence = (max_val + max_val_color + max_val_edges) / 3
            
            if combined_confidence > best_confidence:
                best_confidence = combined_confidence
                best_match = max_loc if max_val > max_val_color else max_loc_color
                best_scale = scale
                
        except Exception as e:
            # Пропускаем ошибочные масштабы
            continue
    
    return best_match, best_confidence, best_scale
