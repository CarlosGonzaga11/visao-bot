"""Alarme 'sem monstrinho' falso (19:17): 1 s depois do revive e depois de 14 s na espera da box."""
import os, sys, time
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
controle.clicar = lambda *a, **k: True; controle.apertar = lambda *a, **k: True
controle.esperar = lambda s: time.sleep(min(s, 0.05)) or False
import bot, config
config.SAIR_DA_BOX = False; config.IGNORAR_SOBRA = False; config.CLICAR_ALVO = False
bot.POKESTOP_ATIVO = False; bot.ORDER_DEPOIS_LUTA = False
bot.fazer_catch = lambda *a, **k: None; bot.descansar = lambda sct: None
bot.efeitos.curar_se_precisar = lambda sct: False
bot.carregar_calibracao = lambda: {"poke_hp": {"x": 1}}
bot.sqm_ocupados = lambda sct: set()
linha = {"alvo": True, "xy": (5, 5)}
alarmes = []
bot.alarmar_e_pausar = lambda sct, texto, motivo, prefixo: alarmes.append(motivo)
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
class Normal(bot.modos.Normal):
    def atacar(self, sct): return False
bot.ESTRATEGIA = Normal()
# Cenário 19:17: espera da box demora (pet vivo o tempo todo dentro dela); aí o pet morre e é revivido 1 s antes
t0 = [0.0]
def barra(sct, b):
    dt = time.time() - t0[0]
    return 80 if dt < 1.5 else 0  # vivo durante a espera; depois morreu (Back!)
bot.ler_barra = barra
chamadas = [0]
def esperar_agrupar(sct):
    chamadas[0] += 1
    if chamadas[0] == 1:
        fim = time.time() + 1.4
        while time.time() < fim:   # "14 s" na espera, lendo a barra do pet (vivo)
            bot.anotar_pet(bot.ler_barra(sct, None)); time.sleep(0.05)
        controle.ultimo_revive = time.time()  # morreu e o revive saiu
    return "vazio"
bot.esperar_agrupar = esperar_agrupar
n = [0]
def inimigos(sct):
    n[0] += 1
    return [linha] if n[0] < 60 else []
bot.inimigos = inimigos
bot.SEM_PET_ALARME_S = 1.0  # espera da box (1,4 s) mais longa que o alarme, como os 14 s reais
t0[0] = time.time()
bot.TIMEOUT_COMBATE = 2.5
bot.combater_ate_limpar(None, bot.LOTOU)
checar("logo depois do revive (Back!/Go!): NÃO alarma", not alarmes, f"({alarmes})")
# pet morto de verdade e sem revive por 8+ s: alarma
alarmes.clear(); n[0] = 0
bot.ler_barra = lambda sct, b: 0
controle.ultimo_revive = 0.0
bot.esperar_agrupar = lambda sct: "vazio"
bot.SEM_PET_ALARME_S = 1.0
bot.TIMEOUT_COMBATE = 2.0
bot.combater_ate_limpar(None, bot.LOTOU)
checar("pet morto de verdade, sem revive: alarma", "sem monstrinho" in alarmes, f"({alarmes})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
