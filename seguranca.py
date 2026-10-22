"""Segurança do Ultron: níveis de risco, allowlist, autorizador central, confirmações e logs de segurança.

Fluxo (ferramentas.executar é o único portão):
  ferramenta -> classificação (risco + operação + alvo) -> autorizar() -> ALLOW | CONFIRM | DENY -> log -> execução
"""
import copy
import hmac
import json
import logging
import re
import subprocess
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass

import config
from config import BASE

# ====================== LOGS (com redação de segredos) ======================
_SEGREDOS = re.compile(r"(?:gsk_|AIza|sk-|ghp_|xox[bap]-)[A-Za-z0-9_\-]{8,}|\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b")


def redigir(texto):
    """Troca por *** qualquer chave de API, token ou PIN que apareça em um texto."""
    t = str(texto)
    for s in (*config.CHAVES.values(), config.TELEGRAM_TOKEN, config.PIN):
        if s and len(s) >= 4:
            t = t.replace(s, "***")
    return _SEGREDOS.sub("***", t)


class _Redator(logging.Filter):
    def filter(self, record):
        try:
            record.msg = redigir(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


logging.basicConfig(
    filename=str(BASE / "logs" / "ultron.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)
for _h in logging.root.handlers:
    _h.addFilter(_Redator())
log = logging.getLogger("ultron")

_log_seg = logging.getLogger("ultron.seguranca")
_log_seg.setLevel(logging.INFO)
_hseg = logging.FileHandler(str(BASE / "logs" / "seguranca.log"), encoding="utf-8")
_hseg.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_hseg.addFilter(_Redator())
_log_seg.addHandler(_hseg)

_SENSIVEIS = re.compile(r"(key|token|senha|password|pin|secret|segredo)", re.I)
_SO_TAMANHO = {"texto", "conteudo", "consulta", "busca", "url", "caminho", "nome", "cidade", "tema", "pergunta", "comando", "fato", "trecho", "origem", "destino"}  # conteúdo livre: só registra o tamanho


def sanitizar_args(args):
    saida = {}
    for k, v in (args or {}).items():
        if _SENSIVEIS.search(str(k)):
            saida[k] = "***"
        elif k in _SO_TAMANHO:
            saida[k] = f"<{len(str(v))} caracteres>"
        else:
            saida[k] = redigir(str(v))[:120]
    return saida


def log_seg(origem, acao, risco, decisao, motivo, args=None, resultado=None):
    usuario = config.TELEGRAM_USER_ID if origem == "telegram" else "local"
    partes = [f"[SECURITY] origem={origem}", f"usuario={usuario}", f"action={acao}", f"risk={risco}",
              f"decision={decisao}", f"reason={motivo}"]
    if args is not None:
        partes.append("args=" + json.dumps(sanitizar_args(args), ensure_ascii=False))
    if resultado:
        partes.append(f"result={resultado}")
    _log_seg.info(" ".join(partes))


_RASTREIO_ORIGENS = {"voz", "desktop", "telegram", "terminal", "chat", "hud", "desconhecida"}
_RASTREIO_EVENTOS = {"intent_selected", "tool_selected", "tool_finished", "step_started", "step_finished"}
_RASTREIO_ACOES = {
    "rocket", "modo_jogo", "minimizar", "hora", "spotify", "conversa",
    "clima", "noticias", "pesquisar_web", "youtube", "abrir_site", "fechar_aplicativo",
    "abrir_programa", "listar_jogos", "minimizar_janelas", "listar_pasta", "ler_arquivo",
    "criar_arquivo", "criar_pasta", "mover_arquivo", "procurar_arquivo", "apagar_arquivo",
    "digitar_texto", "pressionar_tecla", "clicar", "ver_tela", "ajustar_volume",
    "controlar_midia", "info_sistema", "bloquear_tela", "executar_comando", "desligar_pc",
    "reiniciar_pc", "cancelar_desligamento", "lembrar_fato", "esquecer_fato",
    "criar_lembrete", "listar_lembretes",
}
_RASTREIO_ETAPAS = {"-", "intent", "tool_call", "rocket_league", "spotify", "minimizar_janelas"}
_RASTREIO_ESTADOS = {"selected", "started", "success", "failure", "denied", "cancelled", "returned"}


def log_rastreamento(origem, evento, acao, etapa="", estado=""):
    """Registra somente rótulos internos permitidos; nunca recebe ou guarda a fala do usuário."""
    def validar(valor, permitidos):
        if valor == "" and "-" in permitidos:
            return "-"
        return valor if isinstance(valor, str) and valor in permitidos else "omitido"

    log.info("[TRACE] origem=%s evento=%s acao=%s etapa=%s estado=%s",
             validar(origem, _RASTREIO_ORIGENS), validar(evento, _RASTREIO_EVENTOS),
             validar(acao, _RASTREIO_ACOES), validar(etapa, _RASTREIO_ETAPAS),
             validar(estado, _RASTREIO_ESTADOS))


# ====================== PARADA DE EMERGÊNCIA ======================
parada = threading.Event()   # ligado = tudo deve parar
ganchos_parada = []          # funções chamadas na parada (ex: calar a voz)

FRASES_PARADA = {"para", "parar", "pare", "parar tudo", "para tudo", "pare tudo",
                 "cala a boca", "cancela tudo", "cancelar tudo", "chega"}


def normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def eh_parada(texto):
    n = re.sub(r"[^\w\s]", "", normalizar(texto)).replace("ultron", "").strip()
    return n in FRASES_PARADA


def parar_tudo():
    parada.set()
    for g in ganchos_parada:
        try:
            g()
        except Exception:
            pass
    try:
        subprocess.run(["shutdown", "/a"], capture_output=True)  # cancela desligamento agendado
    except Exception:
        pass
    log_seg("local", "parar_tudo", "-", "ALLOW", "emergency_stop")


# ====================== NÍVEIS DE RISCO E CLASSIFICAÇÃO ======================
BAIXO, MEDIO, ALTO, CRITICO = "BAIXO", "MEDIO", "ALTO", "CRITICO"
ALLOW, DENY, CONFIRM = "ALLOW", "DENY", "CONFIRM"


@dataclass
class Classificacao:
    risco: str
    operacao: str = ""          # ex.: "arquivo.criar" (é o que a allowlist autoriza)
    na_allowlist: bool = True   # o alvo (pasta, programa...) está autorizado?
    negar: str = ""             # se preenchido: DENY imediato com este motivo
    resumo: str = ""            # frase humana para a pergunta de confirmação


# ====================== PERMISSÕES / ALLOWLIST ======================
ARQUIVO_PERMISSOES = BASE / "permissoes.json"

_PADRAO = {
    "confirmacao": {"baixo": False, "medio": "fora_da_allowlist", "alto": True, "critico": True},
    "timeouts": {"confirmacao_voz": 6, "confirmacao_teclado": 20, "confirmacao_telegram": 60},
    "allowlist": {
        "programas": {},
        "aceitar_apps_instalados": True,
        "diretorios": [],
        "operacoes": ["arquivo.criar", "pasta.criar", "arquivo.mover"],
        "teclas_seguras": ["playpause", "nexttrack", "prevtrack", "volumemute", "volumeup", "volumedown",
                           "up", "down", "left", "right", "pageup", "pagedown", "home", "end", "esc"],
        "comandos": ["ipconfig", "ping", "tasklist", "systeminfo", "whoami", "hostname",
                     "nslookup", "tracert", "netstat", "where"],
    },
    "criticas": {"permitir_shell_arbitrario": False},
}


def _fundir(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fundir(base[k], v)
        else:
            base[k] = v


def permissoes():
    """Lê o permissoes.json a cada chamada (você pode editar com o Ultron ligado). Aceita o formato antigo."""
    try:
        dados = json.loads(ARQUIVO_PERMISSOES.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"permissoes.json ilegível ({e}); usando padrões restritivos")
        dados = {}
    cfg = copy.deepcopy(_PADRAO)
    al = cfg["allowlist"]
    if "programas" in dados:                      # formato antigo
        al["programas"] = dados["programas"]
    if "pastas" in dados:
        al["diretorios"] = dados["pastas"]
    if dados.get("input_livre"):
        al["operacoes"] = al["operacoes"] + ["input.digitar", "input.tecla", "input.clicar"]
    _fundir(cfg, {k: v for k, v in dados.items() if k in ("confirmacao", "timeouts", "allowlist", "criticas")})
    # pisos de segurança: o arquivo NÃO consegue afrouxar estes três
    cfg["confirmacao"].update(baixo=False, alto=True, critico=True)
    return cfg


def allowlist(chave, padrao=None):
    return permissoes()["allowlist"].get(chave, padrao)


def timeout(nome):
    return permissoes()["timeouts"].get(nome, 60)


def permitir_shell_arbitrario():
    return bool(permissoes()["criticas"].get("permitir_shell_arbitrario", False))


# ====================== AUTORIZADOR CENTRAL ======================
def autorizar(cls):
    """Decide ALLOW / CONFIRM / DENY para uma ação já classificada. Devolve (decisão, motivo)."""
    if cls.negar:
        return DENY, cls.negar
    if cls.risco == BAIXO:
        return ALLOW, "allowlisted_low_risk"
    if cls.risco == MEDIO:
        cfg = permissoes()
        modo = str(cfg["confirmacao"].get("medio", "fora_da_allowlist")).lower()
        if modo == "sempre":
            return CONFIRM, "medium_risk_config_always_confirm"
        if modo == "nunca" and cls.na_allowlist:
            return ALLOW, "medium_risk_confirmation_disabled_by_config"
        if modo != "nunca" and cls.na_allowlist and cls.operacao in cfg["allowlist"]["operacoes"]:
            return ALLOW, "medium_risk_operation_allowlisted"
        return CONFIRM, "medium_risk_not_allowlisted"
    if cls.risco == ALTO:
        return CONFIRM, "high_risk_action"
    if cls.risco == CRITICO:
        return CONFIRM, "critical_risk_action"
    return DENY, "unknown_risk_level"


def pin_valido(texto):
    return bool(config.PIN) and hmac.compare_digest(str(texto).strip().encode(), config.PIN.encode())


def novo_pedido(ferramenta, args, cls, origem):
    """Cria um pedido de confirmação único (id, expiração) para ser aprovado em um canal."""
    agora = time.time()
    valores = ", ".join(str(v) for v in (args or {}).values())[:90]
    resumo = cls.resumo or (f"executar {ferramenta.replace('_', ' ')}" + (f" com {valores}" if valores else ""))
    aviso = {ALTO: "Ação de risco alto. ", CRITICO: "Ação de risco crítico. "}.get(cls.risco, "")
    return {"id": uuid.uuid4().hex[:8], "acao": ferramenta, "risco": cls.risco, "origem": origem,
            "args": sanitizar_args(args), "ts": agora, "expira": agora + timeout("confirmacao_telegram"),
            "exige_pin": cls.risco == CRITICO and bool(config.PIN),
            "mensagem": f"{aviso}Posso {resumo}? Confirma?"}


def pedir_confirmacao(confirmar, pedido):
    """Pergunta ao usuário pelo canal. SÓ devolve True se o canal respondeu True; qualquer falha cancela."""
    log_seg(pedido["origem"], pedido["acao"], pedido["risco"], "CONFIRM_REQUESTED", f"id={pedido['id']}")
    try:
        r = confirmar(pedido["mensagem"], pedido)
    except Exception as e:
        log.warning(f"Falha no canal de confirmação: {e}")
        r = None
    if r is True:
        log_seg(pedido["origem"], pedido["acao"], pedido["risco"], "CONFIRMED", "user_confirmed")
        return True
    log_seg(pedido["origem"], pedido["acao"], pedido["risco"], "CANCELLED",
            "user_denied" if r is False else "no_response_or_channel_error")
    return False


# ====================== COMANDOS (defesa em profundidade) ======================
BLOQUEADOS = [
    r"\bformat\b", r"rm\s+-rf", r"\bdel\b.*(/s|/q)", r"\brd\s+/s", r"\brmdir\s+/s",
    r"system32", r"\breg\s+(delete|add)", r"\bdiskpart\b", r"\bbcdedit\b",
    r"remove-item.*-recurse", r"\bcipher\s+/w", r"vssadmin", r"\bnet\s+user",
    r"\\windows\\", r"\btakeown\b", r"\bicacls\b",
]


def comando_bloqueado(cmd):
    c = cmd.lower()
    return any(re.search(p, c) for p in BLOQUEADOS)


# ====================== INTERPRETAÇÃO LOCAL DE SIM / NÃO ======================
SIM = {"sim", "sin", "cim", "confirmo", "confirmado", "autorizo", "autorizado", "positivo"}
# De propósito curto: "ok", "isso", "vai", "faz", "pode" e "confirma" (eco da própria pergunta) saíam de TV/ruído.
NAO = {"nao", "nem", "cancela", "cancelar", "cancelado", "negativo", "pare", "parar", "deixa", "esquece", "jamais"}


def _palavras(texto):
    return set(re.sub(r"[^\w\s]", " ", normalizar(texto)).split())


def afirmativo(texto):
    return bool(_palavras(texto) & SIM)


def negativo(texto):
    return bool(_palavras(texto) & NAO)


def confirmado(texto):
    return afirmativo(texto) and not negativo(texto)


def decisao(alternativas):
    """Interpretações do reconhecimento de voz (melhor primeiro). True=sim, False=não, None=não entendi.
    Totalmente local: nenhuma chamada ao LLM. 'não pode' / 'não faça' contêm 'não' e por isso negam."""
    for a in alternativas or []:
        if negativo(a):
            return False
        if afirmativo(a):
            return True
    return None
