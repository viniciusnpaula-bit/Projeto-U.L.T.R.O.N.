"""Authenticated loopback-only HTTP API for ULTRON Desktop."""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


_PREFIX = "/api/v1/"
_MAX_BODY = 8192
_MAX_COMMAND = 4000


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


# Porta preferida: o launcher (ULTRON.exe) usa esta porta para saber quando o painel
# está pronto. Continua sendo só loopback; se estiver ocupada, uma porta livre é usada.
PREFERRED_PORT = 3900


def create_server(runtime, token: str, host: str = "127.0.0.1", port: int = PREFERRED_PORT):
    if host != "127.0.0.1":
        raise ValueError("A API do ULTRON só pode usar 127.0.0.1.")
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("O token da API deve ser aleatório e ter pelo menos 32 caracteres.")

    class Handler(BaseHTTPRequestHandler):
        server_version = "ULTRONDesktop/1.9.4"
        sys_version = ""

        def log_message(self, _format, *_args):
            # The standard access log can include local identifiers and is not needed here.
            return

        def _send(self, status: int, data: dict):
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host", "") != expected_host:
                self._send(403, {"error": "local_host_required"})
                return False
            origin = self.headers.get("Origin")
            expected_origin = f"http://{expected_host}"
            if origin is not None and origin != expected_origin:
                self._send(403, {"error": "local_origin_required"})
                return False
            provided = self.headers.get("X-ULTRON-Token", "")
            if not hmac.compare_digest(provided, token):
                self._send(401, {"error": "unauthorized"})
                return False
            return True

        def _path(self):
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                return None
            return parsed.path

        def _read_json(self):
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send(415, {"error": "application_json_required"})
                return None
            try:
                length = int(self.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                self._send(400, {"error": "invalid_content_length"})
                return None
            if length < 0:
                self._send(400, {"error": "invalid_content_length"})
                return None
            if length > _MAX_BODY:
                self._send(413, {"error": "request_too_large"})
                return None
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": "invalid_json"})
                return None
            if not isinstance(value, dict):
                self._send(400, {"error": "json_object_required"})
                return None
            return value

        def do_GET(self):
            if not self._authorized():
                return
            path = self._path()
            try:
                if path == _PREFIX + "health":
                    self._send(200, {"ok": True, "version": "1.9.4"})
                elif path == _PREFIX + "status":
                    self._send(200, runtime.get_snapshot())
                elif path == _PREFIX + "events":
                    self._send(200, {"events": runtime.poll_events()})
                elif path == _PREFIX + "microphones":
                    self._send(200, runtime.list_microphones())
                elif path == _PREFIX + "update":
                    self._send(200, runtime.update_info())
                elif path == _PREFIX + "update/check":
                    self._send(200, runtime.check_update())
                elif path == _PREFIX + "conversation":
                    # Bat-papo de voz: turnos da sessão (texto já redigido pelo runtime).
                    self._send(200, {"turns": runtime.conversation_turns()})
                else:
                    self._send(404, {"error": "not_found"})
            except Exception:
                self._send(500, {"error": "internal_error"})

        def do_POST(self):
            if not self._authorized():
                return
            path = self._path()
            if path is None:
                self._send(400, {"error": "query_not_supported"})
                return
            body = self._read_json()
            if body is None:
                return
            try:
                if path == _PREFIX + "commands":
                    if set(body) != {"text"}:
                        self._send(400, {"error": "invalid_command_payload"})
                        return
                    text = body["text"]
                    if not isinstance(text, str) or not text.strip() or len(text) > _MAX_COMMAND:
                        self._send(400, {"error": "invalid_command_text"})
                        return
                    operation_id = runtime.submit_command(text)
                    self._send(202, {"operation_id": operation_id})
                elif path == _PREFIX + "microphone":
                    if set(body) != {"paused"} or type(body["paused"]) is not bool:
                        self._send(400, {"error": "invalid_microphone_payload"})
                        return
                    paused = body["paused"]
                    if not runtime.set_microphone_paused(paused):
                        self._send(409, {"error": "microphone_state_not_confirmed"})
                        return
                    self._send(200, {"paused": paused})
                elif path == _PREFIX + "microphone/device":
                    if set(body) != {"device_id"} or (body["device_id"] is not None and not isinstance(body["device_id"], str)):
                        self._send(400, {"error": "invalid_microphone_device_payload"})
                        return
                    try:
                        self._send(200, runtime.select_microphone(body["device_id"]))
                    except LookupError:
                        self._send(409, {"error": "microphone_device_unavailable"})
                elif path == _PREFIX + "confirmations":
                    allowed = {"request_id", "approved", "pin"}
                    if not {"request_id", "approved"}.issubset(body) or set(body) - allowed:
                        self._send(400, {"error": "invalid_confirmation_payload"})
                        return
                    if not isinstance(body["request_id"], str) or type(body["approved"]) is not bool:
                        self._send(400, {"error": "invalid_confirmation_payload"})
                        return
                    pin = body.get("pin")
                    if pin is not None and not isinstance(pin, str):
                        self._send(400, {"error": "invalid_confirmation_payload"})
                        return
                    accepted = runtime.answer_confirmation(body["request_id"], body["approved"], pin)
                    if not accepted:
                        self._send(404, {"error": "confirmation_not_pending"})
                        return
                    self._send(200, {"accepted": True})
                elif path == _PREFIX + "emergency-stop":
                    if body:
                        self._send(400, {"error": "empty_payload_required"})
                        return
                    import seguranca
                    seguranca.parar_tudo()
                    self._send(200, {"stopped": True})
                elif path == _PREFIX + "update/apply":
                    if set(body) - {"restart_after"} or ("restart_after" in body and type(body["restart_after"]) is not bool):
                        self._send(400, {"error": "invalid_update_payload"})
                        return
                    self._send(202, runtime.apply_update(bool(body.get("restart_after", False))))
                elif path == _PREFIX + "update/launch":
                    if body:
                        self._send(400, {"error": "empty_payload_required"})
                        return
                    if not runtime.launch_update():
                        self._send(409, {"error": "update_not_prepared"})
                        return
                    self._send(200, {"launched": True})
                elif path == _PREFIX + "update/rollback":
                    if body:
                        self._send(400, {"error": "empty_payload_required"})
                        return
                    if not runtime.rollback_update():
                        self._send(409, {"error": "no_backup_available"})
                        return
                    self._send(200, {"rolled_back": True})
                elif path == _PREFIX + "shutdown":
                    if body:
                        self._send(400, {"error": "empty_payload_required"})
                        return
                    runtime.request_shutdown()
                    self._send(202, {"shutdown_requested": True})
                else:
                    self._send(404, {"error": "not_found"})
            except ValueError:
                self._send(400, {"error": "invalid_request"})
            except RuntimeError:
                self._send(409, {"error": "operation_unavailable"})
            except Exception:
                self._send(500, {"error": "internal_error"})

        def _method_not_allowed(self):
            if not self._authorized():
                return
            self._send(405, {"error": "method_not_allowed"})

        do_PUT = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_OPTIONS = _method_not_allowed

    try:
        server = _Server((host, port), Handler)
    except OSError:
        if port == 0:
            raise
        # Porta preferida ocupada: qualquer porta livre do loopback serve.
        server = _Server((host, 0), Handler)
    actual_host, actual_port = server.server_address[:2]
    return server, f"http://{actual_host}:{actual_port}"
