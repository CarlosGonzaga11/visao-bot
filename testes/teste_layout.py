"""
Layout: o tamanho do mapa MUDA (09/11: barra de ícones/chat maior → sqm 48,45 px) e o bot recusava a medida
nova ("mapa estranho") e usava a antiga 50,9 px. Agora aceita medida plausível repetida. Sem cliques reais.
"""
import json
import os
import sys
import tempfile

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import layout

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


# medição real no print de hoje (janela em (0, 23))
im = cv2.imread(os.path.join(DADOS, "alarme_11-09_15-42-03.png"))
m = layout.medir_mapa(im, (0, 23))
checar("print 09/11 15:42: mapa medido = sqm 48,45, personagem (584, 293)", m and m["sqm"] == 48.45 and m["centro"] == (584, 293), f"{m}")
gv = m["game_view"]
checar("as contas fecham: largura/21 e altura/11 ≈ sqm, centro no meio do mapa",
       abs(gv["width"] / 21 - m["sqm"]) < 0.5 and abs(gv["height"] / 11 - m["sqm"]) < 0.5
       and abs(gv["left"] + gv["width"] / 2 - m["centro"][0]) <= 2 and abs(gv["top"] + gv["height"] / 2 - m["centro"][1]) <= 2)
antigo = layout.medir_mapa(cv2.imread(os.path.join(DADOS, "print_21-05-47.png")), (0, 23))
checar("print antigo 07/11: continua 50,91", antigo and antigo["sqm"] == 50.91, f"{antigo}")

# regra de conferência
tmp = tempfile.mkdtemp()
layout.ARQ_LAYOUT_OK = os.path.join(tmp, "layout_ok.json")
json.dump({"1366x705": {"game_view": {"left": 50, "top": 27, "width": 1069, "height": 560}, "sqm": 50.9,
                        "centro": [584, 307]}}, open(layout.ARQ_LAYOUT_OK, "w"))
janela = {"left": 0, "top": 23, "width": 1366, "height": 705}
nova = dict(m, janela=janela)
layout.time = __import__("time")
seq = []
layout.detectar = lambda sct: dict(seq.pop(0)) if seq else {}
import time as _t
_dorme = _t.sleep
_t.sleep = lambda s: None

seq[:] = [nova]
r = layout._conferir_mapa(None, dict(nova))
salvo = json.load(open(layout.ARQ_LAYOUT_OK))["1366x705"]
checar("medida nova plausível e repetida igual: ACEITA (antes recusava)", r["sqm"] == 48.45 and salvo["sqm"] == 48.45, f"{r['sqm']} / salvo {salvo['sqm']}")

json.dump({"1366x705": {"game_view": {"left": 50, "top": 27, "width": 1069, "height": 560}, "sqm": 50.9,
                        "centro": [584, 307]}}, open(layout.ARQ_LAYOUT_OK, "w"))
ruim = {"janela": janela, "game_view": {"left": 139, "top": 60, "width": 954, "height": 500}, "sqm": 45.45, "centro": (616, 310)}
seq[:] = [dict(ruim)]
r = layout._conferir_mapa(None, dict(ruim))
checar("medida implausível (topo do mapa em y=60, painel na frente): usa a guardada", r["sqm"] == 50.9, f"{r['sqm']}")

seq[:] = [dict(antigo, janela=janela)]
r = layout._conferir_mapa(None, dict(nova))
checar("medida nova que NÃO se repete (2ª deu outra): usa a guardada", r["sqm"] == 50.9, f"{r['sqm']}")
_t.sleep = _dorme

# ---------- medida PELO PERSONAGEM (a borda erra com a barra de ícones no topo) ----------
J = {"left": 0, "top": 23, "width": 1366, "height": 705}
p1803 = cv2.imread(os.path.join(DADOS, "alarme_11-08_18-03-16.png"))
borda = layout.medir_mapa(p1803, (0, 23))
pers = layout.medir_pelo_personagem(p1803, J)
checar("08/11 18:03 (barra de ícones): a BORDA erra (45,8 px, topo do mapa em y=63) — o mesmo erro de 09/11 ao vivo",
       borda and borda["sqm"] < 46.5 and not layout._plausivel(dict(borda, janela=J)), f"{borda}")
checar("08/11 18:03: pelo PERSONAGEM dá 49,3 px, centro (584, 298)", pers and 49 <= pers["sqm"] <= 49.5 and pers["centro"] == (584, 298),
       f"{pers}")
p_hoje = layout.medir_pelo_personagem(im, J)
checar("09/11 15:42: pelo personagem ≈ borda (48,7 x 48,45)", p_hoje and abs(p_hoje["sqm"] - m["sqm"]) <= 0.5, f"{p_hoje}")
p_antigo = layout.medir_pelo_personagem(cv2.imread(os.path.join(DADOS, "print_21-05-47.png")), J)
checar("07/11: pelo personagem = 50,9 e centro (584, 307)", p_antigo and abs(p_antigo["sqm"] - 50.9) < 0.1 and p_antigo["centro"] == (584, 307),
       f"{p_antigo}")


class FakeSct:
    def __init__(self, img):
        self.img = img

    def grab(self, r):
        corte = self.img[r["top"] - 23:r["top"] - 23 + r["height"], r["left"]:r["left"] + r["width"]]
        return np.dstack([corte, np.full(corte.shape[:2], 255, np.uint8)])


import numpy as np
json.dump({"1366x705": {"game_view": {"left": 50, "top": 27, "width": 1069, "height": 560}, "sqm": 50.9,
                        "centro": [584, 307]}}, open(layout.ARQ_LAYOUT_OK, "w"))
_t.sleep = lambda s: None
r = layout._conferir_mapa(FakeSct(p1803), dict(borda, janela=J))
salvo = json.load(open(layout.ARQ_LAYOUT_OK))["1366x705"]
checar("ao vivo com a borda errada: usa a medida do PERSONAGEM (antes: 50,9 guardado) e guarda",
       abs(r["sqm"] - 49.27) < 0.1 and r["centro"] == (584, 298) and abs(salvo["sqm"] - 49.27) < 0.1, f"{r['sqm']} {r['centro']}")
r = layout._conferir_mapa(FakeSct(cv2.imread(os.path.join(DADOS, "print_21-05-47.png"))),
                          dict(antigo, janela=J))
checar("borda e personagem batem (07/11): fica com a borda", r["sqm"] == 50.91, f"{r['sqm']}")
_t.sleep = _dorme

# 09/11 18:20 (Heroi Alfa): borda CERTA (48,45) e "personagem" ERRADO (46,55, pegou outra criatura em x=572)
_t.sleep = lambda s: None
json.dump({"1366x705": {"game_view": {"left": 72, "top": 27, "width": 1023, "height": 536}, "sqm": 48.73,
                        "centro": [584, 295]}}, open(layout.ARQ_LAYOUT_OK, "w"))
errado = {"sqm": 46.55, "centro": (572, 283), "game_view": {"left": 83, "top": 27, "width": 978, "height": 512}}
orig_pers = layout._pelo_personagem_ao_vivo
layout._pelo_personagem_ao_vivo = lambda sct, j: dict(errado)
r = layout._conferir_mapa("sct", dict(m, janela=J))
checar("18:20: borda plausível (48,45) x personagem errado (46,55): fica com a BORDA", r["sqm"] == 48.45 and r["centro"] == (584, 293),
       f"{r['sqm']} {r['centro']}")
layout._pelo_personagem_ao_vivo = orig_pers
_t.sleep = _dorme

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
