"""
Modo NORMAL: o pet morreu no meio da luta → usa revive (09/11 15:40: só os modos revive/outland tinham o
revive de reserva da luta; no normal, se o vigia falhasse — painel na frente do jogo —, só esperava/alarmava).
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
teclas = []
controle.clicar = lambda *a, **k: True
controle.apertar = lambda t: teclas.append(t) or True
controle.esperar = lambda s: time.sleep(min(s, 0.05)) or False
import bot
import config
import cura

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


config.SAIR_DA_BOX = False
config.IGNORAR_SOBRA = False
config.CLICAR_ALVO = False
config.TECLA_REVIVE = "r"
config.REVIVE_SE_MORRER = True
config.REVIVE_CLICAR_POKE = False
config.REVIVE_ESPERA = 0.05
bot.POKESTOP_ATIVO = False
bot.ORDER_DEPOIS_LUTA = False
bot.fight_mode = lambda q: None
bot.fazer_catch = lambda *a, **k: None
bot.descansar = lambda sct: None
bot.checar_catch = lambda sct: None
bot.efeitos.curar_se_precisar = lambda sct: False
bot.carregar_calibracao = lambda: {"poke_hp": {"x": 1}}
bot.sqm_ocupados = lambda sct: set()
bot.alarmar_e_pausar = lambda *a, **k: None
bot.esperar_agrupar = lambda sct: True
bot.modos.TECLA_ATAQUE = "q"
bot.modos.INTERVALO_ATAQUE = 0.05

# pet morto (barra 0) até o revive sair; depois vivo
vivo = [False]
bot.ler_barra = lambda sct, b: 90 if vivo[0] else 0
orig_apertar = controle.apertar


def apertar(t):
    if t == "r":
        vivo[0] = True  # o revive trouxe o pet de volta
    return orig_apertar(t)


controle.apertar = apertar
n = [0]


def inimigos(sct):
    n[0] += 1
    return [{"alvo": True, "xy": (5, 5)}] if n[0] < 40 else []


bot.inimigos = inimigos
bot.ESTRATEGIA = bot.modos.Normal()
controle.ultimo_revive = 0.0
bot.SEM_PET_CARENCIA_S = 0.2
bot.TIMEOUT_COMBATE = 4.0
bot.combater_ate_limpar(None, bot.LOTOU)
i_r = teclas.index("r") if "r" in teclas else None
checar("modo NORMAL, pet morto na luta: usa o revive", i_r is not None, f"{teclas[:8]}")
checar("nenhum combo enquanto o pet estava morto (só depois do revive)", i_r is not None and "q" not in teclas[:i_r],
       f"{teclas[:8]}")
checar("depois do revive volta a combar", i_r is not None and "q" in teclas[i_r:], f"{teclas[:8]}")
checar("um revive só (não fica apertando)", teclas.count("r") == 1, f"({teclas.count('r')} revives)")

# revive desligado no painel: não usa
teclas.clear()
vivo[0] = False
n[0] = 0
controle.ultimo_revive = 0.0
config.REVIVE_SE_MORRER = False
bot.TIMEOUT_COMBATE = 1.0
bot.combater_ate_limpar(None, bot.LOTOU)
checar("'revive se morrer' desligado: modo normal não usa revive", "r" not in teclas, f"{teclas[:6]}")
config.REVIVE_SE_MORRER = True

checar("vigia do pet tenta até 3 revives por morte (antes 2)", cura.REVIVE_TENTATIVAS == 3)

# ---------- modo NORMAL rápido (pedido 09/11): não corre da box, mata e segue ----------
cliques = []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": cliques.append(botao) or True
config.SAIR_DA_BOX = True
config.NORMAL_SEM_FUGIR = True
bot.esperar_chegar = lambda antes, d, espera_inicio=1.0: True
bot.POS = type("P", (), {"atual": lambda self: (1000, 1000, 7)})()
bot.MAPA.esta_bloqueado = lambda p: False
bot.limites_clique = lambda sct: ((-9, 9), (-4, 4))
bot.ler_barra = lambda sct, b: 90
box = {(0, -2), (-1, -2), (1, -2), (0, -3), (0, -1), (-1, -1)}  # box colada em você
bot.sqm_ocupados = lambda sct: set(box)

for modo, deve in (("normal", False), ("revive", True), ("outland", True)):
    bot.ESTRATEGIA = bot.modos.Normal() if modo == "normal" else (bot.modos.Revive() if modo == "revive" else bot.modos.Outland())
    bot.CORRIDAS[0] = bot.EMERGENCIAS[0] = 0
    bot.PET_ABS[0] = None
    bot.ANDANDO[0] = None
    cliques.clear()
    bot.sair_da_box("sct")
    checar(f"modo {modo}: {'sai' if deve else 'NÃO sai'} da box depois do pokestop", bool(cliques) == deve, f"({len(cliques)} cliques)")

bot.ESTRATEGIA = bot.modos.Normal()
cliques.clear()
bot.ULTIMA_VIGIA[0] = 0.0
bot.vigiar_no_combo("sct")
checar("modo normal: a vigia do combo não corre", not cliques)

config.NORMAL_SEM_FUGIR = False
bot.CORRIDAS[0] = bot.EMERGENCIAS[0] = 0
bot.PET_ABS[0] = None
cliques.clear()
bot.sair_da_box("sct")
checar("opção desligada: modo normal volta a sair da box", bool(cliques))
config.NORMAL_SEM_FUGIR = True

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
