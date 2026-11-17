"""Testes simulados das correções ALTAS (5 a 8). Nenhum clique/tecla de verdade, nada gravado em disco."""
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

humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
controle.clicar = lambda *a, **k: True
controle.apertar = lambda *a, **k: True
controle.encerrar = lambda: None
controle._gravar_estado = lambda: None
controle.iniciar_atalhos = lambda: None

import bot
bot.sqm_ocupados = lambda sct: set()  # tela: ninguém na tela (luta segue como antes)
bot.ler_barra = lambda sct, barra: None  # barra do pet: desconhecida (luta segue como antes)
import config
import layout

bot.MAPA.salvar = lambda: None  # não mexe no mapa_memoria.json
resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


# ---------- 7: mínimo do lure muda com o bot rodando ----------
config.LURE_ATIVO = True
layout._setar("LURE_MINIMO", 3)
a = bot.minimo_para_lutar()
layout._setar("LURE_MINIMO", 5)  # o que o vigiar_ajustes faz quando você salva no painel
b = bot.minimo_para_lutar()
cabem = bot.linhas_que_cabem(config.BATTLE_REGION["height"]) - (1 if config.MONSTRINHO_NA_BATTLE else 0)
checar("mínimo do lure lido na hora", a == min(3, cabem) and b == min(5, cabem), f"({a} -> {b}, cabem {cabem})")
checar("decidir_lure usa o valor novo", bot.decidir_lure(4, 100, 100) is None if b > 4 else True)
layout._setar("LURE_ATIVO", False)
checar("lure desligado: luta com 1", bot.minimo_para_lutar() == 1)
layout._setar("LURE_ATIVO", True)
layout._setar("LURE_MINIMO", 99)
m = bot.minimo_para_lutar()
checar("nunca pede mais do que cabe na Battle", m == cabem)

# ---------- 8: 'vazio' só abandona com 2 SEGUIDOS ----------
linha = {"alvo": True, "xy": (50, 50), "nome_img": None}
bot.efeitos.curar_se_precisar = lambda sct: False
bot.fazer_catch = lambda *a, **k: None
bot.descansar = lambda sct: None
bot.ORDER_DEPOIS_LUTA = False
bot.POKESTOP_ATIVO = False
bot.MAGIA_AGRUPAR_ATIVA = True
bot.TIMEOUT_COMBATE = 30
config.IGNORAR_SOBRA = False
bot.ESTRATEGIA = bot.modos.Normal()
bot.ESTRATEGIA.atacar = lambda sct: False


def luta_com(seq):
    """Roda _combater com esperar_agrupar devolvendo `seq`; depois disso a Battle esvazia."""
    fila = list(seq)
    bot.esperar_agrupar = lambda sct: fila.pop(0)
    bot.inimigos = lambda sct: [linha] if fila else []
    bot.controle.esperar = lambda s: False
    return bot.combater_ate_limpar(None, bot.LOTOU)


r = luta_com(["vazio", True, "vazio", True, "vazio", True])
checar("vazio alternado com combo: luta até o fim", r == bot.LUTA_LIMPOU, f"({r})")
r = luta_com([True, "vazio", "vazio", True])
checar("2 vazios seguidos: segue a hunt", r == bot.LUTA_FORA_DE_ALCANCE, f"({r})")

# ---------- 5 e 6: memória da rota no laço principal ----------
class FakePos:
    def __init__(self):
        self.p = (100, 100, 7)

    def start(self):
        pass

    def atual(self):
        return self.p


class Nada:
    def __init__(self, *a, **k):
        pass

    def start(self):
        pass


bot.POS = FakePos()
for nome in ("MonitorCura", "MonitorRevive", "MonitorChat", "MonitorSeguranca"):
    setattr(bot, nome, Nada)
bot.efeitos.MonitorEfeitos = Nada
bot.layout.arrumar_console = lambda: None
bot.layout.detectar_e_aplicar = lambda sct: None
bot.layout.VigiaLayout = Nada
bot.carregar_calibracao = lambda: {}
bot.carregar_rota = lambda: [{"pos": (100 + 5 * i, 100, 7), "lure": False} for i in range(3)]
import posicao
posicao.ponto_suspeito = lambda p, todos: False
controle._rota.set()
_sleep = time.sleep
time.sleep = lambda s: None if s >= 4 else _sleep(s)


def rodar(andar, luta, inimigos_na_battle):
    """Roda o laço principal com andar/luta falsos até o 1º alarme (que encerra o teste)."""
    chamadas, alarmes = [], []

    def andar_falso(sct, wp, numero, lure, ignorar_preso=False):
        chamadas.append(ignorar_preso)
        if len(chamadas) > 20:
            raise controle.ParadaSolicitada()  # laço sem fim (o bug antigo)
        return andar(ignorar_preso)

    def alarme(sct, texto, motivo, prefixo):
        alarmes.append(texto)
        raise controle.ParadaSolicitada()

    bot.andar_ate_coord = andar_falso
    bot.combater_ate_limpar = lambda sct, motivo: luta
    bot.inimigos = lambda sct: [linha] if inimigos_na_battle else []
    bot.alarmar_e_pausar = alarme
    bot.MEMORIA = bot.MemoriaRota()
    bot.rodar_cavebot()
    return chamadas, alarmes


# Cercado + monstro atrás de parede: antes ficava preso -> luta vazia -> preso... para sempre
chamadas, alarmes = rodar(lambda ign: bot.TIMEOUT if ign else bot.PRESO, bot.LUTA_FORA_DE_ALCANCE, False)
checar("preso + luta vazia 2x: para de lutar por 'cercado' ali", chamadas[:3] == [False, False, True], f"({chamadas})")
checar("preso + luta vazia: termina em alarme (não laço infinito)", len(alarmes) == 1 and len(chamadas) <= 6,
       f"({len(chamadas)} tentativas)")

# Ponto que nunca chega (sem monstros): antes pulava de ponto em ponto em silêncio
chamadas, alarmes = rodar(lambda ign: bot.TIMEOUT, None, False)
checar("4 timeouts seguidos: alarme + pausa", len(alarmes) == 1 and len(chamadas) == config.NAV_FALHAS_MAX,
       f"({len(chamadas)} tentativas)")

# Chegar em algum ponto zera a contagem
seq = iter([bot.TIMEOUT, bot.TIMEOUT, bot.TIMEOUT, bot.CHEGOU] + [bot.TIMEOUT] * 10)
chamadas, alarmes = rodar(lambda ign: next(seq), None, False)
checar("chegou num ponto: a contagem recomeça", len(alarmes) == 1 and len(chamadas) == 4 + config.NAV_FALHAS_MAX,
       f"({len(chamadas)} tentativas)")

# Cercado com luta de verdade (matou) NÃO conta como falha
seq2 = iter([bot.PRESO] * 6 + [bot.TIMEOUT] * 10)
chamadas, alarmes = rodar(lambda ign: next(seq2), bot.LUTA_LIMPOU, False)
checar("cercado que lutou de verdade não conta como falha",
       chamadas[:6] == [False] * 6 and len(chamadas) == 6 + config.NAV_FALHAS_MAX, f"({len(chamadas)} tentativas)")

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
