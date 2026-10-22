"""Voz: fala (edge-tts, voz grave) e escuta (microfone + reconhecimento do Google, grátis)."""
import asyncio
import collections
import glob
import os
import queue
import re
import tempfile
import threading
import time
import uuid

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import sounddevice as sd
import speech_recognition as sr

import config
import seguranca
from microphone_devices import resolve_input_device

_lock_fala = threading.RLock()
_parar = threading.Event()
falando = threading.Event()   # ligado enquanto o ULTRON está falando (a interface mostra no orbe)


def parar_fala():
    _parar.set()


def limpar(texto):
    texto = re.sub(r"https?://\S+", "", texto)
    texto = re.sub(r"[*#_`>~|]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


async def _sintetizar(texto, arquivo):
    import edge_tts
    await edge_tts.Communicate(texto, config.VOZ, rate=config.VOZ_RATE, pitch=config.VOZ_PITCH).save(arquivo)


def _tocar(arquivo):
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(arquivo)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy() and not _parar.is_set():
        time.sleep(0.05)
    pygame.mixer.music.stop()
    pygame.mixer.music.unload()
    try:
        os.remove(arquivo)
    except OSError:
        pass


def _falar_offline(texto):
    import pyttsx3
    motor = pyttsx3.init()
    for v in motor.getProperty("voices"):
        if "pt" in (v.id + v.name).lower() or "portug" in v.name.lower():
            motor.setProperty("voice", v.id)
            break
    motor.setProperty("rate", 165)
    motor.say(texto)
    motor.runAndWait()


def _frases(texto):
    """Divide em frases (juntando as muito curtas) para tocar a 1ª enquanto a 2ª ainda é gerada."""
    saida = []
    for p in re.split(r"(?<=[.!?])\s+", texto):
        if saida and len(saida[-1]) < 25:
            saida[-1] += " " + p
        else:
            saida.append(p)
    return saida


def falar(texto, eco=0.5):
    texto = limpar(texto)
    if not texto:
        return
    with _lock_fala:
        _parar.clear()
        t0 = time.perf_counter()
        frases = _frases(texto)
        base = os.path.join(tempfile.gettempdir(), f"ultron_{os.getpid()}_{uuid.uuid4().hex[:6]}")
        fila, parou = queue.Queue(), threading.Event()

        def produzir():
            for i, f in enumerate(frases):
                if parou.is_set() or _parar.is_set():
                    break
                arq = f"{base}_{i}.mp3"
                try:
                    asyncio.run(_sintetizar(f, arq))
                except Exception as e:
                    seguranca.log.warning(f"Voz online falhou ({e}); usando voz offline.")
                    fila.put((None, " ".join(frases[i:])))
                    return
                fila.put((arq, f))
            fila.put(None)

        threading.Thread(target=produzir, daemon=True).start()
        primeira = True
        try:
            while True:
                item = fila.get()
                if item is None:
                    break
                arq, resto = item
                if arq is None:
                    falando.set()
                    try:
                        _falar_offline(resto)
                    except Exception as e2:
                        seguranca.log.error(f"Voz offline falhou: {e2}")
                    break
                if primeira:
                    seguranca.log.info(f"[tempo] 1º áudio {time.perf_counter() - t0:.1f}s")
                    primeira = False
                    falando.set()
                _tocar(arq)
                if _parar.is_set():
                    break
        finally:
            falando.clear()
            parou.set()
            for sobra in glob.glob(base + "_*.mp3"):   # arquivos gerados mas não tocados (parada)
                try:
                    os.remove(sobra)
                except OSError:
                    pass
        time.sleep(eco)  # evita o microfone captar o eco


class Ouvido:
    FS = 16000

    def __init__(self, device_index=None, device_id=None):
        self.rec = sr.Recognizer()
        self.limiar = getattr(config, "LIMIAR_VOZ", 0) or 400.0
        self.pausado = None  # threading.Event: quando ligado, o microfone é liberado
        self.capturando = threading.Event()  # ligado somente enquanto InputStream está aberto
        self.ultimo_erro = None
        self.nivel_atual = 0.0
        self.device_index = device_index
        self.device_id = device_id
        self.device_generation = 0
        self.rec.operation_timeout = 15

    def set_device(self, device_index, device_id=None):
        self.device_index = device_index
        self.device_id = device_id
        self.device_generation += 1

    def _capture_device(self):
        if self.device_id is not None:
            index = resolve_input_device(self.device_id)
            if index is None:
                raise RuntimeError("O microfone selecionado foi desconectado. Escolha outra entrada de áudio.")
            self.device_index = index
        if self.device_index == -1:
            raise RuntimeError("O microfone selecionado não está disponível. Escolha outra entrada de áudio.")
        return self.device_index

    def calibrar(self):
        self.capturando.set()
        try:
            d = sd.rec(int(1.5 * self.FS), samplerate=self.FS, channels=1, dtype="int16",
                       device=self._capture_device())
            sd.wait()
        finally:
            self.capturando.clear()
        ambiente = float(np.sqrt(np.mean(d.astype(np.float32) ** 2)))
        self.limiar = getattr(config, "LIMIAR_VOZ", 0) or max(300.0, ambiente * 3)
        print(f"[mic] ruído ambiente {ambiente:.0f}, limiar {self.limiar:.0f}")

    def _gravar(self, espera, max_seg=15, silencio=None, min_voz=3, fator=1.0):
        silencio = getattr(config, "SILENCIO_FIM", 0.7) if silencio is None else silencio
        if self.pausado is not None and self.pausado.is_set():
            return None
        bloco = int(self.FS * 0.1)
        fila = queue.Queue()
        pre = collections.deque(maxlen=4)
        quadros, falou, sil, voz_n = [], False, 0.0, 0
        ini = ini_fala = time.time()

        def cb(indata, frames, tempo, status):
            fila.put(indata.copy())

        try:
            self.capturando.set()
            with sd.InputStream(samplerate=self.FS, channels=1, dtype="int16", blocksize=bloco,
                                device=self._capture_device(), callback=cb):
                while True:
                    if self.pausado is not None and self.pausado.is_set():
                        return None
                    try:
                        dados = fila.get(timeout=3)
                    except queue.Empty:
                        raise RuntimeError("o microfone parou de enviar áudio")
                    nivel = float(np.sqrt(np.mean(dados.astype(np.float32) ** 2)))
                    self.nivel_atual = nivel
                    agora = time.time()
                    if nivel > self.limiar * fator:
                        if not falou:
                            quadros, falou, ini_fala = list(pre), True, agora
                        sil, voz_n = 0.0, voz_n + 1
                        quadros.append(dados)
                    elif falou:
                        quadros.append(dados)
                        sil += 0.1
                        if sil >= silencio:
                            break
                    else:
                        pre.append(dados)
                        if agora - ini > espera:
                            return None
                    if falou and agora - ini_fala > max_seg:
                        break
        finally:
            self.capturando.clear()
        if voz_n < min_voz:
            return None
        return np.concatenate(quadros).tobytes()

    def escutar(self, espera=60, curto=False):
        """Espera você falar. Devolve o texto (None se nada foi entendido).
        curto=True: modo para respostas rápidas como 'sim'/'não'; devolve uma LISTA de interpretações."""
        if curto:
            pcm = self._gravar(espera, max_seg=5, silencio=0.7, min_voz=2, fator=0.8)
        else:
            pcm = self._gravar(espera)
        if not pcm:
            return None
        audio = sr.AudioData(pcm, self.FS, 2)
        t0 = time.perf_counter()
        try:
            if curto:
                r = self.rec.recognize_google(audio, language="pt-BR", show_all=True)
                alts = [a.get("transcript", "") for a in r.get("alternative", [])] if isinstance(r, dict) else []
                self.ultimo_erro = None
                return alts or None
            texto = self.rec.recognize_google(audio, language="pt-BR")
            self.ultimo_erro = None
            seguranca.log.info(f"[tempo] reconhecimento de voz {time.perf_counter() - t0:.1f}s")
            return texto
        except sr.UnknownValueError:
            self.ultimo_erro = None
            return None
        except sr.RequestError as e:
            self.ultimo_erro = f"Reconhecimento de voz indisponível: {e}"
            seguranca.log.warning(f"Reconhecimento de voz falhou: {e}")
            print("[voz] Falha no reconhecimento (internet?)")
            return None
