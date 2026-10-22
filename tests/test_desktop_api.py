import json
import secrets
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_api import create_server


class FakeRuntime:
    def __init__(self):
        self.snapshot = {
            "core_running": True, "api_running": True, "microphone_paused": False,
            "autostart_installed": False, "shutdown_requested": False, "error": None,
        }
        self.events = [{"type": "notification", "message": "online"}]
        self.commands = []
        self.confirmations = []
        self.pause_requests = []
        self.shutdown_requested = False
        self.pause_result = True
        self.microphones = {"devices": [{"id": None, "name": "Padrão do sistema"},
                                         {"id": "input-1", "name": "Webcam Mic"}],
                            "selected_id": None, "selected_name": "Padrão do sistema",
                            "selected_available": True, "active_name": "Padrão do sistema"}
        self.selected_microphone = None

    def get_snapshot(self):
        return self.snapshot

    def conversation_turns(self):
        return [{"role": "user", "text": "oi", "source": "voz", "at": 1.0}]

    def poll_events(self):
        events, self.events = self.events, []
        return events

    def submit_command(self, text):
        self.commands.append(text)
        return "operation-1"

    def set_microphone_paused(self, paused):
        self.pause_requests.append(paused)
        return self.pause_result

    def list_microphones(self):
        return self.microphones

    def select_microphone(self, device_id):
        if device_id is not None and device_id not in {device["id"] for device in self.microphones["devices"]}:
            raise LookupError("unavailable")
        self.selected_microphone = device_id
        return {"selected": device_id}

    def answer_confirmation(self, request_id, approved, pin=None):
        self.confirmations.append((request_id, approved, pin))
        return True

    def request_shutdown(self):
        self.shutdown_requested = True
        self.snapshot["shutdown_requested"] = True


class DesktopApiTests(unittest.TestCase):
    def setUp(self):
        self.runtime = FakeRuntime()
        self.token = secrets.token_urlsafe(32)
        self.server, self.url = create_server(self.runtime, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def call(self, path, method="GET", data=None, raw=None, headers=None, use_token=True):
        payload = raw if raw is not None else (None if data is None else json.dumps(data).encode())
        request_headers = {} if headers is None else dict(headers)
        if use_token:
            request_headers.setdefault("X-ULTRON-Token", self.token)
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        req = Request(self.url + path, data=payload, headers=request_headers, method=method)
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.loads(response.read().decode())
        except HTTPError as error:
            body = error.read().decode()
            error.close()
            return error.code, json.loads(body)

    def test_health_status_and_events_require_token_and_return_expected_data(self):
        status, health = self.call("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["version"], "1.9.4")
        status, snapshot = self.call("/api/v1/status")
        self.assertEqual(status, 200)
        self.assertFalse(snapshot["microphone_paused"])
        status, events = self.call("/api/v1/events")
        self.assertEqual(status, 200)
        self.assertEqual(events["events"], [{"type": "notification", "message": "online"}])

    def test_conversation_route_returns_voice_turns_only_with_token(self):
        status, _ = self.call("/api/v1/conversation", use_token=False)
        self.assertEqual(status, 401)
        status, data = self.call("/api/v1/conversation")
        self.assertEqual(status, 200)
        self.assertEqual(data["turns"][0]["role"], "user")
        self.assertEqual(data["turns"][0]["source"], "voz")

    def test_missing_or_wrong_token_is_rejected_without_work(self):
        status, _ = self.call("/api/v1/commands", method="POST", data={"text": "hello"}, use_token=False)
        self.assertEqual(status, 401)
        status, _ = self.call("/api/v1/commands", method="POST", data={"text": "hello"},
                              headers={"X-ULTRON-Token": "wrong"})
        self.assertEqual(status, 401)
        self.assertEqual(self.runtime.commands, [])

    def test_exact_host_validation_rejects_remote_or_mismatched_hosts(self):
        status, _ = self.call("/api/v1/health", headers={"Host": "example.com"})
        self.assertEqual(status, 403)
        status, _ = self.call("/api/v1/health", headers={"Origin": "https://example.com"})
        self.assertEqual(status, 403)

    def test_invalid_content_type_utf8_json_and_oversized_body_are_rejected(self):
        status, _ = self.call("/api/v1/commands", method="POST", raw=b"{}",
                              headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _ = self.call("/api/v1/commands", method="POST", raw=b"\xff")
        self.assertEqual(status, 400)
        status, _ = self.call("/api/v1/commands", method="POST", raw=b"{" )
        self.assertEqual(status, 400)
        status, _ = self.call("/api/v1/commands", method="POST", raw=b" " * 8193)
        self.assertEqual(status, 413)
        self.assertEqual(self.runtime.commands, [])

    def test_commands_enforce_text_limit_and_queue_valid_text(self):
        status, _ = self.call("/api/v1/commands", method="POST", data={"text": " "})
        self.assertEqual(status, 400)
        status, _ = self.call("/api/v1/commands", method="POST", data={"text": "x" * 4001})
        self.assertEqual(status, 400)
        status, result = self.call("/api/v1/commands", method="POST", data={"text": "hello"})
        self.assertEqual(status, 202)
        self.assertEqual(result["operation_id"], "operation-1")
        self.assertEqual(self.runtime.commands, ["hello"])

    def test_microphone_and_confirmation_payloads_are_validated(self):
        status, _ = self.call("/api/v1/microphone", method="POST", data={"paused": "yes"})
        self.assertEqual(status, 400)
        status, result = self.call("/api/v1/microphone", method="POST", data={"paused": True})
        self.assertEqual(status, 200)
        self.assertEqual(result["paused"], True)
        self.assertEqual(self.runtime.pause_requests, [True])
        status, _ = self.call("/api/v1/confirmations", method="POST",
                              data={"request_id": "r1", "approved": "yes", "pin": "2468"})
        self.assertEqual(status, 400)
        status, result = self.call("/api/v1/confirmations", method="POST",
                                   data={"request_id": "r1", "approved": True, "pin": "2468"})
        self.assertEqual(status, 200)
        self.assertNotIn("pin", result)
        self.assertEqual(self.runtime.confirmations, [("r1", True, "2468")])

    def test_microphone_devices_are_listed_and_selection_is_validated(self):
        status, result = self.call("/api/v1/microphones")
        self.assertEqual(status, 200)
        self.assertEqual(result, self.runtime.microphones)
        status, result = self.call("/api/v1/microphone/device", method="POST", data={"device_id": None})
        self.assertEqual(status, 200)
        self.assertIsNone(self.runtime.selected_microphone)
        status, result = self.call("/api/v1/microphone/device", method="POST", data={"device_id": "input-1"})
        self.assertEqual(status, 200)
        self.assertEqual(result["selected"], "input-1")
        self.assertEqual(self.runtime.selected_microphone, "input-1")
        status, _ = self.call("/api/v1/microphone/device", method="POST", data={"device_id": 3})
        self.assertEqual(status, 400)
        status, _ = self.call("/api/v1/microphone/device", method="POST", data={"device_id": "disconnected"})
        self.assertEqual(status, 409)

    def test_emergency_stop_and_ordered_shutdown_are_routed(self):
        calls = []
        security = type("Security", (), {"parar_tudo": staticmethod(lambda: calls.append("stop"))})
        with patch.dict(sys.modules, {"seguranca": security}):
            status, _ = self.call("/api/v1/emergency-stop", method="POST", data={})
        self.assertEqual(status, 200)
        self.assertEqual(calls, ["stop"])
        status, result = self.call("/api/v1/shutdown", method="POST", data={})
        self.assertEqual(status, 202)
        self.assertTrue(result["shutdown_requested"])
        self.assertTrue(self.runtime.shutdown_requested)

    def test_unknown_route_and_internal_errors_are_safe(self):
        status, _ = self.call("/api/v1/unknown")
        self.assertEqual(status, 404)
        self.runtime.get_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("secret traceback"))
        status, error = self.call("/api/v1/status")
        self.assertEqual(status, 500)
        self.assertNotIn("traceback", json.dumps(error).lower())
        self.assertNotIn("secret", json.dumps(error).lower())

    def test_server_rejects_non_loopback_bind_address(self):
        with self.assertRaises(ValueError):
            create_server(self.runtime, self.token, host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
