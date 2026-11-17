"""
Trocar o MODO DE HUNT no painel com o bot rodando (09/11 18:22: virou revive no painel e o bot seguiu NORMAL:
combo em recarga com o pet morrendo e lure sem magias). Nenhum mouse/teclado de verdade.
"""
import json
import os
import sys
import tempfile

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
import config
import controle
controle.esperar = lambda s: False
import bot
import layout
import modos

res = []


def checar(nome, ok, extra=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {nome} {extra}", flush=True)


layout._setar("MODO_HUNT", "normal")
bot.ESTRATEGIA = modos.criar()
checar("começa no modo normal (como a hunt remoraid-farm está salva)", bot.ESTRATEGIA.nome == "normal")

# o painel salva o ajustes.json com o modo revive: o vigia aplica e marca para trocar
arq = os.path.join(tempfile.mkdtemp(), "ajustes.json")
json.dump({"MODO_HUNT": "normal"}, open(arq, "w"))
config.ARQ_AJUSTES = arq
import threading, time
paradas = [0]
controle.deve_parar = lambda: paradas[0] >= 3
_sleep = time.sleep


def sono(s):
    paradas[0] += 1
    if paradas[0] == 1:
        json.dump({"MODO_HUNT": "revive", "REVIVE_APOS_LURE": True}, open(arq, "w"))
        os.utime(arq, (time.time() + 5, time.time() + 5))
    _sleep(0.01)


time.sleep = sono
bot.vigiar_ajustes()
time.sleep = _sleep
checar("salvou modo revive no painel: marcado para trocar", bot.TROCAR_MODO[0] is True)
checar("ainda não trocou no meio de um passo (só no próximo ciclo)", bot.ESTRATEGIA.nome == "normal")
bot.aplicar_modo_novo()
checar("próximo ciclo: a ESTRATEGIA vira REVIVE de verdade", bot.ESTRATEGIA.nome == "revive"
       and hasattr(bot.ESTRATEGIA, "usar_revive"), f"({bot.ESTRATEGIA.nome})")
checar("revive: a poção do pet espera (segurar_pot_poke)", controle.segurar_pot_poke is True)
checar("sem mudança nova: não recria de novo", bot.aplicar_modo_novo() is False)

layout._setar("MODO_HUNT", "outland")
bot.TROCAR_MODO[0] = True
bot.aplicar_modo_novo()
checar("trocar para OUTLAND também vale na hora", bot.ESTRATEGIA.nome == "outland"
       and callable(getattr(bot.ESTRATEGIA, "tem_especial", None)))

print("Combo com o pet morto")
src = open(os.path.join(PASTA, "bot.py"), encoding="utf-8").read()
checar("pet ≤3% (morto/na ball) não solta combo 'pet fraco'", "3 < hp_pet < config.BOX_HP_SOLTAR" in src)

print(f"\n{sum(res)}/{len(res)} testes passaram", flush=True)
os._exit(0 if all(res) else 1)
