"""
Segurança: vigia se o personagem morreu ou se o jogo sumiu da tela.

  - HP do personagem em 0% (lido algumas vezes seguidas) = morreu
      -> PARA o bot e toca o alarme.
  - Janelas do jogo (Battle e Pokémon) somem por muito tempo = deslogou, tela de
    login, ou alguma janela cobrindo o jogo
      -> PAUSA o bot e toca o alarme (F12 continua quando estiver tudo certo).
"""
import threading
import time

import mss

import chat
import controle
from tela import ler_barra, localizar_ancora

LEITURAS_MORTE = 3        # leituras seguidas em 0% para considerar morte
SALTO_MORTE_SQM = 30      # personagem "teleportou" mais que isso = voltou pro templo (morreu)
JANELA_MORTE_S = 15.0     # o salto vale como morte se o HP do personagem leu 0% até esse tempo antes
SEM_JOGO_SEGUNDOS = 15.0  # tempo sem achar as janelas do jogo para alarmar


class MonitorSeguranca(threading.Thread):
    def __init__(self, calib, pos_atual=None):
        super().__init__(daemon=True)
        self.barra_hp = calib.get("hp")
        self.barra_poke = calib.get("poke_hp")
        self.pos_atual = pos_atual   # função (x, y, z) ou None (do leitor de coordenadas do bot)
        self.ultima_pos = None
        self.zero_duvidoso = 0.0     # quando o HP do personagem leu 0% com o pet também vazio

    def teleportou(self):
        """
        True se a posição pulou mais de SALTO_MORTE_SQM desde a última leitura (morrer leva pro
        templo). O leitor de coordenadas já só aceita pulo grande lido 2x igual (não é erro de OCR).
        """
        if not self.pos_atual:
            return False
        pos = self.pos_atual()
        if pos is None:
            return False
        antes, self.ultima_pos = self.ultima_pos, pos
        if antes is None:
            return False
        return max(abs(pos[0] - antes[0]), abs(pos[1] - antes[1])) > SALTO_MORTE_SQM

    def run(self):
        zeros = 0
        sumiu_desde = None
        avisou_sumiu = False
        with mss.MSS() as sct:
            geracao = controle.GERACAO[0]
            while not controle.deve_parar():
                # Trocando de personagem (rodízio): a tela de seleção não tem barra de HP nem janelas
                # do jogo — HP "0%" ali virava "MORREU" e o bot PARAVA. Fica quieto e, depois, zera.
                if controle.trocando():
                    zeros, sumiu_desde, avisou_sumiu = 0, None, False
                    time.sleep(0.3)
                    continue
                if geracao != controle.GERACAO[0]:
                    geracao = controle.GERACAO[0]
                    self.ultima_pos = None      # personagem novo em outro lugar não é "teleporte"
                    self.zero_duvidoso = 0.0
                try:
                    # 1) Morte: HP do personagem em 0%
                    if self.barra_hp:
                        pct = ler_barra(sct, self.barra_hp)
                        zeros = zeros + 1 if (pct is not None and pct <= 0) else 0
                        # monstrinho morto/guardado: a janela "Pokémon" fica vazia e a barra do
                        # personagem também parece 0% -> não é morte do personagem
                        if zeros and self.barra_poke:
                            poke = ler_barra(sct, self.barra_poke)
                            if poke is None or poke <= 3:
                                # pet vazio também: a barra do personagem não dá para confiar sozinha.
                                # Antes só zerava (morte com o pet morto/guardado passava batido);
                                # agora guarda e confirma pelo salto de posição (volta pro templo).
                                zeros = 0
                                self.zero_duvidoso = time.time()
                        if zeros >= LEITURAS_MORTE:
                            self.emergencia(sct, "💀 HP do personagem em 0% — o personagem MORREU?", parar=True)
                            return
                    if self.teleportou() and time.time() - self.zero_duvidoso <= JANELA_MORTE_S:
                        self.emergencia(sct, "💀 HP do personagem foi a 0% e ele apareceu longe (templo?) — "
                                             "o personagem MORREU?", parar=True)
                        return

                    # 2) Jogo sumiu da tela (deslogou / tela de login / janela por cima)
                    if controle.esta_pausado():
                        sumiu_desde, avisou_sumiu = None, False
                    else:
                        visivel = (localizar_ancora(sct, "pokemon") is not None
                                   or localizar_ancora(sct, "battle") is not None)
                        if visivel:
                            sumiu_desde, avisou_sumiu = None, False
                        else:
                            sumiu_desde = sumiu_desde or time.time()
                            if not avisou_sumiu and time.time() - sumiu_desde >= SEM_JOGO_SEGUNDOS:
                                self.emergencia(
                                    sct, f"🚫 Não vejo o jogo há {SEM_JOGO_SEGUNDOS:.0f}s — deslogou, morreu "
                                         "ou tem alguma janela cobrindo o jogo?", parar=False)
                                avisou_sumiu = True
                except Exception as e:  # um erro numa leitura não pode desligar a segurança
                    print(f"[Segurança] Erro na leitura (sigo vigiando): {e!r}")
                    time.sleep(1)
                time.sleep(0.3)

    def emergencia(self, sct, motivo, parar):
        print("\n" + "#" * 60)
        print(motivo)
        print("O bot foi " + ("PARADO." if parar else "PAUSADO (F12 continua)."))
        print("#" * 60)
        chat.tocar_som(20)
        chat.salvar_print(sct, motivo)
        if parar:
            controle.encerrar()
        else:
            controle.pausar("segurança")
