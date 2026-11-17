"""Canto diagonal sem caminho (parede / box fechando): não fica preso, vai para outro. Sem cliques reais."""
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
config.CORRIDAS_POR_BOX = 99  # este teste não é sobre o limite de corridas

bot.ler_barra = lambda sct, barra: None
config.BOX_DIAGONAL_SQM = 3
config.SAIR_DA_BOX = True
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.salvar = lambda: None
paredes = set()
bot.MAPA.esta_bloqueado = lambda p: p[:2] in paredes
controle.esperar = lambda s: False
cliques = []
inalcancavel = set()  # sqm (absolutos) que o jogo recusa (o personagem não sai do lugar)


class Pos:
    p = (1000, 1000, 7)

    def atual(self):
        return self.p


bot.POS = Pos()


def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append((botao, d))
    alvo = (Pos.p[0] + d[0], Pos.p[1] + d[1])
    if botao == "left" and alvo not in inalcancavel:
        Pos.p = (alvo[0], alvo[1], Pos.p[2])  # chegou
    return True


controle.clicar = clicar
res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


def diagonal(d, pet):
    r = (d[0] - pet[0], d[1] - pet[1])
    return abs(r[0]) == abs(r[1]) and 3 <= abs(r[0]) <= 5


pet = (0, -2)
box = [(-1, -2), (1, -2), (0, -3), (0, -1), (-1, -1), (1, -3)]
cri = [pet] + box

# 1) caminho livre: escolhe o canto normalmente
print("passos até (3, 1):", bot.passos_ate((3, 1), cri, Pos.p))
checar("caminho existe até o canto livre", bot.passos_ate((3, 1), cri, Pos.p) is not None)

# 2) o canto mais perto tem parede em volta inteira (sem caminho): não escolhe ele
Pos.p = (1000, 1000, 7)
alvo_normal = bot.canto_da_box(None, cri, pet)
paredes.clear()
ax, ay = 1000 + alvo_normal[0], 1000 + alvo_normal[1]
paredes |= {(ax + a, ay + b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b}  # cerca o canto
outro = bot.canto_da_box(None, cri, pet)
checar("canto cercado por parede (sem caminho): escolhe outro", outro != alvo_normal and (outro is None or diagonal(outro, pet)),
       f"(antes {alvo_normal}, agora {outro})")
paredes.clear()

# 3) a box fecha a passagem: monstros fazendo uma parede entre você e o canto
muro = [(x, 1) for x in range(-3, 4)] + [(x, -1) for x in range(-3, 4)] + [(-3, 0), (3, 0)]
cri3 = [pet] + box + [m for m in muro if m not in box and m != pet]
d = bot.canto_da_box(None, cri3, pet)
checar("monstros fechando a passagem: só escolhe canto com caminho",
       d is None or bot.passos_ate(d, cri3, Pos.p) is not None, f"({d})")

# 4) clicou e o personagem NÃO saiu do lugar (o jogo recusou): marca o canto e vai para outro
Pos.p = (1000, 1000, 7)
bot.CANTOS_RUINS.clear()
primeiro = bot.canto_da_box(None, cri, pet)
inalcancavel.add((1000 + primeiro[0], 1000 + primeiro[1]))
cliques.clear()
bot.ir_para_diagonal(None, cri, pet)
esq = [c[1] for c in cliques if c[0] == "left"]
checar("não chegou no canto: tenta OUTRO canto (não insiste no mesmo)", len(esq) == 2 and esq[0] != esq[1], f"(cliques {esq})")
checar("canto sem caminho fica marcado nesta luta", (1000 + primeiro[0], 1000 + primeiro[1], 7) in bot.CANTOS_RUINS)
Pos.p = (1000, 1000, 7)
checar("e não é escolhido de novo", bot.canto_da_box(None, cri, pet) != primeiro)
inalcancavel.clear()

# 5) luta nova: esquece os cantos ruins
bot.CANTOS_RUINS.add((1, 2, 3))
bot.inimigos = lambda sct: []
bot.controle.esperar = lambda s: False
bot.fazer_catch = lambda *a, **k: None
bot.ORDER_DEPOIS_LUTA = False
bot.POKESTOP_ATIVO = False
bot.efeitos.curar_se_precisar = lambda sct: False
bot.descansar = lambda sct: None
bot.combater_ate_limpar(None, bot.LOTOU)
checar("luta nova: cantos ruins esquecidos", not bot.CANTOS_RUINS)

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
