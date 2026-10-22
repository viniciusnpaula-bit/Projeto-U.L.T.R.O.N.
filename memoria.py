"""Memória do Ultron em SQLite: conversas, fatos sobre o usuário e lembretes."""
import sqlite3
import threading
import time

from config import BASE

_lock = threading.Lock()
_db = sqlite3.connect(str(BASE / "dados" / "ultron.db"), check_same_thread=False)
_db.executescript("""
CREATE TABLE IF NOT EXISTS mensagens(id INTEGER PRIMARY KEY, ts REAL, papel TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, texto TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS lembretes(id INTEGER PRIMARY KEY, due REAL, texto TEXT, feito INTEGER DEFAULT 0);
""")


def _x(sql, args=(), buscar=False):
    with _lock:
        cur = _db.execute(sql, args)
        _db.commit()
        return cur.fetchall() if buscar else cur.lastrowid


def salvar_msg(papel, texto):
    _x("INSERT INTO mensagens(ts, papel, texto) VALUES(?,?,?)", (time.time(), papel, texto))


def historico(n=16):
    linhas = _x("SELECT papel, texto FROM mensagens ORDER BY id DESC LIMIT ?", (n,), True)
    msgs = [{"role": p, "content": t} for p, t in reversed(linhas)]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def salvar_fato(texto):
    _x("INSERT OR IGNORE INTO fatos(texto) VALUES(?)", (texto.strip(),))


def listar_fatos():
    return [r[0] for r in _x("SELECT texto FROM fatos ORDER BY id", (), True)]


def apagar_fato(trecho):
    _x("DELETE FROM fatos WHERE texto LIKE ?", (f"%{trecho}%",))


def add_lembrete(due, texto):
    return _x("INSERT INTO lembretes(due, texto) VALUES(?,?)", (due, texto))


def lembretes_vencidos():
    return _x("SELECT id, texto FROM lembretes WHERE feito=0 AND due<=?", (time.time(),), True)


def lembretes_pendentes():
    return _x("SELECT due, texto FROM lembretes WHERE feito=0 ORDER BY due", (), True)


def marcar_feito(id_):
    _x("UPDATE lembretes SET feito=1 WHERE id=?", (id_,))
