"""Testes simulados das 4 correções críticas. Nenhum clique/tecla de verdade."""
import os
import sys
import threading
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import pydirectinput
import controle
import humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade

feitos = []
humano.clicar = lambda x, y, botao="left": feitos.append(("clique", botao, time.time()))
humano.tecla = lambda t: feitos.append(("tecla", t, time.time()))
controle.jogo_no_ponto = lambda x, y: True
controle.jogo_em_foco = lambda: True

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


# ---------- 1. Pausa ----------
feitos.clear()
controle._pausado.set()
r1, r2 = controle.clicar(100, 100), controle.apertar("f1")
checar("pausado: clicar/apertar não agem", not feitos and r1 is False and r2 is False)
controle._pausado.clear()
checar("despausado: clicar/apertar agem", controle.clicar(100, 100) and controle.apertar("f1") and len(feitos) == 2)

# jogo coberto -> pausa enquanto espera -> jogo volta: NÃO pode clicar
feitos.clear()
coberto = [True]
controle.jogo_no_ponto = lambda x, y: not coberto[0]
ret = []
t = threading.Thread(target=lambda: ret.append(controle.clicar(200, 200)))
t.start()
time.sleep(0.8)
controle._pausado.set()
time.sleep(0.6)
coberto[0] = False
t.join(timeout=3)
checar("pausou esperando o jogo: não clica quando o jogo volta",
      not t.is_alive() and ret == [False] and not feitos)
controle._pausado.clear()
controle.jogo_no_ponto = lambda x, y: True

# ---------- FailSafe vira parada normal ----------
def _fs(t):
    raise pydirectinput.FailSafeException("canto")
humano.tecla = _fs
try:
    controle.apertar("f1")
    checar("FailSafe -> ParadaSolicitada", False, "(não lançou)")
except controle.ParadaSolicitada:
    checar("FailSafe -> ParadaSolicitada", controle.deve_parar())
controle._parar.clear()
humano.tecla = lambda t: feitos.append(("tecla", t, time.time()))

# ---------- bot (importa depois dos stubs) ----------
import bot
bot.sqm_ocupados = lambda sct: set()  # tela: ninguém na tela (luta segue como antes)
bot.ler_barra = lambda sct, barra: None  # barra do pet: desconhecida (luta segue como antes)
import config
import tela

cliques_bot = []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": (cliques_bot.append((botao, time.time())), True)[1]

# ---------- 2. Orders em thread x luta ----------
# referência: sem luta, o order depois da luta sai
bot.ORDER_AO_ANDAR[0] = True
bot.order_ao_andar_se_pendente()
time.sleep(1.5)
checar("sem luta: order atrasado sai normalmente", len(cliques_bot) >= 1, f"({len(cliques_bot)} order(s))")

# com luta começando logo depois do 1º passo: nenhum order depois do pokestop
for tentativa in range(5):
    cliques_bot.clear()
    bot.ORDER_AO_ANDAR[0] = True
    bot.order_ao_andar_se_pendente()           # thread dorme 0,12–0,35 s antes do order
    time.sleep(0.05)
    bot.EM_LUTA[0] = True
    bot.cancelar_orders()                       # o que combater_ate_limpar faz agora
    pokestop = time.time()
    time.sleep(2.0)
    depois = [c for c in cliques_bot if c[1] > pokestop]
    bot.EM_LUTA[0] = False
    if depois or cliques_bot:
        break
checar("luta começou: order atrasado NÃO sai", not cliques_bot, f"({len(cliques_bot)} order(s) indevidos)")

# order andando (orders_em_paralelo) cancelado no meio da espera
cliques_bot.clear()
bot.orders_em_paralelo((100, 100, 7), (110, 100, 7))
time.sleep(0.02)
bot.EM_LUTA[0] = True
t0 = time.time()
bot.cancelar_orders()
espera = time.time() - t0
time.sleep(1.2)
bot.EM_LUTA[0] = False
checar("order andando cancelado", not cliques_bot and not bot._order_rodando.is_set(),
       f"(cancelar levou {espera:.2f}s)")

# pausa também bloqueia o order da thread
cliques_bot.clear()
controle._pausado.set()
bot.ORDER_AO_ANDAR[0] = True
bot.order_ao_andar_se_pendente()
time.sleep(1.0)
controle._pausado.clear()
checar("pausado: thread de order não age", not cliques_bot)

# ---------- 3. Luta que estoura o tempo fecha direito (outland) ----------
import modos
linha = {"alvo": True, "xy": (50, 50), "nome_img": None}
bot.inimigos = lambda sct: [linha]
tela.ler_inimigos = lambda sct: [linha]
bot.TIMEOUT_COMBATE = 0.5
bot.MAGIA_AGRUPAR_ATIVA = False
bot.POKESTOP_ATIVO = False
config.IGNORAR_SOBRA = False
bot.efeitos.curar_se_precisar = lambda sct: False
catch_chamado = []
bot.fazer_catch = lambda sct, r, **k: catch_chamado.append(1)
bot.descansar = lambda sct: None
bot.ORDER_DEPOIS_LUTA = False
modos.COMBO_DURACAO = 0.1
out = modos.Outland()
revives = []
out.usar_revive = lambda sct, motivo: (revives.append(motivo), False)[1]
out.sem_progresso = 3
bot.ESTRATEGIA = out
bot.combater_ate_limpar(None, bot.LOTOU)
checar("timeout: catch e fim do modo rodaram",
       bool(catch_chamado) and any("lure limpo" in m for m in revives),
       f"(revives: {revives})")
checar("timeout: contadores do outland zerados", out.sem_progresso == 0 and out.na_luta == 0 and out.qtd_antes is None)
checar("timeout: EM_LUTA volta a False", bot.EM_LUTA[0] is False)

# ---------- 4. Erro de captura de tela ----------
esperas = []
controle.esperar = lambda s: esperas.append(s) or False
pausas = []
controle.pausar = lambda motivo="": pausas.append(motivo)
bot.chat.tocar_som = lambda *a: None
e = bot.ErroDeTela()
agora = [1000.0]
bot.time.time = lambda: agora[0]
import mss.exception
for i in range(40):  # 40 falhas a cada 2 s = 80 s
    e.aconteceu(mss.exception.ScreenShotError("BitBlt"))
    agora[0] += 2
checar("erro de tela: espera em vez de morrer e pausa só 1x depois de 60 s",
       len(esperas) == 40 and len(pausas) == 1)
agora[0] += 30  # voltou ao normal; falha nova depois = episódio novo, sem pausa imediata
e.aconteceu(mss.exception.ScreenShotError("BitBlt"))
checar("erro de tela: falha nova não pausa na hora", len(pausas) == 1)

# o laço principal trata ScreenShotError dentro do while (não fora)
import ast
arvore = ast.parse(open(os.path.join(PASTA, "bot.py"), encoding="utf-8").read())
fn = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "rodar_cavebot")
ok = False
for w in ast.walk(fn):
    if isinstance(w, ast.While):
        for t in w.body:
            if isinstance(t, ast.Try) and any("ScreenShotError" in ast.unparse(h.type) for h in t.handlers):
                ok = True
checar("laço principal: try/except ScreenShotError dentro do while", ok)

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
