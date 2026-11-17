"""Limite da tela (pet não pode sair da tela) e prioridade do pet (morto/apanhando: não corre)."""
import os, sys
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
import bot, config
config.CORRIDAS_POR_BOX = 99
config.BOX_DIAGONAL_SQM = 3; config.DISTANCIA_MONSTROS = 4; config.SAIR_DA_BOX = True; config.BOX_HP_SOLTAR = 60
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.limites_clique = lambda sct: ((-9, 9), (-4, 4))
controle.esperar = lambda s: False
cliques = []
class Pos:
    p = (1000, 1000, 7)
    def atual(self): return self.p
bot.POS = Pos()
def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append(d); Pos.p = (Pos.p[0] + d[0], Pos.p[1] + d[1], 7); return True
controle.clicar = clicar
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
# --- limite da tela: varias boxes, o pet sempre continua na tela depois de andar ---
fora = []
for pet in [(0, -2), (2, -3), (-3, 1), (0, 3), (4, 0)]:
    ring = [(pet[0] + a, pet[1] + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a or b)]
    cri = [pet] + ring
    for f in (bot.canto_da_box(None, cri, pet), bot.fuga(cri, pet)):
        if f is not None and not (abs(pet[0] - f[0]) <= 8 and abs(pet[1] - f[1]) <= 4):
            fora.append((pet, f))
checar("canto/fuga NUNCA deixam o pet fora da tela (teletransporte)", not fora, f"({fora})")
# --- prioridade do pet ---
bot.carregar_calibracao = lambda: {"poke_hp": {"x": 1}}
hp = [0]
bot.ler_barra = lambda sct, barra: hp[0]
controle.ultimo_revive = 0.0
pet = (0, -2); cri = [pet, (-1, -2), (1, -2), (0, -3), (0, -1), (-1, -1), (1, -3)]
# sem ninguém colado em você (monstro a 2 sqm): regra antiga — pet fraco/morto primeiro
longe = [pet, (-1, -2), (1, -2), (0, -3), (1, -3), (-1, -3)]
for valor, deve, nome in ((0, False, "pet morto"), (40, False, "pet com 40% (< BOX_HP_SOLTAR)"), (90, True, "pet com 90%")):
    hp[0] = valor; cliques.clear(); Pos.p = (1000, 1000, 7); bot.CORRIDAS[0] = 0
    andou = bot.ir_para_diagonal("sct", longe, pet)
    checar(f"ninguém colado, {nome}: {'corre' if deve else 'NÃO corre (revive/combo primeiro)'}", bool(andou) == deve and bool(cliques) == deve)
# monstro COLADO em você (20:48: pet 27–57%, "não corro", revive → você foi a 11%): pet vivo → corre
for valor, deve, nome in ((0, False, "pet morto (revive primeiro)"), (40, True, "pet com 40%: corre (sobreviver primeiro)"), (90, True, "pet com 90%")):
    hp[0] = valor; cliques.clear(); Pos.p = (1000, 1000, 7); bot.CORRIDAS[0] = 0
    andou = bot.ir_para_diagonal("sct", cri, pet)
    checar(f"monstro colado, {nome}", bool(andou) == deve and bool(cliques) == deve)
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
