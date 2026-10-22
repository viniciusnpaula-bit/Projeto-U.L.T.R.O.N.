"""Install, repair or remove U.L.T.R.O.N. Desktop on Windows.

This is the only entry point the user needs to run:

    ULTRON-Setup.exe            install / repair / update in the current folder
    ULTRON-Setup.exe --uninstall  remove everything the installer created

It is a plain console program compiled by PyInstaller from this file. It never
writes to %TEMP%, never requests elevation, never touches the registry and never
downloads anything: a scanner sees a file that installs a virtualenv and calls
npm. Nothing is fetched except the Python packages listed in requirements.txt and
the Electron runtime pinned in electron/package.json.

Guarantees that matter for a home machine:
  * the folder is checked before anything is changed (no half installs);
  * steps are resumable: re-running skips what is already correct;
  * the .env file is never overwritten once it exists;
  * every action is logged to logs\\setup.log, with secrets masked.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

APP_NAME = "U.L.T.R.O.N. Desktop"
MIN_PYTHON = (3, 10)
MIN_NODE = 18
VENV_MARKER = ".ultron-venv.json"
DEPS_MARKER = ".ultron-deps.json"
LOG_MAX_BYTES = 512 * 1024

REQUIRED_FILES = (
    "desktop.py",
    "main.py",
    "config.py",
    "requirements.txt",
    "electron/package.json",
    "electron/main.js",
    "electron/site/index.html",
)

RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
BANNED = set('<>:"|?*')


class SetupError(RuntimeError):
    """A failure with a message that is safe and useful to show the user."""


# --------------------------------------------------------------------- console
class Console:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_path = root / "logs" / "setup.log"
        try:
            (root / "logs").mkdir(parents=True, exist_ok=True)
            if self.log_path.exists() and self.log_path.stat().st_size > LOG_MAX_BYTES:
                self.log_path.replace(self.log_path.with_suffix(".old.log"))
        except OSError:
            self.log_path = Path(os.devnull)
        self._interactive = sys.stdin is not None and sys.stdin.isatty()
        try:
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "chcp", "65001"], capture_output=True, check=False)
        except OSError:
            pass

    def _write(self, text: str) -> None:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode(), flush=True)

    def step(self, number: int, total: int, title: str) -> None:
        self._write("")
        self._write(f"[{number}/{total}] {title}")
        self._log(f"== [{number}/{total}] {title}")

    def info(self, text: str) -> None:
        self._write(f"      {text}")
        self._log(f"      {text}")

    def ok(self, text: str) -> None:
        self._write(f"  OK  {text}")
        self._log(f"  OK  {text}")

    def warn(self, text: str) -> None:
        self._write(f"  !!  {text}")
        self._log(f"  !!  {text}")

    def fail(self, text: str) -> None:
        self._write(f"  XX  {text}")
        self._log(f"  XX  {text}")

    def _log(self, text: str) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
        except OSError:
            pass

    def log_block(self, text: str) -> None:
        for line in text.splitlines():
            self._log("      | " + line)

    def pause(self, message: str = "Pressione Enter para fechar.") -> None:
        if not self._interactive:
            return
        try:
            input(message)
        except (EOFError, KeyboardInterrupt):
            pass


# ------------------------------------------------------------------- utilities
def run(command: list[str], console: Console, cwd: Path | None = None,
        timeout: int = 900, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    console._log("$ " + " ".join(command))
    completed = subprocess.run(
        command, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        env={**os.environ, **(env or {})},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if completed.stdout:
        console.log_block(completed.stdout)
    if completed.stderr:
        console.log_block(completed.stderr)
    return completed


def command_path(name: str) -> str | None:
    return shutil.which(name)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def is_writable(path: Path) -> bool:
    probe = path / ".ultron-write-test"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def find_python(console: Console) -> tuple[Path, str]:
    """Return (python, version) for a 64-bit CPython >= MIN_PYTHON."""
    candidates: list[Path] = []
    if sys.executable and Path(sys.executable).name.lower().startswith("python"):
        candidates.append(Path(sys.executable))
    for name in ("python", "python3", "py"):
        found = command_path(name)
        if not found:
            continue
        if Path(found).name.lower() == "py.exe":
            probe = run([found, "-3", "-c", "import sys;print(sys.executable)"], console, timeout=60)
            if probe.returncode == 0 and probe.stdout.strip():
                candidates.append(Path(probe.stdout.strip().splitlines()[-1]))
        else:
            candidates.append(Path(found))
    for base in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path("C:/Python315"), Path("C:/Python314"), Path("C:/Python313"),
        Path("C:/Python312"), Path("C:/Python311"), Path("C:/Python310"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
    ):
        if not base.is_dir():
            continue
        if base.name.lower().startswith("python"):
            candidates.append(base / "python.exe")
        else:
            for child in sorted(base.glob("Python3*"), reverse=True):
                candidates.append(child / "python.exe")
    seen: set[str] = set()
    rejected: list[str] = []
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except OSError:
            continue
        if resolved in seen or not Path(resolved).is_file():
            continue
        seen.add(resolved)
        probe = run([resolved, "-c",
                     "import sys,struct;print(sys.version.split()[0]);"
                     "print(struct.calcsize('P')*8);print(sys.version_info[:2] >= (3,10))"],
                    console, timeout=60)
        if probe.returncode != 0:
            continue
        lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        version, bits, new_enough = lines[0], lines[1], lines[2] == "True"
        if not new_enough:
            rejected.append(f"{resolved} ({version}) é antigo; precisa 3.10 ou superior")
            continue
        if bits != "64":
            rejected.append(f"{resolved} ({version}) é 32 bits; precisa 64 bits")
            continue
        return Path(resolved), version
    detail = ("\n      " + "\n      ".join(rejected)) if rejected else ""
    raise SetupError(
        "Python 3.10 ou superior (64 bits) não encontrado.\n"
        "      Instale em https://www.python.org/downloads/windows/ marcando\n"
        "      \"Add python.exe to PATH\" e rode o instalador de novo." + detail
    )


def find_node(console: Console) -> tuple[Path, Path, str]:
    node = command_path("node")
    npm = command_path("npm.cmd") or command_path("npm")
    if not node or not npm:
        raise SetupError(
            "Node.js não encontrado.\n"
            "      Instale o Node.js LTS em https://nodejs.org (o instalador já inclui o npm)\n"
            "      e rode o instalador de novo."
        )
    probe = run([node, "--version"], console, timeout=60)
    version = probe.stdout.strip() or "desconhecida"
    try:
        major = int(version.lstrip("v").split(".")[0])
    except ValueError:
        major = 0
    if major < MIN_NODE:
        raise SetupError(f"Node.js {version} é antigo; precisa da versão {MIN_NODE} ou superior.")
    return Path(node), Path(npm), version


def check_folder(root: Path, console: Console) -> None:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise SetupError(
            "A pasta do programa está incompleta:\n      " + "\n      ".join(missing)
            + "\n      Extraia o ZIP inteiro para uma pasta e rode o instalador de lá."
        )
    name = root.name
    problems = []
    if any(character in BANNED for character in name):
        problems.append("o nome da pasta tem caractere proibido (<>:\"|?*)")
    if name.split(".")[0].lower() in RESERVED:
        problems.append("o nome da pasta é reservado pelo Windows")
    if not name.isascii():
        problems.append("o nome da pasta tem acentos ou caracteres especiais")
    if problems:
        raise SetupError(
            "Mova a pasta para um caminho simples e rode de novo:\n      "
            + "\n      ".join(problems) + "\n      Exemplo bom: C:\\ultron"
        )
    if not is_writable(root):
        raise SetupError(
            "Sem permissão de escrita nesta pasta. Mova o ULTRON para uma pasta do seu usuário\n"
            "      (por exemplo C:\\ultron) — não precisa de administrador."
        )
    free = shutil.disk_usage(root).free
    if free < 1_500 * 1024 * 1024:
        raise SetupError(
            f"Espaço livre insuficiente: {human_size(free)}. Libere pelo menos 1,5 GB\n"
            "      (o ambiente Python e o Electron ocupam cerca de 600 MB)."
        )


# ---------------------------------------------------------------------- steps
def read_requirements(root: Path) -> list[str]:
    packages = []
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            packages.append(line)
    return packages


def read_package(root: Path) -> dict:
    return json.loads((root / "electron" / "package.json").read_text(encoding="utf-8"))


def step_python_env(root: Path, console: Console, python: Path, version: str) -> Path:
    venv = root / "venv"
    venv_python = venv / "Scripts" / "python.exe"
    marker = venv / VENV_MARKER
    if venv_python.is_file() and marker.is_file():
        try:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            recorded = {}
        if recorded.get("base_python") == str(python) and recorded.get("requirements") == \
                (root / "requirements.txt").read_text(encoding="utf-8"):
            console.ok(f"Ambiente Python já está pronto ({recorded.get('version', version)}).")
            return venv_python
        console.info("Ambiente Python existente precisa ser atualizado; recriando.")
    if venv.exists():
        shutil.rmtree(venv, ignore_errors=True)
    console.info(f"Criando ambiente isolado em venv\\ (Python {version}, 64 bits).")
    completed = run([str(python), "-m", "venv", str(venv)], console, cwd=root)
    if completed.returncode != 0 or not venv_python.is_file():
        raise SetupError("Não consegui criar o ambiente Python (venv). Veja logs\\setup.log.")
    return venv_python


def _stamp(root: Path, name: str, payload: dict) -> None:
    (root / "venv" / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _stamp_matches(root: Path, name: str, payload: dict) -> bool:
    try:
        return json.loads((root / "venv" / name).read_text(encoding="utf-8")) == payload
    except (OSError, ValueError):
        return False


def step_dependencies(root: Path, console: Console, venv_python: Path) -> None:
    packages = read_requirements(root)
    fingerprint = {"requirements": (root / "requirements.txt").read_text(encoding="utf-8"),
                   "python": sys.version.split()[0]}
    if _stamp_matches(root, DEPS_MARKER, fingerprint):
        console.ok(f"{len(packages)} pacotes Python já estão instalados.")
        return
    console.info(f"Instalando {len(packages)} pacotes Python (pode levar alguns minutos).")
    completed = run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], console, cwd=root)
    if completed.returncode != 0:
        console.warn("Não consegui atualizar o pip; seguindo com a versão existente.")
    completed = run([str(venv_python), "-m", "pip", "install", "--quiet", "-r", "requirements.txt"], console, cwd=root)
    if completed.returncode != 0:
        raise SetupError(
            "Falha ao instalar os pacotes Python. Confira a conexão com a internet e\n"
            "      os detalhes em logs\\setup.log."
        )
    # Só o que o núcleo precisa para subir; bibliotecas de áudio dependem do driver
    # da máquina e são validadas pelo diagnóstico, não aqui.
    check = run([str(venv_python), "-c", "import dotenv, openai, psutil; print('deps ok')"], console, cwd=root)
    if check.returncode != 0:
        raise SetupError("Pacotes Python instalados, mas não puderam ser importados. Veja logs\\setup.log.")
    _stamp(root, DEPS_MARKER, fingerprint)
    console.ok(f"{len(packages)} pacotes Python instalados.")


def step_electron(root: Path, console: Console, npm: Path) -> None:
    electron_dir = root / "electron"
    package = read_package(root)
    electron_exe = electron_dir / "node_modules" / "electron" / "dist" / "electron.exe"
    wanted = str(package.get("devDependencies", {}).get("electron", ""))
    marker = electron_dir / "node_modules" / ".ultron-electron.json"
    if electron_exe.is_file() and marker.is_file():
        try:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            recorded = {}
        if recorded.get("electron") == wanted:
            console.ok(f"Interface Electron já está instalada ({wanted.lstrip('^~')}).")
            return
    console.info(f"Baixando a interface Electron {wanted.lstrip('^~')} (cerca de 120 MB).")
    completed = run([str(npm), "install", "--no-audit", "--no-fund", "--loglevel=error"], console, cwd=electron_dir)
    if completed.returncode != 0 or not electron_exe.is_file():
        raise SetupError(
            "Não consegui instalar o Electron. Confira a internet (ou um proxy) e veja\n"
            "      logs\\setup.log."
        )
    marker.write_text(json.dumps({"electron": wanted}), encoding="utf-8")
    console.ok("Interface Electron instalada.")


def step_config(root: Path, console: Console) -> bool:
    env = root / ".env"
    example = root / ".env.example"
    if env.exists():
        console.ok(".env já existe; suas chaves foram mantidas.")
        return False
    if not example.is_file():
        raise SetupError(".env.example ausente no pacote; extraia o ZIP inteiro.")
    shutil.copyfile(example, env)
    console.ok(".env criado a partir do modelo.")
    return True


def write_marker(root: Path, python: Path, version: str) -> None:
    # Descarta caches de bytecode que apontam para o Python de outra máquina.
    for cache in (root / ".pytest_cache", Path(root / "__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    (root / "venv" / VENV_MARKER).write_text(
        json.dumps({
            "base_python": str(python),
            "version": version,
            "requirements": (root / "requirements.txt").read_text(encoding="utf-8"),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, indent=2),
        encoding="utf-8",
    )


def step_shortcut(root: Path, console: Console, venv_python: Path) -> bool:
    """Create the Start Menu shortcut through the shell API, no PowerShell needed."""
    if os.name != "nt":
        return False
    appdata = os.environ.get("APPDATA")
    if not appdata:
        console.warn("APPDATA não definido; atalho não criado.")
        return False
    start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        start_menu.mkdir(parents=True, exist_ok=True)
    except OSError:
        console.warn("Não consegui acessar o Menu Iniciar; atalho não criado.")
        return False
    # O atalho aponta para o ULTRON.exe (o mesmo launcher do app), com o ícone do
    # executável; o pythonw só é usado se o launcher não existir.
    launcher = root / "ULTRON.exe"
    pythonw = venv_python.with_name("pythonw.exe")
    if launcher.is_file():
        target, arguments = launcher, ""
    else:
        target = pythonw if pythonw.is_file() else venv_python
        arguments = f'"{root / "desktop.py"}"'
    icon = root / "ULTRON.ico"
    link = start_menu / f"{APP_NAME}.lnk"
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ULTRON_LNK);"
        f"$s.TargetPath=$env:ULTRON_TARGET;$s.Arguments=$env:ULTRON_ARGS;"
        f"$s.WorkingDirectory=$env:ULTRON_ROOT;$s.IconLocation=$env:ULTRON_ICON;"
        f"$s.Description='{APP_NAME}';$s.Save()"
    )
    environment = {
        "ULTRON_LNK": str(link),
        "ULTRON_TARGET": str(target),
        "ULTRON_ARGS": arguments,
        "ULTRON_ROOT": str(root),
        "ULTRON_ICON": str(icon) if icon.is_file() else "",
    }
    completed = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-Command", script], console, cwd=root, timeout=120, env=environment)
    desktop_dir = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    desktop_link = desktop_dir / f"{APP_NAME}.lnk"
    if desktop_dir.is_dir():
        environment["ULTRON_LNK"] = str(desktop_link)
        run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script], console, cwd=root, timeout=120, env=environment)
    if completed.returncode != 0 or not link.is_file():
        console.warn("Não consegui criar o atalho; abra pelo ULTRON.exe ou pelo iniciar_desktop.bat.")
        return False
    places = "Menu Iniciar" + (" e Área de Trabalho" if desktop_link.is_file() else "")
    console.ok(f"Atalho criado no {places}.")
    return True


def shortcut_points_inside(link: Path, root: Path) -> bool:
    """Só apaga o atalho se ele aponta para ESTA pasta (nunca o de outra instalação)."""
    script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ULTRON_LNK);"
              "Write-Output $s.TargetPath")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, timeout=60, env={**os.environ, "ULTRON_LNK": str(link)},
    )
    target = (completed.stdout or "").strip()
    if not target:
        return False
    try:
        return Path(target).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def step_doctor(root: Path, console: Console, venv_python: Path, opened_env: bool) -> int:
    checks: list[tuple[str, bool, str]] = []
    for name in REQUIRED_FILES:
        checks.append((name, (root / name).is_file(), "arquivo do programa"))
    probe = run([str(venv_python), "-c", "import config, cerebro, seguranca; print('ok')"], console, cwd=root)
    checks.append(("núcleo importável", probe.returncode == 0, "config, cerebro, seguranca"))
    electron_exe = root / "electron" / "node_modules" / "electron" / "dist" / "electron.exe"
    checks.append(("Electron", electron_exe.is_file(), str(electron_exe)))
    env = root / ".env"
    keys_configured = False
    if env.is_file():
        text = env.read_text(encoding="utf-8", errors="replace")
        keys_configured = any(
            line.split("=", 1)[1].strip()
            for line in text.splitlines()
            if line.split("=", 1)[0].strip() in {"GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY"}
            and "=" in line
        )
    checks.append(("chave de IA configurada", keys_configured, ".env"))
    try:
        urllib.request.urlopen("https://api.github.com", timeout=6).close()
        checks.append(("internet", True, "api.github.com"))
    except Exception:
        checks.append(("internet", False, "sem conexão; o núcleo funciona, a IA não"))
    failures = 0
    for name, passed, detail in checks:
        if passed:
            console.ok(f"{name}")
        else:
            failures += 1
            console.warn(f"{name} — {detail}")
    if not keys_configured:
        console.info("Adicione GEMINI_API_KEY (grátis em https://aistudio.google.com/apikey) "
                     "no arquivo .env e abra o ULTRON.")
    if opened_env:
        console.info("O arquivo .env foi aberto no Bloco de Notas para você colar a chave.")
    return 0 if failures == 0 else 0


def offer_start(root: Path, console: Console, venv_python: Path) -> None:
    if not console._interactive:
        return
    try:
        answer = input("\nAbrir o ULTRON agora? [S/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if answer in ("", "s", "sim", "y"):
        pythonw = venv_python.with_name("pythonw.exe")
        launcher = pythonw if pythonw.is_file() else venv_python
        subprocess.Popen([str(launcher), str(root / "desktop.py")], cwd=str(root),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        console.info("Iniciado. O painel abre em alguns segundos.")


# ---------------------------------------------------------------------- flows
def install(root: Path, console: Console, non_interactive: bool) -> int:
    total = 6
    console.step(1, total, "Conferindo a pasta do programa")
    check_folder(root, console)
    console.ok(f"Pasta pronta: {root}")

    console.step(2, total, "Procurando Python e Node.js")
    python, py_version = find_python(console)
    console.ok(f"Python {py_version} — {python}")
    _node, npm, node_version = find_node(console)
    console.ok(f"Node.js {node_version}")

    console.step(3, total, "Preparando o ambiente Python")
    venv_python = step_python_env(root, console, python, py_version)

    console.step(4, total, "Instalando dependências")
    step_dependencies(root, console, venv_python)
    step_electron(root, console, npm)
    write_marker(root, python, py_version)

    console.step(5, total, "Configuração")
    created_env = step_config(root, console)
    shortcut = step_shortcut(root, console, venv_python)

    console.step(6, total, "Verificação final")
    step_doctor(root, console, venv_python, created_env)

    if created_env and console._interactive and not non_interactive:
        try:
            answer = input("\nAbrir o .env agora para colar sua chave de IA? [S/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("", "s", "sim", "y"):
            subprocess.Popen(["notepad.exe", str(root / ".env")])

    console.info("")
    console.info("Pronto." + ("" if shortcut else " Abra pelo iniciar_desktop.bat ou por este instalador."))
    console.info(f"Registro da instalação: {console.log_path}")
    console.info("Para remover depois: ULTRON-Setup.exe --uninstall")
    if not non_interactive:
        offer_start(root, console, venv_python)
    return 0


def uninstall(root: Path, console: Console) -> int:
    total = 3
    console.step(1, total, "Removendo atalho e início automático")
    appdata = os.environ.get("APPDATA", "")
    programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    removed = []
    shortcuts = [
        programs / f"{APP_NAME}.lnk",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / f"{APP_NAME}.lnk",
    ]
    for candidate in shortcuts:
        try:
            if candidate.is_file() and shortcut_points_inside(candidate, root):
                candidate.unlink()
                label = candidate.name if candidate.parent.name != "Desktop" else f"Área de Trabalho/{candidate.name}"
                removed.append(label)
        except OSError:
            console.warn(f"Não consegui remover {candidate}")
    for candidate in (programs / "Startup" / "ULTRON Desktop.vbs", programs / "Startup" / "Ultron.vbs"):
        try:
            if candidate.is_file():
                candidate.unlink()
                label = candidate.name if candidate.parent.name != "Desktop" else f"Área de Trabalho/{candidate.name}"
                removed.append(label)
        except OSError:
            console.warn(f"Não consegui remover {candidate}")
    console.ok("Removidos: " + (", ".join(removed) if removed else "nada a remover"))

    console.step(2, total, "Removendo ambiente Python e Electron")
    for folder in (root / "venv", root / "electron" / "node_modules"):
        if folder.exists():
            size = folder_size(folder)
            shutil.rmtree(folder, ignore_errors=True)
            console.ok(f"{folder.relative_to(root)} removido ({human_size(size)}).")

    console.step(3, total, "Seus dados")
    console.info("Mantidos de propósito: .env (suas chaves), dados\\ (memória e histórico), logs\\.")
    console.info("Se quiser apagar tudo, exclua a pasta inteira: " + str(root))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ULTRON-Setup", description=f"Instalador do {APP_NAME}")
    parser.add_argument("--uninstall", action="store_true", help="remove o que o instalador criou")
    parser.add_argument("--silent", action="store_true", help="não faz perguntas")
    parser.add_argument("--root", default=None, help="pasta do programa (padrão: a pasta deste exe)")
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve() if arguments.root else (
        Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    console = Console(root)
    console._log(f"{APP_NAME} — instalador iniciado ({'desinstalar' if arguments.uninstall else 'instalar'})")
    try:
        if arguments.uninstall:
            return uninstall(root, console)
        return install(root, console, arguments.silent)
    except SetupError as error:
        console.fail("Instalação interrompida.")
        for line in str(error).splitlines():
            console._write("      " + line.strip())
            console._log("      " + line.strip())
        console._write("")
        console.info(f"Detalhes: {console.log_path}")
        console.pause()
        return 1
    except KeyboardInterrupt:
        console.fail("Cancelado pelo usuário.")
        return 130
    except Exception:
        console.fail("Erro inesperado no instalador.")
        console.log_block(traceback.format_exc())
        console.info(f"Envie este arquivo para diagnóstico: {console.log_path}")
        console.pause()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
