"""
VST3 Host Module
================
Встроенный VST3 хостинг для Guitar Rig 7.
"""

from .host import VST3Host
from .plugin import VST3Plugin

__all__ = ['VST3Host', 'VST3Plugin']