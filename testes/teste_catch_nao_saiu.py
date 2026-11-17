"""
Ball que NÃO SAI (09/11 17:33): sem nenhuma mensagem no chat e o corpo do shiny continuando a piscar, o bot
tacou 6 balls (~30 s parado). Ball tacada sempre dá mensagem → 2 assim seguidas = desiste e avisa.
Sem cliques reais.
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
controle.clicar = lambda *a, **k: True
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): acoes.append(("ball", t)) or True
controle.esperar = lambda s: False
import catch
import catch_resultado
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
config.CATCH_PROCURA_S = 0.2
catch.REVER_DEPOIS_BALL_S = 0.0
catch.perfis_ativos = lambda pos, tipo: []
catch.perfis_pelo_corpo = lambda pos: []
catch.corpo_substitui_estrelas = lambda pos: False
catch.estrelas_na_tela = lambda sct: []
catch.capturar = lambda *a, **k: None
avisos = []
catch._avisar_sem_corpo = lambda sct, motivo: avisos.append(motivo)
AQUI = (1929, 1986, 9)
CORPO = (1933, 1987, 9)   # 17:33: 4 sqm
catch.corpo_piscando = lambda sct, pos, c, raio=1, **k: CORPO  # o corpo continua lá piscando


class R:
    def __init__(self):
        self.viu_icone, self.viu, self.corpos, self.empilhados = False, True, [CORPO], set()

    def pos_atual(self):
        return AQUI

    def catch_feito(self):
        self.viu_icone = False

    def marcar_tentado(self, k):
        pass


# chat: nenhuma mensagem nova depois da ball (= ball não saiu)
catch_resultado.foto = lambda sct: ["16:38 Sorry, your pokeball broke."]
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
balls = sum(1 for a in acoes if a[0] == "ball")
checar("ball que não sai: desiste depois de 2 (antes eram 6, ~30 s parado)", balls == 2, f"({balls} balls)")
checar("e avisa (log + print em diagnostico/)", avisos and "não saiu" in avisos[0], f"{avisos}")

# ball que QUEBRA (chat mostra) continua tentando até o limite (regra antiga)
acoes.clear()
avisos.clear()
fotos = [[]]


def foto(sct):
    return list(fotos[0])


def depois_da_ball(x, y, t, espalhar=(0, 0)):
    acoes.append(("ball", t))
    fotos[0] = fotos[0] + ["17:40 Sorry, your pokeball broke."]
    return True


catch_resultado.foto = foto
controle.tecla_no_ponto = depois_da_ball
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
balls = sum(1 for a in acoes if a[0] == "ball")
checar("ball que QUEBRA: continua tentando até o limite (6)", balls == 6, f"({balls} balls)")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
