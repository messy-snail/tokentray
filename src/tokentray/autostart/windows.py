"""Autostart via the per-user Run key.

HKCU rather than HKLM: no administrator prompt, and the entry belongs to the
person who enabled it rather than to the machine.
"""

from __future__ import annotations

import subprocess

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "tokentray"


def _winreg():
    import winreg

    return winreg


def location() -> str:
    return rf"HKCU\{RUN_KEY}\{VALUE_NAME}"


def _read() -> str | None:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None


def is_enabled() -> bool:
    return _read() is not None


def registered_command() -> list[str] | None:
    value = _read()
    if not value:
        return None
    parts = _split(value)
    return [p for p in parts if p != "--autostart"] or None


def enable(command: list[str]) -> None:
    winreg = _winreg()
    quoted = subprocess.list2cmdline(command + ["--autostart"])
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, quoted)


def disable() -> None:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def _split(value: str) -> list[str]:
    """Split a Run-key command line back into argv.

    shlex would mangle Windows paths (backslashes are not escapes here), so use
    the Win32 parser that produced it.
    """
    import ctypes
    from ctypes import wintypes

    argc = ctypes.c_int()
    parser = ctypes.windll.shell32.CommandLineToArgvW
    parser.restype = ctypes.POINTER(ctypes.c_wchar_p)
    argv = parser(value, ctypes.byref(argc))
    if not argv:
        return []
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)
