"""Catch do shiny pelo corpo morto (cor do perfil). Imagens reais; nenhum clique de verdade."""
import glob
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
S = DADOS
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
controle.esperar = lambda s: False

import catch
import config as _cfg; _cfg.CATCH_TENTATIVAS_ESPECIAL = 3; _cfg.CATCH_PROCURA_S = 1.0  # este teste conta 3 balls por corpo
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): (acoes.append(("tecla", t)), acoes.append(("clique", round(x), round(y))), True)[2]

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


catch.PLAYER_TILE_XY = (534, 280)   # centro da imagem do mapa (21 x 11 sqm de 51 px)
catch.SQM_PX = 50.9  # igual ao jogo (número quebrado)
catch.CATCH_ATIVO = True
catch.CATCH_ESTRELAS = True
AQUI = (3480, 1945, 11)
marowak = next(p for p in catch.carregar_perfis() if p["id"] == "marowak_shiny")

checar("perfil Marowak shiny vale na hunt", catch.perfis_pelo_corpo(AQUI) == [marowak])
checar("perfil só de COR não vale longe da hunt", not catch.vale_aqui(dict(marowak, modelo=None), (900, 1300, 7)))
checar("perfil com MODELO (desenho) procura em qualquer hunt (08/11)", catch.perfis_pelo_corpo((900, 1300, 7)) == [marowak])
checar("estrelinhas ignoradas na hunt do Marowak", catch.corpo_substitui_estrelas(AQUI))
checar("estrelinhas continuam valendo em outra hunt", not catch.corpo_substitui_estrelas((900, 1300, 7)))
catch.CATCH_ATIVO = False
checar("catch desligado: nada pelo corpo", catch.perfis_pelo_corpo(AQUI) == [])
catch.CATCH_ATIVO = True

# prints reais do jogo (Gyarados vivo, shiny VIVO, hotbar): nenhum corpo
falsos = []
for f in sorted(glob.glob(os.path.join(DADOS, "especial_16-4*_limpo.png"))):
    achados = catch.encontrar_corpos(cv2.imread(f), [marowak], origem=(0, 0))
    falsos += [(os.path.basename(f), a[3]) for a in achados]
checar("prints sem corpo (Gyarados, shiny vivo, hotbar): nada achado", not falsos, f"({falsos})")

# hotbar sozinha: antes da correção virava "corpo" (ícones azuis ~48 px a 4 sqm)
img = cv2.imread(os.path.join(DADOS, "especial_16-41-54_limpo.png"))
baixo = dict(marowak, min_corpo=25)
achados = catch.encontrar_corpos(img, [baixo], origem=(0, 0))
na_hotbar = [a for a in achados if a[1] > img.shape[0] - catch.ESTRELA_BAIXO]
checar("hotbar nunca vira corpo (mesmo com mínimo baixo)", not na_hotbar, f"({na_hotbar})")

# cola os 2 corpos azuis do seu print no mapa, 2 sqm à direita / 1 abaixo do personagem
corpos = cv2.imread(os.path.join(S, "marowak_shiny.png"))[120:225, 20:200]
img2 = img.copy()
y0, x0 = 280 + 20, 534 + 60
img2[y0:y0 + corpos.shape[0], x0:x0 + corpos.shape[1]] = corpos
achados = catch.encontrar_corpos(img2, [marowak], origem=(0, 0))
sqms = sorted(a[3] for a in achados)
checar("acha os 2 corpos do Marowak shiny", len(achados) == 2, f"(sqm {sqms})")

# fazer_catch no fim da luta: taca ball nos corpos, sem depender de estrelinha
catch._balls_por_corpo.clear()
catch._balls_por_corpo.clear()
catch.TECLA_BALL = "b"
catch.LOOT_ANTES_BALL = False
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(img2, perfis, origem=(0, 0))


class Rastreador:
    viu_icone = False
    viu = False
    corpos = [(3490, 1950, 11)]  # corpo achado pelas estrelinhas: deve ser IGNORADO aqui
    empilhados = set()

    def pos_atual(self):
        return AQUI

    def catch_feito(self):
        pass

    def marcar_tentado(self, k):
        pass


catch.corpo_piscando = lambda *a, **k: None
acoes.clear()
catch.fazer_catch(None, Rastreador(), fim_de_luta=True)
balls = [a for a in acoes if a == ("tecla", "b")]
alvos = [acoes[i + 1] for i, a in enumerate(acoes[:-1]) if a == ("tecla", "b")]  # clique logo depois da tecla da ball
esperados = {(534 + d[0] * 51, 280 + d[1] * 51) for d in sqms}
checar("fim da luta: ball nos 2 corpos (até 3 tentativas cada)", 2 <= len(balls) <= 6
       and {(a[1], a[2]) for a in alvos} == esperados, f"({len(balls)} balls em {sorted(set(alvos))})")

# sem corpo na tela: não taca nada
catch._balls_por_corpo.clear()
catch._balls_por_corpo.clear()
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(img, perfis, origem=(0, 0))
acoes.clear()
catch.fazer_catch(None, Rastreador(), fim_de_luta=True)
checar("sem corpo azul: nenhuma ball (nem pela estrelinha)", not acoes, f"({acoes})")

# ---- corpo some durante a animação da ball e volta: tenta de novo (antes: "Fim do catch" com 1 ball) ----
catch._balls_por_corpo.clear()
chamadas = [0]


def piscando(sct, perfis):
    chamadas[0] += 1
    visivel = chamadas[0] % 3 != 2  # some 1 leitura logo depois de cada ball
    return catch.encontrar_corpos(img2 if visivel else img, perfis, origem=(0, 0))


catch.corpos_na_tela = piscando
acoes.clear()
catch.fazer_catch(None, Rastreador(), fim_de_luta=True)
balls = [a for a in acoes if a == ("tecla", "b")]
checar("corpo some na animação da ball: continua tentando (3 por corpo)", len(balls) == 6, f"({len(balls)} balls)")
acoes.clear()
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(img2, perfis, origem=(0, 0))
catch.fazer_catch(None, Rastreador(), fim_de_luta=True)
checar("luta seguinte: corpo que já levou 3 balls não ganha mais", not [a for a in acoes if a == ("tecla", "b")])
catch.PLAYER_TILE_XY = (534, 283)
real = cv2.imread(os.path.join(DADOS, "print_17-06-03.png"))[1:561, 50:1118]
checar("print das 17:06: acha o corpo do shiny do seu lado",
       [a[3] for a in catch.encontrar_corpos(real, [marowak], origem=(0, 0))] == [(-1, 1)])

# ---- print das 17:27 (sem shiny): Gyarados colado e nomes verdes não viram corpo ----
catch.PLAYER_TILE_XY = (534, 283)
p1727 = cv2.imread(os.path.join(DADOS, "print_17-27-49.png"))[1:561, 50:1118]
verde = {"nome": "verde", "tipo": "especial", "h": [59, 61], "s": [235, 255], "v": [50, 250], "min_corpo": 100}
checar("17:27: borda do Gyarados não vira corpo de shiny (nem com mínimo 25 px)",
       not catch.encontrar_corpos(p1727, [dict(marowak, min_corpo=25)], origem=(0, 0)))
checar("17:27: nomes verdes ('Heroi Alfa', 'Gyarados') não viram corpo",
       not catch.encontrar_corpos(p1727, [verde], origem=(0, 0)))

# ---- 17:32: depois de andar até o lado do corpo, ele fica logo ACIMA de você, com o seu nome por cima ----
catch.PLAYER_TILE_XY = (534, 283)
p1733 = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
checar("17:33: corpo do shiny a 5 sqm achado", [a[3] for a in catch.encontrar_corpos(p1733, [marowak], origem=(0, 0))] == [(5, -3)])
bcx, bcy = int(534 + 5 * 50.9), int(283 - 3 * 50.9)
bloco = p1733[bcy - 40:bcy + 26, bcx - 35:bcx + 35].copy()
ok = True
for d in ((1, -1), (0, -1), (-1, -1)):
    w = p1733.copy()
    tx, ty = int(534 + d[0] * 50.9), int(283 + d[1] * 50.9)
    w[ty - 40:ty + 26, tx - 35:tx + 35] = bloco
    ok &= d in [a[3] for a in catch.encontrar_corpos(w, [marowak], origem=(0, 0))]
checar("corpo logo acima de você (embaixo do seu nome): achado nos 3 sqm", ok)

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
