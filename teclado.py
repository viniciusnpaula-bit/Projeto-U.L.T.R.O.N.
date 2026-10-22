"""Teclado do console sem bloqueio e com timeout (Windows). Usado no fallback de confirmação, no PIN
e na digitação durante o modo voz. Em sistemas sem msvcrt (testes) cai para input()."""
import sys
import threading
import time

try:
    import msvcrt
except ImportError:           # Linux/Mac: só para testes
    msvcrt = None

_lock = threading.Lock()
_prioridade = threading.Event()   # confirmação/PIN têm prioridade sobre a digitação em segundo plano


def disponivel():
    """Existe um console interativo? (falso em modo bandeja/pythonw)"""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _char():
    return msvcrt.getwch() if msvcrt.kbhit() else None


def ler_tecla(prompt, validas, timeout):
    """Espera uma tecla de 'validas' (minúsculas; '\\x1b' = Esc). Devolve a tecla ou None se acabar o tempo."""
    if not disponivel():
        return None
    print(prompt, end="", flush=True)
    if msvcrt is None:
        r = input().strip().lower()[:1]
        return r if r in validas else None
    _prioridade.set()
    try:
        with _lock:
            fim = time.time() + timeout
            while time.time() < fim:
                c = _char()
                if c is None:
                    time.sleep(0.03)
                    continue
                if c in ("\x00", "\xe0"):      # tecla especial (setas...): descarta o segundo código
                    _char()
                    continue
                c = c.lower()
                if c in validas:
                    print("" if c == "\x1b" else c)
                    return c
            print()
            return None
    finally:
        _prioridade.clear()


def ler_linha(prompt, mascarar=False, timeout=30):
    """Lê uma linha (Enter confirma, Esc cancela). Devolve o texto ou None (timeout/cancelado)."""
    if not disponivel():
        return None
    print(prompt, end="", flush=True)
    if msvcrt is None:
        return input()
    _prioridade.set()
    try:
        with _lock:
            fim, buf = time.time() + timeout, []
            while time.time() < fim:
                c = _char()
                if c is None:
                    time.sleep(0.03)
                    continue
                if c in ("\x00", "\xe0"):
                    _char()
                elif c in ("\r", "\n"):
                    print()
                    return "".join(buf)
                elif c == "\x1b":
                    print()
                    return None
                elif c == "\b":
                    if buf:
                        buf.pop()
                        print("\b \b", end="", flush=True)
                elif c.isprintable():
                    buf.append(c)
                    print("*" if mascarar else c, end="", flush=True)
            print()
            return None
    finally:
        _prioridade.clear()


def loop_digitacao(callback):
    """Lê linhas digitadas em segundo plano sem competir com as confirmações."""
    if not disponivel():
        return
    if msvcrt is None:
        while True:
            try:
                t = input().strip()
            except Exception:
                return
            if t:
                callback(t)
    buf = []
    while True:
        if _prioridade.is_set() or not _lock.acquire(blocking=False):
            time.sleep(0.05)
            continue
        try:
            c = _char()
        finally:
            _lock.release()
        if c is None:
            time.sleep(0.03)
            continue
        if c in ("\x00", "\xe0"):
            _lock.acquire()
            try:
                _char()
            finally:
                _lock.release()
        elif c in ("\r", "\n"):
            print()
            texto, buf = "".join(buf).strip(), []
            if texto:
                callback(texto)
        elif c == "\b":
            if buf:
                buf.pop()
                print("\b \b", end="", flush=True)
        elif c.isprintable():
            buf.append(c)
            print(c, end="", flush=True)
