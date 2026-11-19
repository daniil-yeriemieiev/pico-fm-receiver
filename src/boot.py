"""
Boot Configuration Module for Raspberry Pi Pico W.

This module executes automatically on system power-up before ``main.py``.
It holds the Si4703 FM tuner in hardware reset immediately upon boot to prevent
audio pop-noises, configures module search paths, and enables garbage collection.
"""

import gc
import sys
from machine import Pin  # type: ignore

# ============================================================================
# SYSTEM & HARDWARE CONSTANTS
# ============================================================================
PIN_RADIO_RST = 16  # Must match PIN_RADIO_RST in main.py
LIB_PATH = "/lib"
SRC_PATH = "/src"


def setup_environment():
    """
    Configure early hardware states and the MicroPython runtime environment.

    Pulls the Si4703 reset pin LOW immediately to mute the audio output
    during boot, adds optional library directories to ``sys.path``, and
    triggers garbage collection.
    """
    # Hold Si4703 in hardware reset immediately to prevent startup audio click
    rst_pin = Pin(PIN_RADIO_RST, Pin.OUT)
    rst_pin.value(0)

    # Ensure standard project folders are searchable if uploaded as directories
    for path in (LIB_PATH, SRC_PATH):
        if path not in sys.path:
            sys.path.append(path)

    gc.enable()
    gc.collect()
    print("[BOOT] Hardware held in safe reset. Free memory:", gc.mem_free(), "bytes")


if __name__ == "__main__":
    setup_environment()