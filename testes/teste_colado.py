"""Monstro colado no personagem durante a luta (caso do print das 16:28). Sem cliques de verdade."""
import os
import sys
import time

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
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append((botao, d))
    return True


controle.clicar = clicar
controle.apertar = lambda t: True
controle.esperar = lambda s: False
bot.MAPA.esta_bloqueado = lambda p: False
bot.MAPA.salvar = lambda: None


class FakePos:
    def atual(self):
        return (1000, 1000, 7)


bot.POS = FakePos()
config.BOX_DIAGONAL_SQM = 3
config.BOX_RAIO_SQM = 1
resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


# Pet em (-1,-3) com 4 monstros colados nele; 1 monstro colado em VOCÊ em (1,0)
pet = (-1, -3)
box = [(-2, -3), (0, -3), (-1, -4), (-1, -2)]
chaser = (1, 0)
criaturas = set([pet] + box + [chaser])

# achar_pet: o pet é quem tem mais vizinhos
bot.PET_ABS[0] = None
c, n = bot.achar_pet(list(criaturas), 1)
checar("acha o pet certo", c == pet and n == 4, f"({c}, {n})")

# empate (ninguém colado em ninguém): vale onde o pet estava antes, não o monstro colado em você
bot.PET_ABS[0] = (1000 - 2, 1000 - 2, 7)
c, _ = bot.achar_pet([(1, 0), (-2, -2)], 1)
checar("empate: lembra onde o pet estava", c == (-2, -2), f"({c})")

# lugar seguro: longe de todos os monstros (2+ sqm), fora da box
d = bot.lugar_seguro(list(criaturas), pet)
folga = min(bot.cheb(d, m) for m in criaturas if m != pet) if d else 0
checar("lugar seguro fica a 2+ sqm de todo monstro", d is not None and folga >= 2 and bot.cheb(d, pet) >= 2,
       f"({d}, folga {folga})")

# esperar_agrupar: com monstro colado em você, você sai de perto e o pet NÃO vai na sua direção
bot.inimigos = lambda sct: [{"alvo": True}] * 5
bot.checar_catch = lambda sct: None
bot.sqm_ocupados = lambda sct: set(criaturas)
bot.MAGIA_ESPERA_MAX = 0.6
bot.PET_ABS[0] = None
cliques.clear()
bot.esperar_agrupar(None)
saidas = [c for c in cliques if c[0] == "left"]
orders = [c for c in cliques if c[0] == "middle"]
checar("esperando a box: personagem sai de perto do monstro colado", bool(saidas)
       and all(min(bot.cheb(s[1], m) for m in criaturas if m != pet) >= 2 for s in saidas), f"({saidas})")
pet_para_mim = [o for o in orders if bot.cheb(o[1], (0, 0)) < bot.cheb(pet, (0, 0))]
checar("esperando a box: pet nunca vai para perto de você", not pet_para_mim, f"(orders {orders})")

# sem ninguém colado: não anda à toa
cliques.clear()
criaturas_ok = set([pet] + box + [(4, 2)])
bot.sqm_ocupados = lambda sct: set(criaturas_ok)
checar("sem monstro colado: sair_de_perto não anda", bot.sair_de_perto(None) is False and not cliques)

# sair_da_box: o canto mais perto tem monstro colado -> escolhe outro canto
cliques.clear()
bot.PET_ABS[0] = None
pet2 = (0, -3)
box2 = [(1, -3), (-1, -3), (0, -4), (0, -2)]
perigo = (-2, 1)  # colado no canto (-3, 0)
todos = set([pet2] + box2 + [perigo])
bot.sqm_ocupados = lambda sct: set(todos)
bot.sair_da_box(None)
destino = cliques[-1][1] if cliques else None
checar("diagonal da box: não para colado em monstro", destino is not None
       and all(bot.cheb(destino, m) >= 2 for m in todos if m != pet2), f"(foi para {destino})")

# antes do revive: sai de perto se tem monstro colado
cliques.clear()
bot.sqm_ocupados = lambda sct: set(criaturas)
chamadas = []


class ReviveFake(bot.modos.Revive):
    def atacar(self, sct):
        return False

    def nao_matou(self, sct):
        chamadas.append(("revive", len(cliques)))
        return False


bot.ESTRATEGIA = ReviveFake()
bot.MAGIA_AGRUPAR_ATIVA = False
bot.POKESTOP_ATIVO = False
bot.efeitos.curar_se_precisar = lambda sct: False
config.IGNORAR_SOBRA = False
config.CLICAR_ALVO = False
bot.TIMEOUT_COMBATE = 5.0  # o revive pode ser adiado 2x (mundo parado: nunca fica longe) antes de sair
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True  # a posição falsa não anda
bot.REVIVE_ADIADOS[0] = 0
bot.fazer_catch = lambda *a, **k: None
bot.ORDER_DEPOIS_LUTA = False
bot.inimigos = lambda sct: [{"alvo": True, "xy": (1, 1)}]
bot.combater_ate_limpar(None, bot.LOTOU)
checar("antes do revive: sai de perto primeiro", bool(chamadas) and chamadas[0][1] >= 1, f"({chamadas[:2]})")

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
