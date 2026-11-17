"""
Segurança (07/11): player na tela (sem caveira), fala no Default e mensagem privada (aba nova).
Prints reais: 21:36 (aba "Game Chat PT-BR" ativa, Default vermelha), 22:29 (Default ativa), 19:21
(cidade: vários players; 4ª aba "NPCs"), quadros de luta 22:07 (sem player). Sem cliques reais.
"""
import glob
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import numpy as np
import controle
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
import chat
import config
import players

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


def img(nome):
    return cv2.imread(os.path.join(DADOS, nome))


def barra(nome):
    return img(nome)[573:599, 20:1030]  # barra de abas (print da janela 1366x705)


# ---------- 1. barra de abas ----------
ab = chat.ler_abas(barra("alarme_21-36-31.png"))
checar("21:36: Default vermelha, Game Chat ativa", [a["estado"] for a in ab] == ["vermelha", "vermelha", "vermelha", "ativa"],
       f"{[a['estado'] for a in ab]}")
ab = chat.ler_abas(barra("print_22-29-23.png"))
checar("22:29: Default ativa (3 abas)", [a["estado"] for a in ab] == ["ativa", "vermelha", "vermelha"], f"{[a['estado'] for a in ab]}")
nomes = [chat.ler_nome_aba(a) for a in chat.ler_abas(barra("alarme_21-36-31.png"))]
checar("OCR dos nomes das abas", nomes == ["Default", "Server Log", "Loot", "Game Chat PT-BR"], f"{nomes}")

# ---------- 2. mensagem privada = aba nova ----------
v = chat.VigiaAbas()
base = chat.ler_abas(barra("print_22-29-23.png"))
checar("começo: só guarda a linha de base", v.checar(base) == [] and v.base == 3)
checar("nada mudou: sem alarme", v.checar(base) == [])
# PM simulada: aba nova à direita (cópia da aba "Loot", cinza = normal)
b = barra("print_22-29-23.png").copy()
loot = base[2]
pedaco = b[:, loot["x0"] - 2:loot["x1"] + 3].copy()
cinza = pedaco.copy()
texto = cinza.max(axis=2) > 70
cinza[texto] = (140, 140, 140)
b[:, 400:400 + pedaco.shape[1]] = cinza
ev = v.checar(chat.ler_abas(b))
checar("aba nova à direita = mensagem privada", [m for m, _ in ev] == ["aba nova"], f"{ev and [m for m, _ in ev]}")
checar("a mesma aba depois: não toca de novo", v.checar(chat.ler_abas(b)) == [])
vermelho = b.copy()
seg = vermelho[:, 400:400 + pedaco.shape[1]]
seg[seg.max(axis=2) > 70] = (40, 40, 220)  # BGR vermelho
ev = v.checar(chat.ler_abas(vermelho))
checar("aba da PM fica vermelha de novo = outra mensagem", [m for m, _ in ev] == ["mensagem nova na aba"], f"{ev and [m for m, _ in ev]}")
checar("fechou a aba: volta para a linha de base", v.checar(base) == [] and v.base == 3)
config.ALARME_ABAS_IGNORAR = "NPCs, Game Chat, Trade, Help"
checar("aba 'NPCs' e 'Game Chat PT-BR' não são PM", chat.aba_ignorada("NPCs") and chat.aba_ignorada("Game Chat PT-BR"))
checar("aba 'Beltrano' (nome de player) é PM", not chat.aba_ignorada("Beltrano"))

# ---------- 3. falas no Default ----------
config.MEU_NOME = "Heroi Alfa"
f = chat.FiltroFalas()
checar("player falando: toca", f.decidir("21:36 Fulano Silva (Titan 2): Que arrogancia", 0)[0])
checar("a MESMA fala 1 s depois: não toca (antes tocava 2x)", not f.decidir("21:36 Fulano Silva (Titan 2): Que arrogancia", 1)[0])
checar("sua própria fala: não toca", not f.decidir("21:12 Heroi Alfa (167): tem algum", 2)[0])
checar("seu nome com erro de OCR: não toca", not f.decidir("22:50 Heroi Alfn (172): desce", 3)[0])
checar("NPC: não toca", not f.decidir("19:19 Mark: Good bye!", 4)[0])
checar("não deu para ler quem falou: toca (segurança primeiro)", f.decidir("= - sone", 5)[0])
checar("a mesma fala 20 s depois: toca de novo", f.decidir("21:36 Fulano Silva (Titan 2): Que arrogancia", 21)[0])


class FakeSct:
    """grab(região da TELA) recorta o print da janela (janela em y=23 na tela)."""

    def __init__(self, im):
        self.im = im

    def grab(self, r):
        y, x = r["top"] - 23, r["left"]
        corte = self.im[y:y + r["height"], x:x + r["width"]]
        return np.dstack([corte, np.full(corte.shape[:2], 255, np.uint8)])


chat.CHAT_REGION = {"left": 18, "top": 626, "width": 600, "height": 68}
disparos = []
chat.disparar = lambda sct, faixa=None, texto=None, motivo="", pausar=None: disparos.append((motivo, texto))
m = chat.MonitorChat()
m.passo(FakeSct(img("print_22-29-23.png")))
m.passo(FakeSct(img("alarme_21-36-31.png")))  # trocou para o Game Chat (aba nova 'Game Chat PT-BR' = ignorada)
checar("chat global (aba Game Chat ativa): nenhum alarme de fala", not [d for d in disparos if "fala" in d[0]], f"{disparos}")
checar("Game Chat aberto não conta como mensagem privada", not [d for d in disparos if "PRIVADA" in d[0]], f"{disparos}")

# ---------- 4. leitura da Battle (grade de 30 px a partir da 1ª barra) ----------
import config as _cfg
import tela

_tpl = tela._template("battle")


def battle(nome):
    im = img(nome)
    r = cv2.matchTemplate(im, _tpl, cv2.TM_CCOEFF_NORMED)
    _, _, _, (x, y) = cv2.minMaxLoc(r)
    reg = {"left": x + _cfg.BATTLE_ANCORA_OFFSET[0], "top": y + _cfg.BATTLE_ANCORA_OFFSET[1],
           "width": _cfg.BATTLE_REGION["width"], "height": _cfg.BATTLE_REGION["height"]}
    return im[reg["top"]:reg["top"] + reg["height"], reg["left"]:reg["left"] + reg["width"]], reg


for nome, certo, porque in (
        ("alarme_11-06_14-59-08.png", 5, "Gloom + 4 Geodude, 1 alvo (nome vermelho): antes lia 7"),
        ("print_17-06-03.png", 1, "só o pet: antes lia 2 (barra fantasma no cabeçalho)"),
        ("alarme_19-21-22.png", 6, "pet + 5 Sandslash, 1 alvo: antes lia 8"),
        ("print_22-29-23.png", 2, "pet + Marowak ALVO a ~1% (barra vazia): conta pelo nome vermelho"),
        ("alarme_11-06_18-58-11.png", 1, "só o Dugtrio (pet)")):
    linhas = tela.analisar_battle(*battle(nome))
    checar(f"Battle {nome}: {certo} linha(s) — {porque}", len(linhas) == certo, f"(leu {len(linhas)})")
linhas = tela.analisar_battle(*battle("print_22-29-23.png"))
checar("22:29: a linha do Marowak quase morto é o ALVO", linhas[1]["alvo"])

# ---------- 5. player na tela = criatura na tela que não está na Battle ----------
# (1ª versão usava a caveira acima do nome: só existe nas hunts 150+ → alarme falso 23:06)


def caso(nome):
    im = img(nome)
    na = players.criaturas_na_tela(im[1:561, 50:1118], (50, 1), centro=(584, 304), sqm=50.9)
    n, cheia = players.linhas_battle(*battle(nome))
    return na, n, cheia


na, n, cheia = caso("alarme_11-06_18-58-11.png")
checar("06/11 18:58: player Ciclano + o Venusaur dele = 2 estranhos", players.estranhos(na, n) == 2, f"(tela {len(na)} x battle {n})")
na, n, cheia = caso("alarme_11-07_23-06-28.png")
checar("23:06 (hunt sem caveira, o alarme falso): 0 estranhos", players.estranhos(na, n) == 0, f"(tela {len(na)} x battle {n})")
for nome in ("print_21-05-47.png", "print_22-29-23.png", "alarme_21-36-31.png", "print_17-27-49.png"):
    na, n, cheia = caso(nome)
    checar(f"hunt {nome}: 0 estranhos", players.estranhos(na, n) == 0, f"(tela {len(na)} x battle {n})")
checar("quase morto (barra 0–3 px) na tela não conta", players.PREENCH_MIN == 4)

alarmes = []
vp = players.VigiaPlayers(alarmar=lambda sct, texto: alarmes.append(texto))
com = caso("alarme_11-06_18-58-11.png")
sem = caso("alarme_11-07_23-06-28.png")
seq = [com, sem, com, com, com]  # oscila (monstro escondido): 4 das últimas 6 bastam
r = [vp.passo(None, leitura=l, agora=t * 0.5) for t, l in enumerate(seq)]
checar("player na tela (contagem oscilando): alarme com 4 das últimas 6 leituras, 1 vez", len(alarmes) == 1 and r[4] is not None,
       f"{len(alarmes)} alarmes")
for t in (3.0, 5.0, 14.0):
    vp.passo(None, leitura=sem, agora=t)
for t in (15, 15.5, 16, 16.5):
    vp.passo(None, leitura=com, agora=t)
checar("foi embora 10 s e voltou: toca de novo", len(alarmes) == 2, f"{len(alarmes)} alarmes")
antes = len(alarmes)
vp2 = players.VigiaPlayers(alarmar=lambda sct, texto: alarmes.append(texto))
for t in range(10):
    vp2.passo(None, leitura=sem, agora=t * 0.5)
checar("hunt normal por 5 s: nenhum alarme", len(alarmes) == antes)
vp3 = players.VigiaPlayers(alarmar=lambda sct, texto: alarmes.append(texto))
for t in range(6):
    vp3.passo(None, leitura=(com[0], com[1], True), agora=t * 0.5)
checar("Battle cheia (não dá para saber): não toca", len(alarmes) == antes)

# ---------- 6. alarmes FALSOS de 08/11 (layout com a barra de ícones; centro do personagem = (584, 272)) ----------
def caso_inteiro(nome):
    im = img(nome)
    na = players.criaturas_na_tela(im, (0, 0), centro=(584, 272), sqm=50.9)
    n, cheia = players.linhas_battle(*battle(nome))
    return na, n, cheia


na, n, cheia = caso_inteiro("alarme_11-08_18-05-26.png")
checar("08/11 18:05: os 2 Marowak ROSA (anti-block) não contam → 0 estranhos", players.estranhos(na, n) == 0,
       f"(tela {na} x battle {n})")
na, n, cheia = caso_inteiro("alarme_11-08_18-03-16.png")
checar("08/11 18:03: Battle MINIMIZADA lê 0 linhas", n == 0, f"({n})")
vp4 = players.VigiaPlayers(alarmar=lambda sct, texto: alarmes.append(texto))
antes = len(alarmes)
for t in range(8):
    vp4.passo(None, leitura=(na, n, cheia), agora=t * 0.5)
checar("Battle minimizada (0 linhas) por 4 s: nenhum alarme (não dá para saber)", len(alarmes) == antes)
na, n, cheia = caso_inteiro("alarme_11-08_18-21-07.png")
checar("08/11 18:21 (logo depois do revive): 0 estranhos", players.estranhos(na, n) == 0, f"(tela {na} x battle {n})")
barras = tela.encontrar_barras_criaturas(img("alarme_11-08_18-05-26.png"), (0, 0))
checar("ícone da barra de ícones (topo) não vira 'barra vazia' fantasma", not [b for b in barras if b[1] < 40 and b[2] == 0],
       f"{[b for b in barras if b[1] < 40]}")

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
