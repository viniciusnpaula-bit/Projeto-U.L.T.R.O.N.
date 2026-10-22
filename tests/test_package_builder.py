import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
BUILDER = PACKAGE / "tools" / "build_setup.py"
spec = importlib.util.spec_from_file_location("build_setup", BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

REQUIRED_IN_ZIP = (
    "desktop.py", "desktop_api.py", "desktop_runtime.py", "microphone_devices.py", "cerebro.py",
    "launcher.py", "ULTRON.exe", "ULTRON-Setup.exe", "ULTRON.ico", "requirements.txt",
    "permissoes.json", "iniciar_desktop.bat", "LEIA-ME.txt", "NOTAS-RECONSTRUCAO.txt",
    "electron/main.js", "electron/preload.js", "electron/api.js", "electron/package.json",
    "electron/site/index.html", "electron/site/app.js", "electron/site/src/real.js",
    "electron/assets/ULTRON.ico", "tools/make_icon.py", "tools/build_setup.py",
    "installer/ultron_setup.py", "tests/test_desktop_ui.py",
)
# ".env.example" é documentação e deve estar no pacote; ".env" com chaves reais, não.
FORBIDDEN_IN_ZIP = (".env", "venv/", "node_modules/", "dados/", "logs/", "__pycache__/",
                    "electron/dist", "build/", ".pytest_cache/", "setup.log", "ultron.db")


class PackageBuilderTests(unittest.TestCase):
    def test_zip_has_required_files_and_never_ships_local_state(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "ULTRON-Desktop-v9.9.9.zip"
            # A chave local nunca pode vazar para o pacote, mesmo existindo na pasta.
            env_file = PACKAGE / ".env"
            created = not env_file.exists()
            if created:
                env_file.write_text("GEMINI_API_KEY=do-not-package\n", encoding="utf-8")
            try:
                archive = builder.build_zip(output)
                self.assertTrue(archive.is_file())
                with zipfile.ZipFile(archive) as zip_file:
                    names = zip_file.namelist()
                    self.assertIsNone(zip_file.testzip())
                    for required in REQUIRED_IN_ZIP:
                        self.assertIn(required, names)
                    for forbidden in FORBIDDEN_IN_ZIP:
                        hits = [name for name in names
                                if name == forbidden or name.startswith(forbidden.rstrip("/") + "/")]
                        self.assertFalse(hits, f"{forbidden} não deveria estar no pacote: {hits[:3]}")
                    for name in names:
                        if name.endswith(".txt"):
                            self.assertNotIn("do-not-package", zip_file.read(name).decode("utf-8", "ignore"))
            finally:
                if created:
                    env_file.unlink(missing_ok=True)

    def test_icon_has_the_sizes_windows_asks_for(self):
        self.assertEqual(builder.ROOT.joinpath("ULTRON.ico").is_file(), True)
        import struct
        payload = (PACKAGE / "ULTRON.ico").read_bytes()
        reserved, kind, count = struct.unpack("<HHH", payload[:6])
        self.assertEqual((reserved, kind), (0, 1))
        offset = 6
        sizes = []
        for _ in range(count):
            width = payload[offset] or 256
            sizes.append(width)
            offset += 16
        for expected in (16, 32, 48, 256):
            self.assertIn(expected, sizes)


if __name__ == "__main__":
    unittest.main()
