"""Corpo do especial longe demais para a ball / viu especial e não achou corpo. Sem cliques reais."""
import itertools
import os
import sys
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import numpy as np
import controle
import humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade

humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
acoes = []
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": acoes.append(("clique", round(x), round(y))) or True
controle.esperar = lambda s: time.sleep(min(s, 0.3)) or False
import catch
import config as _cfg; _cfg.CATCH_TENTATIVAS_ESPECIAL = 3; _cfg.CATCH_PROCURA_S = 1.0  # este teste conta 3 balls por corpo
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): (acoes.append(("tecla", t)), acoes.append(("clique", round(x), round(y))), True)[2]
import config

catch.CATCH_ATIVO = True
catch.TECLA_BALL = "b"
catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 283), 50.9
catch.corpo_piscando = lambda *a, **k: None
salvos = []
cv2.imwrite = lambda a, img: salvos.append(a) or True  # não grava de verdade
v = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
catch.capturar = lambda sct, reg: v
AQUI = (3497, 1947, 11)
res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


class R:
    def __init__(self, viu_icone=False):
        self.viu_icone, self.viu, self.corpos, self.empilhados = viu_icone, False, [], set()

    def pos_atual(self):
        return AQUI

    def catch_feito(self):
        self.viu_icone = self.viu = False

    def marcar_tentado(self, k):
        pass


# corpo a 5 sqm, mas a ball só alcança 3 -> chega perto e taca
cx, cy = int(534 + 5 * 50.9), int(283 - 3 * 50.9)
bloco = v[cy - 40:cy + 26, cx - 35:cx + 35].copy()
perto = v.copy()
perto[cy - 40:cy + 26, cx - 35:cx + 35] = v[cy - 40 - 60:cy + 26 - 60, cx - 35:cx + 35]  # apaga o corpo de lá
tx, ty = int(534 + 2 * 50.9), int(283 - 1 * 50.9)
perto[ty - 40:ty + 26, tx - 35:tx + 35] = bloco                                         # ...e põe a 2 sqm
tela = {"img": v}
andou = []


def pegar_loot(pos_atual, sqm, lootear=True):
    andou.append(sqm)
    tela["img"] = perto
    return True


catch.pegar_loot = pegar_loot
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(tela["img"], perfis, origem=(0, 0))
catch.CATCH_DISTANCIA_MAX = 3
acoes.clear()
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
balls = [acoes[i + 1] for i, a in enumerate(acoes[:-1]) if a == ("tecla", "b")]
checar("corpo além do alcance da ball: chega perto e taca", andou and len(balls) == 3,
       f"(andou {andou}, {len(balls)} balls em {sorted(set(balls))[:2]})")
catch.CATCH_DISTANCIA_MAX = 6

# corpo dentro do alcance: não anda (auto loot)
andou.clear()
tela["img"] = v
acoes.clear()
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("corpo dentro do alcance: não anda, só taca", not andou and acoes.count(("tecla", "b")) == 3)

# viu o shiny (ícone) e não achou corpo: avisa e salva print
vazio = np.full_like(v, 90)
tela["img"] = vazio
acoes.clear()
salvos.clear()
catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(viu_icone=True), fim_de_luta=True)
checar("viu o especial e não achou corpo: avisa + print", not acoes and len(salvos) == 1, f"({salvos})")

# o especial morreu no MEIO da luta (sem corpo à vista) e no fim também não tem: avisa no fim
salvos.clear()
r = R(viu_icone=True)
catch.fazer_catch(None, r, fim_de_luta=False)   # morreu no meio da luta (rastreador zera depois)
catch.fazer_catch(None, r, fim_de_luta=True)    # fim da luta
checar("morreu no meio da luta e não teve ball: avisa no fim", len(salvos) == 1)

# luta sem especial nenhum: não avisa nada
salvos.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("luta sem especial: nenhum aviso", not salvos)

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
