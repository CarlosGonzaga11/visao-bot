"""Caixa-preta (Fase 1): grava provas quando o personagem leva dano e NUNCA age. Sem cliques reais."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
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
controle.clicar = lambda *a, **k: acoes.append(("clique",)) or True
import bot
import caixa_preta
import config

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


# ---- funções puras ----
r = caixa_preta.resumo_perigo([(0, -1), (3, 3), (-2, 0), (5, 1)])
checar("resumo: monstro mais perto e quantos perto", r["mais_perto_sqm"] == 1 and r["ate_1_sqm"] == 1
       and r["ate_2_sqm"] == 2 and r["ate_3_sqm"] == 3 and r["criaturas_na_tela"] == 4, str(r))
checar("resumo sem criaturas não quebra", caixa_preta.resumo_perigo([])["mais_perto_sqm"] is None)
checar("queda de 20% conta como dano", caixa_preta.caiu(100, 80, 5))
checar("leitura falhou (None) NÃO é dano", not caixa_preta.caiu(100, None, 5) and not caixa_preta.caiu(None, 10, 5))
checar("queda pequena (3%) não conta", not caixa_preta.caiu(100, 97, 5))

# ---- leitura de criaturas no print real (17:27: Gyarados colado no personagem) ----
v = cv2.imread(os.path.join(DADOS, "print_17-27-49.png"))[1:561, 50:1118]
bot.GAME_VIEW = {"left": 0, "top": 0, "width": v.shape[1], "height": v.shape[0]}
bot.PLAYER_TILE_XY, bot.SQM_PX = (534, 303), 50.9
cri = bot.criaturas_na_imagem(v)
r = caixa_preta.resumo_perigo(cri)
checar("print 17:27: vê o pet a 2 sqm (-2, +1)", sorted(cri) == [(-2, 1)] and r["mais_perto_sqm"] == 2, f"{sorted(cri)}")

# ---- thread completa com HP falso ----
tmp = tempfile.mkdtemp(prefix="caixa_")
caixa_preta.PASTA = tmp
caixa_preta.INTERVALO_S = 0.01
caixa_preta.DEPOIS_S = 0.05
caixa_preta.ENTRE_EVENTOS_S = 0.0
caixa_preta.capturar = lambda sct, reg: v
hp_seq = iter([100, 100, None, 100, 98, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78, 78] + [78] * 50)
caixa_preta.ler_barra = lambda sct, barra: next(hp_seq) if barra == "HP" else 100
config.CAIXA_PRETA_QUEDA = 5
config.CAIXA_PRETA_MAX = 20
em_luta = [True]
cp = caixa_preta.CaixaPreta({"hp": "HP", "poke_hp": "PET"}, lambda: (3497, 1947, 11), bot.criaturas_na_imagem, em_luta)
caixa_preta.estado("WAITING_BOX")
caixa_preta.guardar_linha("[Magia] Esperando a box: 3/7 colados no monstrinho, 2 longe\n")
caixa_preta.anotar("canto_da_box: teste")
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    for _ in range(6):
        cp.passo(None)
eventos = os.listdir(tmp)
for _ in range(100):  # o evento é salvo em outra thread (JPEGs + leitura de criaturas)
    if eventos and os.path.exists(os.path.join(tmp, eventos[0], "evento.json")):
        break
    time.sleep(0.1)
    eventos = os.listdir(tmp)
checar("queda 98→78 virou 1 evento (100→98 e None não)", len(eventos) == 1 and cp.eventos == 1, f"{eventos}")
dados = json.load(open(os.path.join(tmp, eventos[0], "evento.json"), encoding="utf-8")) if eventos else {}
checar("evento: perda, estado e perigo certos", dados.get("perda") == 20 and dados.get("estado") == "WAITING_BOX"
       and dados.get("perigo", {}).get("mais_perto_sqm") == 2, f"{dados.get('perda')} {dados.get('estado')}")
lt = dados.get("linha_do_tempo", [])
idx = [i for i, q in enumerate(lt) if q["dano"]]
checar("evento: quadros de ANTES e DEPOIS do dano", len(idx) == 1 and 0 < idx[0] < len(lt) - 1
       and all(os.path.exists(os.path.join(tmp, eventos[0], q["quadro"])) for q in lt), f"{len(lt)} quadros")
checar("evento: leva o log e as decisões", any("Esperando a box" in l for l in dados.get("log_recente", []))
       and any("canto_da_box" in l for l in dados.get("decisoes", [])))
checar("avisa no log o que aconteceu", "Você perdeu 20%" in saida.getvalue(), saida.getvalue().strip()[:120])

# resumo da luta
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    em_luta[0] = False
    cp.passo(None)
checar("fim da luta: escreve o HP mínimo", "de 100% a 78%" in saida.getvalue(), saida.getvalue().strip()[:120])

# limite de eventos
config.CAIXA_PRETA_MAX = 1
hp_seq = iter([78, 50, 50, 50, 50, 50, 50, 50, 50, 50])
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    cp.passo(None); cp.passo(None)
checar("limite de eventos: não salva mais", len(os.listdir(tmp)) == 1 and "limite" in saida.getvalue())

# pausado: nada de evento (e estado PAUSED aparece)
controle._pausado.set()
checar("pausado: estado PAUSED", caixa_preta.estado_atual() == "PAUSED")
controle._pausado.clear()
checar("estado do bot volta depois da pausa", caixa_preta.estado_atual() == "WAITING_BOX")

checar("caixa-preta NUNCA clicou nem apertou nada", acoes == [], str(acoes))
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
