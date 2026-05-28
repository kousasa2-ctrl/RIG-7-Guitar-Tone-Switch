"""
QRGenerator
===========
Генерация QR кодов для WebRTC комнат.
"""

import qrcode
import json
from typing import Optional
from pathlib import Path


class QRGenerator:
    """Генератор QR кодов"""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def generate_room_qr(self, room_id: str) -> Optional[str]:
        """
        Генерация QR кода для комнаты.

        Args:
            room_id: ID комнаты

        Returns:
            Optional[str]: Путь к файлу QR или None
        """
        try:
            # QR содержит информацию о комнате
            qr_data = {
                "type": "gr7_room",
                "room": room_id
            }

            # Создание QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)

            # Создание изображения
            img = qr.make_image(fill_color="black", back_color="white")

            # Сохранение
            filename = f"webrtc_qr_{room_id}.png"
            filepath = self.output_dir / filename
            img.save(filepath)

            return str(filepath)

        except Exception as e:
            print(f"Ошибка генерации QR: {e}")
            return None

    def get_qr_info(self, room_id: str) -> dict:
        """
        Получение информации о QR коде.

        Args:
            room_id: ID комнаты

        Returns:
            dict: Информация о QR
        """
        return {
            "type": "gr7_room",
            "room": room_id
        }