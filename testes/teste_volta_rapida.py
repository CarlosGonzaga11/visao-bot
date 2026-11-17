"""
Volta mais rápida (09/11, sessão 08/11 21:39): pet atrás de quem anda, desvio rápido de criatura no caminho,
silence com a foto da box tirada ANTES do combo. Nenhum mouse/teclado de verdade.
"""
import os
import sys
import time

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
cliques = []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": cliques.append((x, y, botao)) or True
import bot

res = []


def checar(nome, ok, extra=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {nome} {extra}", flush=True)


print("Pet atrás de quem anda")
for d in [(3, 0), (-2, 0), (0, 4), (2, 2), (-3, 1)]:
    atras = bot.vizinhos_atras(d)
    checar(f"andando para {d}: pet só atrás/do lado", atras and all(v[0] * d[0] + v[1] * d[1] < 0 for v in atras), f"{atras}")
checar("sem direção conhecida: qualquer vizinho", len(bot.vizinhos_atras(None)) == 8)


class P:
    def atual(self):
        return (100, 100, 7)


bot.POS = P()
bot.SQM_PX, bot.PLAYER_TILE_XY = 50.9, (584, 307)
lados = set()
for _ in range(40):
    cliques.clear()
    bot.DIRECAO_ANDAR[0] = (4, 0)  # vai andar para a direita
    bot.orders_depois_da_luta(esperar=lambda s: None)
    for x, y, botao in cliques:
        if botao == "middle":
            lados.add(round((x - 584) / 50.9))
checar("depois da luta, andando para a DIREITA: nenhum order cai na frente (x > 0)", lados and max(lados) < 0,
       f"(dx usados: {sorted(lados)})")
checar("nunca order no próprio personagem (RIDE)", 0 not in lados)

print("Criatura no caminho")
checar("pet no sqm da frente -> criatura no caminho",
       bot.criatura_no_caminho((100, 100, 7), (104, 100, 7), {(1, 0), (3, 2)}))
checar("pet do lado (fora do caminho) -> segue andando", not bot.criatura_no_caminho((100, 100, 7), (104, 100, 7), {(0, 1)}))
checar("indo na diagonal: pet na diagonal da frente", bot.criatura_no_caminho((100, 100, 7), (103, 103, 7), {(1, 1)}))
checar("desvio de criatura sai antes da trava de parede", bot.CRIATURA_TRAVA_S < bot.NAV_TRAVADO_S,
       f"({bot.CRIATURA_TRAVA_S}s x {bot.NAV_TRAVADO_S}s)")

print("Silence: foto da box antes do combo")
config.SILENCIO_POS_COMBO_S, config.CONTROLE_TIPO, config.POKES_CONTROLE, config.POKE_CACA = 3.0, "silence", {}, ""
bot.PET_ABS[0] = None
bot.sqm_ocupados = lambda sct: {(4, 0), (5, 0), (4, 1), (3, -1), (5, 1)}  # pet (4,0) + 4 monstros
foto = bot.foto_da_box("sct")
bot.sqm_ocupados = lambda sct: set()  # depois do combo: Hydro Pump por cima, ninguém aparece
bot.iniciar_controle("sct", foto)
checar("box vista ANTES do combo vale para o silence (efeitos escondem as barras depois)",
       bot.em_silencio() and len(bot.CONTROLE_BOX.alvos) == 4, f"({len(bot.CONTROLE_BOX.alvos)} alvos)")
bot.CONTROLE_BOX.parar()
bot.iniciar_controle("sct")
checar("(sem a foto: box vazia depois do combo, sem silence — o problema de 08/11)", not bot.em_silencio())

print(f"\n{sum(res)}/{len(res)} testes passaram", flush=True)
os._exit(0 if all(res) else 1)
