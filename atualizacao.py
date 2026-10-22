"""Atualização do ULTRON a partir do GitHub, verificada e com reversão.

Fluxo (tudo em loopback/local, sem privilégio de administrador):

    GET  /api/v1/update/check     -> consulta o Release mais recente e compara versões
    POST /api/v1/update/apply     -> baixa o ZIP, confere o SHA-256 publicado,
                                     guarda um backup e agenda a troca de arquivos
    POST /api/v1/update/restart   -> reabre o ULTRON com a versão nova
    POST /api/v1/update/rollback  -> volta para o backup anterior (se a troca já ocorreu)

Decisões de segurança:
  * só HTTPS e só hosts do GitHub (api.github.com e o domínio de download de assets);
  * o ZIP só é aplicado se o SHA-256 bater com o `SHA256SUMS.txt` do Release;
  * arquivos de dados (.env, dados/, logs/, venv/, electron/node_modules) nunca são
    tocados na troca — só código e assets do pacote;
  * a troca acontece por um script externo (.bat) que espera o processo terminar,
    porque o Windows não deixa substituir um .exe/.pyc em uso;
  * se algo falhar, a versão anterior continua no backup e o rollback é automático.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

APP_NAME = "U.L.T.R.O.N."
DEFAULT_REPO = "viniciusnpaula-bit/Projeto-U.L.T.R.O.N."
ALLOWED_HOSTS = {"api.github.com", "objects.githubusercontent.com", "github.com",
                 "release-assets.githubusercontent.com"}
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
PROTECTED = (".env", "dados", "logs", "venv", ".git", ".ultron-state.json")
# Nunca sobrescreve nada fora destes tipos: assim um ZIP malicioso não troca código
# arbitrário do sistema — só arquivos do próprio pacote.
ALLOWED_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".json", ".html", ".css", ".svg", ".png",
                    ".ico", ".md", ".txt", ".bat", ".ps1", ".yml", ".yaml", ".toml", ".cfg",
                    ".exe", ".dll", ".woff", ".woff2"}
STATE_NAME = ".ultron-state.json"


class UpdateError(RuntimeError):
    """Falha segura: nada foi alterado no disco."""


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4]) or (0,)


def _current_version(root: Path) -> str:
    try:
        package = json.loads((root / "electron" / "package.json").read_text(encoding="utf-8"))
        return str(package.get("version") or "0.0.0")
    except (OSError, ValueError):
        return "0.0.0"


def _request(url: str, *, timeout: float = 15.0, accept: str = "application/vnd.github+json",
             limit: int = 2 * 1024 * 1024) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"https", "http"}:
        raise UpdateError("Endereço de atualização inválido.")
    if os.environ.get("ULTRON_UPDATE_ALLOW_HTTP") != "1" and parsed.scheme != "https":
        raise UpdateError("A atualização exige HTTPS.")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise UpdateError("O host de atualização não é permitido.")
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "ULTRON-Desktop"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        chunks, total = [], 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise UpdateError("Resposta do GitHub maior que o esperado.")
            chunks.append(chunk)
    return b"".join(chunks)


def _download(url: str, destino: Path, allowed_hosts: set[str]) -> tuple[int, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and os.environ.get("ULTRON_UPDATE_ALLOW_HTTP") != "1":
        raise UpdateError("A atualização exige HTTPS.")
    if parsed.hostname not in allowed_hosts:
        raise UpdateError("Origem do download não permitida.")
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(url, headers={"User-Agent": "ULTRON-Desktop"})
    with urllib.request.urlopen(request, timeout=60) as response, destino.open("wb") as handle:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise UpdateError("O pacote de atualização é grande demais.")
            digest.update(chunk)
            handle.write(chunk)
    return total, digest.hexdigest()


class UpdateManager:
    def __init__(self, root: Path, repo: str | None = None, log=None) -> None:
        self.root = Path(root).resolve()
        self.repo = (repo or os.environ.get("ULTRON_UPDATE_REPO") or DEFAULT_REPO).strip()
        self.log = log or (lambda _msg: None)
        self._lock = threading.Lock()
        self._job: dict | None = None
        self._state_path = self.root / STATE_NAME

    # ------------------------------------------------------------- estado
    @property
    def current_version(self) -> str:
        return _current_version(self.root)

    def _state(self) -> dict:
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, **values) -> dict:
        state = {**self._state(), **values, "updated_at": time.time()}
        try:
            self._state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass
        return state

    def describe(self) -> dict:
        state = self._state()
        last = state.get("last_check") or {}
        return {
            "current_version": self.current_version,
            "repo": self.repo,
            "auto_check": state.get("auto_check", True),
            "last_check": last or None,
            "job": self._job,
        }

    # ------------------------------------------------------------- consulta
    def check(self, *, timeout: float = 15.0) -> dict:
        """Compara a versão instalada com o último Release publicado."""
        with self._lock:
            try:
                raw = _request(f"https://api.github.com/repos/{self.repo}/releases/latest", timeout=timeout)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    resultado = {"status": "sem_release", "current_version": self.current_version,
                                 "repo": self.repo, "message": "Ainda não há release publicado neste repositório."}
                else:
                    resultado = {"status": "erro", "current_version": self.current_version, "repo": self.repo,
                                 "message": f"O GitHub respondeu {error.code}."}
                self._save_state(last_check={**resultado, "at": time.time()})
                return resultado
            except (urllib.error.URLError, OSError, UpdateError) as error:
                resultado = {"status": "erro", "current_version": self.current_version, "repo": self.repo,
                             "message": f"Sem acesso ao GitHub ({type(error).__name__})."}
                self._save_state(last_check={**resultado, "at": time.time()})
                return resultado

            try:
                release = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise UpdateError("Resposta do GitHub inválida.") from None
            tag = str(release.get("tag_name") or release.get("name") or "").strip()
            latest = tag.lstrip("vV")
            assets = release.get("assets") or []
            zip_asset = next((a for a in assets if str(a.get("name", "")).lower().endswith(".zip")), None)
            sums_asset = next((a for a in assets if str(a.get("name", "")).lower() == "sha256sums.txt"), None)
            resultado = {
                "status": "ok",
                "current_version": self.current_version,
                "latest_version": latest or self.current_version,
                "tag": tag,
                "repo": self.repo,
                "update_available": _version_tuple(latest) > _version_tuple(self.current_version),
                "notes": str(release.get("body") or "")[:4000],
                "published_at": release.get("published_at"),
                "html_url": release.get("html_url"),
                "asset": {"name": zip_asset.get("name"), "size": zip_asset.get("size"),
                          "url": zip_asset.get("browser_download_url")} if zip_asset else None,
                "checksums": sums_asset.get("browser_download_url") if sums_asset else None,
            }
            self._save_state(last_check={**resultado, "at": time.time()})
            self.log(f"Atualização: instalada {resultado['current_version']} / publicada {resultado['latest_version']}")
            return resultado

    def set_auto_check(self, enabled: bool) -> bool:
        self._save_state(auto_check=bool(enabled))
        return bool(enabled)

    # ------------------------------------------------------------- aplicação
    def apply(self, *, restart_after: bool = False) -> dict:
        """Baixa, verifica e aplica. Roda em thread; o progresso fica em self._job."""
        if self._job and self._job.get("status") in {"baixando", "aplicando"}:
            return self._job
        self._job = {"status": "baixando", "percent": 0, "message": "Consultando o GitHub…", "started_at": time.time()}
        thread = threading.Thread(target=self._apply_worker, args=(restart_after,),
                                  name="ultron-update", daemon=True)
        thread.start()
        return self._job

    def _set_job(self, **values) -> None:
        if self._job is not None:
            self._job = {**self._job, **values}

    def _apply_worker(self, restart_after: bool) -> None:
        try:
            info = self.check()
            if info.get("status") != "ok":
                self._set_job(status="erro", message=info.get("message") or "Não foi possível verificar.")
                return
            if not info.get("update_available"):
                self._set_job(status="atualizado", percent=100, message="Você já está na versão mais recente.")
                return
            asset = info.get("asset")
            if not asset or not asset.get("url"):
                self._set_job(status="erro", message="O Release não tem um pacote .zip para baixar.")
                return
            if not info.get("checksums"):
                self._set_job(status="erro", message="O Release não publica SHA256SUMS.txt; atualização recusada.")
                return

            self._set_job(status="baixando", percent=5, message=f"Baixando {asset['name']}…")
            work = Path(tempfile.mkdtemp(prefix="ultron-update-"))
            destino = work / str(asset["name"])
            allowed = set(ALLOWED_HOSTS)
            _, digest = _download(str(asset["url"]), destino, allowed)

            self._set_job(percent=45, message="Conferindo a assinatura do pacote (SHA-256)…")
            brutos = _request(str(info["checksums"]), accept="text/plain", limit=512 * 1024).decode("utf-8", "replace")
            esperado = ""
            for linha in brutos.splitlines():
                partes = linha.split()
                if len(partes) >= 2 and partes[-1].lstrip("*") == Path(str(asset["name"])).name:
                    esperado = partes[0].lower()
                    break
            if not esperado:
                shutil.rmtree(work, ignore_errors=True)
                self._set_job(status="erro", message="O pacote não está listado no SHA256SUMS.txt.")
                return
            if esperado != digest:
                shutil.rmtree(work, ignore_errors=True)
                self._set_job(status="erro", message="SHA-256 não confere: o download foi descartado.")
                self.log("Atualização recusada: hash diferente.")
                return

            self._set_job(status="aplicando", percent=60, message="Preparando os arquivos…")
            staging = work / "staging"
            staging.mkdir()
            with zipfile.ZipFile(destino) as archive:
                if archive.testzip() is not None:
                    raise UpdateError("O ZIP está corrompido.")
                for item in archive.infolist():
                    nome = item.filename.replace("\\", "/")
                    if nome.endswith("/") or nome.startswith("__MACOSX"):
                        continue
                    partes = Path(nome).parts
                    if any(parte in {"..", ""} for parte in partes) or Path(nome).is_absolute():
                        raise UpdateError("O ZIP contém caminho inseguro.")
                    if partes[0] in PROTECTED:
                        continue
                    if Path(nome).suffix.lower() not in ALLOWED_SUFFIXES:
                        continue
                    alvo = staging.joinpath(*partes)
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as origem, alvo.open("wb") as saida:
                        shutil.copyfileobj(origem, saida)

            if not (staging / "electron" / "package.json").is_file():
                raise UpdateError("O pacote não parece ser do ULTRON (sem electron/package.json).")

            backup = self._backup_root() / f"backup-{self.current_version}-{time.strftime('%Y%m%d-%H%M%S')}"
            script = self._write_apply_script(staging, backup)
            self._save_state(pending_backup=str(backup), pending_version=str(info.get("latest_version")),
                             applied_manifest=self._manifest(staging))
            self._set_job(status="pronto", percent=100,
                          message=f"Versão {info['latest_version']} verificada. Feche o painel para aplicar.",
                          script=str(script), backup=str(backup), version=str(info.get("latest_version")))
            self.log(f"Atualização {info['latest_version']} pronta em {staging}; script {script}")
            if restart_after is not None:
                self._save_state(restart_after=bool(restart_after))
        except UpdateError as error:
            self._set_job(status="erro", message=str(error))
            self.log(f"Atualização falhou: {error}")
        except Exception as error:  # noqa: BLE001 - nunca deixa a thread morrer em silêncio
            self._set_job(status="erro", message=f"Falha inesperada na atualização ({type(error).__name__}).")
            self.log(f"Atualização falhou: {type(error).__name__}")

    # ------------------------------------------------------------- apoio
    def _backup_root(self) -> Path:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        destino = Path(base) / "ULTRON" / "updates"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def _manifest(self, folder: Path) -> dict[str, str]:
        manifesto = {}
        for arquivo in folder.rglob("*"):
            if arquivo.is_file():
                manifesto[arquivo.relative_to(folder).as_posix()] = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        return manifesto

    def _write_apply_script(self, staging: Path, backup: Path) -> Path:
        """Script .bat que espera o ULTRON sair, troca os arquivos e reabre.

        A troca usa robocopy com /XD nas pastas protegidas: dados do usuário,
        ambiente Python e node_modules ficam intactos.
        """
        destino = self._backup_root() / f"aplicar-{int(time.time())}.bat"
        reabrir = self.root / "ULTRON.exe"
        script = f"""@echo off
chcp 65001 >nul
title Aplicando atualização do U.L.T.R.O.N.
echo Aguardando o ULTRON fechar...
:espera
tasklist /FI "IMAGENAME eq ULTRON.exe" | find /I "ULTRON.exe" >nul && (timeout /t 1 /nobreak >nul & goto espera)
tasklist /FI "IMAGENAME eq electron.exe" | find /I "electron.exe" >nul && (timeout /t 1 /nobreak >nul & goto espera)
echo Backup em "{backup}"...
robocopy "{self.root}" "{backup}" /E /NFL /NDL /NJH /NJS /NP /XD venv node_modules dados logs .git build /XF *.log >nul
echo Copiando a versão nova...
robocopy "{staging}" "{self.root}" /E /IS /IT /NFL /NDL /NJH /NJS /NP /XD venv node_modules dados logs .git build >nul
if errorlevel 8 goto falhou
echo Atualização aplicada.
if /I "{os.environ.get("ULTRON_UPDATE_REOPEN", "1")}"=="1" start "" "{reabrir}"
exit /b 0
:falhou
echo A cópia falhou. Restaurando a versão anterior...
robocopy "{backup}" "{self.root}" /E /IS /IT /NFL /NDL /NJH /NJS /NP /XD venv node_modules dados logs .git build >nul
start "" "{reabrir}"
exit /b 1
"""
        destino.write_text(script, encoding="utf-8", newline="\r\n")
        return destino

    def launch_apply(self) -> bool:
        """Inicia o script de aplicação (a troca acontece depois que o app sair)."""
        job = self._job or {}
        script = job.get("script")
        if not script or not Path(script).is_file():
            return False
        try:
            # A janela do script PRECISA existir: é ela que espera o ULTRON sair.
            subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/c", str(script)], cwd=str(self.root))
            return True
        except OSError:
            return False

    def rollback(self) -> bool:
        """Restaura o backup guardado pela última atualização aplicada."""
        backup = self._state().get("pending_backup")
        if not backup:
            return False
        origem = Path(backup)
        if not origem.is_dir():
            return False
        for arquivo in origem.rglob("*"):
            if not arquivo.is_file():
                continue
            relativo = arquivo.relative_to(origem)
            destino = self.root / relativo
            if relativo.parts and relativo.parts[0] in PROTECTED:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(arquivo, destino)
        self._save_state(rolled_back_at=time.time())
        self.log("Rollback aplicado a partir do backup.")
        return True


def default_manager(root: Path, log=None) -> UpdateManager:
    return UpdateManager(root, log=log)


if __name__ == "__main__":  # utilidade de linha de comando
    raiz = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    print(json.dumps(UpdateManager(raiz).check(), indent=2, ensure_ascii=False))
