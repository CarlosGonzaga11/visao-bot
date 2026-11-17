"""Fugir para o lado de ONDE VEIO (caminho limpo), não para a frente. Sem mouse real."""
import os, sys, time
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
import bot, config
config.NORMAL_SEM_FUGIR = False  # teste do POSICIONAMENTO: não depende do modo salvo no ajustes.json
bot.ler_barra = lambda sct, barra: None
config.CORRIDAS_POR_BOX = 2; config.BOX_DIAGONAL_SQM = 3; config.DISTANCIA_MONSTROS = 4; config.SAIR_DA_BOX = True
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot._andou = lambda antes, espera=1.0: True
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True  # idem (a posição falsa não anda)
controle.esperar = lambda s: False
class Pos:
    p = (1000, 1000, 7)
    def atual(self): return self.p
bot.POS = Pos()
cliques = []
def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append((botao, d)); return True
controle.clicar = clicar
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
# andou de baixo para cima (y 1008 -> 1000): veio de BAIXO
bot.RASTRO.clear()
for y in range(1008, 999, -1):
    Pos.p = (1000, y, 7); bot.anotar_rastro()
v = bot.direcao_de_onde_veio()
checar("sabe de onde veio (de baixo)", v and v[1] > 0.9, f"({v})")
bot.VEIO_DE[0] = v
# box à esquerda do personagem (pet em (-4, 0)); cantos seguros em cima e embaixo
pet = (-4, 0)
cri = [pet] + [(pet[0] + a, pet[1] + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
d = bot.canto_da_box(None, cri, pet) or bot.fuga(cri, pet)
checar("escolhe canto do lado de onde veio (embaixo da box)", d and d[1] > pet[1], f"(canto {d}, pet {pet})")
bot.VEIO_DE[0] = (0.0, -1.0)  # se tivesse vindo de cima
d2 = bot.canto_da_box(None, cri, pet) or bot.fuga(cri, pet)
checar("vindo de cima: canto de cima", d2 and d2[1] < pet[1], f"({d2})")
# segurança primeiro: canto de trás com monstro perto -> vai para o da frente (seguro)
bot.VEIO_DE[0] = (0.0, 1.0)
cri_perigo = cri + [(d[0], d[1] - 1), (d[0] + 1, d[1])] if d else cri
d3 = bot.canto_da_box(None, cri_perigo, pet) or bot.fuga(cri_perigo, pet)
f3 = d3 and min(bot.cheb(d3, m) for m in cri_perigo)
checar("canto de trás perigoso: segurança primeiro (vai para um lugar a 4+ sqm)", d3 is None or f3 >= 3, f"({d3}, folga {f3})")
# bug da ordem: luta anterior gastou as 2 corridas -> luta nova AINDA sai de perto da box no pokestop
bot.CORRIDAS[0] = 2
Pos.p = (1000, 1000, 7)
colado = [(0, -1), (0, -2), (1, -2), (-1, -2), (0, -3)]
bot.sqm_ocupados = lambda sct: set(colado)
bot.inimigos = lambda sct: []
bot.POKESTOP_ATIVO = True; bot.TECLA_POKESTOP = "p"
controle.apertar = lambda t: True
bot.fazer_catch = lambda *a, **k: None
bot.ORDER_DEPOIS_LUTA = False
bot.efeitos.curar_se_precisar = lambda sct: False
bot.descansar = lambda sct: None
cliques.clear()
bot.combater_ate_limpar(None, bot.LOTOU)
checar("luta nova: sai de perto da box no pokestop mesmo se a anterior gastou as corridas",
       any(c[0] == "left" for c in cliques), f"({cliques})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
