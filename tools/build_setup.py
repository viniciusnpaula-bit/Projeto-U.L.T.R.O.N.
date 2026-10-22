"""Build the ULTRON Desktop distribution: one signed-looking, plain console setup exe.

    python tools/build_setup.py                 # build ULTRON-Setup.exe
    python tools/build_setup.py --zip           # also rebuild ULTRON-Desktop-vX.zip

The icon is validated before compiling, so a broken ICO can never ship again (that
is exactly why some antivirus products flagged the old package: a 111 KB icon whose
header was fine but whose payload was a non-standard PNG sequence).

Build order matters: the .ico is fixed first, then PyInstaller embeds it with
--icon, and only then is the archive assembled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
BUILD = ROOT / "build"
DIST = BUILD / "dist"
EXE_NAME = "ULTRON-Setup.exe"


def step(title: str) -> None:
    print(f"\n== {title}")


def run(command: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(command))
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None)
    if completed.returncode != 0:
        raise SystemExit(f"comando falhou ({completed.returncode}): {command[0]}")


def python_exe() -> str:
    return sys.executable


def check_icon() -> None:
    step("Validando o ícone")
    run([python_exe(), str(TOOLS / "make_icon.py"), "--check"])


def ensure_icon() -> None:
    step("Gerando o ícone multi-resolução")
    run([python_exe(), str(TOOLS / "make_icon.py")])


def build_exe(name: str = "ULTRON-Setup", entry: str = "installer/ultron_setup.py",
              description: str = "Instalador do U.L.T.R.O.N. Desktop",
              console: bool = True) -> Path:
    step(f"Compilando {name}")
    DIST.mkdir(parents=True, exist_ok=True)
    work = BUILD / f"pyinstaller-{name}"
    version_file = BUILD / f"version_info_{name}.txt"
    product_version = json.loads((ROOT / "electron" / "package.json").read_text(encoding="utf-8"))["version"]
    major, minor, patch = (product_version.split(".") + ["0", "0"])[:3]
    version_file.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=(1, 9, 4, 0), prodvers=(1, 9, 4, 0), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'ULTRON'),
        StringStruct('FileDescription', '{description}'),
        StringStruct('FileVersion', '1.9.4.0'),
        StringStruct('InternalName', '{name}'),
        StringStruct('OriginalFilename', '{name}.exe'),
        StringStruct('ProductName', 'U.L.T.R.O.N. Desktop'),
        StringStruct('ProductVersion', '1.9.4')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    run([
        python_exe(), "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--console" if console else "--windowed",
        "--name", name,
        "--icon", str(ROOT / "ULTRON.ico"),
        "--version-file", str(version_file),
        "--distpath", str(DIST),
        "--workpath", str(work),
        "--specpath", str(BUILD),
        "--log-level", "WARN",
        str(ROOT / entry),
    ])
    exe = DIST / f"{name}.exe"
    if not exe.is_file():
        raise SystemExit(f"{name}.exe não foi gerado")
    shutil.copyfile(exe, ROOT / f"{name}.exe")
    return ROOT / f"{name}.exe"


def write_checksums(paths: list[Path]) -> Path:
    target = DIST / "SHA256SUMS.txt"
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
        print(f"  sha256 {path.name}: {digest}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build_zip(output: Path | None = None) -> Path:
    step("Montando o ZIP de distribuição")
    package_version = json.loads((ROOT / "electron" / "package.json").read_text(encoding="utf-8"))["version"]
    output = Path(output) if output else ROOT.parent / f"ULTRON-Desktop-v{package_version}.zip"
    # Pastas de saída de build (electron/dist*, dist-portable etc.) nunca entram no ZIP:
    # eram ~2 GB de instaladores antigos que ninguém usa e que só geram alerta.
    skip_dirs = {"build", "venv", "node_modules", ".venv", "__pycache__", "logs", "dados",
                 ".git", ".pytest_cache", "out"}
    members: list[Path] = []
    for item in sorted(ROOT.rglob("*")):
        relative = item.relative_to(ROOT)
        if any(part in skip_dirs for part in relative.parts):
            continue
        if any(part.startswith(("dist", "build-")) for part in relative.parts[:2]):
            continue
        if item.is_dir():
            continue
        if item.suffix.lower() in {".pyc", ".pyo", ".log", ".zip", ".spec", ".tmp"}:
            continue
        if item.name.startswith(".ultron-") or item.name in {"setup.log", "SHA256SUMS.txt", ".env"}:
            continue
        if item.name.endswith((".db", ".sqlite", ".sqlite3")) or relative.parts[0] in {"logs", "dados"}:
            continue
        if item.stat().st_size > 40 * 1024 * 1024:  # nunca empacotar ambiente embutido por engano
            print(f"  (ignorado por tamanho: {relative})")
            continue
        members.append(item)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in members:
            archive.write(item, item.relative_to(ROOT).as_posix())
    print(f"  {output} ({len(members)} arquivos, {output.stat().st_size / 1024 / 1024:.1f} MB)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", action="store_true", help="também gerar o ZIP de distribuição")
    parser.add_argument("--icon-only", action="store_true", help="só regerar o ícone")
    arguments = parser.parse_args()
    ensure_icon()
    check_icon()
    if arguments.icon_only:
        return 0
    setup_exe = build_exe()
    app_exe = build_exe(name="ULTRON", entry="launcher.py", console=False,
                        description="Painel do U.L.T.R.O.N. Desktop")
    artifacts = [setup_exe, app_exe]
    write_checksums(artifacts)
    if arguments.zip:
        archive = build_zip()
        artifacts.append(archive)
        write_checksums(artifacts)
    print("\nPronto:", ", ".join(str(path) for path in artifacts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
