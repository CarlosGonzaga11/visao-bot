"""
Catch com o PET em cima do corpo do especial (07/11 22:13): o desenho do Gyarados escondia as
estrelinhas; depois da 1ª ball o bot achava que tinha pegado e desistia. Agora tira o pet de cima
(order) e olha de novo. Sem cliques reais.
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
acoes = []
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": acoes.append(("clique", botao)) or True
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): acoes.append(("ball", t)) or True
controle.esperar = lambda s: time.sleep(min(s, 0.05)) or False
import bot
import catch
import config

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


catch.CATCH_ATIVO = True
catch.CATCH_ESTRELAS = True
catch.TECLA_BALL = "2"
catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False
config.CATCH_AJUSTE_X = config.CATCH_AJUSTE_Y = 0
config.CATCH_TENTATIVAS_ESPECIAL = 6
config.CATCH_PROCURA_S = 0.5
catch.REVER_DEPOIS_BALL_S = 0.3
catch.perfis_ativos = lambda pos, tipo: []
catch.perfis_pelo_corpo = lambda pos: []
catch.corpo_substitui_estrelas = lambda pos: False
catch.corpo_piscando = lambda *a, **k: None
catch.capturar = lambda *a, **k: None
AQUI = (1000, 1000, 7)
CORPO = (1003, 1000, 7)          # o shiny morreu aqui
pet_em_cima = [True]             # o desenho do pet cobre as estrelinhas


def estrelas(sct):
    return [] if pet_em_cima[0] else [{"vivo": False, "sqm": (3, 0)}]


catch.estrelas_na_tela = estrelas


class R:
    def __init__(self):
        self.viu_icone, self.viu, self.corpos, self.empilhados = False, True, [CORPO], set()

    def pos_atual(self):
        return AQUI

    def catch_feito(self):
        self.viu_icone = False

    def marcar_tentado(self, k):
        pass


# ---- antes (sem tirar o pet): 1 ball e desiste ----
catch._balls_por_corpo.clear()
catch.TIRAR_PET[0] = None
acoes.clear()
pet_em_cima[0] = True
catch.fazer_catch(None, R(), fim_de_luta=True)
balls_antes = sum(1 for a in acoes if a[0] == "ball")
checar("(prova do bug) sem tirar o pet: só 1 ball e desiste", balls_antes == 1, f"({balls_antes} balls)")

# ---- agora: tira o pet de cima e continua ----
bot.POS = type("P", (), {"atual": lambda self: AQUI})()
bot.PET_ABS[0] = (1004, 1000, 7)  # pet (pokestop) colado no corpo
pedidos = []


def tirar(corpo):
    ok = bot.tirar_pet_do_corpo(corpo)
    pedidos.append((corpo, ok))
    if ok:
        pet_em_cima[0] = False  # o pet saiu: as estrelinhas aparecem
    return ok


catch._balls_por_corpo.clear()
catch.TIRAR_PET[0] = tirar
acoes.clear()
pet_em_cima[0] = True
catch.fazer_catch(None, R(), fim_de_luta=True)
balls = sum(1 for a in acoes if a[0] == "ball")
i_order = next((i for i, a in enumerate(acoes) if a == ("clique", "middle")), None)
checar("pet em cima do corpo: dá order para tirar ele de lá", pedidos and pedidos[0][1] and i_order is not None, f"{pedidos}")
checar("depois do order: continua tacando ball (estrelinhas visíveis)", balls >= 3, f"({balls} balls)")
checar("order sai DEPOIS da 1ª ball e ANTES da 2ª",
       i_order is not None and [a[0] for a in acoes[:i_order]].count("ball") == 1, f"{acoes[:4]}")
checar("pet vai para longe do corpo (3 sqm, para a direita)", bot.PET_ABS[0] == (1006, 1000, 7), f"{bot.PET_ABS[0]}")

# pet longe do corpo: não mexe nele
bot.PET_ABS[0] = (1000, 995, 7)
checar("pet longe do corpo: não dá order", bot.tirar_pet_do_corpo(CORPO) is False)
# no meio da luta (não é fim de luta): nunca tira o pet do pokestop
catch._balls_por_corpo.clear()
bot.PET_ABS[0] = (1004, 1000, 7)
pedidos.clear()
acoes.clear()
pet_em_cima[0] = True
catch.fazer_catch(None, R(), fim_de_luta=False)
checar("no meio da luta: não tira o pet do pokestop", not pedidos and ("clique", "middle") not in acoes, f"{pedidos}")
catch.TIRAR_PET[0] = None

# ---------- 22:28: estrelinha marcou o lugar errado (3 sqm ao lado), ball no chão vazio ----------
import cv2
perfil = {"id": "marowak_shiny", "nome": "Marowak shiny", "tipo": "especial", "h": [93, 99], "s": [130, 255],
          "v": [55, 245], "pixels": 375, "local": [3475, 1950, 11], "amostra": None, "pelo_corpo": True, "min_corpo": 80}
catch.carregar_perfis = lambda: [perfil]
catch.perfis_pelo_corpo = lambda pos: [perfil] if pos is None or catch.vale_aqui(perfil, pos) else []
catch.corpo_substitui_estrelas = lambda pos: False
tela_2229 = cv2.imread(os.path.join(DADOS, "print_22-29-23.png"))[1:561, 50:1118]
catch.capturar = lambda sct, reg: tela_2229
catch.GAME_VIEW = {"left": 50, "top": 1, "width": 1068, "height": 560}
catch.PLAYER_TILE_XY, catch.SQM_PX = (584, 307), 50.9
AQUI = (552, 1487, 6)                  # longe (outro andar) de onde o perfil foi calibrado
CORPO = (546, 1488, 6)                 # onde a estrelinha disse que morreu (errado)
pet_em_cima[0] = True                  # sem estrelinha na tela depois da 1ª ball
catch.TIRAR_PET[0] = None
alvos_ball = []
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): alvos_ball.append(
    (round((x - 584) / 50.9), round((y - 307) / 50.9))) or True
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("22:28: viu o shiny morrer → acha o corpo de verdade pela cor (-3, 0)", (-3, 0) in alvos_ball, f"(balls em {alvos_ball})")
checar("22:28: insiste no corpo de verdade (mais de 1 ball)", alvos_ball.count((-3, 0)) >= 2, f"(balls em {alvos_ball})")

# sem ter visto especial nesta luta: perfil de outro lugar NÃO vale (não taca no mato de outro mapa)
class R2(R):
    def __init__(self):
        super().__init__()
        self.viu, self.corpos = False, []


alvos_ball.clear()
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R2(), fim_de_luta=True)
checar("sem especial nesta luta: perfil de outro lugar não é usado", alvos_ball == [], f"({alvos_ball})")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
