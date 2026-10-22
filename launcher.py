"""ULTRON launcher — the single thing a shortcut or the installer points at.

Why this exists: the old package shipped *both* a compiled launcher (launcher.cs →
"ULTRON Desktop.exe") and a batch file that called pythonw.exe, and they disagreed
about which one was the real entry point. That is confusing for a user and noisy for
an antivirus (an unsigned PE that fires another hidden process). This script is the
only entry point now:

    ULTRON.exe              open the desktop panel (no console window)
    ULTRON.exe --texto      console chat through main.py
    ULTRON.exe --bandeja    tray icon only
    ULTRON.exe --doctor     local diagnostics, prints a report, changes nothing

It is compiled by tools/build_setup.py into ULTRON.exe with the official icon and
version information. Running it from source works too (python launcher.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "U.L.T.R.O.N. Desktop"


def _install_root() -> Path:
    """Pasta do programa. Quando compilado, é onde o ULTRON.exe está (não a pasta
    temporária onde o PyInstaller se extrai)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = _install_root()
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
VENV_PYTHONW = ROOT / "venv" / "Scripts" / "pythonw.exe"


def _show_error(message: str) -> None:
    if sys.stderr is not None and sys.stderr.isatty():
        print(f"{APP_NAME}: {message}", file=sys.stderr)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, message, APP_NAME,
            0x00000010 | 0x00040000,  # MB_ICONERROR | MB_TOPMOST
        )
    except Exception:
        pass


def _show_info(message: str) -> None:
    if sys.stderr is not None and sys.stderr.isatty():
        print(f"{APP_NAME}: {message}")
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x00000040 | 0x00040000)
    except Exception:
        pass


def _installed() -> bool:
    return VENV_PYTHON.is_file() and (ROOT / "desktop.py").is_file()


def _needs_setup_message() -> None:
    setup = ROOT / "ULTRON-Setup.exe"
    hint = (
        "O ULTRON ainda não está instalado nesta pasta.\n\n"
        f"Execute o instalador: {setup.name if setup.is_file() else 'o instalador baixado'}\n"
        "Ele instala as dependências sozinho — não é preciso administrador."
    )
    _show_error(hint)


def _spawn(arguments: list[str], *, hidden: bool) -> int:
    python = VENV_PYTHONW if hidden and VENV_PYTHONW.is_file() else VENV_PYTHON
    flags = 0x00000008 if hidden else 0  # DETACHED_PROCESS: the panel outlives the launcher
    if hidden:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [str(python), *arguments],
        cwd=str(ROOT),
        close_fds=True,
        creationflags=flags,
    )
    return process.pid


def _wait_for_api(timeout_seconds: float = 8.0) -> bool:
    """Panel is ready when the loopback API answers; keeps the launch feeling instant."""
    import socket
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.4)
            try:
                probe.connect(("127.0.0.1", 3900))
                return True
            except OSError:
                time.sleep(0.25)
    return False


def _doctor() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"{APP_NAME} — diagnóstico local\n{'-' * 46}")
    checks = [
        ("Python isolado", VENV_PYTHON.is_file(), str(VENV_PYTHON)),
        ("desktop.py", (ROOT / "desktop.py").is_file(), "ponto de entrada"),
        ("Electron", (ROOT / "electron" / "node_modules" / "electron" / "dist" / "electron.exe").is_file(),
         "interface"),
        (".env", (ROOT / ".env").is_file(), "chaves de IA"),
        ("Dados", (ROOT / "dados" / "ultron.db").is_file(), "memória e histórico"),
    ]
    failures = 0
    for title, passed, detail in checks:
        print(f"  {'OK ' if passed else 'XX '} {title:<16} {detail}")
        failures += 0 if passed else 1
    if VENV_PYTHON.is_file():
        probe = subprocess.run([str(VENV_PYTHON), "-c", "import config, cerebro, seguranca"],
                               cwd=str(ROOT), capture_output=True, text=True)
        print(f"  {'OK ' if probe.returncode == 0 else 'XX '} {'núcleo':<16} config, cerebro, seguranca")
        if probe.returncode != 0:
            failures += 1
            print(probe.stderr.strip()[-800:])
    print("-" * 46)
    print("Diagnóstico concluído." if failures == 0 else f"{failures} problema(s) encontrado(s).")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    if argv and argv[0] in {"--doctor", "--diagnostico", "-d"}:
        return _doctor()
    if not _installed():
        if os.name == "nt":
            _needs_setup_message()
        return 1
    if argv and argv[0] in {"--texto"}:
        return subprocess.call([str(VENV_PYTHON), str(ROOT / "main.py"), "--texto"], cwd=str(ROOT))
    if argv and argv[0] in {"--bandeja"}:
        return subprocess.call([str(VENV_PYTHON), str(ROOT / "main.py"), "--bandeja"], cwd=str(ROOT))
    if argv and argv[0] in {"--instalar-inicio", "--remover-inicio"}:
        return subprocess.call([str(VENV_PYTHON), str(ROOT / "desktop.py"), argv[0]], cwd=str(ROOT))
    _spawn([str(ROOT / "desktop.py")], hidden=True)
    if not _wait_for_api() and sys.stderr is not None and sys.stderr.isatty():
        print("O painel está demorando para responder; veja logs\\ultron.log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
