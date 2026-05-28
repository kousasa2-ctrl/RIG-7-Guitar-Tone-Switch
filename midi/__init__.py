"""
MIDI Module
===========
Управление MIDI через virtualMIDI SDK.
"""

from .virtual_midi import VirtualMIDIPort
from .router import MIDIRouter

__all__ = ['VirtualMIDIPort', 'MIDIRouter']