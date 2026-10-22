import json
import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_ui import DesktopPanel, _ApiClient


class DesktopUiTests(unittest.TestCase):
    def test_graphic_theme_uses_dark_surfaces_and_ultron_red_accent(self):
        colors = DesktopPanel.theme_colors()
        self.assertEqual(colors["background"], "#0B0F14")
        self.assertEqual(colors["surface"], "#121923")
        self.assertEqual(colors["accent"], "#F04452")
        self.assertEqual(colors["text"], "#E7EDF4")

    def test_client_sends_run_token_json_and_short_timeout(self):
        response = MagicMock()
        response.read.return_value = b'{"ok":true}'
        response.__enter__.return_value = response
        client = _ApiClient("http://127.0.0.1:53123", "T" * 43)
        with patch("desktop_ui.urllib.request.urlopen", return_value=response) as open_url:
            self.assertEqual(client.request("POST", "/api/v1/commands", {"text": "hello"}), {"ok": True})
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("X-ultron-token"), "T" * 43)
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data.decode()), {"text": "hello"})
        self.assertEqual(open_url.call_args.kwargs["timeout"], 3)

    def test_command_validation_enforces_4000_character_limit(self):
        self.assertEqual(DesktopPanel.command_payload("  oi  "), {"text": "oi"})
        self.assertEqual(len(DesktopPanel.command_payload("x" * 4000)["text"]), 4000)
        with self.assertRaises(ValueError):
            DesktopPanel.command_payload("x" * 4001)
        with self.assertRaises(ValueError):
            DesktopPanel.command_payload("  ")

    def test_action_requests_only_target_documented_endpoints(self):
        self.assertEqual(DesktopPanel.action_request("microphone", True),
                         ("POST", "/api/v1/microphone", {"paused": True}))
        self.assertEqual(DesktopPanel.action_request("emergency-stop"),
                         ("POST", "/api/v1/emergency-stop", {}))
        self.assertEqual(DesktopPanel.action_request("shutdown"),
                         ("POST", "/api/v1/shutdown", {}))
        with self.assertRaises(ValueError):
            DesktopPanel.action_request("shell")

    def test_status_displays_core_microphone_and_opt_in_startup_state(self):
        status = DesktopPanel.format_status({
            "core_running": True, "api_running": True, "microphone_paused": True,
            "autostart_installed": True, "shutdown_requested": False, "error": None,
        })
        self.assertIn("Núcleo online", status)
        self.assertIn("Microfone pausado", status)
        self.assertIn("Início automático ativo", status)

    def test_event_display_never_serializes_pin_or_internal_fields(self):
        text = DesktopPanel.format_event({
            "type": "confirmation_request", "request_id": "private-id", "message": "Confirma a ação?",
            "risk": "CRITICO", "requires_pin": True, "pin": "2468",
        })
        self.assertEqual(text, "Confirma a ação?")
        self.assertNotIn("2468", text)
        self.assertNotIn("private-id", text)
        self.assertIsNone(DesktopPanel.format_event({"type": "unknown", "pin": "2468"}))

    def test_critical_confirmation_is_sent_to_local_api_not_rendered_or_logged(self):
        panel = DesktopPanel.__new__(DesktopPanel)
        panel.root = object()
        panel._handled_confirmations = set()
        panel._requests = queue.Queue()
        event = {"type": "confirmation_request", "request_id": "r-1", "message": "Confirma?",
                 "risk": "CRITICO", "requires_pin": True}
        with patch("desktop_ui.messagebox.askyesno", return_value=True), \
             patch("desktop_ui.simpledialog.askstring", return_value="2468"):
            panel._handle_event(event)
        tag, method, path, payload = panel._requests.get_nowait()
        self.assertEqual((tag, method, path), ("confirmation", "POST", "/api/v1/confirmations"))
        self.assertEqual(payload, {"request_id": "r-1", "approved": True, "pin": "2468"})
        self.assertNotIn("pin", event)

    def test_closing_panel_stops_polling_and_invokes_shutdown_callback_once(self):
        panel = DesktopPanel.__new__(DesktopPanel)
        panel._close_called = False
        panel._closing = False
        panel._requests = queue.Queue()
        panel.on_close = Mock()
        panel._finish_close()
        panel._finish_close()
        self.assertTrue(panel._closing)
        self.assertTrue(panel._close_called)
        self.assertIsNone(panel._requests.get_nowait())
        panel.on_close.assert_called_once_with()

    def test_request_errors_do_not_expose_exception_or_pin_text(self):
        panel = DesktopPanel.__new__(DesktopPanel)
        panel.client = Mock()
        panel.client.request.side_effect = RuntimeError("PIN=2468 secret-token")
        panel._requests = queue.Queue()
        panel._results = queue.Queue()
        panel._requests.put(("confirmation", "POST", "/api/v1/confirmations", {"pin": "2468"}))
        panel._requests.put(None)
        panel._request_loop()
        tag, result, error = panel._results.get_nowait()
        self.assertEqual(tag, "confirmation")
        self.assertIsNone(result)
        self.assertNotIn("2468", error)
        self.assertNotIn("secret-token", error)


if __name__ == "__main__":
    unittest.main()
