"""Pet cercado na box: sem order (não tem caminho) e, ao sair com sobra, puxar pela tela. Sem cliques de verdade."""
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
controle._rota.set()
bloqueados = set()
bot.MAPA.esta_bloqueado = lambda p: p in bloqueados
bot.MAPA.caminho = lambda a, b: [None] * bot.distancia(a, b)
bot.MAPA.salvar = lambda: None


class FakePos:
    p = (1000, 1000, 7)

    def atual(self):
        return self.p


bot.POS = FakePos()
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True  # a posição falsa não anda (chegada coberta em teste_sobrevivencia)
config.BOX_RAIO_SQM = 1
resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


V8 = bot.VIZINHOS_8
pet = (0, -2)
cercado = [(pet[0] + dx, pet[1] + dy) for dx, dy in V8]
checar("8 monstros em volta: cercado", bot.pet_cercado(cercado + [pet], pet))
meio = cercado[:4]
checar("4 em volta e o resto livre: não cercado", not bot.pet_cercado(meio + [pet], pet))
# 5 monstros + parede conhecida nos outros 3 = cercado
bloqueados.update({(1000 + pet[0] + dx, 1000 + pet[1] + dy, 7) for dx, dy in V8[5:]})
checar("monstros + parede: cercado", bot.pet_cercado(cercado[:5] + [pet], pet))
bloqueados.clear()

# esperar_agrupar com pet cercado e monstro longe: NÃO dá order (antes tentava e não andava)
longe = (5, -2)
todos = set(cercado + [pet, longe])
bot.inimigos = lambda sct: [{"alvo": True}] * 12
bot.checar_catch = lambda sct: None
bot.sqm_ocupados = lambda sct: set(todos)
bot.MAGIA_ESPERA_MAX = 2.5
bot.PET_ABS[0] = None
cliques.clear()
bot.esperar_agrupar(None)
checar("pet cercado: sem order para levar na direção dos outros", not [c for c in cliques if c[0] == "middle"],
       f"({cliques})")

# mesmo cenário sem cerco: o order sai (comportamento antigo preservado)
todos = set(meio + [pet, longe])
bot.sqm_ocupados = lambda sct: set(todos)
cliques.clear()
bot.esperar_agrupar(None)
checar("pet livre: order na direção dos outros continua", bool([c for c in cliques if c[0] == "middle"]))

# saindo da luta com sobra e pet cercado: anda até o pet sair da tela
andou = []


def andar_fake(sct, wp, numero, lure, z_final=None, ignorar_preso=False):
    andou.append(wp["pos"])
    FakePos.p = wp["pos"]
    return bot.CHEGOU


bot.andar_ate_coord = andar_fake
todos = set(cercado + [pet])
bot.sqm_ocupados = lambda sct: set(todos)
bot.PET_ABS[0] = None
FakePos.p = (1000, 1000, 7)
ok = bot.pet_preso_na_saida(None)
pet_abs = (1000 + pet[0], 1000 + pet[1])
fim = FakePos.p
fora = abs(pet_abs[0] - fim[0]) > 10 or abs(pet_abs[1] - fim[1]) > 5
checar("sobra + pet cercado: personagem anda até o pet sair da tela", ok and fora and len(andou) == 1,
       f"(foi para {andou})")
checar("escolhe o caminho mais curto (para baixo, longe do pet)", andou and andou[0][1] > 1000, f"({andou})")

# sobra mas pet livre: não anda à toa
andou.clear()
todos = set(meio + [pet])
FakePos.p = (1000, 1000, 7)
checar("sobra + pet livre: não puxa pela tela", bot.pet_preso_na_saida(None) is False and not andou)

# rota desligada: nunca anda (o mouse é do jogador)
todos = set(cercado + [pet])
controle._rota.clear()
checar("rota desligada: não anda", bot.pet_preso_na_saida(None) is False and not andou)
controle._rota.set()

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
