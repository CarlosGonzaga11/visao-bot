"""
Thread que fica vigiando o HP do personagem e do monstrinho e aperta as hotkeys de cura sozinha,
em paralelo com o cavebot.

Poção do monstrinho: ela cura aos poucos e é CANCELADA se ele levar um hit. Por isso:
  - só toma com a Battle sem inimigos (CURA_POKE_FORA_COMBATE);
  - depois de tomar, espera POT_DURACAO antes de tomar outra (não desperdiça).
"""
import threading
import time

import mss

import controle
from config import (
    CURA_HP_ATIVA, HP_LIMITE, TECLA_CURA_HP,
    CURA_POKE_ATIVA, POKE_HP_LIMITE, TECLA_CURA_POKE, COOLDOWN_CURA,
    CURA_POKE_FORA_COMBATE, POT_DURACAO, DESCANSAR_ATE,
)
from tela import ler_barra, ler_monstros


class MonitorCura(threading.Thread):
    def __init__(self, calib):
        super().__init__(daemon=True)
        # (nome, barra, limite %, tecla, espera entre usos, só fora de combate)
        self.barras = []
        if calib.get("hp"):
            self.barras.append(("HP personagem", calib["hp"], HP_LIMITE, TECLA_CURA_HP,
                                COOLDOWN_CURA, False))
        if calib.get("poke_hp"):
            # Fora de combate dá para curar mais (até onde o descanso pede)
            limite = max(POKE_HP_LIMITE, DESCANSAR_ATE) if CURA_POKE_FORA_COMBATE else POKE_HP_LIMITE
            self.barras.append(("HP monstrinho", calib["poke_hp"], limite, TECLA_CURA_POKE,
                                max(COOLDOWN_CURA, POT_DURACAO), CURA_POKE_FORA_COMBATE))
        self.ultimo_uso = {b[0]: 0.0 for b in self.barras}

    def run(self):
        if not self.barras:
            print("[Cura] Nenhuma barra calibrada/ativada. Cura automática desligada.")
            return
        print("[Cura] Monitor ativo: " + ", ".join(
            f"{n} < {lim}%" + (" (só fora de combate)" if fora else "")
            for n, _, lim, _, _, fora in self.barras))

        # mss precisa de uma instância própria por thread
        with mss.MSS() as sct:
            while not controle.deve_parar():
                try:
                    if not controle.esta_pausado():
                        self.verificar(sct)
                except Exception as e:  # um erro numa leitura não pode desligar a cura
                    print(f"[Cura] Erro lendo as barras (sigo vigiando): {e!r}")
                    time.sleep(1)
                time.sleep(0.15)

    def verificar(self, sct):
        em_combate = None  # só lê a Battle se precisar
        import config
        for nome, barra, limite, tecla, espera, fora_combate in self.barras:
            if not (config.CURA_HP_ATIVA if nome == "HP personagem" else config.CURA_POKE_ATIVA):
                continue  # desligada no painel
            pct = ler_barra(sct, barra)
            if pct is None or pct <= 0:
                continue  # janela não visível, ou 0% (morto: quem cuida é a segurança)
            agora = time.time()
            if pct >= limite or agora - self.ultimo_uso[nome] < espera:
                continue
            if nome == "HP monstrinho" and controle.segurar_pot_poke:
                continue  # vai usar revive no fim do lure: a poção seria desperdício
            if fora_combate:
                if em_combate is None:
                    em_combate = len(ler_monstros(sct)) > 0
                if em_combate:
                    continue  # com inimigo batendo, a poção seria cancelada
            controle.apertar(tecla)
            self.ultimo_uso[nome] = agora
            print(f"[Cura] {nome} em {pct:.0f}% -> apertou {tecla.upper()}")


REVIVE_TENTATIVAS = 3  # revives seguidos (a cada 4 s) por morte; antes 2 (tecla presa = perdia uma)


class MonitorRevive(threading.Thread):
    """
    Vigia o HP do monstrinho o tempo todo (0,1 s). Se ele estava vivo e a barra foi a 0%,
    ele morreu: aperta o revive NA HORA (em qualquer modo), para o personagem não ficar
    sozinho apanhando. Só revive de novo depois de ver o monstrinho vivo outra vez
    (ou tenta 1 vez mais, 4 s depois, se o primeiro não pegou).
    """

    def __init__(self, calib):
        super().__init__(daemon=True)
        self.barra = calib.get("poke_hp")

    def reviver(self, sct):
        import config
        from modos import OFF_RETRATO
        from tela import localizar_ancora
        controle.ultimo_revive = time.time()
        controle.apertar(config.TECLA_REVIVE)
        if config.REVIVE_CLICAR_POKE:
            titulo = localizar_ancora(sct, "pokemon")
            if titulo:
                time.sleep(0.12)
                controle.clicar(titulo[0] + OFF_RETRATO[0], titulo[1] + OFF_RETRATO[1], espalhar=(6, 6))

    def run(self):
        import config
        if not self.barra:
            return
        print(f"[Revive] Vigiando o monstrinho: se morrer, revive na hora (tecla {config.TECLA_REVIVE}).")
        vivo, zeros, tentativas, ultimo = False, 0, 0, 0.0
        with mss.MSS() as sct:
            while not controle.deve_parar():
                time.sleep(0.1)
                if not (config.REVIVE_SE_MORRER and config.TECLA_REVIVE):
                    vivo, zeros = False, 0
                    time.sleep(0.5)
                    continue  # desligado no painel
                if controle.esta_pausado():
                    continue
                try:
                    pct = ler_barra(sct, self.barra)
                except Exception:
                    continue
                if pct is None:
                    continue
                if pct > 3:
                    vivo, zeros, tentativas = True, 0, 0
                    continue
                if not vivo:
                    continue  # nunca viu vivo (ex.: guardado): não gasta revive
                zeros += 1
                if time.time() - controle.ultimo_revive < 5:
                    zeros = 0  # acabou de usar revive: "Back!/Go!" esvazia a barra, não é morte
                    continue
                if zeros >= 2 and tentativas < REVIVE_TENTATIVAS and time.time() - ultimo > 4:
                    tentativas += 1
                    ultimo = time.time()
                    print(f"[Revive] 💀 Monstrinho morreu! Revive na hora (tentativa {tentativas}).")
                    self.reviver(sct)
