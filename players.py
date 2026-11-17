"""
Segurança: OUTRO PLAYER chegou na sua tela.

Regra (07/11, 2ª versão): a Battle lista o SEU pet e os monstros; players, NPCs e os pokémons de
outros players NÃO aparecem nela (print 19:21: "Jogador A", "Jogador B" e um Gyarados vermelho na tela, fora
da Battle). Então:

    estranhos = criaturas na tela (sem você) − linhas da Battle

(1ª versão usava a caveira acima do nome, mas a caveira só existe nas hunts 150+ — alarme falso
23:06 numa hunt mais baixa.)

Cuidados (para não dar alarme falso):
  - barra quase VAZIA na tela (0–3% de vida) não conta: na Battle ela pode não ser lida;
  - barras nas faixas da barra de ícones (em cima) e da hotbar (embaixo) não contam (barra falsa);
  - Battle cheia (mais monstros do que linhas cabem) → não dá para saber, não decide;
  - a tela e a Battle são lidas em momentos um pouco diferentes (monstro entrando na tela):
    só toca com estranho em PLAYER_LEITURAS das últimas PLAYER_JANELA leituras (~3 s).
Limite conhecido: monstro da Battle escondido na tela (atrás da barra de ícones, empilhado) "empata"
com um estranho e o alarme demora (print 19:21: Jogador A/Jogador B não contaram naquele instante).
Erros "para menos" (monstros empilhados, criatura atrás da janela da Battle) só fazem o alarme não
tocar, nunca tocar à toa. Só lê a tela; nunca clica.
"""
import threading
import time

import mss

import config
import controle
from config import PLAYER_TILE_XY, SQM_PX
from tela import (GAME_VIEW, analisar_battle, capturar, encontrar_barras_criaturas, linhas_que_cabem,
                  regiao_battle)

FAIXA_TOPO, FAIXA_BAIXO = 40, 60  # barra de ícones (em cima) e hotbar (embaixo) ficam POR CIMA do mapa
PREENCH_MIN = 4                   # barra com menos que isso de cor (px) = quase morto: não conta
PLAYER_LEITURAS = 4               # leituras com estranho (das últimas PLAYER_JANELA) para alarmar
PLAYER_JANELA = 6                 # ~3 s: a conta oscila (monstro escondido/empilhado), não precisa ser seguido
PLAYER_REARMAR_S = 10.0           # sem estranho por isso: pode tocar de novo
INTERVALO_S = 0.5


def criaturas_na_tela(img, origem, centro=None, sqm=None):
    """Criaturas na tela (sqm em relação a você), sem você, sem quase-mortos e fora das faixas da UI."""
    cx0, cy0 = centro or PLAYER_TILE_XY
    s = sqm or SQM_PX
    h = img.shape[0]
    achadas = []
    for bx, by, preench, rosa in encontrar_barras_criaturas(img, (0, 0)):
        if by < FAIXA_TOPO or by > h - FAIXA_BAIXO or preench < PREENCH_MIN:
            continue
        if rosa:
            continue  # monstro ROSA (anti-block) não entra na Battle (alarme falso 08/11 18:05)
        rel = (round((bx + 13 + origem[0] - cx0) / s), round((by + 26 + origem[1] - cy0) / s))
        if rel != (0, 0):
            achadas.append(rel)
    return achadas


def linhas_battle(img_battle, regiao):
    """(quantas linhas a Battle tem — pet + monstros, qualquer cor —, está cheia?)."""
    n = len(analisar_battle(img_battle, regiao))
    return n, n >= linhas_que_cabem(img_battle.shape[0])


def estranhos(na_tela, n_battle):
    """Quantas criaturas na tela não estão na Battle (player, NPC ou pokémon de outro player)."""
    return max(0, len(na_tela) - n_battle)


class VigiaPlayers(threading.Thread):
    def __init__(self, calib=None, alarmar=None):
        super().__init__(daemon=True)
        self.alarmar = alarmar  # função(sct, texto) — padrão: chat.disparar
        self.historico = []  # últimas PLAYER_JANELA leituras: tinha estranho?
        self.armado = True
        self.ultimo_visto = 0.0
        self.ultimo_alarme_n = 0
        self.avisou_battle = 0.0
        self.ultimo_scan = 0.0      # (leitura de nomes: fora desta versão)

    def ler(self, sct):
        """(criaturas na tela, linhas da Battle, Battle cheia) — None se não achou a Battle."""
        reg = regiao_battle(sct)
        if reg is None:
            return None
        n, cheia = linhas_battle(capturar(sct, reg), reg)
        tela = criaturas_na_tela(capturar(sct, GAME_VIEW), (GAME_VIEW["left"], GAME_VIEW["top"]))
        return tela, n, cheia

    def passo(self, sct, leitura=None, agora=None):
        """Uma leitura. Devolve as criaturas na tela quando o alarme toca (senão None)."""
        agora = time.time() if agora is None else agora
        if leitura is None:
            leitura = self.ler(sct)
        if leitura is None or leitura[2]:
            return None  # sem Battle na tela, ou Battle cheia: não dá para saber
        na_tela, n_battle, _ = leitura
        if n_battle == 0:
            # o seu pet é SEMPRE a 1ª linha: 0 linhas = Battle MINIMIZADA ou ilegível (alarme falso 08/11
            # 18:03, só o título da Battle na tela) → não dá para saber
            self.historico = []
            if agora - self.avisou_battle > 60:
                self.avisou_battle = agora
                print("[Players] ⚠️ Não consigo ler a Battle (minimizada?): sem vigia de player por enquanto.")
            return None
        n = estranhos(na_tela, n_battle)
        self.historico = (self.historico + [n > 0])[-PLAYER_JANELA:]
        if n == 0:
            if not self.armado and agora - self.ultimo_visto >= PLAYER_REARMAR_S:
                self.armado, self.ultimo_alarme_n = True, 0
            return None
        self.ultimo_visto = agora
        if sct is not None and agora - self.ultimo_scan >= 3.0:
            self.ultimo_scan = agora
            self.escanear(sct)
        if sum(self.historico) < PLAYER_LEITURAS:
            return None
        if self.armado or n > self.ultimo_alarme_n:
            self.armado, self.ultimo_alarme_n = False, n
            texto = (f"{n} criatura(s) na tela que não estão na Battle (player, NPC ou pokémon de player): "
                     f"{len(na_tela)} na tela x {n_battle} na Battle")
            if self.alarmar:
                self.alarmar(sct, texto)
            return na_tela
        return None

    def escanear(self, sct):
        """(Leitura de nomes ficou fora desta versão.)"""
        return

    def run(self):
        import chat
        if self.alarmar is None:
            self.alarmar = lambda sct, texto: chat.disparar(
                sct, texto=texto, motivo="👤 PLAYER NA TELA",
                pausar=bool(getattr(config, "ALARME_PLAYER_PAUSAR", True)))
        print("[Players] 👤 Vigiando players na tela (criatura que não está na Battle).")
        with mss.MSS() as sct:
            while not controle.deve_parar():
                try:
                    if getattr(config, "ALARME_PLAYER_ATIVO", True) and not controle.esta_pausado():
                        self.passo(sct)
                    else:
                        self.historico = []
                except Exception as e:  # nunca derruba o bot
                    print(f"[Players] erro (sigo vigiando): {e!r}")
                    time.sleep(2)
                time.sleep(INTERVALO_S)
