from pedalboard import load_plugin
import os

vst_path = os.path.join("plugins", "Guitar Rig 7.vst3")

if os.path.exists(vst_path):
    print(f"Файл найден: {vst_path}")
    try:
        plugin = load_plugin(vst_path)
        print("VST3 плагин успешно загружен!")
        print(f"Параметры плагина: {list(plugin.parameters.keys())[:5]} ...")
    except Exception as e:
        print(f"Ошибка загрузки плагина: {e}")
else:
    print(f"ФАЙЛ НЕ НАЙДЕН по пути: {vst_path}")