import contextlib
import io
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SafeDiagnosticTests(unittest.TestCase):
    def test_running_diagnostic_does_not_use_live_services_or_devices(self):
        effects = []

        def module(name, **attrs):
            value = types.ModuleType(name)
            for key, item in attrs.items():
                setattr(value, key, item)
            return value

        tools = module(
            "ferramentas", FERRAMENTAS={},
            executar=lambda *args, **kwargs: effects.append("tool"),
            _catalogo=lambda *args, **kwargs: effects.append("catalog"),
            _resolver_app=lambda *args, **kwargs: effects.append("app"),
        )
        brain = module(
            "cerebro",
            _chamar=lambda *args, **kwargs: effects.append("cloud_ai"),
            descrever_imagem=lambda *args, **kwargs: effects.append("cloud_vision"),
        )
        fake_image = types.SimpleNamespace(new=lambda *args, **kwargs: types.SimpleNamespace(
            save=lambda *args, **kwargs: None))
        fake_pil = module("PIL", Image=fake_image)
        fake_modules = {
            "config": module("config"),
            "memoria": module("memoria", listar_fatos=lambda: []),
            "ferramentas": tools,
            "cerebro": brain,
            "sounddevice": module("sounddevice", query_devices=lambda *a, **k: [{"max_input_channels": 1, "max_output_channels": 1}], rec=lambda *a, **k: effects.append("capture"), play=lambda *a, **k: effects.append("playback")),
            "voz": module("voz", falar=lambda *a, **k: effects.append("speech")),
            "pyautogui": module("pyautogui", screenshot=lambda: effects.append("screenshot")),
            "PIL": fake_pil,
            "pystray": module("pystray"),
        }
        output = io.StringIO()
        with patch.dict(sys.modules, fake_modules), contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT / "diagnostico.py"), run_name="__main__")
        self.assertEqual([], effects)


class TracePrivacyTests(unittest.TestCase):
    def test_trace_uses_known_labels_and_never_logs_free_text(self):
        sys.path.insert(0, str(ROOT))
        import seguranca
        with patch.object(seguranca.log, "info") as logger:
            seguranca.log_rastreamento("voz", "intent_selected", "modo_jogo", "", "selected")
            seguranca.log_rastreamento("texto privado TOKEN-NAO-REGISTRAR", "TOKEN-NAO-REGISTRAR",
                                       "TOKEN-NAO-REGISTRAR", "TOKEN-NAO-REGISTRAR", "TOKEN-NAO-REGISTRAR")
        logged = " ".join(str(call) for call in logger.call_args_list)
        self.assertIn("intent_selected", logged)
        self.assertIn("modo_jogo", logged)
        self.assertNotIn("TOKEN-NAO-REGISTRAR", logged)
        self.assertNotIn("texto privado", logged)
        safe_args = seguranca.sanitizar_args({"consulta": "busca confidencial", "caminho": "pasta pessoal", "acao": "playpause"})
        self.assertNotIn("busca confidencial", str(safe_args))
        self.assertNotIn("pasta pessoal", str(safe_args))
        self.assertEqual("playpause", safe_args["acao"])


if __name__ == "__main__":
    unittest.main()

