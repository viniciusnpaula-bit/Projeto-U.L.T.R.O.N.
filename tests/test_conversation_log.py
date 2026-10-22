import sys
import threading
import types
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import desktop_runtime


class FakeSecurity:
    def redigir(self, texto):
        return str(texto).replace("2468", "****")

    class log:
        @staticmethod
        def error(*_args, **_kwargs):
            return None


class ConversationLogTests(unittest.TestCase):
    """O bat-papo de voz recebe cada fala reconhecida e cada resposta do núcleo."""

    def setUp(self):
        self.runtime = desktop_runtime.DesktopRuntime(start_voice=False)
        self.runtime._security = FakeSecurity()

    def drenar(self):
        return [evento for evento in self.runtime.poll_events() if evento.get("type") == "conversation_turn"]

    def test_turnos_ficam_em_ordem_e_aparecem_nos_eventos(self):
        self.runtime._registrar_conversa("user", "Ei, Ultron, abra o navegador", "voz")
        self.runtime._registrar_conversa("assistant", "Abrindo agora, senhor.", "voz")
        turnos = self.runtime.conversation_turns()
        self.assertEqual([t["role"] for t in turnos], ["user", "assistant"])
        self.assertEqual(turnos[0]["text"], "Ei, Ultron, abra o navegador")
        eventos = self.drenar()
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[1]["source"], "voz")
        self.assertIsInstance(eventos[0]["at"], float)

    def test_pin_e_token_nunca_chegam_ao_bat_papo(self):
        self.runtime._registrar_conversa("user", "meu pin é 2468", "voz")
        self.runtime._registrar_conversa("assistant", "A chave sk-abc123 não pode aparecer", "voz")
        texto = " ".join(turno["text"] for turno in self.runtime.conversation_turns())
        self.assertNotIn("2468", texto)
        self.assertIn("****", texto)

    def test_papeis_invalidos_e_texto_vazio_sao_ignorados(self):
        self.runtime._registrar_conversa("system", "ignore", "voz")
        self.runtime._registrar_conversa("user", "", "voz")
        self.assertEqual(self.runtime.conversation_turns(), [])

    def test_historico_e_limitado_para_nao_crescer_sem_fim(self):
        for indice in range(self.runtime.MAX_TURNOS + 25):
            self.runtime._registrar_conversa("user", f"fala {indice}", "voz")
        turnos = self.runtime.conversation_turns()
        self.assertEqual(len(turnos), self.runtime.MAX_TURNOS)
        self.assertEqual(turnos[-1]["text"], f"fala {self.runtime.MAX_TURNOS + 24}")


class VoiceBridgeTests(unittest.TestCase):
    """modo_voz precisa avisar o painel a cada fala reconhecida e a cada resposta."""

    def test_modo_voz_publica_fala_reconhecida_e_resposta(self):
        publicados = []

        class OuvidoFalso:
            device_index = 0
            device_generation = 1
            capturando = threading.Event()
            pausado = threading.Event()
            limiar = 400
            nivel_atual = 0
            ultimo_erro = None

            def __init__(self, **_kwargs):
                # primeira fala com o nome de ativação, depois uma fala qualquer (janela de 10 s)
                self.falas = iter(["Ei, Ultron, status", "e o volume?"])

            def calibrar(self):
                return None

            def escutar(self, **_kwargs):
                return next(self.falas, None)

        voz_falsa = types.ModuleType("voz")
        voz_falsa.Ouvido = OuvidoFalso
        voz_falsa.falar = lambda *_args, **_kwargs: None
        voz_falsa.parar_fala = lambda *_args, **_kwargs: None
        voz_falsa.falando = threading.Event()

        with patch.dict(sys.modules, {"voz": voz_falsa}):
            import main
            with patch.object(main, "responder", return_value="Tudo certo, senhor."), \
                 patch.object(main, "atalho_parada", create=True), \
                 patch.object(main.confirmacao, "criar_confirmador_voz", return_value=lambda *_a, **_k: True):
                parar = threading.Event()

                def estado(nome, erro=None):
                    if nome == "encerrado":
                        parar.set()

                def conversa(papel, texto, origem):
                    publicados.append((papel, texto, origem))
                    if papel == "assistant" and len(publicados) >= 4:
                        parar.set()     # duas trocas foram publicadas: fim do teste

                main.modo_voz(bandeja=False, entrada_teclado=False, stop_event=parar,
                              estado_voz=estado, conversa=conversa)

        self.assertIn(("user", "status", "voz"), publicados)
        self.assertIn(("assistant", "Tudo certo, senhor.", "voz"), publicados)


if __name__ == "__main__":
    unittest.main()
