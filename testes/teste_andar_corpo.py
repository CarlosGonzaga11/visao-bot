"""Andou até o corpo (4 sqm) -> tela rolando -> corpo volta: taca ball. Some de vez: avisa."""
import os, sys
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import cv2
import controle, humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
acoes = []
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": acoes.append(("clique", round(x), round(y))) or True
controle.esperar = lambda s: False
import catch
import config as _cfg; _cfg.CATCH_TENTATIVAS_ESPECIAL = 3; _cfg.CATCH_PROCURA_S = 1.0  # este teste conta 3 balls por corpo
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): (acoes.append(("tecla", t)), acoes.append(("clique", round(x), round(y))), True)[2]
catch.CATCH_ATIVO = True; catch.TECLA_BALL = "b"; catch.LOOT_ANTES_BALL = False
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 283), 50.9
catch.pegar_loot = lambda pos_atual, sqm, lootear=True: acoes.append(("andou", sqm)) or True
catch.corpo_piscando = lambda *a, **k: None
catch.capturar = lambda sct, reg: v
salvos = []
cv2.imwrite = lambda a, img: salvos.append(a) or True  # não grava de verdade
v = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
marowak = next(p for p in catch.carregar_perfis() if p["id"] == "marowak_shiny")
AQUI = (3497, 1947, 11)
class R:
    viu_icone = viu = False; corpos = []; empilhados = set()
    def pos_atual(self): return AQUI
    def catch_feito(self): pass
    def marcar_tentado(self, k): pass
res = []
def checar(n, ok, e=""):
    res.append(ok); print(("✅" if ok else "❌") + f" {n} {e}")
import numpy as np
vazio = np.full_like(v, 90)
import itertools, time as _t
controle.esperar = lambda seg: _t.sleep(min(seg, 0.4)) or False  # o tempo passa (o rever conta 3 s)
import config
config.CATCH_CHEGAR_PERTO = False
leituras = itertools.chain(itertools.repeat(v))
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(next(leituras), perfis, origem=(0, 0))
acoes.clear(); catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
cx, cy = round(534 + 5 * 50.9), round(283 - 3 * 50.9)
balls = [acoes[i + 1] for i, a in enumerate(acoes[:-1]) if a == ("tecla", "b")]
checar("auto loot (padrao): NAO anda, taca a ball direto no corpo a 5 sqm",
       not [a for a in acoes if a[0] == "andou"] and len(balls) == 3 and all(abs(b[1] - cx) <= 8 and abs(b[2] - cy) <= 8 for b in balls),
       f"(balls {balls}, alvo {(cx, cy)})")
config.CATCH_CHEGAR_PERTO = True  # os casos abaixo testam a opcao ligada
leituras = itertools.chain([v, vazio, vazio], itertools.repeat(v))   # acha (5 sqm) -> anda -> some 2 leituras -> volta
real = cv2.imread  # noqa
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(next(leituras), perfis, origem=(0, 0))
acoes.clear(); catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("opção ligada: andou até o corpo, tela rolou, corpo voltou: taca ball", ("andou", (5, -3)) in acoes and ("tecla", "b") in acoes,
       f"(balls {balls}, alvo {(cx, cy)})")
leituras = itertools.chain([v], itertools.repeat(vazio))                 # acha -> anda -> some de vez
acoes.clear(); catch._balls_por_corpo.clear()
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("corpo sumiu de vez depois de andar: avisa e salva print", ("tecla", "b") not in acoes and bool(salvos), f"({salvos[-1:]})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
