"""Ícone na bandeja do sistema (perto do relógio): pausar/retomar escuta, abrir logs, sair."""
import os
from pathlib import Path

import pystray
from PIL import Image

import config


def _icone(_ativo):
    with Image.open(Path(config.BASE) / "ULTRON-Logo-icon.png") as logo:
        return logo.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)


def executar(pausado):
    """Mostra o ícone e bloqueia até o usuário escolher 'Sair'."""
    def alternar(icon, item):
        pausado.clear() if pausado.is_set() else pausado.set()
        icon.icon = _icone(not pausado.is_set())
        icon.title = "Ultron: pausado" if pausado.is_set() else "Ultron: ouvindo"

    def texto_pausa(item):
        return "Retomar escuta" if pausado.is_set() else "Pausar escuta"

    menu = pystray.Menu(
        pystray.MenuItem(texto_pausa, alternar, default=True),
        pystray.MenuItem("Abrir pasta de logs", lambda icon, item: os.startfile(str(config.BASE / "logs"))),
        pystray.MenuItem("Sair do Ultron", lambda icon, item: icon.stop()),
    )
    pystray.Icon("ultron", _icone(True), "Ultron: ouvindo", menu).run()
