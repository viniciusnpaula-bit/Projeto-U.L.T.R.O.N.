import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atualizacao


def release_fake(tag="v9.9.9", nome_zip="ULTRON-Desktop-v9.9.9.zip", com_checksums=True):
    assets = [{"name": nome_zip, "size": 1024, "browser_download_url": "https://github.com/x/y/releases/a.zip"}]
    if com_checksums:
        assets.append({"name": "SHA256SUMS.txt", "size": 80,
                       "browser_download_url": "https://github.com/x/y/releases/SHA256SUMS.txt"})
    return json.dumps({"tag_name": tag, "body": "novidades", "assets": assets,
                       "html_url": "https://github.com/x/y/releases"}).encode()


def zip_valido(versao="9.9.9"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("electron/package.json", json.dumps({"version": versao}))
        archive.writestr("electron/site/index.html", "<html></html>")
        archive.writestr("cerebro.py", "print('oi')")
        archive.writestr("dados/ultron.db", b"nao pode entrar")
        archive.writestr(".env", "GEMINI_API_KEY=nao pode entrar")
        archive.writestr("notas.exe", b"MZ")
    return buffer.getvalue()


class UpdateManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "ultron"
        (self.root / "electron").mkdir(parents=True)
        (self.root / "electron" / "package.json").write_text(json.dumps({"version": "1.9.4"}), encoding="utf-8")
        (self.root / "ULTRON.exe").write_bytes(b"MZ")
        os.environ["LOCALAPPDATA"] = str(Path(self.temp.name) / "AppData")
        self.manager = atualizacao.UpdateManager(self.root)

    def tearDown(self):
        os.environ.pop("ULTRON_UPDATE_ALLOW_HTTP", None)
        os.environ.pop("LOCALAPPDATA", None)
        self.temp.cleanup()

    def test_version_compare_only_offers_newer_releases(self):
        self.assertGreater(atualizacao._version_tuple("1.9.10"), atualizacao._version_tuple("1.9.9"))
        self.assertFalse(atualizacao._version_tuple("1.9.4") > atualizacao._version_tuple("1.9.4"))

    def test_check_reports_update_available(self):
        with patch.object(atualizacao, "_request", return_value=release_fake()):
            info = self.manager.check()
        self.assertEqual(info["status"], "ok")
        self.assertEqual(info["current_version"], "1.9.4")
        self.assertEqual(info["latest_version"], "9.9.9")
        self.assertTrue(info["update_available"])

    def test_check_without_release_is_not_an_error(self):
        import urllib.error
        erro = urllib.error.HTTPError("u", 404, "not found", {}, None)
        with patch.object(atualizacao, "_request", side_effect=erro):
            info = self.manager.check()
        self.assertEqual(info["status"], "sem_release")

    def test_hosts_outside_github_are_refused(self):
        with self.assertRaises(atualizacao.UpdateError):
            atualizacao._request("https://exemplo-malicioso.com/release.json")
        with self.assertRaises(atualizacao.UpdateError):
            atualizacao._request("http://api.github.com/repos/x/y")   # sem HTTPS

    def _aplicar(self, conteudo, checksums_top="sha256-ok"):
        pacote = zip_valido()
        digest = hashlib.sha256(pacote).hexdigest()
        destino = Path(self.temp.name) / "pacote.zip"
        destino.write_bytes(pacote)

        def download(_url, alvo, _hosts):
            alvo.write_bytes(pacote)
            return len(pacote), digest

        texto = f"{digest if checksums_top == 'sha256-ok' else '0'*64}  ULTRON-Desktop-v9.9.9.zip\n"
        with patch.object(atualizacao, "_request", side_effect=[release_fake(), texto.encode()]), \
             patch.object(atualizacao, "_download", side_effect=download):
            self.manager.apply()
            for _ in range(100):
                if self.manager._job["status"] in {"pronto", "erro", "atualizado"}:
                    break
                import time
                time.sleep(0.02)
        return self.manager._job

    def test_apply_rejects_wrong_hash(self):
        job = self._aplicar(zip_valido(), checksums_top="sha256-errado")
        self.assertEqual(job["status"], "erro")
        self.assertIn("SHA-256", job["message"])

    def test_apply_stages_only_safe_code_and_never_user_data(self):
        job = self._aplicar(zip_valido())
        self.assertEqual(job["status"], "pronto", job.get("message"))
        staging = Path(job["script"]).parent  # script fica na pasta de updates
        self.assertTrue(staging.is_dir())
        # o .bat gerado nunca copia por cima de dados do usuário
        script = Path(job["script"]).read_text(encoding="utf-8")
        self.assertIn("/XD venv node_modules dados logs .git build", script)
        self.assertIn("tasklist", script)

    def test_release_without_checksums_is_refused(self):
        with patch.object(atualizacao, "_request", return_value=release_fake(com_checksums=False)):
            self.manager.apply()
            for _ in range(100):
                if self.manager._job["status"] in {"pronto", "erro", "atualizado"}:
                    break
                import time
                time.sleep(0.02)
        self.assertEqual(self.manager._job["status"], "erro")
        self.assertIn("SHA256SUMS", self.manager._job["message"])


if __name__ == "__main__":
    unittest.main()
