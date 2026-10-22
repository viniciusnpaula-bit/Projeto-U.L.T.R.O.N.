"""Start the ULTRON core, protected local API, and Electron Desktop UI."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
from pathlib import Path


def _show_error(title: str, message: str, *, info: bool = False) -> None:
    try:
        from tkinter import messagebox
        if info:
            messagebox.showinfo(title, message)
        else:
            messagebox.showerror(title, message)
    except Exception:
        print(f"{title}: {message}")


def _electron_paths() -> tuple[Path, Path]:
    package = Path(__file__).resolve().parent / "electron"
    return package / "node_modules" / "electron" / "dist" / "electron.exe", package


def _launch_electron(executable: Path, app_dir: Path, api_url: str, token: str) -> int:
    if not executable.is_file():
        raise FileNotFoundError("Electron não instalado. Execute ULTRON-Setup.exe para instalar o Desktop.")
    if not all((app_dir / name).is_file() for name in ("package.json", "main.js", "site/index.html")):
        raise FileNotFoundError("Os arquivos do aplicativo Electron estão incompletos.")
    required_environment = {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA",
        "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "PROGRAMFILES", "PROGRAMFILES(X86)",
    }
    child_env = {key: value for key, value in os.environ.items()
                 if key.upper() in required_environment}
    child_env.update(ULTRON_API_URL=api_url, ULTRON_API_TOKEN=token)
    return subprocess.run([str(executable), str(app_dir)], cwd=app_dir, env=child_env,
                          check=False).returncode


def main() -> int:
    try:
        import config
    except Exception:
        _show_error("ULTRON Desktop", "Não consegui carregar a configuração. Execute ULTRON-Setup.exe e tente novamente.")
        return 1

    if not any(config.CHAVES.get(provider) for provider in config.PROVEDORES):
        _show_error("ULTRON Desktop", "Nenhuma chave de IA configurada. Edite o arquivo .env e reinicie.")
        return 1

    try:
        import main as core_main
        import seguranca
        import telegram_bot
        from desktop_api import create_server
        from desktop_runtime import DesktopRuntime
    except Exception:
        _show_error("ULTRON Desktop", "Faltam dependências do ULTRON. Execute ULTRON-Setup.exe e tente novamente.")
        return 1

    if not core_main.instancia_unica():
        _show_error("ULTRON Desktop", "O ULTRON já está em execução.", info=True)
        return 0

    runtime = None
    server = None
    server_thread = None
    server_started = False
    closed = False
    close_lock = threading.Lock()

    def cleanup():
        nonlocal closed
        with close_lock:
            if closed:
                return
            closed = True
        if server is not None:
            if server_started:
                try:
                    server.shutdown()
                except Exception:
                    pass
            try:
                server.server_close()
            except Exception:
                pass
        if server_thread is not None and server_thread is not threading.current_thread():
            server_thread.join(timeout=3)
        if runtime is not None:
            try:
                runtime.set_api_running(False)
                runtime.shutdown()
            except Exception:
                pass

    try:
        core_main.preparar_windows()
        threading.Thread(target=core_main.loop_lembretes, name="ultron-lembretes", daemon=True).start()
        core_main.atalho_parada()
        telegram_bot.iniciar()

        runtime = DesktopRuntime()
        runtime.start()
        token = secrets.token_urlsafe(32)
        server, api_url = create_server(runtime, token)
        server_thread = threading.Thread(target=server.serve_forever,
                                         name="ultron-desktop-api", daemon=True)
        server_thread.start()
        server_started = True
        runtime.set_api_running(True)

        executable, ui_dir = _electron_paths()
        return _launch_electron(executable, ui_dir, api_url, token)
    except Exception as exc:
        try:
            seguranca.log.error(f"Inicialização do Desktop falhou ({type(exc).__name__}).")
        except Exception:
            pass
        _show_error("ULTRON Desktop", "Não consegui iniciar o painel local. Confira a instalação e logs\\ultron.log.")
        return 1
    finally:
        cleanup()


def _run_cli() -> int:
    args = sys.argv[1:]
    if args == ["--instalar-inicio"]:
        from desktop_autostart import install
        try:
            entry = install(None, Path(sys.executable).with_name("pythonw.exe"), Path(__file__).resolve())
        except Exception:
            print("Não consegui instalar o início automático. Verifique a pasta de inicialização do Windows.")
            return 1
        print(f"Início automático ativado: {entry}")
        return 0
    if args == ["--remover-inicio"]:
        from desktop_autostart import remove
        try:
            removed = remove(None)
        except Exception:
            print("Não consegui remover o início automático. Verifique a pasta de inicialização do Windows.")
            return 1
        print("Início automático removido." if removed else "O início automático não estava ativado.")
        return 0
    if args:
        print("Uso: desktop.py [--instalar-inicio|--remover-inicio]")
        return 2
    return main()


if __name__ == "__main__":
    raise SystemExit(_run_cli())
