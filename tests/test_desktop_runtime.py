import importlib
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_runtime import DesktopRuntime


class FakeMain:
    def __init__(self):
        self.pausado = threading.Event()
        self.ouvido = None

    def modo_voz(self, bandeja, entrada_teclado, stop_event, ouvido_pronto, microphone_device_index=None,
                 microphone_device_id=None):
        class FakeOuvido:
            def __init__(self):
                self.capturando = threading.Event()
                self.device_index = microphone_device_index
                self.device_id = microphone_device_id

            def set_device(self, device_index, device_id=None):
                self.device_index = device_index
                self.device_id = device_id

        self.ouvido = FakeOuvido()
        ouvido_pronto(self.ouvido)
        while not stop_event.is_set():
            if self.pausado.is_set():
                self.ouvido.capturando.clear()
            else:
                self.ouvido.capturando.set()
            stop_event.wait(0.005)
        self.ouvido.capturando.clear()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.main = FakeMain()
        self.security = types.SimpleNamespace(
            pin_valido=lambda value: value == "2468",
            timeout=lambda name: 0.06,
            log_seg=lambda *args, **kwargs: None,
            redigir=lambda text: text,
            parada=threading.Event(),
            parar_tudo=lambda: None,
        )
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

        def processar(text, confirmar, origem):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            self.calls.append((text, origem))
            try:
                if text == "confirm":
                    return confirmar("Confirma?", {
                        "acao": "arquivo.apagar", "risco": "CRITICO", "origem": "desktop",
                        "exige_pin": True,
                    })
                if text == "critical-pin-unconfigured":
                    return confirmar("Confirma?", {
                        "acao": "arquivo.apagar", "risco": "CRITICO", "origem": "desktop",
                        "exige_pin": False,
                    })
                if text == "high":
                    return confirmar("Confirma?", {
                        "acao": "sistema.desligar", "risco": "ALTO", "origem": "desktop",
                        "exige_pin": False,
                    })
                time.sleep(0.04)
                return "resposta " + text
            finally:
                with self.lock:
                    self.active -= 1

        self.brain = types.SimpleNamespace(processar=processar, NOTIFICADORES=[])
        self.modules = patch.dict(sys.modules, {
            "main": self.main, "cerebro": self.brain, "seguranca": self.security,
        })
        self.modules.start()
        self.runtime = DesktopRuntime()
        self.runtime.start()

    def tearDown(self):
        self.runtime.shutdown()
        self.modules.stop()

    def events_until(self, predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        collected = []
        while time.monotonic() < deadline:
            collected.extend(self.runtime.poll_events())
            if predicate(collected):
                return collected
            time.sleep(0.005)
        return collected

    def test_startup_is_idempotent_and_shutdown_releases_capture(self):
        self.runtime.start()
        deadline = time.monotonic() + 1
        while self.main.ouvido is None and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertIsNotNone(self.main.ouvido)
        self.assertTrue(self.main.ouvido.capturando.wait(0.5))
        self.runtime.shutdown()
        self.assertTrue(self.main.pausado.is_set())
        self.assertFalse(self.main.ouvido.capturando.is_set())

    def test_commands_are_serialized_and_use_desktop_origin(self):
        self.runtime.submit_command("um")
        self.runtime.submit_command("dois")
        events = self.events_until(lambda items: sum(e.get("type") == "command_result" for e in items) == 2)
        results = [e for e in events if e.get("type") == "command_result"]
        self.assertEqual(self.max_active, 1)
        self.assertEqual({text for text, origin in self.calls}, {"um", "dois"})
        self.assertTrue(all(origin == "desktop" for text, origin in self.calls))
        self.assertEqual({e["response"] for e in results}, {"resposta um", "resposta dois"})

    def test_pause_waits_for_active_capture_to_release_and_can_resume(self):
        self.assertTrue(self.main.ouvido.capturando.wait(0.5))
        self.assertTrue(self.runtime.set_microphone_paused(True))
        self.assertTrue(self.main.pausado.is_set())
        self.assertFalse(self.main.ouvido.capturando.is_set())
        self.assertTrue(self.runtime.set_microphone_paused(False))
        self.assertFalse(self.main.pausado.is_set())

    def test_device_change_pauses_and_reuses_the_existing_capture_instance(self):
        audio = types.SimpleNamespace(
            query_devices=lambda: [
                {"name": "Output", "max_input_channels": 0, "hostapi": 0},
                {"name": "Webcam Mic", "max_input_channels": 1, "hostapi": 0},
            ],
            query_hostapis=lambda: [{"name": "WASAPI"}],
            default=types.SimpleNamespace(device=(1, 0)),
        )
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"LOCALAPPDATA": temp}), \
                patch.dict(sys.modules, {"sounddevice": audio}):
            self.assertTrue(self.main.ouvido.capturando.wait(0.5))
            existing_capture = self.main.ouvido
            self.runtime.select_microphone('["WASAPI","Webcam Mic",0]')
            self.assertIs(self.main.ouvido, existing_capture)
            self.assertEqual(existing_capture.device_index, 1)
            self.assertFalse(self.main.pausado.is_set())

    def test_core_notifications_are_forwarded_to_desktop_events(self):
        self.brain.NOTIFICADORES[0]("Lembrete para o usuário")
        events = self.runtime.poll_events()
        self.assertEqual(events, [{"type": "notification", "message": "Lembrete para o usuário"}])

    def test_shutdown_request_is_reported_in_runtime_snapshot(self):
        self.runtime.request_shutdown()
        self.assertTrue(self.runtime.get_snapshot()["shutdown_requested"])

    def test_startup_status_uses_the_desktop_entry_not_core_tray_entry(self):
        autostart = types.SimpleNamespace(is_installed=lambda: True)
        with patch.dict(sys.modules, {"desktop_autostart": autostart}):
            self.assertTrue(self.runtime.get_snapshot()["autostart_installed"])

    def test_confirmation_timeout_cancels_high_risk_action(self):
        self.runtime.submit_command("high")
        events = self.events_until(lambda items: any(e.get("type") == "command_result" for e in items), timeout=1)
        result = next(e for e in events if e.get("type") == "command_result")
        self.assertIsNone(result["response"])

    def test_critical_action_requires_valid_keyboard_pin(self):
        self.runtime.submit_command("confirm")
        events = self.events_until(lambda items: any(e.get("type") == "confirmation_request" for e in items))
        request = next(e for e in events if e.get("type") == "confirmation_request")
        self.assertTrue(request["requires_pin"])
        self.assertTrue(self.runtime.answer_confirmation(request["request_id"], True, "2468"))
        results = self.events_until(lambda items: any(e.get("type") == "command_result" for e in items))
        result = next(e for e in results if e.get("type") == "command_result")
        self.assertIs(result["response"], True)

    def test_invalid_pin_cancels_critical_action(self):
        self.runtime.submit_command("confirm")
        events = self.events_until(lambda items: any(e.get("type") == "confirmation_request" for e in items))
        request = next(e for e in events if e.get("type") == "confirmation_request")
        self.assertTrue(self.runtime.answer_confirmation(request["request_id"], True, "0000"))
        results = self.events_until(lambda items: any(e.get("type") == "command_result" for e in items))
        result = next(e for e in results if e.get("type") == "command_result")
        self.assertFalse(result["response"])

    def test_critical_action_always_requires_pin_even_if_core_config_marks_optional(self):
        self.runtime.submit_command("critical-pin-unconfigured")
        events = self.events_until(lambda items: any(e.get("type") == "confirmation_request" for e in items))
        request = next(e for e in events if e.get("type") == "confirmation_request")
        self.assertTrue(request["requires_pin"])
        self.assertTrue(self.runtime.answer_confirmation(request["request_id"], True))
        results = self.events_until(lambda items: any(e.get("type") == "command_result" for e in items))
        result = next(e for e in results if e.get("type") == "command_result")
        self.assertFalse(result["response"])


class VoiceCaptureTests(unittest.TestCase):
    def test_capture_event_covers_inputstream_and_clears_when_pause_closes_it(self):
        class Frame:
            def copy(self):
                return self

            def astype(self, _type):
                return self

        class Stream:
            def __init__(self, callback, **kwargs):
                self.callback = callback
                self.kwargs = kwargs
                streams.append(kwargs)
                self.stop = threading.Event()

            def __enter__(self):
                def feed():
                    while not self.stop.is_set():
                        self.callback(Frame(), 1, None, None)
                        time.sleep(0.005)
                self.thread = threading.Thread(target=feed, daemon=True)
                self.thread.start()
                return self

            def __exit__(self, *_args):
                self.stop.set()
                self.thread.join(timeout=0.5)

        class BrokenStream(Stream):
            def __exit__(self, *args):
                super().__exit__(*args)
                raise RuntimeError("input stream failed while closing")

        np = types.SimpleNamespace(float32=float, mean=lambda data: 0, sqrt=lambda value: 0,
                                   concatenate=lambda frames: b"")
        sd = types.SimpleNamespace(InputStream=Stream)
        streams = []
        class Recognizer:
            pass
        sr = types.SimpleNamespace(Recognizer=Recognizer, AudioData=object)
        config = types.SimpleNamespace(LIMIAR_VOZ=400.0)
        security = types.SimpleNamespace(log=types.SimpleNamespace(warning=lambda *a: None))
        with patch.dict(sys.modules, {"numpy": np, "sounddevice": sd,
                                     "speech_recognition": sr, "config": config,
                                     "seguranca": security}):
            sys.modules.pop("voz", None)
            voice = importlib.import_module("voz")
            ouvido = voice.Ouvido(device_index=7)
            ouvido.pausado = threading.Event()
            result = []
            thread = threading.Thread(target=lambda: result.append(ouvido._gravar(30)))
            thread.start()
            self.assertTrue(ouvido.capturando.wait(0.5))
            self.assertEqual(streams[0]["device"], 7)
            ouvido.pausado.set()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertIsNone(result[0])
            self.assertFalse(ouvido.capturando.is_set())

            sd.InputStream = BrokenStream
            outro = voice.Ouvido()
            error = []
            def capture_with_error():
                try:
                    outro._gravar(0)
                except RuntimeError as exc:
                    error.append(str(exc))
            thread = threading.Thread(target=capture_with_error)
            thread.start()
            thread.join(timeout=1)
            self.assertEqual(error, ["input stream failed while closing"])
            self.assertFalse(outro.capturando.is_set())
            sys.modules.pop("voz", None)


class MicrophoneDeviceTests(unittest.TestCase):
    def test_device_list_only_contains_audio_inputs_and_uses_stable_identifiers(self):
        audio = types.SimpleNamespace(
            query_devices=lambda: [
                {"name": "Saída HDMI", "max_input_channels": 0, "hostapi": 0},
                {"name": "Webcam Mic", "max_input_channels": 1, "hostapi": 0},
            ],
            query_hostapis=lambda: [{"name": "WASAPI"}],
            default=types.SimpleNamespace(device=(1, 0)),
        )
        # O teste precisa de um estado limpo: sem isso, uma preferência de microfone
        # salva na máquina de quem roda os testes altera o resultado.
        with patch.dict(sys.modules, {"sounddevice": audio}), \
                patch.object(DesktopRuntime, "_microphone_settings_path",
                             classmethod(lambda cls: Path(tempfile.gettempdir())
                                        / f"ultron-teste-{os.getpid()}-{id(audio)}" / "microphone.json")):
            runtime = DesktopRuntime(start_voice=False)
            result = runtime.list_microphones()
        self.assertEqual([device["name"] for device in result["devices"]], ["Padrão do sistema", "Webcam Mic"])
        self.assertIsInstance(result["devices"][1]["id"], str)
        self.assertTrue(result["selected_available"])

    def test_selected_input_is_persisted_and_missing_input_is_not_substituted(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            devices = [{"name": "Webcam Mic", "max_input_channels": 1, "hostapi": 0}]
            audio = types.SimpleNamespace(
                query_devices=lambda: devices,
                query_hostapis=lambda: [{"name": "WASAPI"}],
                default=types.SimpleNamespace(device=(0, -1)),
            )
            with patch.dict(os.environ, {"LOCALAPPDATA": temp}), patch.dict(sys.modules, {"sounddevice": audio}):
                runtime = DesktopRuntime(start_voice=False)
                selected = runtime.select_microphone(runtime.list_microphones()["devices"][1]["id"])
                self.assertEqual(selected["selected_name"], "Webcam Mic")
                config_path = Path(temp) / "ULTRON" / "microphone.json"
                self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["name"], "Webcam Mic")
                devices.clear()
                missing = runtime.list_microphones()
            self.assertFalse(missing["selected_available"])
            self.assertEqual(missing["selected_name"], "Webcam Mic")
            self.assertEqual(runtime._microphone_device_index, -1)


if __name__ == "__main__":
    unittest.main()
