"""
'Fugiram' falso (09/11 18:07): na tela só aparecia 1 criatura — o SHINY (barra magenta), com a barra do pet
tapada por "ICE BEAM!/MISS!" — e o bot achou que era o pet: "os monstros fugiram" → 4 lutas abertas e largadas
em 20 s. Recorte real: testes/dados/especial_11-09_18-07-35.png (GAME_VIEW do layout 48,73 px). Sem cliques.
"""
import os
import sys
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import controle
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
controle.clicar = lambda *a, **k: True
controle.apertar = lambda *a, **k: True
controle.esperar = lambda s: time.sleep(min(s, 0.05)) or False
import bot
import config

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


img = cv2.imread(os.path.join(DADOS, "especial_11-09_18-07-35.png"))
bot.GAME_VIEW = {"left": 72, "top": 27, "width": img.shape[1], "height": img.shape[0]}
bot.PLAYER_TILE_XY, bot.SQM_PX = (584, 295), 48.73
bot.capturar = lambda sct, reg: img
pet = [100]
bot.ler_pet_pct = lambda sct: pet[0]
checar("18:07:35: a única criatura (barra magenta) é MONSTRO, não o pet", bot.unica_e_monstro("sct") is True)

# criatura comum (barra verde cheia) e pet com 100%: pode ser o pet → regra antiga
import numpy as np
bot.encontrar_barras_criaturas = lambda im, origem: [(584 - 13, 295 + 2 * 49 - 26, 25, False), (571, 269, 25, False)]
checar("1 criatura verde com vida igual à do pet: pode ser o pet (não decide)", bot.unica_e_monstro("sct") is False)
pet[0] = 30
checar("1 criatura com 100% e o pet com 30%: é monstro", bot.unica_e_monstro("sct") is True)

# esperar_agrupar: só o monstro na tela → solta o combo (antes: "sumiram" e largava a luta)
bot.inimigos = lambda sct: [{"alvo": True, "xy": (5, 5)}]
bot.checar_catch = lambda sct: None
bot.sqm_ocupados = lambda sct: {(0, 2)}
bot.ler_barra = lambda sct, b: 30
config.NORMAL_SEM_FUGIR = True
t = time.time()
r = bot.esperar_agrupar("sct")
checar("só o monstro na tela (pet tapado): solta o combo em ~1 s, não 'fugiram'", r is True and time.time() - t < 2.5,
       f"({r}, {time.time() - t:.1f}s)")

# a única criatura é o pet (vida igual): continua valendo 'sumiram'
pet[0] = 100
bot.ler_barra = lambda sct, b: 100
r = bot.esperar_agrupar("sct")
checar("só o PET na tela: continua 'sumiram' (monstro fugiu de verdade)", r == "sumiram", f"({r})")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
