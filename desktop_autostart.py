"""Explicit, reversible opt-in Windows startup entry for ULTRON Desktop."""
from __future__ import annotations

import os
from pathlib import Path


# Nome único: o núcleo (main.py) criava "Ultron.vbs" no mesmo lugar e as duas
# entradas podiam iniciar dois processos.
_ENTRY_NAME = "ULTRON Desktop.vbs"
_LEGACY_ENTRIES = ("Ultron.vbs",)


def startup_path(appdata: str | Path | None = None) -> Path:
    if appdata is None:
        appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("A pasta de inicialização do usuário não está disponível.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / _ENTRY_NAME


def is_installed(appdata: str | Path | None = None) -> bool:
    try:
        return startup_path(appdata).is_file()
    except (OSError, RuntimeError):
        return False


def install(appdata: str | Path | None, python_exe: str | Path, script_path: str | Path) -> Path:
    destination = startup_path(appdata)
    python_exe = Path(python_exe).resolve()
    script_path = Path(script_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    current_dir = str(script_path.parent).replace('"', '""')
    command = f'"{python_exe}" "{script_path}"'.replace('"', '""')
    contents = ("Set sh = CreateObject(\"WScript.Shell\")\r\n"
                f'sh.CurrentDirectory = "{current_dir}"\r\n'
                f'sh.Run "{command}", 0, False\r\n')
    destination.write_text(contents, encoding="utf-16")
    return destination


def remove(appdata: str | Path | None = None) -> bool:
    destination = startup_path(appdata)
    removed = False
    for candidate in (destination, *(destination.parent / name for name in _LEGACY_ENTRIES)):
        try:
            candidate.unlink()
            removed = True
        except FileNotFoundError:
            continue
    return removed


def is_installed_any(appdata: str | Path | None = None) -> bool:
    """True if any entry (current or legacy) would start ULTRON with Windows."""
    try:
        path = startup_path(appdata)
    except RuntimeError:
        return False
    return path.is_file() or any((path.parent / name).is_file() for name in _LEGACY_ENTRIES)
