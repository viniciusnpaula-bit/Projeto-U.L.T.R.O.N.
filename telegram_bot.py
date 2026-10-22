"""Controle pelo celular via Telegram. Só responde ao seu ID de usuário.
Confirmações por BOTÕES (independentes do microfone), cada uma ligada a um id único, ao seu usuário e a um prazo."""
import asyncio
import threading
import time

import cerebro
import config
import seguranca

_lock = threading.Lock()
_pendentes = {}                      # id do pedido -> {"evento", "resp", "expira"}
_pin_espera = {"evento": None, "valor": None}


def autorizado(user_id):
    return bool(config.TELEGRAM_USER_ID) and user_id == config.TELEGRAM_USER_ID


def resolver(user_id, cid, resp):
    """Registra o clique de um botão. Devolve 'ok' | 'nao_autorizado' | 'expirado'."""
    if not autorizado(user_id):
        seguranca.log_seg("telegram", "confirmacao", "-", "DENY", f"unauthorized_confirmation user={user_id}")
        return "nao_autorizado"
    with _lock:
        p = _pendentes.get(cid)
        if not p or p["evento"].is_set() or time.time() > p["expira"]:
            seguranca.log_seg("telegram", "confirmacao", "-", "DENY", f"expired_or_unknown_confirmation id={cid}")
            return "expirado"
        p["resp"] = resp
        p["evento"].set()
    return "ok"


class Confirmador:
    """Usado como confirmar(msg, pedido). enviar(texto, cid) manda a pergunta com botões; pedir_pin(texto) pede o PIN."""

    def __init__(self, enviar, pedir_pin=None):
        self.enviar = enviar
        self.pedir_pin = pedir_pin

    def __call__(self, msg, pedido):
        cid, ev = pedido["id"], threading.Event()
        with _lock:
            _pendentes[cid] = {"evento": ev, "resp": None, "expira": pedido["expira"]}
        try:
            restante = max(1, int(pedido["expira"] - time.time()))
            self.enviar(f"⚠️ {msg}\n(risco {pedido['risco']} · expira em {restante}s)", cid)
            if not ev.wait(max(1, pedido["expira"] - time.time())):
                return None
            with _lock:
                resp = _pendentes[cid]["resp"]
        finally:
            with _lock:
                _pendentes.pop(cid, None)
        if resp != "s":
            return False
        if pedido["exige_pin"]:
            pin = self.pedir_pin("Esta ação exige o seu PIN. Envie o PIN agora (a mensagem será apagada).") if self.pedir_pin else None
            if pin is None or not seguranca.pin_valido(pin):
                seguranca.log_seg("telegram", pedido["acao"], pedido["risco"], "DENY", "pin_invalid_or_missing")
                return False
        return True


def iniciar():
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_USER_ID):
        return False
    threading.Thread(target=_rodar, daemon=True).start()
    return True


def _rodar():
    from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # concurrent_updates: sem isso o clique no botão ficava preso atrás da mensagem que está esperando a confirmação
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("parar", _parar))
    app.add_handler(CallbackQueryHandler(_botao, pattern=r"^c:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _mensagem))
    cerebro.NOTIFICADORES.append(lambda t: asyncio.run_coroutine_threadsafe(
        app.bot.send_message(config.TELEGRAM_USER_ID, t), loop))
    try:
        app.run_polling(stop_signals=None, close_loop=False)
    except Exception as e:
        seguranca.log.error(f"Telegram caiu: {e}")
        print(f"[telegram] erro: {e}")


async def _parar(update, ctx):
    if not update.effective_user or not autorizado(update.effective_user.id):
        return
    with _lock:
        for p in _pendentes.values():
            p["resp"] = "n"
            p["evento"].set()
    seguranca.parar_tudo()
    await update.message.reply_text("Tudo parado.")


async def _botao(update, ctx):
    q = update.callback_query
    try:
        _, cid, resp = q.data.split(":")
    except ValueError:
        await q.answer()
        return
    estado = resolver(q.from_user.id, cid, resp)
    if estado == "ok":
        await q.answer("Registrado.")
        try:
            await q.edit_message_reply_markup(reply_markup=None)   # remove os botões: uso único
        except Exception:
            pass
    elif estado == "nao_autorizado":
        await q.answer("Você não está autorizado.", show_alert=True)
    else:
        await q.answer("Confirmação expirada ou já usada.", show_alert=True)


async def _mensagem(update, ctx):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if not update.effective_user or not autorizado(update.effective_user.id):
        seguranca.log_seg("telegram", "mensagem", "-", "DENY", "unauthorized_user")
        return                                            # ignora estranhos em silêncio
    texto = (update.message.text or "").strip()
    loop = asyncio.get_running_loop()

    if _pin_espera["evento"] and not _pin_espera["evento"].is_set():      # esta mensagem é o PIN
        _pin_espera["valor"] = texto
        _pin_espera["evento"].set()
        try:
            await update.message.delete()
        except Exception:
            pass
        return
    with _lock:
        if _pendentes:
            await update.message.reply_text("Há uma confirmação pendente. Use os botões ✅ / ❌ acima.")
            return

    def enviar(txt, cid):
        botoes = InlineKeyboardMarkup([[InlineKeyboardButton("✅ CONFIRMAR", callback_data=f"c:{cid}:s"),
                                        InlineKeyboardButton("❌ CANCELAR", callback_data=f"c:{cid}:n")]])
        asyncio.run_coroutine_threadsafe(update.message.reply_text(txt, reply_markup=botoes), loop).result(15)

    def pedir_pin(txt):
        _pin_espera.update(evento=threading.Event(), valor=None)
        asyncio.run_coroutine_threadsafe(update.message.reply_text(txt), loop).result(15)
        _pin_espera["evento"].wait(45)
        return _pin_espera["valor"]

    resposta = await asyncio.to_thread(cerebro.processar, texto, Confirmador(enviar, pedir_pin), "telegram")
    await update.message.reply_text(resposta)
