"""Fallback Tkinter panel for U.L.T.R.O.N. Desktop.

The Electron panel is the official interface. This module is kept as a light,
dependency-free panel for machines where the Electron step was skipped (or for
diagnosing the local API): it speaks the same loopback API, with the same token
and the same rules — the PIN is sent straight to the API and never rendered,
logged or stored here.

    python desktop_ui.py      (needs ULTRON_API_URL and ULTRON_API_TOKEN from a
                               running core, which desktop.py sets up for a child)
"""
from __future__ import annotations

import json
import os
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

MAX_COMMAND_CHARS = 4000
POLL_MS = 1200


class _ApiClient:
    """Minimal loopback client. Only documented routes, short timeout, no retries."""

    def __init__(self, base_url: str, token: str, timeout: float = 3.0) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise ValueError("A API do ULTRON deve estar em 127.0.0.1.")
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("Token da API inválido.")
        self.base_url = f"http://{parsed.hostname}:{parsed.port}"
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        request.add_header("X-ULTRON-Token", self.token)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
        return json.loads(body or b"{}")


class DesktopPanel:
    """Tk panel: status, transcript and a command box, all through the local API."""

    BACKGROUND = "#0B0F14"
    SURFACE = "#121923"
    ACCENT = "#F04452"
    TEXT = "#E7EDF4"

    @staticmethod
    def theme_colors() -> dict:
        return {"background": DesktopPanel.BACKGROUND, "surface": DesktopPanel.SURFACE,
                "accent": DesktopPanel.ACCENT, "text": DesktopPanel.TEXT}

    @staticmethod
    def command_payload(text: str) -> dict:
        clean = (text or "").strip()
        if not clean:
            raise ValueError("Comando vazio.")
        if len(clean) > MAX_COMMAND_CHARS:
            raise ValueError("Comando longo demais.")
        return {"text": clean}

    @staticmethod
    def action_request(action: str, paused: bool = False) -> tuple[str, str, dict]:
        if action == "microphone":
            return "POST", "/api/v1/microphone", {"paused": bool(paused)}
        if action == "emergency-stop":
            return "POST", "/api/v1/emergency-stop", {}
        if action == "shutdown":
            return "POST", "/api/v1/shutdown", {}
        raise ValueError(f"Ação não permitida: {action}")

    @staticmethod
    def format_status(snapshot: dict) -> str:
        parts = ["Núcleo online" if snapshot.get("core_running") else "Núcleo offline",
                 "API ativa" if snapshot.get("api_running") else "API inativa"]
        parts.append("Microfone pausado" if snapshot.get("microphone_paused") else "Microfone ativo")
        if snapshot.get("autostart_installed"):
            parts.append("Início automático ativo")
        if snapshot.get("error"):
            parts.append(f"Erro: {snapshot['error']}")
        return " · ".join(parts)

    @staticmethod
    def format_event(event: dict) -> str | None:
        if event.get("type") != "confirmation_request":
            return None
        message = event.get("message")
        return message if isinstance(message, str) and message.strip() else None

    def __init__(self, base_url: str, token: str, on_close=None) -> None:
        self.client = _ApiClient(base_url, token)
        self.on_close = on_close
        self._requests: queue.Queue = queue.Queue()
        self._results: queue.Queue = queue.Queue()
        self._handled_confirmations: set[str] = set()
        self._close_called = False
        self._closing = False
        self.root = tk.Tk()
        self.root.title("U.L.T.R.O.N. Desktop")
        self.root.configure(bg=self.BACKGROUND)
        self.root.geometry("720x560")
        self.root.protocol("WM_DELETE_WINDOW", self._finish_close)
        colors = self.theme_colors()
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TLabel", background=colors["background"], foreground=colors["text"])
        self.status = tk.StringVar(value="Conectando…")
        ttk.Label(self.root, textvariable=self.status).pack(anchor="w", padx=12, pady=(12, 4))
        self.transcript = tk.Text(self.root, height=22, bg=colors["surface"], fg=colors["text"],
                                  insertbackground=colors["accent"], relief="flat", wrap="word")
        self.transcript.pack(fill="both", expand=True, padx=12)
        self.transcript.configure(state="disabled")
        entry_row = tk.Frame(self.root, bg=self.BACKGROUND)
        entry_row.pack(fill="x", padx=12, pady=12)
        self.command = tk.Entry(entry_row, bg=colors["surface"], fg=colors["text"],
                                insertbackground=colors["accent"], relief="flat")
        self.command.pack(side="left", fill="x", expand=True, ipady=6)
        self.command.bind("<Return>", lambda _event: self._send_command())
        ttk.Button(entry_row, text="Enviar", command=self._send_command).pack(side="left", padx=(8, 0))
        ttk.Button(entry_row, text="Microfone", command=self._toggle_microphone).pack(side="left", padx=(8, 0))
        threading.Thread(target=self._request_loop, daemon=True).start()
        self.root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ helpers
    def _append(self, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{text}\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _submit(self, tag: str, method: str, path: str, payload: dict | None = None) -> None:
        self._requests.put((tag, method, path, payload))

    def _request_loop(self) -> None:
        while True:
            item = self._requests.get()
            if item is None:
                self._results.put(None)
                return
            tag, method, path, payload = item
            try:
                self._results.put((tag, self.client.request(method, path, payload), None))
            except Exception as error:  # noqa: BLE001 - o texto do erro nunca chega à tela
                # Never forward the exception text: it can carry the PIN or the token.
                self._results.put((tag, None, f"Falha na API local ({type(error).__name__})."))

    def _poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                result = self._results.get_nowait()
                if result is None:
                    continue
                tag, data, error = result
                if error:
                    self._append(error)
                elif tag == "status" and isinstance(data, dict):
                    self.status.set(self.format_status(data))
                elif tag == "events" and isinstance(data, dict):
                    for event in data.get("events", []):
                        self._handle_event(event)
                    if isinstance(data.get("status"), dict):
                        self.status.set(self.format_status(data["status"]))
                elif tag == "command" and isinstance(data, dict):
                    reply = data.get("reply") or data.get("message")
                    if isinstance(reply, str):
                        self._append(f"ULTRON: {reply}")
        except queue.Empty:
            pass
        self._submit("events", "GET", "/api/v1/events")
        self.root.after(POLL_MS, self._poll)

    def _handle_event(self, event: dict) -> None:
        request_id = event.get("request_id")
        if event.get("type") != "confirmation_request" or not isinstance(request_id, str):
            return
        if request_id in self._handled_confirmations:
            return
        self._handled_confirmations.add(request_id)
        message = self.format_event(event) or "Confirma esta ação?"
        if not messagebox.askyesno("ULTRON", message):
            self._submit("confirmation", "POST", "/api/v1/confirmations",
                         {"request_id": request_id, "approved": False})
            return
        pin = simpledialog.askstring("ULTRON", "PIN do proprietário:", show="*") if event.get("requires_pin") else None
        payload = {"request_id": request_id, "approved": True}
        if pin:
            payload["pin"] = pin
        self._submit("confirmation", "POST", "/api/v1/confirmations", payload)
        # O PIN nunca entra no dicionário do evento, no histórico ou nos logs.
        event.pop("pin", None)

    def _send_command(self) -> None:
        try:
            payload = self.command_payload(self.command.get())
        except ValueError as error:
            self._append(str(error))
            return
        self.command.delete(0, "end")
        self._append(f"Você: {payload['text']}")
        self._submit("command", "POST", "/api/v1/commands", payload)

    def _toggle_microphone(self) -> None:
        paused = "pausado" not in self.status.get()
        method, path, payload = self.action_request("microphone", paused)
        self._submit("microphone", method, path, payload)

    def _finish_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._requests.put(None)
        if not self._close_called:
            self._close_called = True
            if callable(self.on_close):
                self.on_close()
        root = getattr(self, "root", None)
        if root is not None:
            root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    base_url = os.environ.get("ULTRON_API_URL", "")
    token = os.environ.get("ULTRON_API_TOKEN", "")
    if not base_url or not token:
        print("Abra o painel pelo ULTRON.exe. Esta tela precisa da API local em execução.")
        return 1
    DesktopPanel(base_url, token).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
