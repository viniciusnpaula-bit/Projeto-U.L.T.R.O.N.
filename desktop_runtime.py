"""Lifecycle and request coordination for the local Desktop panel."""
from __future__ import annotations

import importlib
import inspect
import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from microphone_devices import enumerate_input_devices


class DesktopRuntime:
    """Runs one core voice loop and serializes Desktop commands through the core."""

    def __init__(self, start_voice: bool = True):
        self.start_voice = start_voice
        self._events: queue.Queue[dict] = queue.Queue()
        self._commands: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._pending: dict[str, dict] = {}
        self._pending_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._microphone_lock = threading.RLock()
        self._stop = threading.Event()
        self._started = False
        self._api_running = False
        self._shutdown_requested = False
        self._error: str | None = None
        self._voice_state = "iniciando"
        self._microphone_error: str | None = None
        self._main = None
        self._security = None
        self._cerebro = None
        self._ouvido = None
        self._turns: list[dict] = []
        self._turns_lock = threading.Lock()
        try:
            import atualizacao
            self._updater = atualizacao.UpdateManager(Path(__file__).resolve().parent,
                                                      repo=os.environ.get("ULTRON_UPDATE_REPO"),
                                                      log=self._log_update)
        except Exception:
            self._updater = None
        self._microphone_preference = self._load_microphone_preference()
        self._microphone_device_id = self._microphone_preference["id"] if self._microphone_preference else None
        self._microphone_device_index = None
        self._command_thread: threading.Thread | None = None
        self._voice_thread: threading.Thread | None = None
        self._notification_callback = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._started:
                return
            self._stop.clear()
            self._main = importlib.import_module("main")
            self._security = importlib.import_module("seguranca")
            self._cerebro = importlib.import_module("cerebro")
            self._main.pausado.clear()
            self._shutdown_requested = False
            self._voice_state = "iniciando"
            self._microphone_error = None
            try:
                if self._microphone_preference:
                    self._resolve_microphone_preference()
                else:
                    self._resolve_default_microphone()
            except Exception:
                self._microphone_device_index = -1
                self._microphone_error = "Não foi possível acessar a lista de entradas de microfone. Verifique a permissão de microfone do Windows."
                self._voice_state = "erro"
            notifiers = getattr(self._cerebro, "NOTIFICADORES", None)
            if isinstance(notifiers, list):
                self._notification_callback = self._notify
                notifiers.append(self._notification_callback)
            self._command_thread = threading.Thread(
                target=self._command_loop, name="ultron-desktop-commands", daemon=True)
            self._command_thread.start()
            self._started = True
            self._error = None
            if self.start_voice:
                self._voice_thread = threading.Thread(
                    target=self._voice_loop, name="ultron-desktop-voice", daemon=True)
                self._voice_thread.start()

    def _voice_loop(self) -> None:
        try:
            kwargs = {
                "bandeja": False,
                "entrada_teclado": False,
                "stop_event": self._stop,
                "ouvido_pronto": self._set_ouvido,
            }
            parameters = inspect.signature(self._main.modo_voz).parameters
            if "microphone_device_index" in parameters:
                kwargs["microphone_device_index"] = self._microphone_device_index
            if "microphone_device_id" in parameters:
                kwargs["microphone_device_id"] = self._microphone_device_id
            if "conversa" in parameters:
                kwargs["conversa"] = self._registrar_conversa
            try:
                if "estado_voz" in inspect.signature(self._main.modo_voz).parameters:
                    kwargs["estado_voz"] = self._set_voice_state
            except (TypeError, ValueError):
                pass
            self._main.modo_voz(**kwargs)
        except Exception:
            self._error = "Falha ao iniciar ou manter a escuta do ULTRON."
            self._set_voice_state("erro", self._error)

    MAX_TURNOS = 80   # últimas falas mantidas na sessão (≈40 trocas)

    def _registrar_conversa(self, papel: str, texto: str, origem: str = "voz") -> None:
        """Registra um turno do bat-papo de voz. Nunca guarda PIN, chave ou token."""
        if papel not in {"user", "assistant"} or not texto:
            return
        try:
            seguro = self._security.redigir(str(texto)) if self._security else str(texto)
        except Exception:
            seguro = "—"
        turno = {
            "type": "conversation_turn",
            "role": papel,
            "text": str(seguro)[:2000],
            "source": str(origem)[:16],
            "at": time.time(),
        }
        self._events.put(turno)
        with self._turns_lock:
            self._turns.append({key: turno[key] for key in ("role", "text", "source", "at")})
            if len(self._turns) > self.MAX_TURNOS:
                del self._turns[:-self.MAX_TURNOS]

    def _log_update(self, mensagem: str) -> None:
        try:
            if self._security:
                self._security.log.info(str(mensagem)[:300])
            else:
                print(f"[atualizacao] {mensagem}"[:300])
        except Exception:
            pass

    def update_info(self) -> dict:
        if self._updater is None:
            return {"current_version": "desconhecida", "status": "indisponivel"}
        return self._updater.describe()

    def check_update(self) -> dict:
        if self._updater is None:
            return {"status": "indisponivel", "message": "Módulo de atualização não carregado."}
        return self._updater.check()

    def apply_update(self, restart_after: bool = False) -> dict:
        if self._updater is None:
            return {"status": "indisponivel", "message": "Módulo de atualização não carregado."}
        return self._updater.apply(restart_after=restart_after)

    def launch_update(self) -> bool:
        return bool(self._updater and self._updater.launch_apply())

    def rollback_update(self) -> bool:
        return bool(self._updater and self._updater.rollback())

    def conversation_turns(self) -> list[dict]:
        with self._turns_lock:
            return list(self._turns)

    def _set_voice_state(self, state: str, error: str | None = None) -> None:
        self._voice_state = str(state)[:40]
        if state == "erro" and error:
            try:
                safe_error = self._security.redigir(str(error))
            except Exception:
                safe_error = "Falha ao acessar ou reconhecer o microfone."
            self._microphone_error = safe_error[:180]
        else:
            self._microphone_error = None

    def _set_ouvido(self, ouvido) -> None:
        if hasattr(ouvido, "set_device") and (
            ouvido.device_index != self._microphone_device_index or
            getattr(ouvido, "device_id", None) != self._microphone_device_id
        ):
            ouvido.set_device(self._microphone_device_index, self._microphone_device_id)
        self._ouvido = ouvido

    def shutdown(self) -> None:
        with self._lifecycle_lock:
            if not self._started:
                return
            self._main.pausado.set()
            self._stop.set()
            with self._pending_lock:
                for pending in self._pending.values():
                    pending["approved"] = False
                    pending["pin"] = None
                    pending["event"].set()
            self._commands.put(None)

            ouvido = self._ouvido
            deadline = time.monotonic() + 4.0
            while ouvido is not None and ouvido.capturando.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            for thread in (self._voice_thread, self._command_thread):
                if thread is not None and thread is not threading.current_thread():
                    thread.join(timeout=4.5)
            self._api_running = False
            self._started = False
            notifiers = getattr(self._cerebro, "NOTIFICADORES", None)
            if isinstance(notifiers, list) and self._notification_callback in notifiers:
                notifiers.remove(self._notification_callback)
            self._notification_callback = None

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    def set_api_running(self, running: bool) -> None:
        self._api_running = bool(running)

    def set_microphone_paused(self, paused: bool) -> bool:
        with self._microphone_lock:
            if not self._started:
                return False
            if paused:
                self._main.pausado.set()
                ouvido = self._ouvido
                deadline = time.monotonic() + 4.0
                while ouvido is not None and ouvido.capturando.is_set() and time.monotonic() < deadline:
                    time.sleep(0.01)
                return ouvido is None or not ouvido.capturando.is_set()
            if self._stop.is_set():
                return False
            self._main.pausado.clear()
            return True

    @staticmethod
    def _microphone_settings_path() -> Path:
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "ULTRON" / "microphone.json"

    @classmethod
    def _load_microphone_preference(cls):
        try:
            value = json.loads(cls._microphone_settings_path().read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("id"), str) and isinstance(value.get("name"), str):
                return {"id": value["id"][:512], "name": value["name"][:256]}
        except (OSError, ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _audio_inputs():
        return enumerate_input_devices()

    def _resolve_microphone_preference(self, inputs=None):
        _audio, inputs = self._audio_inputs() if inputs is None else (None, inputs)
        selected = next((device for device in inputs if device["id"] == self._microphone_preference["id"]), None)
        self._microphone_device_index = selected["index"] if selected else -1
        self._microphone_device_id = self._microphone_preference["id"]
        if selected is None:
            self._microphone_error = f"O microfone selecionado não está disponível: {self._microphone_preference['name']}. Escolha outra entrada antes de retomar a escuta."
            self._voice_state = "erro"
        return selected

    def _resolve_default_microphone(self):
        audio, inputs = self._audio_inputs()
        default = next((device for device in inputs if device["index"] == audio.default.device[0]), None)
        self._microphone_device_index = default["index"] if default else -1
        self._microphone_device_id = None
        if default is None:
            self._microphone_error = "Nenhuma entrada padrão de microfone está disponível. Conecte ou selecione um dispositivo de entrada."
            self._voice_state = "erro"
        return default

    def list_microphones(self):
        audio, inputs = self._audio_inputs()
        selected = next((device for device in inputs if self._microphone_preference and
                         device["id"] == self._microphone_preference["id"]), None)
        default_index = audio.default.device[0]
        default = next((device for device in inputs if device["index"] == default_index), None)
        if self._microphone_preference:
            selected_available = selected is not None
            selected_name = selected["name"] if selected else self._microphone_preference["name"]
            target_index = selected["index"] if selected else -1
        else:
            selected_available = default is not None
            selected_name = default["name"] if default else "Padrão do sistema"
            target_index = default["index"] if default else -1
        self._apply_microphone_device(target_index, self._microphone_preference["id"] if self._microphone_preference else None)
        devices = [{"id": None, "name": "Padrão do sistema"}]
        devices.extend({"id": device["id"], "name": device["name"]} for device in inputs)
        return {"devices": devices, "selected_id": self._microphone_preference["id"] if self._microphone_preference else None,
                "selected_name": selected_name, "selected_available": selected_available,
                "active_name": selected_name if selected_available else None}

    def select_microphone(self, device_id):
        if device_id is not None and (not isinstance(device_id, str) or len(device_id) > 512):
            raise ValueError("Identificador de microfone inválido.")
        audio, inputs = self._audio_inputs()
        selected = next((device for device in inputs if device["id"] == device_id), None) if device_id else None
        if device_id is not None and selected is None:
            raise LookupError("O microfone escolhido não está disponível. Atualize a lista e selecione uma entrada conectada.")
        target_index = selected["index"] if selected else next(
            (item["index"] for item in inputs if item["index"] == audio.default.device[0]), -1)
        if target_index == -1:
            raise LookupError("Não há entrada padrão de áudio disponível. Conecte um microfone ou escolha outra entrada.")
        preference = {"id": selected["id"], "name": selected["name"]} if selected else None
        with self._microphone_lock:
            was_paused = bool(self._started and self._main.pausado.is_set())
            if self._started:
                self._main.pausado.set()
                ouvido = self._ouvido
                deadline = time.monotonic() + 4.0
                while ouvido is not None and ouvido.capturando.is_set() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if ouvido is not None and ouvido.capturando.is_set():
                    raise RuntimeError("A captura atual não foi liberada; tente novamente.")
            settings = self._microphone_settings_path()
            try:
                settings.parent.mkdir(parents=True, exist_ok=True)
                temporary = settings.with_suffix(".tmp")
                temporary.write_text(json.dumps(preference or {"id": None, "name": "Padrão do sistema"}, ensure_ascii=False), encoding="utf-8")
                temporary.replace(settings)
            except OSError as exc:
                if self._started and not was_paused and not self._stop.is_set():
                    self._main.pausado.clear()
                raise RuntimeError("Não foi possível salvar a preferência do microfone no perfil local do Windows.") from exc
            self._microphone_preference = preference
            self._apply_microphone_device(target_index, device_id)
            self._microphone_error = None
            self._voice_state = "iniciando"
            if self._started and not was_paused and not self._stop.is_set():
                self._main.pausado.clear()
        return {"selected_id": device_id, "selected_name": selected["name"] if selected else "Padrão do sistema",
                "selected_available": True, "active_name": selected["name"] if selected else
                next(item["name"] for item in inputs if item["index"] == target_index)}

    def _apply_microphone_device(self, device_index, device_id=None):
        with self._microphone_lock:
            current = getattr(self._ouvido, "device_index", self._microphone_device_index)
            current_id = getattr(self._ouvido, "device_id", self._microphone_device_id)
            if self._microphone_device_index == device_index and current == device_index and current_id == device_id:
                return
            was_paused = bool(self._started and self._main.pausado.is_set())
            if self._started and not was_paused:
                self._main.pausado.set()
            ouvido = self._ouvido
            deadline = time.monotonic() + 4.0
            while ouvido is not None and ouvido.capturando.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            if ouvido is not None and ouvido.capturando.is_set():
                raise RuntimeError("A captura atual não foi liberada para atualizar o microfone.")
            self._microphone_device_index = device_index
            self._microphone_device_id = device_id
            if ouvido is not None and hasattr(ouvido, "set_device"):
                ouvido.set_device(device_index, device_id)
            if device_index == -1:
                name = self._microphone_preference["name"] if self._microphone_preference else "Padrão do sistema"
                self._microphone_error = f"O microfone selecionado não está disponível: {name}. Escolha outra entrada antes de retomar a escuta."
                self._voice_state = "erro"
            elif self._microphone_error and "não está disponível" in self._microphone_error:
                self._microphone_error = None
                self._voice_state = "iniciando"
            if self._started and not was_paused and not self._stop.is_set():
                self._main.pausado.clear()

    def submit_command(self, text: str) -> str:
        if not self._started or self._stop.is_set():
            raise RuntimeError("O ULTRON Desktop não está em execução.")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("O comando deve conter de 1 a 4000 caracteres.")
        operation_id = uuid.uuid4().hex
        self._commands.put((operation_id, text.strip()))
        return operation_id

    def get_snapshot(self) -> dict:
        autostart = False
        try:
            autostart = importlib.import_module("desktop_autostart").is_installed()
        except Exception:
            autostart = False
        metrics = {}
        try:
            psutil = importlib.import_module("psutil")
            metrics = {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "ram_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(os.path.abspath(os.sep)).percent,
            }
        except Exception:
            pass
        return {
            **metrics,
            "core_running": bool(self._started and not self._stop.is_set()),
            "api_running": self._api_running,
            "microphone_paused": bool(self._main is not None and self._main.pausado.is_set()),
            "speaking": bool(getattr(sys.modules.get("voz"), "falando", None) and sys.modules["voz"].falando.is_set()),
            "microphone_state": self._voice_state,
            "microphone_error": self._microphone_error,
            "microphone_capturing": bool(self._ouvido is not None and self._ouvido.capturando.is_set()),
            "microphone_level": int(getattr(self._ouvido, "nivel_atual", 0)) if self._ouvido else 0,
            "microphone_threshold": int(getattr(self._ouvido, "limiar", 0)) if self._ouvido else 0,
            "microphone_device": self._microphone_preference["name"] if self._microphone_preference else "Padrão do sistema",
            "microphone_device_available": self._microphone_device_index != -1,
            "autostart_installed": autostart,
            "shutdown_requested": self._shutdown_requested,
            "error": self._error,
        }

    def _notify(self, text: str) -> None:
        try:
            safe_text = self._security.redigir(str(text))[:1000]
        except Exception:
            safe_text = "Notificação do ULTRON."
        self._events.put({"type": "notification", "message": safe_text})

    def poll_events(self) -> list[dict]:
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def answer_confirmation(self, request_id: str, approved: bool, pin: str | None = None) -> bool:
        if not isinstance(request_id, str) or type(approved) is not bool:
            return False
        if pin is not None and not isinstance(pin, str):
            return False
        with self._pending_lock:
            pending = self._pending.get(request_id)
            if pending is None or pending["expired"] or pending["event"].is_set():
                return False
            pending["approved"] = approved
            pending["pin"] = pin if approved else None
            pending["event"].set()
            return True

    def _confirmar(self, message: str, pedido: dict):
        request_id = uuid.uuid4().hex
        risk = str(pedido.get("risco", "")).upper()
        requires_pin = bool(pedido.get("exige_pin")) or risk == "CRITICO"
        pending = {
            "event": threading.Event(),
            "approved": False,
            "pin": None,
            "expired": False,
            "pedido": pedido,
            "requires_pin": requires_pin,
        }
        with self._pending_lock:
            self._pending[request_id] = pending
        self._events.put({
            "type": "confirmation_request",
            "request_id": request_id,
            "message": str(message)[:1000],
            "risk": risk,
            "requires_pin": requires_pin,
        })
        try:
            timeout = max(0.0, float(self._security.timeout("confirmacao_teclado")))
        except Exception:
            timeout = 20.0
        answered = pending["event"].wait(timeout)
        with self._pending_lock:
            if not answered:
                pending["expired"] = True
            self._pending.pop(request_id, None)
            approved = pending["approved"] if answered else False
            pin = pending["pin"]
            pending["pin"] = None
        if not answered or not approved:
            return False if answered else None
        if requires_pin:
            try:
                valid = bool(pin) and bool(self._security.pin_valido(pin))
            except Exception:
                valid = False
            if not valid:
                try:
                    self._security.log_seg(
                        pedido.get("origem", "desktop"), pedido.get("acao", ""), risk,
                        "DENY", "pin_invalid_or_missing")
                except Exception:
                    pass
                return False
        return True

    def _command_loop(self) -> None:
        while True:
            item = self._commands.get()
            if item is None:
                return
            operation_id, text = item
            if self._stop.is_set():
                response = "Comando cancelado pelo encerramento do ULTRON Desktop."
            else:
                try:
                    response = self._cerebro.processar(text, self._confirmar, "desktop")
                except Exception:
                    self._error = "Falha ao processar um comando do Desktop."
                    try:
                        self._security.log.error(self._error)
                    except Exception:
                        pass
                    response = self._error
            self._events.put({"type": "command_result", "operation_id": operation_id,
                              "response": response})

