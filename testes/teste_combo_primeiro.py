"""
Box pronta = COMBO PRIMEIRO (pedido do usuário 09/11, Heroi Alfa 18:20: com a box feita em volta do pet o bot
corria para a diagonal e só depois soltava a magia). Box ainda não pronta + perigo = continua se afastando.
Sem cliques reais.
"""
import os
import sys
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import controle
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
cliques = []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": cliques.append(botao) or True
controle.apertar = lambda t: True
controle.esperar = lambda s: time.sleep(min(s, 0.02)) or False
import bot
import config

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


config.SAIR_DA_BOX = True
config.NORMAL_SEM_FUGIR = False
config.BOX_RAIO_SQM = 3
config.BOX_DIAGONAL_SQM = 3
config.DISTANCIA_MONSTROS = 4
config.CORRIDAS_POR_BOX = 2
bot.ESTRATEGIA = bot.modos.Outland()
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.limites_clique = lambda sct: ((-9, 9), (-4, 4))
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True
bot.POS = type("P", (), {"atual": lambda self: (1000, 1000, 7)})()
bot.ler_barra = lambda sct, b: 90
bot.checar_catch = lambda sct: None
bot.MAGIA_ESPERA_MAX = 1.0

# pet a 2 sqm (você perto demais = em_perigo) com os 3 inimigos colados nele: box PRONTA
pet = (0, -2)
box = [pet, (-1, -2), (1, -2), (0, -3)]
bot.sqm_ocupados = lambda sct: set(box)
bot.inimigos = lambda sct: [{"alvo": True, "xy": (5, 5)}] * 3
bot.PET_ABS[0] = (1000, 998, 7)
checar("box já pronta no pokestop (3 de 3 colados no pet)", bot.box_ja_pronta("sct"))
cliques.clear()
bot.CORRIDAS[0] = bot.EMERGENCIAS[0] = 0
t = time.time()
r = bot.esperar_agrupar("sct")
checar("box pronta e você perto: COMBO na hora, sem correr antes", r is True and not cliques and time.time() - t < 0.5,
       f"({r}, {len(cliques)} cliques, {time.time() - t:.2f}s)")

# box NÃO pronta (só 1 de 3 colado, os outros longe) e você perto do pet: continua se afastando
box[:] = [pet, (-1, -2), (5, 3), (6, 3)]
bot.PET_ABS[0] = (1000, 998, 7)
checar("box ainda não pronta", not bot.box_ja_pronta("sct"))
cliques.clear()
bot.CORRIDAS[0] = bot.EMERGENCIAS[0] = 0
bot.ANDANDO[0] = None
bot.esperar_agrupar("sct")
checar("box não pronta + perigo: se afasta (como antes)", "left" in cliques, f"({cliques})")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
