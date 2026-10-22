"""Canais de confirmação por voz e por teclado. O Telegram tem o seu próprio canal (botões) em telegram_bot.py.
Cada canal devolve: True = sim | False = não | None = sem resposta. Só True autoriza; todo o resto cancela."""
import seguranca
import teclado


def _pin_pelo_teclado(pedido):
    if not teclado.disponivel():
        return False
    pin = teclado.ler_linha("PIN: ", mascarar=True, timeout=30)
    ok = pin is not None and seguranca.pin_valido(pin)
    if not ok:
        seguranca.log_seg(pedido["origem"], pedido["acao"], pedido["risco"], "DENY", "pin_invalid_or_missing")
    return ok


def confirmar_terminal(msg, pedido):
    if not teclado.disponivel():
        return None
    print(f"\n[CONFIRMAÇÃO | risco {pedido['risco']}] {msg}")
    r = teclado.ler_tecla("[S]im / [N]ão / Esc: ", "sn\x1b", seguranca.timeout("confirmacao_teclado"))
    if r is None:
        print("Confirmação não recebida. Ação cancelada.")
        return None
    if r != "s":
        return False
    if pedido["exige_pin"] and not _pin_pelo_teclado(pedido):
        return False
    return True


def criar_confirmador_voz(ouvido, voz):
    """Fluxo: pergunta falada -> escuta curta -> (1 nova tentativa) -> fallback por teclado -> cancela."""
    def confirmar_voz(msg, pedido):
        print(f"[CONFIRMAÇÃO | risco {pedido['risco']}] {msg}")
        voz.falar(msg, eco=0.2)        # pausa mínima só para o eco do alto-falante sumir
        decisao = None
        for tentativa in range(2):
            alts = ouvido.escutar(espera=seguranca.timeout("confirmacao_voz"), curto=True)
            print(f"Você (confirmação): {alts}")
            decisao = seguranca.decisao(alts)
            if decisao is not None:
                break
            if tentativa == 0:
                voz.falar("Não entendi. Diga sim ou não.", eco=0.2)
        if decisao is None and teclado.disponivel():
            print("[teclado] Não entendi sua voz. Responda: S = sim, N = não, Esc = cancelar")
            r = teclado.ler_tecla("[S]im / [N]ão / Esc: ", "sn\x1b", seguranca.timeout("confirmacao_teclado"))
            decisao = None if r is None else (r == "s")
        if decisao is None:
            voz.falar("Confirmação não recebida. Ação cancelada.")
            return None
        if decisao is False:
            return False
        if pedido["exige_pin"]:
            if not teclado.disponivel():
                seguranca.log_seg(pedido["origem"], pedido["acao"], pedido["risco"], "DENY", "pin_required_no_keyboard")
                voz.falar("Esta ação exige PIN digitado e não há teclado disponível. Cancelei.")
                return False
            voz.falar("Digite o PIN no teclado.")
            if not _pin_pelo_teclado(pedido):
                voz.falar("PIN incorreto. Cancelei.")
                return False
        return True
    return confirmar_voz
