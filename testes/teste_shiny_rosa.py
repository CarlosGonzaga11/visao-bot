"""
Shiny com nome/barra MAGENTA na tela (na Battle a barra é verde) — 09/11 18:07: o bot achou que as estrelinhas
eram de um CORPO (a barra rosa não contava como viva) e tacou 11 balls num shiny vivo andando (contador sempre 1/6).
Print real: testes/dados/print_11-09_18-08-05.png (layout 48,73 px, personagem (584, 295)). Sem cliques reais.
"""
import os
import sys
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import controle
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
acoes = []
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
controle.clicar = lambda *a, **k: True
controle.esperar = lambda s: False
import catch
import catch_resultado
import config

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


im = cv2.imread(os.path.join(DADOS, "print_11-09_18-08-05.png"))
catch.PLAYER_TILE_XY, catch.SQM_PX = (584, 295), 48.73
e = catch.especiais_por_estrela(im, (0, 23))
checar("18:08: estrelinhas do shiny ligadas à barra ROSA → VIVO (não é corpo)",
       e == [{"sqm": (-1, 0), "vivo": True, "rosa": True}], f"{e}")

# rastreador: shiny de barra magenta seguido na luta; a luta acaba → vira corpo (ball nele)
r = catch.RastreadorEspecial(lambda: (1930, 1988, 9))
r.estrelados = {1: {"pos": (1929, 1988, 9), "visto": time.time(), "battle": 1, "vezes": 3, "rosa": True}}
r.luta_acabou()
# magenta na tela é a marca do SHINY (print 18:07:35: barra verde na Battle) — se a luta acabou, ele morreu: vira corpo
checar("fim da luta com shiny de barra magenta: vira corpo (é o shiny que estava na luta)", r.corpos == [(1929, 1988, 9)],
       f"{r.corpos}")

# catch: ball que não dá NENHUMA mensagem e o alvo andando (sqm diferente a cada ball) → para em 3
catch.CATCH_ATIVO = True
catch.CATCH_ESTRELAS = True
catch.TECLA_BALL = "2"
catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False
config.CATCH_AJUSTE_X = config.CATCH_AJUSTE_Y = 0
config.CATCH_TENTATIVAS_ESPECIAL = 6
config.CATCH_PROCURA_S = 0.2
catch.REVER_DEPOIS_BALL_S = 0.0
catch.perfis_ativos = lambda pos, tipo: []
catch.perfis_pelo_corpo = lambda pos: []
catch.corpo_substitui_estrelas = lambda pos: False
catch.corpo_piscando = lambda *a, **k: None
catch.capturar = lambda *a, **k: None
avisos = []
catch._avisar_sem_corpo = lambda sct, motivo: avisos.append(motivo)
passo = [0]


def estrelas(sct):
    passo[0] += 1  # o "corpo" (o shiny vivo, visto como sem barra) anda a cada olhada
    return [{"sqm": (1 + passo[0] % 3, passo[0] % 2), "vivo": False, "rosa": False}]


catch.estrelas_na_tela = estrelas
catch_resultado.foto = lambda sct: ["18:04 Sorry, your pokeball broke."]  # nada de novo depois da ball
balls = []
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): balls.append(t) or True


class R:
    def __init__(self):
        self.viu_icone, self.viu, self.corpos, self.empilhados = False, True, [], set()

    def pos_atual(self):
        return (1930, 1988, 9)

    def catch_feito(self):
        self.viu_icone = False

    def marcar_tentado(self, k):
        pass


catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("alvo andando + nenhuma mensagem no chat: para em 3 balls (antes 11)", len(balls) == 3, f"({len(balls)} balls)")
checar("e avisa", avisos and "sem mensagem" in avisos[-1], f"{avisos}")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
