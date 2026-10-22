"""Testes da FASE 1 (segurança). Rodar:  venv\\Scripts\\python testes_seguranca.py
Nada perigoso é executado de verdade: as ferramentas reais são trocadas por 'dublês' que só registram a chamada.
O autorizador, as classificações, a allowlist, as confirmações e os logs são os REAIS."""
import json
import os
import shutil
import threading
import time
import unittest
from pathlib import Path

import config
import confirmacao
import ferramentas
import seguranca
import teclado
import telegram_bot

RAIZ = Path.home() / f".ultron_teste_{os.getpid()}"
PERMITIDO = RAIZ / "permitido"
FORA = RAIZ / "fora"
CHAMADAS = []
ORIGINAIS = {}
ARQ_ORIGINAL = seguranca.ARQUIVO_PERMISSOES
FERRAMENTAS_FALSAS = ("controlar_midia", "abrir_programa", "fechar_aplicativo", "criar_pasta", "criar_arquivo", "apagar_arquivo",
                      "desligar_pc", "reiniciar_pc", "executar_comando", "pressionar_tecla",
                      "abrir_site", "ver_tela", "lembrar_fato")


def escrever_config(**mudancas):
    base = json.loads((Path(__file__).parent / "permissoes.json").read_text(encoding="utf-8"))
    base["allowlist"]["diretorios"] = [str(PERMITIDO)]
    for caminho, valor in mudancas.items():          # ex.: confirmacao__medio="nunca"
        d = base
        *ks, ultimo = caminho.split("__")
        for k in ks:
            d = d[k]
        d[ultimo] = valor
    arq = RAIZ / "permissoes_teste.json"
    arq.write_text(json.dumps(base), encoding="utf-8")
    seguranca.ARQUIVO_PERMISSOES = arq


def setUpModule():
    PERMITIDO.mkdir(parents=True)
    FORA.mkdir()
    for nome in FERRAMENTAS_FALSAS:
        ORIGINAIS[nome] = ferramentas.FERRAMENTAS[nome]["fn"]
        ferramentas.FERRAMENTAS[nome]["fn"] = (lambda n: lambda **k: (CHAMADAS.append((n, k)), "ok-dublê")[1])(nome)


def tearDownModule():
    seguranca.ARQUIVO_PERMISSOES = ARQ_ORIGINAL
    shutil.rmtree(RAIZ, ignore_errors=True)


class Conf:
    """Canal de confirmação de mentira: devolve a resposta combinada e registra se foi chamado."""
    def __init__(self, resp):
        self.resp, self.pedidos = resp, []

    def __call__(self, msg, pedido):
        self.pedidos.append(pedido)
        return self.resp


class Base(unittest.TestCase):
    def setUp(self):
        CHAMADAS.clear()
        escrever_config()
        config.PIN = ""

    def rodar(self, nome, args, conf, origem="teste"):
        return ferramentas.executar(nome, args, conf, origem)

    def executou(self, nome):
        return any(c[0] == nome for c in CHAMADAS)


class T01_a_03_BaixoRisco(Base):
    def test01_pausar_musica_sem_confirmacao(self):
        c = Conf(None)
        self.rodar("controlar_midia", {"acao": "pausar"}, c)
        self.assertTrue(self.executou("controlar_midia"))
        self.assertEqual(c.pedidos, [], "BAIXO não pode chamar o fluxo de confirmação")

    def test02_aumentar_volume_sem_confirmacao(self):
        c = Conf(None)
        self.rodar("controlar_midia", {"acao": "volume_mais"}, c)
        self.assertTrue(self.executou("controlar_midia"))
        self.assertEqual(c.pedidos, [])

    def test03_abrir_chrome_allowlist_sem_confirmacao(self):
        c = Conf(None)
        self.rodar("abrir_programa", {"nome": "Chrome"}, c)
        self.assertTrue(self.executou("abrir_programa"))
        self.assertEqual(c.pedidos, [])

    def test03a_fechar_aplicativo_exige_confirmacao(self):
        c = Conf(False)
        self.rodar("fechar_aplicativo", {"nome": "Chrome"}, c)
        self.assertEqual(len(c.pedidos), 1)
        self.assertEqual(c.pedidos[0]["risco"], "ALTO")
        self.assertFalse(self.executou("fechar_aplicativo"))

    def test03aa_correspondencia_de_app_usa_titulo_ou_nome_do_processo(self):
        self.assertTrue(ferramentas._corresponde_janela("Chrome", "Nova guia", "chrome.exe"))
        self.assertTrue(ferramentas._corresponde_janela("Calculadora", "Calculadora", "CalculatorApp.exe"))
        self.assertFalse(ferramentas._corresponde_janela("Edge", "Nova guia - Chrome", "chrome.exe"))

    def test03b_teclas_de_midia_baixo_e_perigosas_alto(self):
        c = Conf(None)
        self.rodar("pressionar_tecla", {"teclas": "playpause"}, c)
        self.assertTrue(self.executou("pressionar_tecla") and not c.pedidos)
        CHAMADAS.clear()
        c = Conf(False)
        self.rodar("pressionar_tecla", {"teclas": "alt+f4"}, c)
        self.assertEqual(len(c.pedidos), 1)
        self.assertEqual(c.pedidos[0]["risco"], "ALTO")
        self.assertFalse(self.executou("pressionar_tecla"))

    def test03c_alt_f4_nao_envia_atalho_a_janela_ativa(self):
        token = ferramentas._AUTORIZADO.set("pressionar_tecla")
        try:
            resultado = ORIGINAIS["pressionar_tecla"]("alt+f4")
        finally:
            ferramentas._AUTORIZADO.reset(token)
        self.assertIn("janela ativa", resultado)


class T04_Medio(Base):
    def test04_criar_pasta_na_allowlist_executa(self):
        c = Conf(None)
        self.rodar("criar_pasta", {"caminho": "teste"}, c)      # caminho relativo cai no diretório permitido
        self.assertTrue(self.executou("criar_pasta"))
        self.assertEqual(c.pedidos, [])

    def test04b_criar_pasta_fora_da_allowlist_pede_confirmacao(self):
        c = Conf(False)
        self.rodar("criar_pasta", {"caminho": str(FORA / "teste")}, c)
        self.assertEqual(len(c.pedidos), 1)
        self.assertFalse(self.executou("criar_pasta"))

    def test04c_operacao_fora_da_lista_de_operacoes_pede_confirmacao(self):
        escrever_config(allowlist__operacoes=[])
        c = Conf(True)
        self.rodar("criar_pasta", {"caminho": "teste"}, c)
        self.assertEqual(len(c.pedidos), 1)
        self.assertTrue(self.executou("criar_pasta"))

    def test04d_modo_nunca_nao_libera_fora_da_allowlist(self):
        escrever_config(confirmacao__medio="nunca")
        c = Conf(False)
        self.rodar("criar_pasta", {"caminho": str(FORA / "x")}, c)
        self.assertEqual(len(c.pedidos), 1)

    def test04e_area_protegida_e_negada_sempre(self):
        escrever_config(confirmacao__medio="nunca")
        c = Conf(True)
        r = self.rodar("criar_arquivo", {"caminho": str(seguranca.BASE / "x.txt"), "conteudo": "a"}, c)
        self.assertIn("NEGADA", r)
        self.assertFalse(self.executou("criar_arquivo"))
        self.assertEqual(c.pedidos, [])


class T05_a_07_AltoCritico(Base):
    def test05_apagar_pede_confirmacao(self):
        c = Conf(False)
        self.rodar("apagar_arquivo", {"caminho": str(PERMITIDO / "x.txt")}, c)
        self.assertEqual(c.pedidos[0]["risco"], "ALTO")
        self.assertFalse(self.executou("apagar_arquivo"))
        c = Conf(True)
        self.rodar("apagar_arquivo", {"caminho": str(PERMITIDO / "x.txt")}, c)
        self.assertTrue(self.executou("apagar_arquivo"))

    def test05b_apagar_fora_da_home_negado(self):
        r = self.rodar("apagar_arquivo", {"caminho": "/etc/passwd" if os.name != "nt" else "C:\\Windows\\x"}, Conf(True))
        self.assertIn("NEGADA", r)

    def test06_desligar_pede_confirmacao(self):
        c = Conf(False)
        self.rodar("desligar_pc", {}, c)
        self.assertEqual(c.pedidos[0]["risco"], "ALTO")
        self.assertFalse(self.executou("desligar_pc"))
        self.rodar("reiniciar_pc", {}, Conf(False))
        self.assertFalse(self.executou("reiniciar_pc"))

    def test06b_config_antiga_pedir_confirmacao_false_nao_libera_alto(self):
        arq = RAIZ / "antigo.json"
        arq.write_text(json.dumps({"programas": {}, "pastas": [str(PERMITIDO)], "pedir_confirmacao": False,
                                   "confirmacao": {"alto": False, "critico": False, "baixo": True}}), encoding="utf-8")
        seguranca.ARQUIVO_PERMISSOES = arq
        c = Conf(False)
        self.rodar("desligar_pc", {}, c)
        self.assertEqual(len(c.pedidos), 1)
        self.rodar("controlar_midia", {"acao": "pausar"}, c)
        self.assertEqual(len(c.pedidos), 1, "BAIXO nunca confirma, mesmo que o arquivo peça")

    def test07_powershell_e_negado_pela_protecao_critica(self):
        c = Conf(True)
        for cmd in ("powershell -Command Get-Process", "cmd /c dir", "format c:", "ipconfig & del x",
                    "C:\\temp\\ipconfig.exe", "del /s /q C:\\x"):
            r = self.rodar("executar_comando", {"comando": cmd}, c)
            self.assertIn("NEGADA", r, cmd)
        self.assertFalse(self.executou("executar_comando"))
        self.assertEqual(c.pedidos, [])

    def test07b_comando_da_allowlist_e_critico_e_exige_confirmacao(self):
        c = Conf(False)
        self.rodar("executar_comando", {"comando": "ipconfig /all"}, c)
        self.assertEqual(c.pedidos[0]["risco"], "CRITICO")
        self.assertFalse(self.executou("executar_comando"))
        self.rodar("executar_comando", {"comando": "ipconfig /all"}, Conf(True))
        self.assertTrue(self.executou("executar_comando"))

    def test07c_shell_arbitrario_so_com_config_explicita_e_ainda_confirma(self):
        escrever_config(criticas__permitir_shell_arbitrario=True)
        c = Conf(False)
        self.rodar("executar_comando", {"comando": "powershell -Command Get-Date"}, c)
        self.assertEqual(c.pedidos[0]["risco"], "CRITICO")
        self.assertFalse(self.executou("executar_comando"))
        r = self.rodar("executar_comando", {"comando": "format c:"}, Conf(True))   # padrões bloqueados valem sempre
        self.assertIn("NEGADA", r)

    def test07d_critico_exige_pin_quando_configurado(self):
        config.PIN = "4321"
        c = Conf(False)
        self.rodar("executar_comando", {"comando": "ping 8.8.8.8"}, c)
        self.assertTrue(c.pedidos[0]["exige_pin"])
        self.assertTrue(seguranca.pin_valido("4321") and not seguranca.pin_valido("0000") and not seguranca.pin_valido(""))


class T08_a_11_Confirmacao(Base):
    def test08_sem_resposta_cancela(self):
        self.rodar("desligar_pc", {}, Conf(None))
        self.assertFalse(self.executou("desligar_pc"))

    def test08b_erro_no_canal_cancela(self):
        def quebrado(msg, pedido):
            raise RuntimeError("microfone quebrou")
        self.rodar("desligar_pc", {}, quebrado)
        self.assertFalse(self.executou("desligar_pc"))

    def test09_sim_confirma(self):
        self.assertIs(seguranca.decisao(["sim"]), True)
        self.rodar("desligar_pc", {}, Conf(True))
        self.assertTrue(self.executou("desligar_pc"))

    def test10_variacoes_de_sim(self):
        for frase in ("sim", "SIM", "Confirmo.", "Confirmado.", "autorizo", "positivo", "sim, pode"):
            self.assertIs(seguranca.decisao([frase]), True, frase)

    def test10b_palavras_genericas_nao_confirmam(self):
        for frase in ("ok", "isso", "vai", "faz", "pode fazer", "claro", "confirma", "Confirma?"):
            self.assertIsNone(seguranca.decisao([frase]), frase)

    def test11_variacoes_de_nao(self):
        for frase in ("não", "cancela", "cancelar", "pare", "parar", "não faça", "deixa", "esquece", "não pode", "Não!"):
            self.assertIs(seguranca.decisao([frase]), False, frase)
        self.rodar("desligar_pc", {}, Conf(False))
        self.assertFalse(self.executou("desligar_pc"))

    def test11b_ausencia_ou_ruido_nunca_vira_sim(self):
        for alts in (None, [], [""], ["talvez"], ["hmm"]):
            self.assertIsNone(seguranca.decisao(alts))

    def test11c_alternativas_do_reconhecimento(self):
        self.assertIs(seguranca.decisao(["sin", "sim"]), True)


class FakeVoz:
    def __init__(self):
        self.falas = []

    def falar(self, texto, eco=0.5):
        self.falas.append(texto)


class FakeOuvido:
    def __init__(self, respostas):
        self.r = list(respostas)
        self.chamadas = 0

    def escutar(self, espera=60, curto=False):
        self.chamadas += 1
        return self.r.pop(0) if self.r else None


class T11d_CanalDeVoz(Base):
    def pedido(self, risco="ALTO"):
        return seguranca.novo_pedido("desligar_pc", {}, seguranca.Classificacao(risco, "x", True), "voz")

    def setUp(self):
        super().setUp()
        self._disp, self._tecla = teclado.disponivel, teclado.ler_tecla
        teclado.disponivel = lambda: False

    def tearDown(self):
        teclado.disponivel, teclado.ler_tecla = self._disp, self._tecla

    def test_sim_de_primeira(self):
        ouv, voz = FakeOuvido([["sim"]]), FakeVoz()
        self.assertIs(confirmacao.criar_confirmador_voz(ouv, voz)("Confirma?", self.pedido()), True)
        self.assertEqual(ouv.chamadas, 1)

    def test_tenta_de_novo_uma_vez(self):
        ouv, voz = FakeOuvido([None, ["sim"]]), FakeVoz()
        self.assertIs(confirmacao.criar_confirmador_voz(ouv, voz)("Confirma?", self.pedido()), True)
        self.assertEqual(ouv.chamadas, 2)
        self.assertTrue(any("Não entendi" in f for f in voz.falas))

    def test_sem_resposta_sem_teclado_cancela(self):
        ouv, voz = FakeOuvido([None, None]), FakeVoz()
        self.assertIsNone(confirmacao.criar_confirmador_voz(ouv, voz)("Confirma?", self.pedido()))
        self.assertTrue(any("cancelada" in f.lower() for f in voz.falas))

    def test_nao(self):
        self.assertIs(confirmacao.criar_confirmador_voz(FakeOuvido([["não"]]), FakeVoz())("?", self.pedido()), False)

    def test_fallback_por_teclado_s_n_esc(self):
        teclado.disponivel = lambda: True
        for tecla, esperado in (("s", True), ("n", False), ("\x1b", False), (None, None)):
            teclado.ler_tecla = lambda *a, t=tecla, **k: t
            ouv = FakeOuvido([None, None])
            r = confirmacao.criar_confirmador_voz(ouv, FakeVoz())("?", self.pedido())
            self.assertIs(r, esperado, repr(tecla))

    def test_pin_sem_teclado_nega(self):
        config.PIN = "1234"
        ped = self.pedido("CRITICO")
        self.assertTrue(ped["exige_pin"])
        self.assertIs(confirmacao.criar_confirmador_voz(FakeOuvido([["sim"]]), FakeVoz())("?", ped), False)


class T12_a_13_Telegram(Base):
    def setUp(self):
        super().setUp()
        self._uid = config.TELEGRAM_USER_ID
        config.TELEGRAM_USER_ID = 111

    def tearDown(self):
        config.TELEGRAM_USER_ID = self._uid

    def test12_comando_perigoso_pede_confirmacao_no_telegram_e_executa_se_autorizado(self):
        enviados = []

        def enviar(texto, cid):
            enviados.append((texto, cid))
            threading.Timer(0.1, lambda: telegram_bot.resolver(111, cid, "s")).start()

        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(enviar), "telegram")
        self.assertEqual(len(enviados), 1)
        self.assertIn("ALTO", enviados[0][0])
        self.assertTrue(self.executou("desligar_pc"))

    def test12b_cancelar_no_botao(self):
        def enviar(texto, cid):
            threading.Timer(0.1, lambda: telegram_bot.resolver(111, cid, "n")).start()
        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(enviar), "telegram")
        self.assertFalse(self.executou("desligar_pc"))

    def test13_confirmacao_de_usuario_nao_autorizado_e_negada(self):
        escrever_config(timeouts__confirmacao_telegram=1)
        resultados = []

        def enviar(texto, cid):
            resultados.append(telegram_bot.resolver(999, cid, "s"))     # outra pessoa clicando no botão
        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(enviar), "telegram")
        self.assertEqual(resultados, ["nao_autorizado"])
        self.assertFalse(self.executou("desligar_pc"))

    def test13b_confirmacao_antiga_nao_autoriza_acao_nova(self):
        ids = []

        def enviar(texto, cid):
            ids.append(cid)
            threading.Timer(0.1, lambda: telegram_bot.resolver(111, cid, "n")).start()
        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(enviar), "telegram")
        antigo = ids[0]
        self.assertEqual(telegram_bot.resolver(111, antigo, "s"), "expirado")        # reaproveitar o id antigo
        self.assertEqual(telegram_bot.resolver(111, "idinexistente", "s"), "expirado")
        escrever_config(timeouts__confirmacao_telegram=1)
        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(lambda t, c: None), "telegram")   # nova ação, ninguém clica
        self.assertFalse(self.executou("desligar_pc"))

    def test13c_expiracao(self):
        escrever_config(timeouts__confirmacao_telegram=1)
        t0 = time.time()
        self.rodar("desligar_pc", {}, telegram_bot.Confirmador(lambda t, c: None), "telegram")
        self.assertLess(time.time() - t0, 5)
        self.assertFalse(self.executou("desligar_pc"))


class T14_Bypass(Base):
    def test14_chamada_direta_sem_autorizador_e_bloqueada(self):
        for fn, args in ((ferramentas.executar_comando, ("ipconfig",)), (ferramentas.apagar_arquivo, ("x",)),
                         (ferramentas.desligar_pc, ()), (ferramentas.reiniciar_pc, ()),
                         (ferramentas.fechar_aplicativo, ("Chrome",)),
                         (ferramentas.pressionar_tecla, ("enter",)), (ferramentas.controlar_midia, ("pausar",))):
            with self.assertRaises(PermissionError):
                fn(*args)
        self.assertEqual(CHAMADAS, [])

    def test14b_ferramenta_inexistente(self):
        self.assertIn("desconhecida", self.rodar("formatar_disco", {}, Conf(True)))

    def test14c_argumentos_invalidos_nao_executam(self):
        r = self.rodar("apagar_arquivo", {}, Conf(True))
        self.assertIn("inválidos", r)
        self.assertFalse(self.executou("apagar_arquivo"))

    def test14d_todas_as_ferramentas_passam_pelo_portao(self):
        for nome, f in ferramentas.FERRAMENTAS.items():
            real = ORIGINAIS.get(nome, f["fn"])        # (alguns estão trocados por dublês nestes testes)
            self.assertTrue(hasattr(real, "__wrapped__"), f"{nome} não está protegida")


class T16_Correcoes_1_5_1(Base):
    def test16_site_simples_abre_sem_confirmar(self):
        c = Conf(None)
        self.rodar("abrir_site", {"url": "https://www.google.com"}, c)
        self.assertTrue(self.executou("abrir_site"))
        self.assertEqual(c.pedidos, [])

    def test16b_site_com_parametros_ou_longo_exige_confirmacao(self):
        for url in ("https://x.com/?d=segredo", "https://x.com/#a", "https://x.com/" + "a" * 120):
            CHAMADAS.clear()
            c = Conf(False)
            self.rodar("abrir_site", {"url": url}, c)
            self.assertEqual(len(c.pedidos), 1, url)
            self.assertFalse(self.executou("abrir_site"), url)
        c = Conf(True)
        self.rodar("abrir_site", {"url": "https://x.com/?q=1"}, c)
        self.assertTrue(self.executou("abrir_site"))

    def test16c_lembrar_fato_e_ver_tela_exigem_confirmacao(self):
        for nome, args in (("lembrar_fato", {"fato": "x"}), ("ver_tela", {})):
            CHAMADAS.clear()
            c = Conf(False)
            self.rodar(nome, args, c)
            self.assertEqual(len(c.pedidos), 1, nome)
            self.assertFalse(self.executou(nome), nome)
            c = Conf(True)
            self.rodar(nome, args, c)
            self.assertTrue(self.executou(nome), nome)

    def test16d_operacao_liberada_no_permissoes_json_nao_pergunta(self):
        escrever_config(allowlist__operacoes=["tela.ver"])
        c = Conf(None)
        self.rodar("ver_tela", {}, c)
        self.assertTrue(self.executou("ver_tela"))
        self.assertEqual(c.pedidos, [])

    def test16e_esquecer_fato_vazio_nao_apaga_tudo(self):
        import memoria
        memoria.salvar_fato("zz fato de teste")
        try:
            self.rodar("esquecer_fato", {"trecho": ""}, Conf(None))
            self.assertIn("zz fato de teste", memoria.listar_fatos())
        finally:
            memoria.apagar_fato("zz fato de teste")


class T15_Logs(Base):
    def ler(self, nome):
        for h in list(seguranca._log_seg.handlers) + list(seguranca.logging.root.handlers):
            h.flush()
        return (seguranca.BASE / "logs" / nome).read_text(encoding="utf-8")

    def test_formato_do_log_de_seguranca(self):
        self.rodar("controlar_midia", {"acao": "pausar"}, Conf(None), "voz")
        self.rodar("desligar_pc", {}, Conf(None), "telegram")
        self.rodar("executar_comando", {"comando": "powershell x"}, Conf(None), "voz")
        txt = self.ler("seguranca.log")
        for trecho in ("[SECURITY]", "origem=voz", "origem=telegram", "action=controlar_midia", "risk=BAIXO",
                       "decision=ALLOW", "reason=allowlisted_low_risk", "action=desligar_pc", "risk=ALTO",
                       "decision=CONFIRM", "reason=high_risk_action", "decision=CANCELLED", "risk=CRITICO",
                       "decision=DENY", "reason=not_allowlisted"):
            self.assertIn(trecho, txt, trecho)

    def test_segredos_nunca_aparecem_nos_logs(self):
        chave, pin = "gsk_TESTESEGREDO1234567890abc", "pin-super-secreto-77"
        config.CHAVES["groq"], config.PIN = chave, pin
        seguranca.log.warning(f"erro da API com a chave {chave} e pin {pin}")
        self.rodar("criar_arquivo", {"caminho": str(PERMITIDO / "a.txt"), "conteudo": f"senha {chave}"}, Conf(None))
        self.rodar("executar_comando", {"comando": f"ping {chave}"}, Conf(None))
        seguranca.log_seg("teste", "x", "BAIXO", "ALLOW", "t", {"api_key": chave, "token": "abc", "caminho": pin})
        for nome in ("ultron.log", "seguranca.log"):
            txt = self.ler(nome)
            self.assertNotIn(chave, txt)
            self.assertNotIn(pin, txt)
        config.CHAVES["groq"], config.PIN = "", ""


if __name__ == "__main__":
    unittest.main(verbosity=2)
