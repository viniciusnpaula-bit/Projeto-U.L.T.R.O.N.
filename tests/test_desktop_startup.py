import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import desktop
from desktop_autostart import install, is_installed, remove, startup_path


class StartupHarness:
    def __init__(self, keys=None):
        self.events = []
        self.tokens = []
        self.exit_code = 0
        self.keys = {"gemini": "configured"} if keys is None else keys
        self.modules = self._modules()

    def _modules(self):
        harness = self
        fake_config = types.SimpleNamespace(PROVEDORES=["gemini", "groq"], CHAVES=self.keys)
        fake_core = types.SimpleNamespace(
            instancia_unica=lambda: harness.events.append("instance-check") or True,
            preparar_windows=lambda: harness.events.append("prepare-windows"),
            loop_lembretes=lambda: None,
            atalho_parada=lambda: harness.events.append("hotkey"),
        )
        fake_security = types.SimpleNamespace(log=types.SimpleNamespace(error=lambda message: None))
        fake_telegram = types.SimpleNamespace(iniciar=lambda: harness.events.append("telegram") or False)

        class Runtime:
            def __init__(self):
                harness.events.append("runtime-created")

            def start(self):
                harness.events.append("runtime-start")

            def set_api_running(self, value):
                harness.events.append(("api-running", value))

            def shutdown(self):
                harness.events.append("runtime-stop")

        class Server:
            def __init__(self):
                self.stop = threading.Event()
                harness.events.append("server-created")

            def serve_forever(self):
                harness.events.append("server-serving")
                self.stop.wait(1)

            def shutdown(self):
                harness.events.append("server-shutdown")
                self.stop.set()

            def server_close(self):
                harness.events.append("server-close")

        def create_server(runtime, token):
            harness.events.append("api-created")
            harness.tokens.append(token)
            return Server(), "http://127.0.0.1:50000"

        def launch(executable, app_dir, api_url, token):
            harness.events.append("electron-start")
            harness.electron = (executable, app_dir, api_url, token)
            return harness.exit_code

        fake_tk = types.ModuleType("tkinter")
        fake_tk.messagebox = types.SimpleNamespace(
            showerror=lambda *args, **kwargs: harness.events.append("showerror"),
            showinfo=lambda *args, **kwargs: harness.events.append("showinfo"))
        stack = ExitStack()
        stack.enter_context(patch.dict(sys.modules, {
            "config": fake_config,
            "main": fake_core,
            "seguranca": fake_security,
            "telegram_bot": fake_telegram,
            "desktop_runtime": types.SimpleNamespace(DesktopRuntime=Runtime),
            "desktop_api": types.SimpleNamespace(create_server=create_server),
            "tkinter": fake_tk,
        }))
        stack.enter_context(patch.object(desktop, "_electron_paths", return_value=(Path("electron.exe"), Path("electron-app")), create=True))
        stack.enter_context(patch.object(desktop, "_launch_electron", side_effect=launch, create=True))
        return stack


class DesktopStartupTests(unittest.TestCase):
    def test_missing_provider_key_stops_before_starting_any_service(self):
        harness = StartupHarness(keys={"gemini": "", "groq": ""})
        with harness.modules:
            result = desktop.main()
        self.assertEqual(result, 1)
        self.assertEqual(harness.events, ["showerror"])

    def test_desktop_starts_core_api_and_electron_then_cleans_up_once(self):
        harness = StartupHarness()
        with harness.modules:
            result = desktop.main()
        self.assertEqual(result, 0)
        self.assertLess(harness.events.index("runtime-start"), harness.events.index("server-serving"))
        self.assertLess(harness.events.index("server-serving"), harness.events.index("electron-start"))
        self.assertEqual(harness.events.count("runtime-stop"), 1)
        self.assertEqual(harness.events.count("server-shutdown"), 1)
        self.assertEqual(len(harness.tokens[0]), 43)

    def test_each_run_uses_a_fresh_api_token(self):
        tokens = []
        for _ in range(2):
            harness = StartupHarness()
            with harness.modules:
                self.assertEqual(desktop.main(), 0)
            tokens.append(harness.tokens[0])
        self.assertNotEqual(tokens[0], tokens[1])

    def test_nonzero_electron_exit_is_returned_after_runtime_cleanup(self):
        harness = StartupHarness()
        harness.exit_code = 7
        with harness.modules:
            result = desktop.main()
        self.assertEqual(result, 7)
        self.assertEqual(harness.events.count("runtime-stop"), 1)
        self.assertEqual(harness.events.count("server-shutdown"), 1)

    def test_electron_launch_requires_files_and_receives_api_credentials_in_child_environment(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            exe = root / "electron.exe"
            exe.write_bytes(b"fixture")
            app_dir = root / "electron-app"
            (app_dir / "site").mkdir(parents=True)
            (app_dir / "package.json").write_text("{}", encoding="utf-8")
            (app_dir / "main.js").write_text("// fixture", encoding="utf-8")
            (app_dir / "site" / "index.html").write_text("<html>", encoding="utf-8")
            with patch.dict(os.environ, {"ULTRON_TEST_SECRET": "do-not-forward"}):
                with patch.object(desktop.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as run:
                    self.assertEqual(desktop._launch_electron(exe, app_dir, "http://127.0.0.1:50000", "x" * 43), 7)
            args, kwargs = run.call_args
            self.assertEqual(args[0], [str(exe), str(app_dir)])
            self.assertEqual(kwargs["cwd"], app_dir)
            self.assertEqual(kwargs["env"]["ULTRON_API_URL"], "http://127.0.0.1:50000")
            self.assertEqual(kwargs["env"]["ULTRON_API_TOKEN"], "x" * 43)
            self.assertNotIn("ULTRON_TEST_SECRET", kwargs["env"])
            with self.assertRaises(FileNotFoundError):
                desktop._launch_electron(root / "missing.exe", app_dir, "http://127.0.0.1:1", "x" * 43)

    def test_startup_entry_install_and_remove_are_scoped_to_injected_appdata(self):
        test_root = Path(__file__).resolve().parent / "tmp_autostart"
        test_root.mkdir(exist_ok=True)
        try:
            appdata = test_root / "fake-appdata"
            pythonw = test_root / "venv" / "Scripts" / "pythonw.exe"
            script = test_root / "desktop.py"
            script.write_text("# fixture", encoding="utf-8")
            entry = install(appdata, pythonw, script)
            self.assertEqual(entry, startup_path(appdata))
            self.assertTrue(is_installed(appdata))
            content = entry.read_text(encoding="utf-16")
            self.assertIn(str(pythonw), content)
            self.assertIn(str(script), content)
            self.assertTrue(remove(appdata))
            self.assertFalse(is_installed(appdata))
            self.assertFalse(remove(appdata))
        finally:
            for path in sorted(test_root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if test_root.exists():
                test_root.rmdir()


if __name__ == "__main__":
    unittest.main()
