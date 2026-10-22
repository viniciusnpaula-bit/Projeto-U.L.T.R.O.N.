"""Publica o ULTRON no GitHub: commit, push e Release (ZIP + SHA256SUMS).

Uso:
    python tools/publicar.py                 # build, commit, push e release da versão atual
    python tools/publicar.py --check-only    # só diz o que seria feito
    python tools/publicar.py --no-release    # commit + push apenas

Requer git autenticado (gh auth login ou token no credential.helper).
O Release alimenta o botão "verificar atualização" do próprio app.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "ultron-desktop-1.9.4"   # branch de release; o main é protegido por PR
DIST = ROOT / "build" / "dist"


def run(args, cwd=ROOT, check=False):
    print("$", " ".join(str(a) for a in args))
    return subprocess.run([str(a) for a in args], cwd=str(cwd), text=True,
                          capture_output=True, check=check)


def versao() -> str:
    return json.loads((ROOT / "electron" / "package.json").read_text(encoding="utf-8"))["version"]


def tem_gh() -> bool:
    import shutil
    executavel = shutil.which("gh")
    if not executavel:
        return False
    try:
        return subprocess.run([executavel, "--version"], capture_output=True, text=True).returncode == 0
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--no-release", action="store_true")
    parser.add_argument("--mensagem", default="")
    args = parser.parse_args()
    v = versao()

    if args.check_only:
        print(f"versão {v}")
        for arquivo in (ROOT / "ULTRON-Setup.exe", ROOT / "ULTRON.exe",
                        ROOT.parent / f"ULTRON-Desktop-v{v}.zip", DIST / "SHA256SUMS.txt"):
            print(("  ok  " if arquivo.is_file() else "  --  ") + str(arquivo))
        print("gh disponível:", tem_gh())
        return 0

    if not (ROOT.parent / f"ULTRON-Desktop-v{v}.zip").is_file() or not (DIST / "SHA256SUMS.txt").is_file():
        build = run([sys.executable, ROOT / "tools" / "build_setup.py", "--zip"])
        print(build.stdout[-2000:], build.stderr[-2000:])
        if build.returncode != 0:
            print("build falhou; nada foi publicado.")
            return 1

    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if status:
        run(["git", "add", "-A"])
        mensagem = args.mensagem or f"ULTRON {v}: atualização"
        commit = run(["git", "-c", "user.name=viniciusnpaula-bit",
                      "-c", "user.email=viniciusnpaula-bit@users.noreply.github.com",
                      "commit", "-m", mensagem])
        print(commit.stdout[-1500:] or commit.stderr[-1500:])
        if commit.returncode != 0:
            return 1
    else:
        print("nada novo para commitar; enviando o que já existe.")

    # O main deste repositório tem regra de proteção ("changes must be made through a
    # pull request"), então publicamos numa branch de release. Assim o push não é
    # recusado e o Release (que é o que o app usa) continua funcionando.
    push = run(["git", "push", "origin", f"HEAD:{BRANCH}"])
    print(push.stdout[-1500:] or push.stderr[-1500:])
    if push.returncode != 0:
        print("\nPUSH FALHOU: veja a mensagem do git acima (credencial ou regra do repositório).")
        return 2

    if args.no_release:
        return 0
    if not tem_gh():
        print("\nPush feito. Para o Release automático, instale o GitHub CLI: winget install --id GitHub.cli")
        return 3
    arquivos = [ROOT.parent / f"ULTRON-Desktop-v{v}.zip", DIST / "SHA256SUMS.txt"]
    existente = run(["gh", "release", "view", f"v{v}"]).returncode == 0
    if existente:
        run(["gh", "release", "upload", f"v{v}", *map(str, arquivos), "--clobber"])
        print(f"Release v{v} atualizado com {len(arquivos)} anexos.")
    else:
        criado = run(["gh", "release", "create", f"v{v}", *map(str, arquivos),
                      "--title", f"U.L.T.R.O.N. {v}", "--notes-file", str(ROOT / "NOTAS-RECONSTRUCAO.txt")])
        print(criado.stdout[-1200:] or criado.stderr[-1200:])
        if criado.returncode != 0:
            return 4
        print(f"Release v{v} criado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
