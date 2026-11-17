"""Testes simulados das correções MÉDIAS (9 a 11). Nenhum clique/tecla de verdade."""
import os
import sys
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import controle
import humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade

teclas = []
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
controle.clicar = lambda *a, **k: True
controle.apertar = lambda t: teclas.append(t) or True
controle.encerrar = lambda: None
controle._gravar_estado = lambda: None

import bot
bot.sqm_ocupados = lambda sct: set()  # tela: ninguém na tela (luta segue como antes)
import efeitos as _ef
_curar_original = _ef.curar_se_precisar
import config
import efeitos
config.TECLA_REVIVE = config.TECLA_REVIVE or "r"  # não depende da tecla salva no ajustes.json
import seguranca

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


# ---------- 9: sem monstrinho na luta ----------
linha = {"alvo": True, "xy": (50, 50), "nome_img": None}
bot.inimigos = lambda sct: [linha]
bot.efeitos.curar_se_precisar = lambda sct: False
bot.fazer_catch = lambda *a, **k: None
bot.descansar = lambda sct: None
bot.ORDER_DEPOIS_LUTA = False
bot.POKESTOP_ATIVO = False
bot.MAGIA_AGRUPAR_ATIVA = False
config.IGNORAR_SOBRA = False
config.CLICAR_ALVO = False
bot.carregar_calibracao = lambda: {"poke_hp": {"fake": 1}}
hp_pet = [0]
bot.ler_barra = lambda sct, barra: hp_pet[0]
alarmes = []
bot.alarmar_e_pausar = lambda sct, texto, motivo, prefixo: alarmes.append(motivo)
controle.ultimo_revive = 0.0


class NormalContando(bot.modos.Normal):
    combos = 0

    def atacar(self, sct):
        NormalContando.combos += 1
        time.sleep(0.05)
        return False


bot.ESTRATEGIA = NormalContando()
bot.TIMEOUT_COMBATE = 10
r = bot.combater_ate_limpar(None, bot.LOTOU)
checar("normal sem pet: não aperta o combo", NormalContando.combos == 0, f"({NormalContando.combos} combos)")
checar("normal sem pet: alarme + pausa", alarmes.count("sem monstrinho") >= 1, f"({alarmes})")

# pet vivo: luta normal (sem alarme)
alarmes.clear()
NormalContando.combos = 0
hp_pet[0] = 80
bot.TIMEOUT_COMBATE = 1
bot.combater_ate_limpar(None, bot.LOTOU)
checar("pet vivo: combo sai normalmente, sem alarme", NormalContando.combos > 0 and not alarmes)

# pet some por pouco tempo (troca / Back!-Go!): não alarma, não trava
alarmes.clear()
NormalContando.combos = 0
t0 = time.time()
bot.ler_barra = lambda sct, barra: 0 if time.time() - t0 < 1.0 else 80
bot.TIMEOUT_COMBATE = 3
bot.combater_ate_limpar(None, bot.LOTOU)
checar("pet some 1 s: sem alarme e luta continua", not alarmes and NormalContando.combos > 0)

# modo revive: tenta 1 revive (e não fica revivendo sem parar)
bot.ler_barra = lambda sct, barra: 0
revives = []
rv = bot.modos.Revive()
eventos = []  # ordem: revives e alarmes
rv.usar_revive = lambda sct, motivo: (revives.append(motivo), eventos.append(("revive", motivo)),
                                      setattr(controle, "ultimo_revive", time.time()), False)[3]
rv.atacar = lambda sct: time.sleep(0.05) or False
bot.ESTRATEGIA = rv
alarmes.clear()
controle.ultimo_revive = 0.0
bot.TIMEOUT_COMBATE = 9.5
bot.SEM_PET_ALARME_S = 2.0  # alarme 2 s (+6 s de folga dos revives) cabe nos 9,5 s da luta
alarme_antigo = bot.alarmar_e_pausar
bot.alarmar_e_pausar = lambda sct, texto, motivo, prefixo: (alarmes.append(motivo), eventos.append(("alarme", motivo)))
bot.combater_ate_limpar(None, bot.LOTOU)
bot.alarmar_e_pausar = alarme_antigo
i_alarme = next((i for i, e in enumerate(eventos) if e[0] == "alarme"), len(eventos))
fora = [e for e in eventos[:i_alarme] if e[0] == "revive" and "fora" in e[1]]
# (depois do alarme, que no jogo PAUSA, o bot pode tentar de novo quando você apertar F12)
checar("revive sem pet: 1 revive e depois alarme", len(fora) == 1 and "sem monstrinho" in alarmes,
       f"({eventos[:6]})")

# ---------- 10: Medicine que não resolve ----------
efeitos.curar_se_precisar = _curar_original
efeitos.MEDICINE_ATIVO = True
efeitos.TECLA_MEDICINE = "f9"
efeitos.MEDICINE_ESPERA = 0
efeitos.MEDICINE_CLICAR_POKE = False
efeitos.negativos_na_tela = lambda sct: [{"tipo": "borda", "x": 1, "y": 1, "img": None}]
efeitos.controle.esperar = lambda s: False
teclas.clear()
for _ in range(20):
    efeitos.curar_se_precisar(None)
checar("Medicine sem efeito: para depois de 2 usos", teclas.count("f9") == 2, f"({teclas.count('f9')} usos)")
efeitos._estado["desistiu_ate"] = time.time() - 1  # passou o tempo de espera
efeitos.curar_se_precisar(None)
checar("Medicine: tenta de novo depois da espera", teclas.count("f9") == 3)
efeitos.negativos_na_tela = lambda sct: []
efeitos.curar_se_precisar(None)
checar("Medicine: efeito saiu zera tudo", efeitos._estado["usos_seguidos"] == 0 and efeitos._estado["desistiu_ate"] == 0)

# ---------- 11: morte com o pet também vazio ----------
emerg = []
pos = [(1000, 1000, 7)]
m = seguranca.MonitorSeguranca({"hp": {"a": 1}, "poke_hp": {"b": 1}}, pos_atual=lambda: pos[0])
m.emergencia = lambda sct, motivo, parar: emerg.append((motivo, parar))
leituras = {"hp": 0, "poke": 0}
seguranca.ler_barra = lambda sct, barra: leituras["hp"] if "a" in barra else leituras["poke"]
seguranca.localizar_ancora = lambda sct, nome: (1, 1)
seguranca.time.sleep = lambda s: None  # (só neste módulo de teste; o laço roda por chamadas)


def rodar_monitor(passos):
    """Roda o laço do monitor por `passos` voltas (cada volta chama `passos[i]()` antes)."""
    voltas = iter(passos)

    def parar():
        try:
            next(voltas)()
            return False
        except StopIteration:
            return True
    antigo = seguranca.controle.deve_parar
    seguranca.controle.deve_parar = parar
    seguranca.mss.MSS = lambda: __import__("contextlib").nullcontext(None)
    try:
        m.run()
    finally:
        seguranca.controle.deve_parar = antigo


# pet guardado e personagem parado: NÃO é morte
rodar_monitor([lambda: None] * 10)
checar("HP 0% com pet vazio, sem sair do lugar: não acusa morte", not emerg)
# morreu: HP 0% + pet vazio + apareceu no templo (longe)
rodar_monitor([lambda: None] * 3 + [lambda: pos.__setitem__(0, (3000, 2000, 7))] + [lambda: None] * 3)
checar("HP 0% com pet vazio + salto pro templo: morte e PARA", len(emerg) == 1 and emerg[0][1] is True,
       f"({emerg})")
# andou de escada/teleporte normal sem HP 0: não é morte
emerg.clear()
m2 = seguranca.MonitorSeguranca({"hp": {"a": 1}, "poke_hp": {"b": 1}}, pos_atual=lambda: pos[0])
m2.emergencia = lambda sct, motivo, parar: emerg.append((motivo, parar))
leituras.update(hp=90, poke=90)
m = m2
rodar_monitor([lambda: None] * 2 + [lambda: pos.__setitem__(0, (100, 100, 7))] + [lambda: None] * 2)
checar("salto de posição com HP normal: não é morte", not emerg)
# morte com o pet vivo continua sendo detectada como antes
leituras.update(hp=0, poke=90)
rodar_monitor([lambda: None] * 5)
checar("HP 0% com pet vivo: morte (como antes)", len(emerg) == 1)

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
