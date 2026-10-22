"""ULTRON - ponto de entrada.
   python main.py                  -> modo voz com janela
   python main.py --bandeja        -> modo voz em segundo plano, com ícone na bandeja (sem janela)
   python main.py --texto          -> só terminal
   python main.py --instalar-inicio / --remover-inicio   -> iniciar junto com o Windows
   python main.py --testar                               -> testes locais (roda pytest)"""
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import config

# Sem janela (pythonw) não existe saída de texto: manda tudo para um arquivo.
if sys.stdout is None or sys.stderr is None or "--bandeja" in sys.argv:
    sys.stdout = sys.stderr = open(config.BASE / "logs" / "console.log", "a", buffering=1, encoding="utf-8")

import cerebro
import confirmacao
import memoria
import seguranca
import teclado

WAKE = re.compile(r"(?:\b(?:ei|hey|oi|ouça|e aí)\b[\s,]*)?\b(ultr[oa]n|ultrom|ultra on|altron)\b[\s,.!?]*")
pausado = threading.Event()   # ligado = Ultron não escuta (microfone liberado)
_trava = None


# ---------- utilidades ----------
def responder(texto, confirmar, origem):
    resp = cerebro.processar(texto, confirmar, origem)
    print(f"Ultron: {resp}")
    return resp


def loop_lembretes():
    while True:
        try:
            for id_, texto in memoria.lembretes_vencidos():
                memoria.marcar_feito(id_)
                cerebro.notificar(f"Lembrete, {config.NOME}: {texto}")
        except Exception as e:
            seguranca.log.warning(f"Lembretes: {e}")
        time.sleep(5)


def atalho_parada():
    try:
        import keyboard
        keyboard.add_hotkey(config.HOTKEY_PARAR, seguranca.parar_tudo)
        print(f"[parada de emergência] atalho: {config.HOTKEY_PARAR}")
    except Exception as e:
        print(f"[aviso] atalho de parada indisponível: {e}")


def preparar_windows():
    """Evita que o Windows congele ou deixe o Ultron 'sonolento' quando ele está em segundo plano."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        # 1) Desliga o QuickEdit: clicar na janela preta congelava o programa até apertar Enter
        h = k.GetStdHandle(-10)
        modo = ctypes.c_uint()
        if k.GetConsoleMode(h, ctypes.byref(modo)):
            k.SetConsoleMode(h, (modo.value | 0x80) & ~0x40)

        # 2) Desliga o "modo eficiência" (economia de energia) para este processo
        class _Estado(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]
        estado = _Estado(1, 1, 0)
        k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(estado), ctypes.sizeof(estado))
    except Exception as e:
        seguranca.log.warning(f"preparar_windows: {e}")


def instancia_unica():
    global _trava
    _trava = socket.socket()
    try:
        _trava.bind(("127.0.0.1", 47653))
        return True
    except OSError:
        return False


def _arquivo_inicio():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Ultron.vbs"


def instalar_inicio():
    pyw = Path(sys.executable).with_name("pythonw.exe")
    base = Path(__file__).resolve().parent
    vbs = ('Set sh = CreateObject("WScript.Shell")\r\n'
           f'sh.CurrentDirectory = "{base}"\r\n'
           'WScript.Sleep 15000\r\n'
           f'sh.Run """{pyw}"" ""{base / "main.py"}"" --bandeja", 0, False\r\n')
    destino = _arquivo_inicio()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(vbs, encoding="utf-16")
    print(f"Pronto! O Ultron vai iniciar sozinho (em segundo plano) quando você entrar no Windows.\nArquivo: {destino}")


def remover_inicio():
    destino = _arquivo_inicio()
    if destino.exists():
        destino.unlink()
        print("Início automático removido.")
    else:
        print("O início automático não estava ativado.")


# ---------- modos ----------
def modo_texto():
    cerebro.NOTIFICADORES.append(lambda t: print(f"\nUltron: {t}"))
    print("Ultron em modo texto. Digite 'sair' para encerrar.")
    while True:
        try:
            t = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if t.lower() in ("sair", "exit"):
            return
        if t:
            responder(t, confirmacao.confirmar_terminal, "terminal")


def _reiniciar_audio():
    """Recarrega a lista de dispositivos de som (útil se o microfone mudou ou travou)."""
    try:
        import sounddevice as sd
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def modo_voz(bandeja=False, entrada_teclado=True, stop_event=None,
             ouvido_pronto: Callable[[object], None] | None = None,
             estado_voz: Callable[[str, str | None], None] | None = None,
             microphone_device_index=None, microphone_device_id=None,
             conversa: Callable[[str, str, str], None] | None = None):
    def publicar_estado(estado, erro=None):
        if estado_voz is not None:
            try:
                estado_voz(estado, erro)
            except Exception:
                pass

    def publicar_conversa(papel, texto):
        """Leva cada fala reconhecida e cada resposta ao painel (bat-papo de voz)."""
        if conversa is None or not texto:
            return
        try:
            conversa(str(papel)[:12], str(texto)[:4000], "voz")
        except Exception:
            pass

    import voz
    ouvido = voz.Ouvido(device_index=microphone_device_index, device_id=microphone_device_id)
    ouvido.pausado = pausado
    if ouvido_pronto is not None:
        ouvido_pronto(ouvido)
    seguranca.ganchos_parada.append(voz.parar_fala)
    cerebro.NOTIFICADORES.append(lambda t: (print(f"\nUltron: {t}"), voz.falar(t)))

    confirmar_voz = confirmacao.criar_confirmador_voz(ouvido, voz)

    def digitado(texto):
        publicar_conversa("user", texto)
        resposta = responder(texto, confirmacao.confirmar_terminal, "terminal")
        publicar_conversa("assistant", resposta)
        voz.falar(resposta)

    def loop():
        calibrado, falhas, janela, device_generation = False, 0, 0.0, -1   # janela: 10s sem precisar do nome após uma resposta
        pausado_reportado = False
        erro_audio = None
        while stop_event is None or not stop_event.is_set():
            if pausado.is_set():
                if not pausado_reportado:
                    publicar_estado("pausado")
                    pausado_reportado = True
                if stop_event is not None:
                    stop_event.wait(0.1)
                else:
                    time.sleep(0.1)
                continue
            pausado_reportado = False
            try:
                if ouvido.device_index == -1:
                    erro_audio = "O microfone selecionado não está disponível. Escolha uma entrada conectada."
                    publicar_estado("erro", erro_audio)
                    if stop_event is not None:
                        stop_event.wait(0.2)
                    else:
                        time.sleep(0.2)
                    continue
                if device_generation != ouvido.device_generation:
                    calibrado = False
                    device_generation = ouvido.device_generation
                if not calibrado:
                    if erro_audio is None:
                        publicar_estado("calibrando")
                    ouvido.calibrar()
                    calibrado = True
                    erro_audio = None
                    voz.falar(f"Ultron online. À sua disposição, {config.NOME}.")
                    print("Diga 'Ei, Ultron' seguido do comando.")
                if erro_audio is None:
                    publicar_estado("ouvindo")
                texto = ouvido.escutar()
                erro_reconhecimento = getattr(ouvido, "ultimo_erro", None)
                if erro_reconhecimento:
                    erro_audio = str(erro_reconhecimento)[:180]
                    publicar_estado("erro", erro_audio)
                else:
                    erro_audio = None
                    publicar_estado("ouvindo")
                falhas = 0
            except Exception as e:
                if stop_event is not None and stop_event.is_set():
                    break
                falhas += 1
                erro_audio = str(e)[:180]
                seguranca.log.error(f"Microfone/escuta (falha {falhas}): {e}")
                print(f"[erro de microfone] {e} - tentando de novo...")
                publicar_estado("erro", erro_audio)
                _reiniciar_audio()
                time.sleep(min(3 * falhas, 20))
                continue
            if not texto or pausado.is_set():
                continue
            m = WAKE.search(texto.lower())
            if m:
                cmd = texto[m.end():].strip()
                if not cmd:
                    voz.falar("Pois não?")
                    cmd = ouvido.escutar(espera=8)
                    if not cmd:
                        continue
            elif time.time() < janela:
                cmd = texto
            else:
                continue
            try:
                publicar_conversa("user", cmd)
                publicar_estado("processando")
                t_ia = time.perf_counter()
                resposta = responder(cmd, confirmar_voz, "voz")
                seguranca.log.info(f"[tempo] IA {time.perf_counter() - t_ia:.1f}s")
                publicar_conversa("assistant", resposta)
                voz.falar(resposta)
            except Exception as e:
                seguranca.log.error(f"Erro ao responder: {e}")
            publicar_estado("ouvindo")
            janela = time.time() + 10
        publicar_estado("encerrado")

    if not bandeja:
        if entrada_teclado:
            threading.Thread(target=teclado.loop_digitacao, args=(digitado,), daemon=True).start()
        loop()
        return
    threading.Thread(target=loop, daemon=True).start()
    try:
        import bandeja
        bandeja.executar(pausado)       # bloqueia até escolher "Sair"
    except Exception as e:
        seguranca.log.error(f"Bandeja indisponível ({e}); rodando sem ícone.")
        while True:
            time.sleep(3600)


def rodar_testes():
    """Roda a suíte de testes localmente. Mantido fora do modo vivo para não iniciar o núcleo."""
    import shutil
    pytest = shutil.which("pytest") or str(Path(sys.executable).with_name("pytest.exe"))
    if not Path(pytest).is_file() and not shutil.which("pytest"):
        print("pytest não está instalado no ambiente. Instale com: pip install pytest")
        return 1
    return subprocess.call([str(sys.executable), "-m", "pytest", str(config.BASE / "tests"), "-q",
                            *[arg for arg in sys.argv[1:] if not arg.startswith("--testar")]])


if __name__ == "__main__":
    if "--testar" in sys.argv:
        sys.exit(rodar_testes())
    if "--instalar-inicio" in sys.argv:
        instalar_inicio()
        sys.exit(0)
    if "--remover-inicio" in sys.argv:
        remover_inicio()
        sys.exit(0)
    if not any(config.CHAVES.get(p) for p in config.PROVEDORES):
        print("Nenhuma chave de API no arquivo .env. Rode ULTRON-Setup.exe ou edite o .env.")
        sys.exit(1)
    somente_texto = "--texto" in sys.argv
    if not somente_texto and not instancia_unica():
        print("O Ultron já está rodando (veja o ícone perto do relógio).")
        sys.exit(0)
    preparar_windows()
    threading.Thread(target=loop_lembretes, daemon=True).start()
    atalho_parada()
    import telegram_bot
    if telegram_bot.iniciar():
        print("[telegram] bot ativo")
    try:
        if somente_texto:
            modo_texto()
        else:
            modo_voz(bandeja="--bandeja" in sys.argv)
    except KeyboardInterrupt:
        pass
    print("Ultron encerrado.")
    os._exit(0)
