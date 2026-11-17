"""Personagem sempre na DIAGONAL da box e longe dos monstros (ataque em área). Sem cliques de verdade."""
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import controle
import humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade

humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None

import bot
import config
config.NORMAL_SEM_FUGIR = False  # teste do POSICIONAMENTO: não depende do modo salvo no ajustes.json
config.CORRIDAS_POR_BOX = 99  # este teste não é sobre o limite de corridas

bot.ler_barra = lambda sct, barra: None
cliques = []


def clicar(x, y, espalhar=(0, 0), botao="left"):
    cliques.append((botao, (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX),
                            round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))))
    return True


controle.clicar = clicar
controle.apertar = lambda t: True
controle.esperar = lambda s: False
bot.MAPA.esta_bloqueado = lambda p: False
bot._andou = lambda antes, espera=1.0: True  # aqui o personagem sempre chega (outro teste cobre a falha)
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True  # idem (a posição falsa não anda)


class FakePos:
    def atual(self):
        return (1000, 1000, 7)


bot.POS = FakePos()
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
config.BOX_DIAGONAL_SQM = 3
config.BOX_RAIO_SQM = 3
config.SAIR_DA_BOX = True
resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


def diagonal(d, pet, k=3):
    r = (d[0] - pet[0], d[1] - pet[1])
    return abs(r[0]) == abs(r[1]) and k <= abs(r[0]) <= 9


def folga(d, criaturas, pet):
    return min(bot.cheb(d, m) for m in criaturas if m != pet)


# pet em (0,-2) com a box em volta; você do lado da box
pet = (0, -2)
box = [(-1, -2), (1, -2), (0, -3), (0, -1), (-1, -1), (1, -3)]
cri = [pet] + box
bot.PET_ABS[0] = None
cliques.clear()
bot.ir_para_diagonal(None, cri, pet)
d = cliques[-1][1] if cliques else None
checar("vai para um canto DIAGONAL da box", d is not None and diagonal(d, pet), f"(foi para {d}, pet {pet})")
checar("canto longe de todo monstro (4+ sqm)", d is not None and folga(d, cri, pet) >= 4, f"(folga {d and folga(d, cri, pet)})")

# já está no canto diagonal, longe: não anda
pet2 = (-5, -5)  # box a 4+ sqm de você
cri2 = [pet2, (-6, -5), (-5, -6), (-4, -5)]
cliques.clear()
checar("já na diagonal e longe: fica parado", bot.ir_para_diagonal(None, cri2, pet2) is False and not cliques)

# no canto diagonal, mas um monstro veio colar em você: muda de canto
cri3 = cri2 + [(1, 0)]  # monstro colou em você
cliques.clear()
bot.ir_para_diagonal(None, cri3, pet2)
d = cliques[-1][1] if cliques else None
checar("monstro colou em você no canto: vai para outro canto diagonal",
       d is not None and folga(d, cri3, pet2) >= 3 and abs(pet2[0]-d[0]) <= 8 and abs(pet2[1]-d[1]) <= 4, f"(foi para {d})")

# os cantos a 3 sqm têm monstro perto: vai para a diagonal mais longe (4 ou 5)
pet4 = (0, -3)  # anel de monstros a 2 sqm do pet; você fora dele
anel = [(pet4[0] + a, pet4[1] + b) for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2)
        if (a or b) and max(abs(a), abs(b)) == 2]
cri4 = [pet4] + anel
cliques.clear()
bot.ir_para_diagonal(None, cri4, pet4)
d = cliques[-1][1] if cliques else None
r = d and (d[0] - pet4[0], d[1] - pet4[1])
checar("box larga: diagonal mais longe para ficar fora do ataque em área",
       d is not None and folga(d, cri4, pet4) >= 4 and abs(r[1]) <= 4, f"(foi para {d}, {r} do pet)")

# sair_da_box (logo depois do pokestop) usa a mesma regra
bot.sqm_ocupados = lambda sct: set(cri)
bot.PET_ABS[0] = None
cliques.clear()
bot.sair_da_box(None)
d = cliques[-1][1] if cliques else None
checar("depois do pokestop: diagonal da box", d is not None and diagonal(d, pet) and folga(d, cri, pet) >= 4, f"({d})")

# esperando a box: o pet foi levado (a box mudou de lugar) -> o personagem volta para a diagonal
bot.inimigos = lambda sct: [{"alvo": True}] * 7
bot.checar_catch = lambda sct: None
estado = {"n": 0}


def tela(sct):
    estado["n"] += 1
    if estado["n"] < 4:
        return set(cri2)                    # você na diagonal (ok)
    return {(2, 1), (3, 1), (1, 1), (2, 2), (2, 0)}  # pet foi para (2,1): agora você está colado na box


bot.sqm_ocupados = tela
bot.MAGIA_ESPERA_MAX = 1.5
bot.PET_ABS[0] = None
cliques.clear()
bot.esperar_agrupar(None)
andou = [c for c in cliques if c[0] == "left"]
print('cliques', cliques)
checar("pet mudou de lugar na espera da box: personagem volta para a diagonal", bool(andou), f"({andou})")
checar("nunca anda para perto da box", all(min(bot.cheb(a[1], m) for m in [(2, 1), (3, 1), (1, 1), (2, 2), (2, 0)])
                                         >= 2 for a in andou[-1:]), f"({andou[-1:]})")

# SAIR_DA_BOX desligado: não mexe no personagem na espera
config.SAIR_DA_BOX = False
estado["n"] = 10
cliques.clear()
bot.esperar_agrupar(None)
checar("opção desligada: não reposiciona", not [c for c in cliques if c[0] == "left"])

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
