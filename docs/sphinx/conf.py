"""Sphinx configuration for the Pico W FM radio receiver."""

import sys
import types
from pathlib import Path

# Repository root is two levels above this file (docs/sphinx/conf.py)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "src"))

project = "Pico W FM Radio Receiver"
author = "Daniil Yeriemieiev, Maxim Sudakov, Gleb Dulesov"
copyright = "2026, " + author

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

# The drivers combine constants with "|" at import time (const(), Pin.IRQ_*),
# so these stubs return real integers; a plain mock object cannot do that
micropython_stub = types.ModuleType("micropython")
micropython_stub.const = lambda value: value
sys.modules["micropython"] = micropython_stub


class _PinMeta(type):
    """Metaclass returning an integer for any upper-case constant."""

    def __getattr__(cls, name):
        """Return a stable integer for Pin.<NAME> constants."""
        if name.isupper():
            return 1 << (sum(map(ord, name)) % 16)
        raise AttributeError(name)


class _Pin(metaclass=_PinMeta):
    """Stub of machine.Pin, only for the documentation build."""

    def __init__(self, *args, **kwargs):
        """Accept any arguments."""


machine_stub = types.ModuleType("machine")
machine_stub.Pin = _Pin
for _name in ("I2C", "Timer", "PWM", "ADC", "SPI", "UART"):
    setattr(machine_stub, _name, _Pin)
sys.modules["machine"] = machine_stub

# MicroPython-only modules without import-time arithmetic
autodoc_mock_imports = [
    "framebuf",
    "rp2",
    "utime",
    "network",
]
autodoc_member_order = "bysource"
autoclass_content = "both"

exclude_patterns = ["_build"]
html_theme = "sphinx_rtd_theme"

html_context = {
    "display_github": True,
    "github_user": "daniil-yeriemieiev",
    "github_repo": "pico-fm-receiver",
    "github_version": "main",
    "conf_py_path": "/docs/sphinx/",
}
