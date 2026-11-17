"""
Modos de hunt (como o bot luta depois de juntar o lure).

  normal    : ataca com o combo, espera o intervalo, repete até limpar.

  revive    : ataca com o combo; se não matou tudo, usa REVIVE (revive o monstrinho
              e zera o cooldown das magias) e ataca de novo — fica nesse ciclo até
              matar. Quando matou, usa revive de novo (já sai com tudo pronto) e vai
              para a próxima volta.

  nightmare : sem revive. Ataca com o monstrinho que está fora; enquanto as magias
              dele estão em cooldown, troca para outro monstrinho que esteja pronto
              e ataca com ele. Se nenhum estiver pronto, espera o cooldown.
"""
import time

import caixa_preta
import controle
import humano
from config import (
    MODO_HUNT, TECLA_ATAQUE, INTERVALO_ATAQUE, COMBO_DURACAO,
    TECLA_REVIVE, REVIVE_CLICAR_POKE, REVIVE_ESPERA, REVIVE_APOS_LURE,
    NIGHTMARE_TECLAS, NIGHTMARE_COOLDOWN, TROCA_ESPERA, NIGHTMARE_VOLTAR_PRIMEIRO,
)

# Retrato do monstrinho no painel "Pokémon", em relação ao título do painel
OFF_RETRATO = (30, 60)


def lista_teclas(texto):
    """'1, 2, 3' -> ['1', '2', '3']"""
    return [t.strip().lower() for t in str(texto).replace(";", ",").split(",") if t.strip()]



def esperar_combo(sct, segundos):
    """
    Espera o combo sair, mas para na hora em que a Battle esvazia: matou tudo, não tem por que
    ficar parado (vai para o catch e o próximo lure). Retorna True se houve pausa (F12).
    """
    from tela import ler_inimigos
    fim = time.time() + segundos
    while time.time() < fim:
        if controle.esperar(min(0.15, max(0.01, fim - time.time()))):
            return True
        try:
            if not ler_inimigos(sct):
                return False
        except Exception:
            pass
        if VIGIA[0]:
            VIGIA[0](sct)  # monstro vindo em você no meio do combo: sai de perto (bot.vigiar_no_combo)
    return False


VIGIA = [None]  # o bot liga aqui a vigia de perigo durante o combo (bot.vigiar_no_combo)

class Normal:
    nome = "normal"
    descansa = True  # depois da luta, espera o monstrinho curar

    def atacar(self, sct):
        caixa_preta.estado("COMBO")
        controle.apertar(TECLA_ATAQUE)
        return esperar_combo(sct, humano.variar(INTERVALO_ATAQUE))

    def nao_matou(self, sct):
        return False

    def fim(self, sct):
        pass


class Revive(Normal):
    nome = "revive"
    descansa = False  # o revive já cura o monstrinho

    def __init__(self):
        self.revives = 0
        self.atacou = False

    def atacar(self, sct):
        self.atacou = True  # usou as magias nesta luta (só aí o revive do fim faz sentido)
        self.ultimo_combo = time.time()
        caixa_preta.estado("COMBO")
        controle.apertar(TECLA_ATAQUE)
        return esperar_combo(sct, humano.variar(COMBO_DURACAO))  # tempo do combo sair todo

    def usar_revive(self, sct, motivo):
        if not TECLA_REVIVE:
            print("[Revive] ⚠️ Falta a tecla do revive (painel, aba Modo de hunt).")
            return False
        # pular só se NENHUM combo saiu depois do último revive (aí as magias ainda estão prontas);
        # se combou depois dele, as magias estão em recarga: precisa do revive sim
        if time.time() - controle.ultimo_revive < 6 and getattr(self, "ultimo_combo", 0) < controle.ultimo_revive:
            # acabou de usar revive (ex.: o monstrinho morreu e o revive de emergência saiu): as
            # magias já estão resetadas e a vida cheia — outro revive agora seria desperdício
            print(f"[Revive] ⏭️ Revive usado há pouco: não uso de novo ({motivo}).")
            return False
        self.revives += 1
        print(f"[Revive] 💊 Usando revive ({motivo}) — total nesta sessão: {self.revives}")
        controle.ultimo_revive = time.time()
        caixa_preta.estado("REVIVING")
        controle.apertar(TECLA_REVIVE)
        if REVIVE_CLICAR_POKE:
            from tela import localizar_ancora
            titulo = localizar_ancora(sct, "pokemon")
            if titulo:
                controle.esperar(humano.variar(0.15))
                controle.clicar(titulo[0] + OFF_RETRATO[0], titulo[1] + OFF_RETRATO[1], espalhar=(6, 6))
        return controle.esperar(humano.variar(REVIVE_ESPERA))

    def nao_matou(self, sct):
        return self.usar_revive(sct, "não matou, reseta as magias")

    def fim(self, sct):
        if REVIVE_APOS_LURE and getattr(self, "atacou", True):
            self.usar_revive(sct, "lure limpo, pronto para a próxima volta")
        self.atacou = False


class Nightmare(Normal):
    nome = "nightmare"
    descansa = True

    def __init__(self, teclas=None, cooldown=None):
        self.teclas = teclas if teclas is not None else lista_teclas(NIGHTMARE_TECLAS)
        self.cooldown = NIGHTMARE_COOLDOWN if cooldown is None else cooldown
        self.pronto_em = [0.0] * max(1, len(self.teclas))  # quando cada poke volta a ter magia
        self.atual = 0  # o 1º da lista é o que está fora quando o bot começa
        self.esperando = False
        # a luta pode demorar por causa dos cooldowns: o tempo máximo de combate cresce junto
        self.timeout_min = self.cooldown * 3 + 30

    def _prontos(self, agora):
        return [i for i, t in enumerate(self.pronto_em) if t <= agora]

    def trocar(self, i, motivo=""):
        if i == self.atual or not self.teclas:
            return False
        print(f"[Nightmare] 🔄 Trocando para o poke {i + 1} ({self.teclas[i].upper()}){motivo}")
        controle.apertar(self.teclas[i])
        self.atual = i
        return controle.esperar(humano.variar(TROCA_ESPERA))

    def atacar(self, sct):
        agora = time.time()
        if not self.teclas:
            print("[Nightmare] ⚠️ Falta a lista de teclas dos pokes (painel, aba Modo de hunt).")
            return super().atacar(sct)

        if self.pronto_em[self.atual] > agora:
            prontos = self._prontos(agora)
            if prontos:
                # o próximo pronto depois do atual, em ordem (1→2→3→1...)
                n = len(self.teclas)
                prox = min(prontos, key=lambda i: (i - self.atual) % n)
                if self.trocar(prox, " — o atual está em cooldown"):
                    return True
            else:
                espera = min(self.pronto_em) - agora
                if not self.esperando:
                    print(f"[Nightmare] ⏳ Todos em cooldown, esperando {espera:.0f}s...")
                    self.esperando = True
                return controle.esperar(min(espera, 2.0))  # volta a checar a Battle a cada 2 s

        self.esperando = False
        print(f"[Nightmare] ⚔️ Poke {self.atual + 1} soltando as magias")
        caixa_preta.estado("COMBO")
        controle.apertar(TECLA_ATAQUE)
        self.pronto_em[self.atual] = time.time() + self.cooldown
        return esperar_combo(sct, humano.variar(COMBO_DURACAO))

    def fim(self, sct):
        if NIGHTMARE_VOLTAR_PRIMEIRO and self.atual != 0:
            self.trocar(0, " — voltando pro 1º para puxar o próximo lure")


class Outland(Revive):
    """
    Outland: os pokes são fortes demais para um combo só.
    Lure → combo → não matou? revive (reseta as magias) → combo de novo… até a Battle limpar.
    Depois de matar tudo, SEMPRE revive antes de ir pro próximo lure. Não deixa sobra para trás.
    """
    nome = "outland"

    def __init__(self):
        super().__init__()
        self.na_luta = 0
        self.sem_progresso = 0
        self.qtd_antes = None
        self.tem_especial = lambda: False  # o bot liga isso no rastreador de especiais

    def nao_matou(self, sct):
        import config
        from tela import ler_inimigos
        qtd = len(ler_inimigos(sct))
        if self.qtd_antes is not None and qtd < self.qtd_antes:
            self.sem_progresso = 0  # o combo matou alguém: está valendo a pena
        self.qtd_antes = qtd
        especial = self.tem_especial()  # shiny/especial tem MUITA vida: revive até matar
        limite = int(getattr(config, "OUTLAND_MAX_REVIVES", 6))
        if not especial and self.sem_progresso >= limite:
            if self.sem_progresso == limite:
                print(f"[Outland] ⚠️ {limite} revives seguidos sem matar ninguém: sigo só com o combo.")
                self.sem_progresso += 1
            return False
        self.na_luta += 1
        self.sem_progresso += 1
        extra = " — tem especial/shiny" if especial else ""
        return self.usar_revive(sct, f"não matou, reseta as magias ({self.na_luta}º nesta luta{extra})")

    def fim(self, sct):
        if getattr(self, "atacou", True):  # não usou magia nesta luta: não precisa resetar
            self.usar_revive(sct, "lure limpo, pronto para o próximo")
        self.atacou = False
        self.na_luta = self.sem_progresso = 0
        self.qtd_antes = None


def criar():
    modo = str(MODO_HUNT).lower()
    if modo == "outland":
        return Outland()
    if modo == "revive":
        return Revive()
    if modo == "nightmare":
        return Nightmare()
    return Normal()
