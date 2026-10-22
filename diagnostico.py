"""Verificações locais sem executar comandos do usuário ou consultar serviços externos."""
import ast
import importlib.util
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _executar(nome, verificacao):
    try:
        return nome, True, verificacao()
    except Exception as erro:
        return nome, False, f"Verificação indisponível ({type(erro).__name__})."


def _python():
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 ou superior necessário.")
    return f"Python {sys.version_info.major}.{sys.version_info.minor} disponível."


def _dependencias():
    modulos = {
        "python-dotenv": "dotenv", "openai": "openai", "requests": "requests",
        "feedparser": "feedparser", "ddgs": "ddgs", "edge-tts": "edge_tts",
        "pygame-ce": "pygame", "pyttsx3": "pyttsx3", "SpeechRecognition": "speech_recognition",
        "sounddevice": "sounddevice", "numpy": "numpy", "pyautogui": "pyautogui",
        "pyperclip": "pyperclip", "psutil": "psutil", "send2trash": "send2trash",
        "keyboard": "keyboard", "python-telegram-bot": "telegram", "pillow": "PIL",
        "pystray": "pystray",
    }
    ausentes = []
    for pacote, modulo in modulos.items():
        try:
            disponivel = modulo in sys.modules or importlib.util.find_spec(modulo) is not None
        except (ImportError, ValueError):
            disponivel = False
        if not disponivel:
            ausentes.append(pacote)
    if ausentes:
        raise RuntimeError("Dependências ausentes: " + ", ".join(ausentes))
    return f"{len(modulos)} dependências verificadas sem importá-las ou chamar serviços."


def _configuracao():
    chaves = ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY")
    valores = {nome: os.environ.get(nome, "") for nome in chaves}
    arquivo = BASE / ".env"
    if arquivo.is_file():
        from dotenv import dotenv_values
        valores.update({nome: valor or "" for nome, valor in dotenv_values(arquivo).items() if nome in chaves})
    quantidade = sum(bool(valores.get(nome)) for nome in chaves)
    if not quantidade:
        raise RuntimeError("Nenhuma chave de provedor configurada; valores nunca são exibidos.")
    return f"{quantidade} provedor(es) configurado(s); valores ocultos e sem teste de rede."


def _ferramentas():
    arquivo = BASE / "ferramentas.py"
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    nomes = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "ferramenta"
               for d in no.decorator_list):
            nomes.append(no.name)
    if not nomes:
        raise RuntimeError("Nenhuma ferramenta declarada no registro.")
    return f"{len(nomes)} ferramenta(s) declarada(s); nenhuma foi executada."


def _api_local():
    import desktop_api
    from desktop_runtime import DesktopRuntime
    if not callable(desktop_api.create_server) or not callable(DesktopRuntime):
        raise RuntimeError("Módulos locais incompletos.")
    return "API autenticada e runtime carregáveis; nenhum servidor foi iniciado."


def _audio():
    import sounddevice as audio
    dispositivos = audio.query_devices()
    entradas = sum(int(item.get("max_input_channels", 0)) > 0 for item in dispositivos)
    saidas = sum(int(item.get("max_output_channels", 0)) > 0 for item in dispositivos)
    if not entradas:
        raise RuntimeError("Nenhuma entrada de áudio detectada.")
    if not saidas:
        raise RuntimeError("Nenhuma saída de áudio detectada.")
    return f"{entradas} entrada(s) e {saidas} saída(s) detectadas; sem gravar ou reproduzir áudio."


def _voz():
    disponiveis = []
    for modulo, nome in (("edge_tts", "voz online"), ("pyttsx3", "voz local"), ("speech_recognition", "reconhecimento")):
        try:
            if importlib.util.find_spec(modulo) is not None:
                disponiveis.append(nome)
        except (ImportError, ValueError):
            pass
    if not disponiveis:
        raise RuntimeError("Nenhum mecanismo de voz instalado.")
    return "Mecanismos instalados: " + ", ".join(disponiveis) + "; sem falar ou enviar áudio."


def _inicializacao():
    arquivos = (
        "desktop.py", "desktop_api.py", "desktop_runtime.py", "main.py", "cerebro.py",
        "ferramentas.py", "seguranca.py", "electron/package.json", "electron/main.js",
        "electron/preload.js", "electron/site/index.html",
    )
    ausentes = [nome for nome in arquivos if not (BASE / nome).is_file()]
    if ausentes:
        raise RuntimeError("Arquivos de inicialização ausentes: " + ", ".join(ausentes))
    return f"{len(arquivos)} arquivos de inicialização encontrados."


def diagnosticar():
    """Retorna verificações de configuração e disponibilidade sem ações externas."""
    verificacoes = (
        ("Python", _python), ("Dependências", _dependencias), ("Configuração", _configuracao),
        ("Registro de ferramentas", _ferramentas), ("API local", _api_local),
        ("Microfone e saída de áudio", _audio), ("Recursos de voz", _voz),
        ("Inicialização", _inicializacao),
    )
    return [_executar(nome, verificar) for nome, verificar in verificacoes]


def main():
    for nome, ok, detalhe in diagnosticar():
        print(f"[{'OK' if ok else 'ATENÇÃO'}] {nome}: {detalhe}")
    print("Diagnóstico local concluído. Nenhuma rede, captura, fala ou ação em aplicativos foi executada.")


if __name__ == "__main__":
    main()
