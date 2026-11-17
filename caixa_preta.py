"""
Caixa-preta: grava PROVAS de quando o personagem leva dano (Fase 1 — só observa, nunca age).

Por que existe: o personagem saiu de lutas com 10–21% de HP e o log não dizia QUANDO nem ONDE ele
apanhou. Sem isso não dá para saber se uma magia em área tem aviso visível, nem qual posição é
perigosa. Esta thread:

  - lê a barra de HP do personagem e do pet ~4x por segundo e guarda os últimos ~3 s da tela do jogo
    (só na memória);
  - quando o HP do personagem CAI (CAIXA_PRETA_QUEDA % ou mais de uma leitura para a outra), salva
    em diagnostico/caixa_preta/<data_hora>/:
        quadro_XX.jpg  -> a tela do jogo ~3 s ANTES e ~1,5 s DEPOIS do dano
        evento.json    -> para cada quadro: HP, pet, posição, criaturas (sqm em relação a você),
                          estado do bot; o resumo (monstro mais perto, quantos perto) e as últimas
                          linhas do log (o que o bot decidiu e por quê)
  - no fim de cada luta escreve no log o HP mínimo do personagem naquela luta.

Nunca clica, nunca aperta tecla, nunca muda decisão do bot. Até CAIXA_PRETA_MAX eventos por sessão.
"""
import collections
import json
import os
import threading
import time

import cv2
import mss

import config
import controle
from tela import capturar, ler_barra, GAME_VIEW

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico", "caixa_preta")
INTERVALO_S = 0.25      # leituras por segundo: 4
ANTES_S = 3.0           # quanto da tela guardar antes do dano
DEPOIS_S = 1.5          # e depois
ENTRE_EVENTOS_S = 2.0   # dano seguido (mesmo golpe/combo) vira 1 evento só

# ---------- O que o bot está fazendo (escrito pelo bot; a caixa-preta só lê) ----------
_estado = ["IDLE", time.time()]
_linhas = collections.deque(maxlen=60)   # últimas linhas do log (com horário)
_detalhes = collections.deque(maxlen=30)  # detalhes de decisão que não vão para o console


def estado(nome):
    """O bot avisa o que está fazendo (NAVIGATING, POSITIONING, FIGHTING, COMBO, REVIVING...)."""
    if _estado[0] != nome:
        _estado[0], _estado[1] = nome, time.time()


def estado_do_bot():
    """O último estado que o bot avisou (sem olhar a pausa)."""
    return _estado[0]


def estado_atual():
    if controle.esta_pausado():
        return "PAUSED"
    return _estado[0]


def guardar_linha(texto):
    """Chamado pelo log do bot (_Log) a cada linha: vai junto no evento como 'o que o bot pensou'."""
    texto = texto.rstrip()
    if texto:
        _linhas.append(time.strftime("%H:%M:%S ") + texto)


def anotar(texto):
    """Detalhe de decisão (ex.: opções de canto avaliadas) só para a caixa-preta, sem poluir o log."""
    _detalhes.append(time.strftime("%H:%M:%S ") + texto)


# ---------- Análise (funções puras, testáveis) ----------

def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def resumo_perigo(criaturas):
    """Monstro mais perto (sqm) e quantos estão a até 1, 2 e 3 sqm do personagem (pet incluso)."""
    dist = sorted(cheb(c, (0, 0)) for c in criaturas)
    return {
        "mais_perto_sqm": dist[0] if dist else None,
        "ate_1_sqm": sum(1 for d in dist if d <= 1),
        "ate_2_sqm": sum(1 for d in dist if d <= 2),
        "ate_3_sqm": sum(1 for d in dist if d <= 3),
        "criaturas_na_tela": len(dist),
    }


def caiu(antes, agora, minimo):
    """O HP caiu de verdade? (leitura que falhou = None nunca conta como dano)."""
    return antes is not None and agora is not None and antes - agora >= minimo


class CaixaPreta(threading.Thread):
    """
    criaturas_na_imagem(img) -> set de (dx, dy): a mesma leitura que o bot usa (sqm_ocupados), feita
    sobre um quadro já capturado (assim o evento mostra o que o bot VIA naquele instante).
    em_luta: lista [bool] do bot (EM_LUTA).
    """

    def __init__(self, calib, pos_atual, criaturas_na_imagem, em_luta):
        super().__init__(daemon=True)
        self.barra_hp = calib.get("hp")
        self.barra_pet = calib.get("poke_hp")
        self.pos_atual = pos_atual
        self.criaturas_na_imagem = criaturas_na_imagem
        self.em_luta = em_luta
        self.quadros = collections.deque(maxlen=int(ANTES_S / INTERVALO_S) + 1)
        self.eventos = 0
        self.ultimo_evento = 0.0
        self.hp_antes = None
        self.luta = None  # {"inicio", "hp_min", "hp_inicio"} durante a luta

    # -- uma leitura --
    def ler(self, sct):
        q = {"t": time.time(), "estado": estado_atual(), "pos": None, "hp": None, "pet": None, "img": None}
        try:
            q["pos"] = self.pos_atual()
        except Exception:
            pass
        if self.barra_hp:
            q["hp"] = ler_barra(sct, self.barra_hp)
        if self.barra_pet:
            q["pet"] = ler_barra(sct, self.barra_pet)
        q["img"] = capturar(sct, GAME_VIEW)
        return q

    def run(self):
        if not self.barra_hp:
            print("[CaixaPreta] ⚠️ Barra de HP do personagem não calibrada: caixa-preta desligada.")
            return
        print("[CaixaPreta] 📼 Gravando provas de dano no personagem (só observa, não age).")
        with mss.MSS() as sct:
            while not controle.deve_parar():
                inicio = time.time()
                try:
                    if getattr(config, "CAIXA_PRETA_ATIVA", True) and not controle.esta_pausado():
                        self.passo(sct)
                    else:
                        self.quadros.clear()
                        self.hp_antes = None
                except Exception as e:  # a caixa-preta nunca derruba o bot
                    print(f"[CaixaPreta] erro (ignorado): {e!r}")
                    time.sleep(1.0)
                time.sleep(max(0.02, INTERVALO_S - (time.time() - inicio)))

    def passo(self, sct):
        q = self.ler(sct)
        self.quadros.append(q)
        self.vigiar_luta(q)
        minimo = float(getattr(config, "CAIXA_PRETA_QUEDA", 5))
        if caiu(self.hp_antes, q["hp"], minimo) and time.time() - self.ultimo_evento > ENTRE_EVENTOS_S:
            self.ultimo_evento = time.time()
            if self.eventos < int(getattr(config, "CAIXA_PRETA_MAX", 20)):
                self.eventos += 1
                self.gravar_evento(sct, self.hp_antes, q)
            else:
                print(f"[CaixaPreta] 💥 Você perdeu {self.hp_antes - q['hp']:.0f}% (limite de eventos salvos atingido).")
        if q["hp"] is not None:
            self.hp_antes = q["hp"]

    def vigiar_luta(self, q):
        """Resumo de cada luta: HP mínimo do personagem (antes nada dizia que ele apanhou)."""
        if self.em_luta[0] and self.luta is None:
            self.luta = {"inicio": q["t"], "hp_inicio": q["hp"], "hp_min": q["hp"]}
        elif self.em_luta[0] and q["hp"] is not None:
            m = self.luta["hp_min"]
            self.luta["hp_min"] = q["hp"] if m is None else min(m, q["hp"])
        elif not self.em_luta[0] and self.luta is not None:
            l, self.luta = self.luta, None
            if l["hp_min"] is not None and l["hp_inicio"] is not None and l["hp_min"] < l["hp_inicio"] - 1:
                print(f"[CaixaPreta] 🩸 Nesta luta seu HP foi de {l['hp_inicio']:.0f}% a {l['hp_min']:.0f}% "
                      f"({q['t'] - l['inicio']:.0f}s de luta).")

    def gravar_evento(self, sct, hp_antes, q_dano):
        """Junta os quadros de antes, lê mais DEPOIS_S de tela e salva tudo (sem travar o bot)."""
        antes = list(self.quadros)
        depois = []
        fim = time.time() + DEPOIS_S
        while time.time() < fim and not controle.deve_parar():
            time.sleep(INTERVALO_S)
            q = self.ler(sct)
            depois.append(q)
            if q["hp"] is not None:
                self.hp_antes = q["hp"]
        self.quadros.clear()
        perda = hp_antes - q_dano["hp"]
        cri = sorted(self.criaturas_na_imagem(q_dano["img"]))
        perigo = resumo_perigo(cri)
        nome = time.strftime("%Y-%m-%d_%H-%M-%S")
        pasta = os.path.join(PASTA, nome)
        print(f"[CaixaPreta] 💥 Você perdeu {perda:.0f}% ({hp_antes:.0f}% → {q_dano['hp']:.0f}%) | "
              f"estado {q_dano['estado']} | monstro mais perto: {perigo['mais_perto_sqm']} sqm | "
              f"{perigo['ate_3_sqm']} a até 3 sqm | provas em diagnostico/caixa_preta/{nome}")
        linhas, detalhes = list(_linhas), list(_detalhes)
        threading.Thread(target=self._salvar, args=(pasta, antes + depois, q_dano, hp_antes, perigo, linhas, detalhes),
                         daemon=True).start()

    def _salvar(self, pasta, quadros, q_dano, hp_antes, perigo, linhas, detalhes):
        try:
            os.makedirs(pasta, exist_ok=True)
            linha_tempo = []
            for i, q in enumerate(quadros):
                arq = f"quadro_{i:02d}.jpg"
                cv2.imwrite(os.path.join(pasta, arq), q["img"], [cv2.IMWRITE_JPEG_QUALITY, 90])
                linha_tempo.append({
                    "quadro": arq,
                    "t": round(q["t"] - q_dano["t"], 2),  # 0 = leitura em que o dano apareceu
                    "dano": q is q_dano,
                    "hora": time.strftime("%H:%M:%S", time.localtime(q["t"])),
                    "hp": q["hp"], "pet": q["pet"], "pos": q["pos"], "estado": q["estado"],
                    "criaturas": sorted(self.criaturas_na_imagem(q["img"])),
                })
            dados = {
                "hp_antes": hp_antes, "hp_depois": q_dano["hp"], "perda": hp_antes - q_dano["hp"],
                "estado": q_dano["estado"], "pos": q_dano["pos"], "perigo": perigo,
                "em_luta": bool(self.em_luta[0]),
                "linha_do_tempo": linha_tempo,
                "log_recente": linhas, "decisoes": detalhes,
            }
            with open(os.path.join(pasta, "evento.json"), "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"[CaixaPreta] não consegui salvar o evento: {e!r}")
