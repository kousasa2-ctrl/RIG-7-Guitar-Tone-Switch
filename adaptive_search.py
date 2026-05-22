import cv2
import numpy as np
import pyautogui
import os
import time
from typing import Optional, Tuple, Dict, List
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
SEARCH_SCALES = [0.75, 0.85, 1.0, 1.15, 1.25, 1.4]

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

class AdaptiveSearchResult:
    def __init__(self, success: bool, position: Optional[Tuple[int, int]] = None, 
                 confidence: float = 0.0, stage: str = "", debug_info: Dict = None):
        self.success = success
        self.position = position
        self.confidence = confidence
        self.stage = stage
        self.debug_info = debug_info or {}

class AdaptiveSearchEngine:
    def __init__(self, logger_func=None):
        self.logger = logger_func or print
        self.last_known_positions = {}
        self.search_stats = {}
        
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
    
    def _save_debug_overlay(self, screenshot_bgr, top_left, bottom_right, stage: str = ""):
        """Сохранение debug overlay при fail"""
        debug_img = screenshot_bgr.copy()
        cv2.rectangle(debug_img, top_left, bottom_right, (0, 255, 0), 3)
        
        timestamp = int(time.time())
        filename = f"debug_match_{stage}_{timestamp}.png" if stage else f"debug_match_{timestamp}.png"
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
    
    def _stage_fast_match(self, zone_gray: np.ndarray, template_gray: np.ndarray, 
                         confidence: float) -> Optional[AdaptiveSearchResult]:
        """STAGE 1: Быстрый grayscale поиск"""
        self._log("Trying grayscale match...", "SEARCH")
        self._log(f"confidence={confidence:.2f}", "SEARCH")
        
        res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Fast match found: {max_val:.3f} >= {confidence:.3f}", "SEARCH")
            return AdaptiveSearchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                stage="fast_match"
            )
        
        return None
    
    def _stage_multi_scale_search(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                 confidence: float) -> Optional[AdaptiveSearchResult]:
        """STAGE 2: Multi-scale поиск для обработки DPI и масштабирования"""
        self._log("Trying multi-scale search...", "SEARCH")
        
        for scale in SEARCH_SCALES:
            if abs(scale - 1.0) < 0.01:
                continue  # Пропускаем оригинальный размер, т.к. он уже проверен
            
            self._log(f"scale={scale:.2f} confidence={confidence:.2f}", "SEARCH")
            
            scaled_template = self._resize_template(template_gray, scale)
            if scaled_template.shape != template_gray.shape:
                res = cv2.matchTemplate(zone_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                
                if max_val >= confidence:
                    self._log(f"Multi-scale match found: {max_val:.3f} >= {confidence:.3f}", "SEARCH")
                    return AdaptiveSearchResult(
                        success=True,
                        position=max_loc,
                        confidence=max_val,
                        stage=f"multi_scale_{scale:.2f}"
                    )
        
        return None
    
    def _stage_color_match(self, zone_bgr: np.ndarray, template_bgr: np.ndarray,
                          confidence: float) -> Optional[AdaptiveSearchResult]:
        """STAGE 3: Color matching"""
        self._log("Trying color matching...", "SEARCH")
        self._log(f"confidence={confidence:.2f}", "SEARCH")
        
        res = cv2.matchTemplate(zone_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Color match found: {max_val:.3f} >= {confidence:.2f}", "SEARCH")
            return AdaptiveSearchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                stage="color_match"
            )
        
        return None
    
    def _stage_edge_match(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                         confidence: float) -> Optional[AdaptiveSearchResult]:
        """STAGE 4: Edge detection с Canny"""
        self._log("Trying edge detection...", "SEARCH")
        self._log(f"confidence={confidence:.2f}", "SEARCH")
        
        # Canny edge detection
        zone_edges = cv2.Canny(zone_gray, 50, 150)
        template_edges = cv2.Canny(template_gray, 50, 150)
        
        res = cv2.matchTemplate(zone_edges, template_edges, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= confidence:
            self._log(f"Edge match found: {max_val:.3f} >= {confidence:.2f}", "SEARCH")
            return AdaptiveSearchResult(
                success=True,
                position=max_loc,
                confidence=max_val,
                stage="edge_match"
            )
        
        return None
    
    def _stage_last_known_position(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                  image_key: str, confidence: float) -> Optional[AdaptiveSearchResult]:
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
            return AdaptiveSearchResult(
                success=True,
                position=adjusted_pos,
                confidence=max_val,
                stage="last_known_position"
            )
        
        return None
    
    def _stage_relaxed_confidence(self, zone_gray: np.ndarray, template_gray: np.ndarray,
                                confidence_levels: List[float]) -> Optional[AdaptiveSearchResult]:
        """STAGE 6: Поиск с пониженным confidence"""
        self._log("Trying relaxed confidence search...", "SEARCH")
        
        for confidence in confidence_levels:
            self._log(f"confidence={confidence:.2f}", "SEARCH")
            
            res = cv2.matchTemplate(zone_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= confidence:
                self._log(f"Relaxed match found: {max_val:.3f} >= {confidence:.3f}", "SEARCH")
                return AdaptiveSearchResult(
                    success=True,
                    position=max_loc,
                    confidence=max_val,
                    stage=f"relaxed_{confidence:.2f}"
                )
        
        return None
    
    def _perform_single_search(self, image_key: str, zone_gray: np.ndarray, zone_bgr: np.ndarray,
                              template_gray: np.ndarray, template_bgr: np.ndarray,
                              screen_w: int, screen_h: int) -> Optional[AdaptiveSearchResult]:
        """Выполнение одного прохода поиска через все стадии"""
        
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
        
        return None
    
    def locate_image_adaptive(self, image_key: str, timeout: float = 5.0,
                            debug: bool = False, max_retries: int = 3,
                            fullscreen: bool = False) -> Optional[AdaptiveSearchResult]:
        """
        Адаптивный поиск изображения с multi-stage pipeline
        
        Args:
            image_key: Ключ или имя файла из VALID_ASSETS
            timeout: Максимальное время поиска
            debug: Сохранять debug overlay при ошибке
            max_retries: Максимальное количество повторных попыток
            fullscreen: Если True, искать по всему экрану (для диагностики)
            
        Returns:
            AdaptiveSearchResult с информацией о результате
        """
        start_time = time.time()
        
        try:
            asset_path = self._resolve_asset_path(image_key)
        except ValueError as exc:
            self._log(str(exc), "ERROR")
            return AdaptiveSearchResult(success=False, debug_info={"error": str(exc)})
        
        template_bgr = cv2.imread(asset_path, cv2.IMREAD_COLOR)
        if template_bgr is None:
            self._log(f"[CV] ОШИБКА: Не удалось загрузить шаблон '{asset_path}'", "ERROR")
            return AdaptiveSearchResult(success=False, debug_info={"error": "template_load_failed"})
        
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        template_h, template_w = template_gray.shape
        
        # Инициализация статистики
        if image_key not in self.search_stats:
            self.search_stats[image_key] = {"attempts": 0, "successes": 0, "best_confidence": 0.0}
        
        self.search_stats[image_key]["attempts"] += 1
        
        deadline = time.time() + timeout
        best_result = None
        best_confidence = 0.0
        
        retry_count = 0
        while time.time() < deadline and retry_count < max_retries:
            try:
                # Скриншот
                screenshot = pyautogui.screenshot()
                screenshot_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
                screen_h, screen_w = screenshot_gray.shape
                
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
                    time.sleep(0.2)
                    continue
                
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
                    
                    self._log(f"Image found at stage: {result.stage}, confidence: {result.confidence:.3f}", "SEARCH")
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
            
            return best_result
        
        # Полный провал
        self._log(f"Image '{image_key}' not found within {timeout} seconds", "ERROR")
        return AdaptiveSearchResult(success=False, debug_info={"timeout": True})
    
    def get_search_stats(self, image_key: str = None) -> Dict:
        """Получение статистики поиска"""
        if image_key:
            return self.search_stats.get(image_key, {})
        return self.search_stats
    
    def clear_stats(self):
        """Очистка статистики"""
        self.search_stats.clear()
        self.last_known_positions.clear()