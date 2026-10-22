import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cerebro
import main


class GameActionTests(unittest.TestCase):
    def test_voice_phrases_resolve_to_the_three_deterministic_actions(self):
        self.assertEqual(cerebro._acao_rapida("Ei, Ultron, abra o Rocket League"), "rocket")
        self.assertEqual(cerebro._acao_rapida("Ative o modo jogo"), "modo_jogo")
        self.assertEqual(cerebro._acao_rapida("Minimize todas as janelas"), "minimizar")
        self.assertEqual(cerebro._acao_rapida("Jogue Rocket League"), "rocket")
        self.assertEqual(cerebro._acao_rapida("Minimiza tudo"), "minimizar")

    def test_voice_wake_phrase_leaves_game_mode_command_intact(self):
        utterance = "Ei, Ultron, ative o modo jogo"
        match = main.WAKE.search(utterance.lower())
        self.assertIsNotNone(match)
        command = utterance[match.end():].strip()
        self.assertEqual(command, "ative o modo jogo")
        self.assertEqual(cerebro._acao_rapida(command), "modo_jogo")
        with patch.object(main.cerebro, "processar", return_value="feito") as processar, \
             patch("builtins.print"):
            main.responder(command, None, "voz")
        processar.assert_called_once_with("ative o modo jogo", None, "voz")

    def test_game_mode_runs_tools_in_order_and_stops_on_first_failure(self):
        execute = Mock(side_effect=["Abrindo Rocket League.", "Abrindo Spotify.", "Minimizei 3 janela(s) visível(is)."])
        result = cerebro._executar_acao_rapida("modo_jogo", execute, None, "desktop")
        self.assertEqual([call.args[0] for call in execute.call_args_list],
                         ["abrir_programa", "abrir_programa", "minimizar_janelas"])
        self.assertIn("Modo jogo ativado", result)

        execute = Mock(return_value="Não encontrei 'Rocket League'.")
        result = cerebro._executar_acao_rapida("modo_jogo", execute, None, "desktop")
        self.assertEqual(execute.call_count, 1)
        self.assertIn("Rocket League", result)

    def test_game_mode_does_not_minimize_when_spotify_fails(self):
        execute = Mock(side_effect=["Abrindo Rocket League.", "Falha ao abrir Spotify."])
        result = cerebro._executar_acao_rapida("modo_jogo", execute, None, "desktop")
        self.assertEqual([call.args[0] for call in execute.call_args_list],
                         ["abrir_programa", "abrir_programa"])
        self.assertIn("Spotify", result)

    def test_game_mode_reports_minimization_failure_after_both_apps_start(self):
        execute = Mock(side_effect=["Abrindo Rocket League.", "Abrindo Spotify.", "Falha ao minimizar."])
        result = cerebro._executar_acao_rapida("modo_jogo", execute, None, "desktop")
        self.assertEqual(execute.call_count, 3)
        self.assertIn("minimizar", result)

    def test_quick_actions_dispatch_before_the_ai_model(self):
        with patch.object(cerebro, "_executar_acao_rapida", return_value="feito") as action, \
             patch.object(cerebro, "_loop", side_effect=AssertionError("modelo chamado")), \
             patch.object(cerebro.memoria, "salvar_msg"):
            self.assertEqual(cerebro.processar("Ei, Ultron, ative o modo jogo", None, "voz"), "feito")
        action.assert_called_once_with("modo_jogo", cerebro.ferramentas.executar, None, "voz")

    def test_desktop_buttons_submit_commands_recognized_by_the_same_backend(self):
        html = (Path(__file__).resolve().parents[1] / "electron" / "site" / "index.html").read_text(encoding="utf-8")
        app = (Path(__file__).resolve().parents[1] / "electron" / "site" / "app.js").read_text(encoding="utf-8")
        # A interface 2.0 tem uma única tela: os verbos ficam na câmara (nav.verbs),
        # e o mesmo backend reconhece os comandos.
        self.assertIn('class="verbs"', html)
        self.assertIn("document.querySelectorAll('[data-command]')", app)
        self.assertIn("send(button.dataset.command)", app)
        verbs = html.split('class="verbs"', 1)[1].split("</nav>", 1)[0]
        for label, command in (("Abrir Rocket League", "Abra o Rocket League"),
                               ("Modo jogo", "Ative o modo jogo"),
                               ("Minimizar tudo", "Minimize tudo")):
            self.assertIn(f'data-command="{command}"', verbs)
            self.assertIn(label, verbs)

    def test_hud_keeps_live_actions_and_removes_placeholder_dashboard_cards(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "electron" / "site" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("core-emblem", html)
        self.assertNotIn("capability-grid", html)
        # uma linha de comando só, um botão de microfone só, métricas reais no topo
        self.assertIn('id="commandInput"', html)
        self.assertIn('id="micButton"', html)
        self.assertIn('id="cpuVal"', html)
        self.assertIn('data-command="Ative o modo jogo"', html)
        self.assertNotIn('id="chatInput"', html)  # a interface antiga tinha um segundo campo
        self.assertNotIn('class="sidebar"', html)  # e uma barra lateral

    def test_hud_places_only_real_metrics_in_the_top_strip(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "electron" / "site" / "index.html").read_text(encoding="utf-8")
        strip = html.split('class="signals"', 1)[1].split("</header>", 1)[0]
        for metric in ("cpuVal", "ramVal", "diskVal"):
            self.assertIn(f'id="{metric}"', strip)
        self.assertIn('id="sessionCount"', html)
        for unsupported in ("VRAM", "Agentes Ativos", "Taxa de Tokens", "Latência do Sistema"):
            self.assertNotIn(unsupported, html)

    def test_hud_theme_picker_uses_local_palette_setting(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "electron" / "site" / "index.html").read_text(encoding="utf-8")
        app = (root / "electron" / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="themeSwatches"', html)
        for theme in ("ultron", "jarvis", "amber", "emerald"):
            self.assertIn(f'data-theme="{theme}"', html)
        self.assertIn("localStorage.getItem('ultron-theme')", app)
        self.assertIn("document.documentElement.dataset.theme", app)

    def test_product_version_is_consistent(self):
        root = Path(__file__).resolve().parents[1]
        product_files = (
            root / "electron" / "package.json", root / "electron" / "package-lock.json",
            root / "electron" / "preload.js", root / "electron" / "mini-preload.js",
            root / "desktop_api.py", root / "electron" / "site" / "index.html",
            root / "LEIA-ME.txt", root / "electron" / "README.md", root / "NOTAS-RECONSTRUCAO.txt",
        )
        for path in product_files:
            self.assertIn("1.9.4", path.read_text(encoding="utf-8"), str(path))
        self.assertIn('"version"]', (root / "tools" / "build_setup.py").read_text(encoding="utf-8"))
        self.assertIn("ULTRON-Desktop-v", (root / "tools" / "build_setup.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
