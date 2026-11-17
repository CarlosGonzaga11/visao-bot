"""
Posicionamento (Fase 2, provas de 07/11 21:37): em 11 de 16 lutas as 2 corridas iam embora no 1º
segundo (decidia de novo ainda andando) e às vezes cruzava a box (21:39:10: (+4,-4) e 1 s depois
(-4,+4) do pet). Agora: espera CHEGAR antes de decidir de novo e nunca vai para o lado oposto do pet.
O personagem anda de verdade na simulação (1 sqm a cada 0,1 s). Sem cliques reais.
"""
import os
import sys
import threading
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
import bot
import config
config.NORMAL_SEM_FUGIR = False  # teste do POSICIONAMENTO: não depende do modo salvo no ajustes.json

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


config.SAIR_DA_BOX = True
config.BOX_DIAGONAL_SQM = 3
config.DISTANCIA_MONSTROS = 4
config.BOX_HP_SOLTAR = 60
config.CORRIDAS_POR_BOX = 2
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.MAPA.salvar = lambda: None
bot.limites_clique = lambda sct: ((-9, 9), (-4, 4))
bot.ler_barra = lambda sct, barra: None
controle.esperar = lambda s: time.sleep(s) or False
controle.apertar = lambda t: True

# ---------- 1. regra: não atravessar ----------
checar("você em (-3,+3) do pet → canto (+3,-3) do pet = atravessa", bot.atravessa_a_box((6, -6), (3, -3)))
checar("canto do lado (−3,−3) do pet = contorna, não atravessa", not bot.atravessa_a_box((0, -6), (3, -3)))
checar("mesmo lado = não atravessa", not bot.atravessa_a_box((-1, 1), (3, -3)))
checar("você em linha com o pet (sem quadrante) = não conta como atravessar", not bot.atravessa_a_box((3, -6), (0, -3)))


# ---------- 2. mundo que anda de verdade ----------
class Mundo:
    passo_s = 0.1    # tempo de 1 sqm andando
    atraso_s = 0.0   # a coordenada (OCR do minimapa) chega atrasada
    hist = []        # [(tempo, (x, y))]
    pos = [1000, 1000]
    destino = None
    parar_em = None  # para antes de chegar (sqm ocupado/caminho mudou)
    nao_anda = False


def andar():
    while True:
        time.sleep(Mundo.passo_s)
        d = Mundo.destino
        if d is None or Mundo.nao_anda or tuple(Mundo.pos) == d or tuple(Mundo.pos) == Mundo.parar_em:
            continue
        Mundo.pos[0] += (d[0] > Mundo.pos[0]) - (d[0] < Mundo.pos[0])
        Mundo.pos[1] += (d[1] > Mundo.pos[1]) - (d[1] < Mundo.pos[1])
        Mundo.hist.append((time.time(), tuple(Mundo.pos)))


threading.Thread(target=andar, daemon=True).start()


class Pos:
    def atual(self):
        if Mundo.atraso_s:
            limite = time.time() - Mundo.atraso_s
            velhas = [p for t, p in Mundo.hist if t <= limite]
            p = velhas[-1] if velhas else Mundo.inicio
            return (p[0], p[1], 7)
        return (Mundo.pos[0], Mundo.pos[1], 7)


bot.POS = Pos()
cliques = []


def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    cliques.append((time.time(), d))
    Mundo.destino = (Mundo.pos[0] + d[0], Mundo.pos[1] + d[1])
    return True


controle.clicar = clicar

# chega: só devolve quando está no destino
Mundo.pos, Mundo.destino = [1000, 1000], None
antes = bot.POS.atual()
clicar(bot.PLAYER_TILE_XY[0] + 4 * bot.SQM_PX, bot.PLAYER_TILE_XY[1] - 4 * bot.SQM_PX)
t = time.time()
ok = bot.esperar_chegar(antes, (4, -4))
checar("esperar_chegar: devolve só depois de chegar (4 sqm ≈ 0,4 s)", ok and tuple(Mundo.pos) == (1004, 996)
       and time.time() - t >= 0.35, f"({time.time() - t:.2f}s, {Mundo.pos})")

# não sai do lugar: devolve False em ~1 s
Mundo.nao_anda = True
antes = bot.POS.atual()
t = time.time()
ok = bot.esperar_chegar(antes, (3, 3))
checar("não saiu do lugar: False em ~1 s", ok is False and 0.9 <= time.time() - t <= 1.6, f"({time.time() - t:.2f}s)")
Mundo.nao_anda = False

# para no meio do caminho: True quando para (0,6 s parado)
Mundo.pos = [1000, 1000]
Mundo.parar_em = (1002, 1002)
antes = bot.POS.atual()
clicar(bot.PLAYER_TILE_XY[0] + 5 * bot.SQM_PX, bot.PLAYER_TILE_XY[1] + 5 * bot.SQM_PX)
t = time.time()
ok = bot.esperar_chegar(antes, (5, 5))
checar("parou antes do destino: segue (sem esperar o tempo todo)", ok and time.time() - t < 1.6, f"({time.time() - t:.2f}s)")
Mundo.parar_em = None

# ---------- 3. o caso 21:39:10 (box a um canto, decide de novo) ----------
# Criaturas em coordenada ABSOLUTA: o personagem anda e elas ficam (pet no pokestop).
pet_abs = (1004, 996)
box_abs = [pet_abs] + [(pet_abs[0] + a, pet_abs[1] + b) for a, b in ((-1, 0), (1, 0), (0, 1), (0, -1), (1, 1), (-1, -1))]


def criaturas_rel():
    return [(x - Mundo.pos[0], y - Mundo.pos[1]) for x, y in box_abs]


bot.sqm_ocupados = lambda sct: set(criaturas_rel())
Mundo.pos, Mundo.destino = [1002, 998], None  # você em (-2,+2) do pet: perto demais da box
Mundo.inicio, Mundo.hist = (1002, 998), []
Mundo.passo_s, Mundo.atraso_s = 0.25, 0.3  # como no jogo: ~4 sqm/s e o OCR atrasado
cliques.clear()
bot.CORRIDAS[0] = 0
bot.EMERGENCIAS[0] = 0
bot.CANTOS_RUINS.clear()
bot.PET_ABS[0] = pet_abs + (7,)
lados = []
for _ in range(4):
    time.sleep(0.15)  # o laço da espera da box lê a tela a cada ~0,1 s
    cri = criaturas_rel()                      # a tela é sempre a posição de verdade
    pet, _ = bot.achar_pet(cri, 1)              # como na luta: pet pela memória (POS atrasado)
    if bot.ir_para_diagonal("sct", cri, pet):
        lados.append(((Mundo.pos[0] - pet_abs[0] > 0) - (Mundo.pos[0] - pet_abs[0] < 0),
                      (Mundo.pos[1] - pet_abs[1] > 0) - (Mundo.pos[1] - pet_abs[1] < 0)))
cruzou = any(a[0] == -b[0] and a[1] == -b[1] and a[0] and a[1] for a, b in zip(lados, lados[1:]))
fim = (Mundo.pos[0] - pet_abs[0], Mundo.pos[1] - pet_abs[1])
checar("box ao lado: vai para o canto e NÃO troca para o canto oposto", not cruzou and lados, f"lados {lados}, fim {fim} do pet")
checar("depois de chegar no canto seguro: não gasta mais corridas", bot.CORRIDAS[0] == 1, f"({bot.CORRIDAS[0]} corridas)")
checar("termina longe da box (4+ sqm de todos)",
       min(max(abs(Mundo.pos[0] - x), abs(Mundo.pos[1] - y)) for x, y in box_abs) >= 4, f"(fim {fim} do pet)")

# Mesmo cenário, mas com 1 monstro colado em você do seu lado: sai, mas não pelo meio da box
Mundo.passo_s, Mundo.atraso_s = 0.1, 0.0
Mundo.pos, Mundo.destino = [1008, 992], None  # você em (+4,-4) do pet
box_abs.append((1007, 993))                    # colado em você
bot.CORRIDAS[0] = 0
bot.CANTOS_RUINS.clear()
cliques.clear()
cri = criaturas_rel()
pet = (pet_abs[0] - Mundo.pos[0], pet_abs[1] - Mundo.pos[1])
bot.ir_para_diagonal("sct", cri, pet)
destinos = [(d[0] - pet[0], d[1] - pet[1]) for _, d in cliques]
checar("monstro colado do seu lado: nunca vai para o lado OPOSTO do pet (-,+)",
       cliques and not any(r[0] < 0 and r[1] > 0 for r in destinos), f"(destinos do pet: {destinos})")

# ---------- 4. vigia durante o combo (22:10: monstro veio 3 -> 2 -> 1 sqm no meio do combo) ----------
Mundo.passo_s, Mundo.atraso_s = 0.1, 0.0
Mundo.pos, Mundo.destino = [1000, 1000], None
pet_abs = (996, 996)
box_abs[:] = [pet_abs, (995, 996), (996, 995)]
intruso = [1005, 1001]  # fora da box, a 5 sqm, vindo em você
parar_intruso = [False]


def intruso_anda():
    while not parar_intruso[0]:
        time.sleep(0.25)
        alvo = Mundo.pos
        if max(abs(intruso[0] - alvo[0]), abs(intruso[1] - alvo[1])) > 1:
            intruso[0] += (alvo[0] > intruso[0]) - (alvo[0] < intruso[0])
            intruso[1] += (alvo[1] > intruso[1]) - (alvo[1] < intruso[1])


bot.sqm_ocupados = lambda sct: set(criaturas_rel()) | {(intruso[0] - Mundo.pos[0], intruso[1] - Mundo.pos[1])}
bot.PET_ABS[0] = pet_abs + (7,)
bot.ULTIMA_VIGIA[0] = 0.0
bot.modos.VIGIA[0] = bot.vigiar_no_combo
bot.modos.TECLA_ATAQUE, bot.modos.INTERVALO_ATAQUE = "a", 2.5
import tela as _tela
_tela.ler_inimigos = lambda sct: [1]
cliques.clear()
menor = [99]
colado_s = [0.0]  # tempo total com o monstro colado em você (1 sqm)


def medir():
    while not parar_intruso[0]:
        d = max(abs(intruso[0] - Mundo.pos[0]), abs(intruso[1] - Mundo.pos[1]))
        menor[0] = min(menor[0], d)
        if d <= 1:
            colado_s[0] += 0.02
        time.sleep(0.02)


threading.Thread(target=intruso_anda, daemon=True).start()
threading.Thread(target=medir, daemon=True).start()
t0 = time.time()
bot.modos.Normal().atacar("sct")  # combo de verdade: ~2,5 s com a vigia ligada
parar_intruso[0] = True
checar("no meio do combo: viu o monstro vindo e saiu de perto", bool(cliques),
       f"(cliques {[(round(t - t0, 1), d) for t, d in cliques]})")
# a vigia olha a cada 0,3 s e o monstro simulado persegue sem parar: um encosto rápido pode
# acontecer; o que importa é não FICAR colado (sem a vigia ele fica colado o combo inteiro)
checar("monstro vindo no combo: nunca fica colado em você (≤ 0,3 s no total)", colado_s[0] <= 0.3,
       f"(colado {colado_s[0]:.2f}s, mais perto {menor[0]} sqm)")
bot.modos.VIGIA[0] = None

# ---------- 5. 08/11: sem perigo, a luta segue ENQUANTO anda (antes o 1º combo esperava 6,8 s) ----------
Mundo.passo_s, Mundo.atraso_s = 0.25, 0.0  # ~4 sqm/s
pet_abs = (1003, 997)                      # pet a 2 sqm (pokestop logo depois do lure)
box_abs[:] = [pet_abs, (1004, 997), (1003, 996), (1004, 996), (1004, 998), (1002, 996)]  # box em volta do pet


def mundo_box(pos):
    Mundo.pos, Mundo.destino, Mundo.parar_em, Mundo.nao_anda = list(pos), None, None, False
    bot.sqm_ocupados = lambda sct: set(criaturas_rel())
    bot.PET_ABS[0] = pet_abs + (7,)
    bot.CORRIDAS[0] = bot.EMERGENCIAS[0] = 0
    bot.CANTOS_RUINS.clear()
    bot.ANDANDO[0] = None
    cliques.clear()


mundo_box((1001, 999))
t = time.time()
bot.sair_da_box("sct")
gasto = time.time() - t
dest = cliques and (Mundo.destino[0] - Mundo.pos[0], Mundo.destino[1] - Mundo.pos[1])
checar("sem perigo: sai da box SEM travar (clica e já volta para a luta)",
       cliques and gasto < 0.3 and bot.ANDANDO[0] is not None, f"({gasto:.2f}s, faltam {dest} sqm)")
checar("a caminhada está em andamento (ninguém decide outro canto)", bot.ainda_andando())

# esperar a box ENQUANTO anda: box já fechada → solta o combo antes de chegar no canto
bot.inimigos = lambda sct: [{"alvo": False, "xy": (5, 5)}] * 5
bot.checar_catch = lambda sct: None
bot.ler_barra = lambda sct, barra: None
config.BOX_RAIO_SQM = 3
bot.MAGIA_ESPERA_MAX = 4.5
n_cliques = len(cliques)
t = time.time()
r = bot.esperar_agrupar("sct")
gasto = time.time() - t
checar("box fechada com você ainda andando: combo LIBERADO na hora", r is True and gasto < 1.5, f"({r}, {gasto:.2f}s)")
checar("durante a caminhada não escolheu outro canto", len(cliques) == n_cliques, f"({len(cliques) - n_cliques} cliques a mais)")

# perigo (monstro colado em você): continua esperando chegar antes de seguir
mundo_box((1001, 999))
box_abs.append((1000, 1000))  # colado em você
t = time.time()
bot.sair_da_box("sct")
gasto = time.time() - t
checar("com monstro colado: sai e ESPERA chegar (como antes)", cliques and bot.ANDANDO[0] is None and gasto >= 0.4,
       f"({gasto:.2f}s)")
box_abs.pop()

# não saiu do lugar (sem caminho): o canto vai para CANTOS_RUINS, igual ao jeito que espera
mundo_box((1001, 999))
Mundo.nao_anda = True
bot.sair_da_box("sct")
time.sleep(1.1)
checar("caminhada sem travar que nem saiu do lugar: canto marcado como sem caminho",
       not bot.ainda_andando() and len(bot.CANTOS_RUINS) == 1, f"{bot.CANTOS_RUINS}")
Mundo.nao_anda = False

# revive: só com você PARADO (espera a caminhada acabar)
mundo_box((1001, 999))
bot.sair_da_box("sct")
alvo = tuple(Mundo.destino)
bot.ler_pet_pct = lambda sct: 80
bot.preparar_revive("sct")
checar("antes do revive: espera a caminhada acabar (parado no canto)", tuple(Mundo.pos) == alvo and not bot.ainda_andando(),
       f"(em {tuple(Mundo.pos)}, destino {alvo})")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
