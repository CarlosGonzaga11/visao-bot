"""Personagem LONGE da box (magia em área): pet estável, só se mexe com perigo, nunca atravessa a box."""
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
config.BOX_DIAGONAL_SQM = 3
config.DISTANCIA_MONSTROS = 4
config.SAIR_DA_BOX = True
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.MAPA.salvar = lambda: None
controle.esperar = lambda s: False
cliques = []


class Pos:
    p = (1000, 1000, 7)

    def atual(self):
        return self.p


bot.POS = Pos()


def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append((botao, d))
    if botao == "left":
        Pos.p = (Pos.p[0] + d[0], Pos.p[1] + d[1], 7)
    return True


controle.clicar = clicar
res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


def rel(abs_cri):
    """Criaturas em coordenada do mapa -> relativas ao personagem agora."""
    return [(c[0] - Pos.p[0], c[1] - Pos.p[1]) for c in abs_cri]


# box em coordenada do MAPA: pet em (1000, 997), monstros em volta
PET = (1000, 997)
BOX = [(999, 997), (1001, 997), (1000, 996), (1000, 998), (999, 996), (1001, 998)]

# 1) pet estável: um monstro empata em vizinhos com o pet em algumas leituras -> pet continua o mesmo
Pos.p = (1000, 1003, 7)
bot.PET_ABS[0] = None
c0, _ = bot.achar_pet(rel([PET] + BOX), 1)
outro = BOX + [(1002, 997), (1002, 998)]  # (1001,997) passa a ter tantos vizinhos quanto o pet
escolhas = set()
for _ in range(5):
    c, _ = bot.achar_pet(rel([PET] + outro), 1)
    escolhas.add((c[0] + Pos.p[0], c[1] + Pos.p[1]))
checar("pet não troca de criatura a cada leitura", escolhas == {PET}, f"({escolhas})")

# 2) longe de todos (5+ sqm), fora da diagonal exata: NÃO se mexe
Pos.p = (1006, 1001, 7)  # 6 sqm à direita / 4 abaixo do pet
cri = rel([PET] + BOX)
checar("longe da box (fora da diagonal exata): não se mexe", not bot.em_perigo(cri, rel([PET])[0]))

# 3) você a 2 sqm da box -> perigo -> vai para longe (4+ de todos), na diagonal
Pos.p = (1002, 999, 7)
bot.PET_ABS[0] = (PET[0], PET[1], 7)
cliques.clear()
cri = rel([PET] + BOX)
centro, _ = bot.achar_pet(cri, 1)
checar("a 2 sqm da box: está em perigo", bot.em_perigo(cri, centro))
bot.ir_para_diagonal(None, cri, centro)
depois = rel([PET] + BOX)
folga = min(bot.cheb((0, 0), m) for m in depois)
dpet = (Pos.p[0] - PET[0], Pos.p[1] - PET[1])
checar("foi para 4+ sqm de TODOS (pet e monstros)", folga >= 4, f"(folga {folga}, {dpet} do pet)")
checar("e na diagonal do pet", abs(dpet[0]) == abs(dpet[1]), f"({dpet})")

# 4) nunca atravessa a box: você do lado direito-baixo -> fica do lado direito-baixo
Pos.p = (1002, 999, 7)
cri = rel([PET] + BOX)
d = bot.canto_da_box(None, cri, rel([PET])[0])
alvo = (Pos.p[0] + d[0], Pos.p[1] + d[1])
checar("canto a 4+ sqm de todos e com o pet na tela", min(bot.cheb(alvo, m) for m in [PET] + BOX) >= 4 and abs(alvo[0]-PET[0]) <= 8 and abs(alvo[1]-PET[1]) <= 4, f"(canto {alvo}, pet {PET})")
# o caminho até lá não passa colado em ninguém
checar("o caminho até o canto não passa perto dos monstros", bot.passos_ate(d, cri, Pos.p) is not None)

# 5) sem canto seguro (parede de monstros): foge para o sqm mais longe alcançável
Pos.p = (1000, 1000, 7)
muro = [(x, 998) for x in range(990, 1011)]  # fileira de monstros 2 sqm acima, de ponta a ponta
cri = rel([PET] + BOX + muro)
cliques.clear()
bot.CANTOS_RUINS.clear()
bot.ir_para_diagonal(None, cri, rel([PET])[0])
f_depois = min(bot.cheb((0, 0), m) for m in rel([PET] + BOX + muro))
checar("sem canto seguro: se afasta (fica mais longe que antes)", cliques and f_depois > 2, f"(folga {f_depois})")

# 6) espera da box: longe = parado; monstro chega perto = sai (não fica trocando de canto)
Pos.p = (1005, 1002, 7)
bot.PET_ABS[0] = (PET[0], PET[1], 7)
estado = {"n": 0}
VEIO = (1004, 1001)  # um monstro vem para colado em você


def tela(sct):
    estado["n"] += 1
    extra = [VEIO] if estado["n"] > 6 else []
    return set(rel([PET] + BOX + extra))


bot.sqm_ocupados = tela
bot.inimigos = lambda sct: [{"alvo": True}] * 7
bot.checar_catch = lambda sct: None
bot.MAGIA_ESPERA_MAX = 1.0
cliques.clear()
bot.esperar_agrupar(None)
saidas = [c for c in cliques if c[0] == "left"]
checar("espera da box: só se mexe quando o monstro chega perto (1 vez, sem pular de canto)", len(saidas) == 1,
       f"({saidas})")
fim = min(bot.cheb((Pos.p[0], Pos.p[1]), m) for m in [PET] + BOX + [VEIO])
checar("e termina a 4+ sqm de todos", fim >= 4, f"(folga {fim})")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
