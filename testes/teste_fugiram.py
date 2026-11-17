"""Battle com monstros a ~2% (fugiram, fora da tela): continuam inimigos e o bot não espera 28 s."""
import os, sys, time
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import cv2, numpy as np
import controle, humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
controle.clicar = lambda *a, **k: True; controle.apertar = lambda *a, **k: True
import tela
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
img = cv2.imread(os.path.join(DADOS, "print_19-40-55.png"))
battle = img[130:330, 8:208].copy()
linhas = tela.analisar_battle(battle, {"left": 8, "top": 130})
checar("Battle 19:40: 3 linhas (Gyarados + 2 Marowak a ~2%)", len(linhas) == 3, f"({len(linhas)})")
checar("Marowak com ~2% de vida NÃO vira 'roxo/não atacável'", linhas and not any(l["rosa"] for l in linhas),
       f"({[l['rosa'] for l in linhas]})")
roxo = battle.copy()
y = 192 - 130
roxo[y - 2:y + 3, 48:120] = (200, 60, 140)  # barra roxa de verdade
l2 = tela.analisar_battle(roxo, {"left": 8, "top": 130})
checar("barra roxa de verdade continua não atacável", any(l["rosa"] for l in l2))
# --- luta com os 2 fora da tela ---
import bot, config
bot.ler_barra = lambda sct, b: None
config.IGNORAR_SOBRA = False; config.CLICAR_ALVO = False; config.SAIR_DA_BOX = False
bot.POKESTOP_ATIVO = False; bot.ORDER_DEPOIS_LUTA = False
bot.fazer_catch = lambda *a, **k: None; bot.descansar = lambda sct: None
bot.efeitos.curar_se_precisar = lambda sct: False
bot.inimigos = lambda sct: [{"alvo": False, "xy": (5, 5)}] * 2
bot.checar_catch = lambda sct: None
bot.sqm_ocupados = lambda sct: {(1, -1)}  # só o pet na tela
bot.MAGIA_ESPERA_MAX = 4.5
bot.TIMEOUT_COMBATE = 60
class N(bot.modos.Normal):
    def atacar(self, sct): return False
bot.ESTRATEGIA = N()
t = time.time()
r = bot.combater_ate_limpar(None, bot.LOTOU)
gasto = time.time() - t
checar("monstros fora da tela: segue a hunt em ~3 s (não 28 s)", r == bot.LUTA_FORA_DE_ALCANCE and gasto < 6, f"({r}, {gasto:.1f}s)")
# monstros visíveis: não sai
bot.sqm_ocupados = lambda sct: {(1, -1), (2, -1), (1, -2)}
bot.MAGIA_ESPERA_MAX = 0.5
chamadas = [0]
def inimigos(sct):
    chamadas[0] += 1
    return [{"alvo": True, "xy": (5, 5)}] * 2 if chamadas[0] < 15 else []
bot.inimigos = inimigos
r = bot.combater_ate_limpar(None, bot.LOTOU)
checar("monstros na tela: luta normalmente (não 'sumiram')", r == bot.LUTA_LIMPOU, f"({r})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
