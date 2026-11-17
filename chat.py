"""
Alarme de mensagens no chat "Default".

Como funciona:
  - A cada meio segundo, tira um print da área de mensagens do chat.
  - Separa as linhas de texto e guarda uma "impressão digital" de cada uma.
    Quando chega mensagem nova, aparece uma linha que ainda não foi vista.
  - Se a linha nova for AMARELA (alguém falando: jogador, NPC, GM), toca o alarme.
    Mensagens do sistema (ex.: "Sorry, your pokeball broke." em lilás) são ignoradas,
    a não ser que ALARME_QUALQUER_MSG esteja ligado.
  - Ao tocar: bipa, pausa o bot (opcional), salva um print em alarmes/ e
    registra o texto lido (OCR) em alarmes/chat_log.txt.

Importante: deixe a aba "Default" selecionada no chat.
"""
import hashlib
import os
import threading
import time
from datetime import datetime

import cv2
import mss
import numpy as np

import controle
from config import (
    CHAT_REGION, ALARME_ATIVO, ALARME_QUALQUER_MSG, ALARME_PAUSAR_BOT, ALARME_DURACAO,
    TESSERACT_CMD,
)

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR_ALARMES = os.path.join(PASTA, "alarmes")

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    OCR_OK = os.path.exists(TESSERACT_CMD)
except ImportError:
    OCR_OK = False


# ---------- Leitura do chat ----------

def mascara_texto(img):
    """Pixels de texto (o fundo do chat é quase preto)."""
    return img.max(axis=2) > 110


def separar_linhas(img):
    """Retorna [(y0, y1)] de cada linha de texto na imagem do chat."""
    texto = mascara_texto(img)
    ys = np.nonzero(texto.sum(axis=1) >= 2)[0]
    linhas, inicio = [], None
    for i, y in enumerate(ys):
        if inicio is None:
            inicio = y
        if i == len(ys) - 1 or ys[i + 1] > y + 1:
            linhas.append((int(inicio), int(y)))
            inicio = None
    return linhas


def recorte_linha(img, y0, y1):
    return img[max(0, y0 - 2):y1 + 3]


def impressao_digital(faixa):
    """Hash do formato do texto da linha (igual mesmo depois que a linha sobe no chat)."""
    m = mascara_texto(faixa)
    cols = np.nonzero(m.any(axis=0))[0]
    if len(cols) == 0:
        return None
    m = m[:, cols[0]:cols[-1] + 1]
    return hashlib.md5(np.packbits(m).tobytes() + str(m.shape).encode()).hexdigest()


def eh_fala(faixa):
    """Linha amarela = alguém falando (jogador, NPC, GM)."""
    px = faixa[mascara_texto(faixa)]
    if len(px) == 0:
        return False
    amarelo = (px[:, 0] < 90) & (px[:, 1] > 170) & (px[:, 2] > 170)
    return amarelo.mean() > 0.4


def ler_texto(faixa):
    """Tenta ler o texto da linha (OCR). A fonte do jogo é pixelada, então pode vir com erros."""
    if not OCR_OK:
        return "(OCR indisponível)"
    cinza = faixa.max(axis=2)
    grande = cv2.resize(cinza, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    img = cv2.copyMakeBorder(255 - grande, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    try:
        return pytesseract.image_to_string(img, lang="eng", config="--psm 7").strip()
    except Exception as e:
        return f"(erro no OCR: {e})"


class LeitorChat:
    """
    Compara a lista de linhas do chat com a anterior.
    Quando chega mensagem, as linhas antigas sobem e as novas aparecem embaixo:
    as novas são o que sobra depois de "encaixar" a lista antiga na atual.
    Assim, duas mensagens iguais seguidas também contam como duas.
    """

    def __init__(self):
        self.anterior = None  # lista de impressões digitais (de cima para baixo)

    def novas_linhas(self, img):
        faixas, hashes = [], []
        for y0, y1 in separar_linhas(img):
            h = impressao_digital(img[y0:y1 + 1])  # recorte justo: não muda ao subir
            if h:
                hashes.append(h)
                faixas.append(recorte_linha(img, y0, y1))

        anterior, self.anterior = self.anterior, hashes
        if anterior is None or hashes == anterior:
            return []  # primeira leitura (o que já estava no chat não conta) ou nada mudou

        # Acha quantas linhas do topo sumiram (d) para a lista antiga encaixar na nova
        for d in range(len(anterior) + 1):
            resto = anterior[d:]
            if hashes[:len(resto)] == resto:
                return faixas[len(resto):]
        return faixas  # não encaixou (ex.: chat limpo): considera tudo novo


# ---------- Barra de abas do chat (Default / Server Log / Loot / ... / PM) ----------
#
# Medido nos prints de 07/11 (janela 1366x705): a barra fica de 30 a 4 px ACIMA da área das mensagens.
# Texto das abas: linhas 9..18 da barra; moldura das abas: linhas 3..6 e 20..23.
#   aba ATIVA  = texto branco (+ moldura clara)  | aba com mensagem NOVA = texto VERMELHO
#   aba normal = texto cinza
# Mensagem privada (print do usuário 22:50): abre uma ABA NOVA à direita com o nome do player.
BARRA_ACIMA, BARRA_ALTURA = 30, 26
TEXTO_Y = (9, 19)
MOLDURA_Y = ((3, 7), (20, 24))
FUNDO_MAX = 60   # fundo da barra: brilho ~18–52


def regiao_abas(chat_region):
    return {"left": chat_region["left"] + 2, "top": chat_region["top"] - BARRA_ACIMA,
            "width": 1010, "height": BARRA_ALTURA}


def ler_abas(img):
    """
    Abas da barra (esquerda → direita): [{"x0", "x1", "estado": "ativa"|"vermelha"|"normal", "img"}].
    Separa pelos grupos de texto (colunas de moldura não contam; vão de >10 px separam abas).
    A seta "<" da esquerda (≤ 10 px de largura) é ignorada.
    """
    brilho = img.max(axis=2)
    texto = brilho[TEXTO_Y[0]:TEXTO_Y[1]] > FUNDO_MAX + 10
    moldura = np.zeros(img.shape[1], bool)
    for a, b in MOLDURA_Y:
        moldura |= (brilho[a:b] > FUNDO_MAX + 10).any(axis=0)
    cols = np.nonzero(texto.any(axis=0) & ~moldura)[0]
    if len(cols) == 0:
        return []
    grupos, ini, ant = [], cols[0], cols[0]
    for c in cols[1:]:
        if c - ant > 10:
            grupos.append((ini, ant))
            ini = c
        ant = c
    grupos.append((ini, ant))
    hsv = cv2.cvtColor(img[TEXTO_Y[0]:TEXTO_Y[1]], cv2.COLOR_BGR2HSV)
    abas = []
    for x0, x1 in grupos:
        if x1 - x0 < 10:
            continue  # seta "<" / ">"
        m = texto[:, x0:x1 + 1]
        h = hsv[:, x0:x1 + 1][m]
        b = brilho[TEXTO_Y[0]:TEXTO_Y[1], x0:x1 + 1][m]
        vermelho = (((h[:, 0] < 10) | (h[:, 0] > 170)) & (h[:, 1] > 120)).mean()
        branco = ((h[:, 1] < 50) & (b > 170)).mean()
        estado = "vermelha" if vermelho > 0.5 else ("ativa" if branco > 0.25 else "normal")
        abas.append({"x0": int(x0), "x1": int(x1), "estado": estado,
                     "img": img[TEXTO_Y[0] - 2:TEXTO_Y[1] + 2, max(0, x0 - 2):x1 + 3]})
    return abas


class VigiaAbas:
    """
    Compara as abas com as do começo (linha de base). Aba NOVA (mais abas que antes, entra à direita)
    = mensagem privada (ou canal aberto) → alarme com o nome lido por OCR, menos as abas da lista
    ALARME_ABAS_IGNORAR (ex.: "NPCs", que abre ao falar com NPC). Aba nova que fica VERMELHA de novo =
    outra mensagem privada. Server Log/Loot/Default ficam vermelhas sozinhas (mensagens do bot): são da
    linha de base e não contam.
    """

    def __init__(self):
        self.base = None          # quantas abas tinha no começo (ou depois de fechar alguma)
        self.avisadas = {}        # índice da aba nova -> estava vermelha no último aviso

    def checar(self, abas):
        """Devolve [(motivo, aba)] para alarmar."""
        if not abas:
            return []
        if self.base is None or len(abas) < self.base:
            self.base = len(abas)  # começo, ou fechou aba: nova linha de base
            self.avisadas = {i: v for i, v in self.avisadas.items() if i < len(abas)}
            return []
        eventos = []
        for i in range(self.base, len(abas)):
            aba = abas[i]
            vermelha = aba["estado"] == "vermelha"
            if i not in self.avisadas:
                self.avisadas[i] = vermelha
                eventos.append(("aba nova", aba))
            elif vermelha and not self.avisadas[i]:
                self.avisadas[i] = True
                eventos.append(("mensagem nova na aba", aba))
            elif not vermelha:
                self.avisadas[i] = False
        return eventos


def ler_nome_aba(aba):
    """Nome da aba por OCR (pode vir com erro: a fonte é pixelada)."""
    return ler_texto(aba["img"]) if aba.get("img") is not None and aba["img"].size else "?"


def aba_ignorada(nome):
    import config
    lista = [n.strip().lower() for n in str(getattr(config, "ALARME_ABAS_IGNORAR", "")).split(",") if n.strip()]
    nome = (nome or "").strip().lower()
    return any(n and (n == nome or n in nome) for n in lista)


# ---------- Quem falou (OCR da linha do Default) ----------
# Fala de player: "21:36 Fulano Silva (Titan 2): texto" ou "21:12 Heroi Alfa (167): texto" (nível/rank
# entre parênteses). NPC: "19:19 Mark: Good bye!" (sem parênteses).
import re

_PADRAO_FALA = re.compile(r"^\s*\d{1,2}[:.]\d{2}\s+(?P<nome>[^:(]+?)\s*(?P<nivel>\([^)]*\))?\s*:")


def quem_falou(texto):
    """("player"|"npc"|"?", nome) a partir do texto lido da linha."""
    m = _PADRAO_FALA.match(texto or "")
    if not m:
        return "?", ""
    return ("player" if m.group("nivel") else "npc"), m.group("nome").strip()


def eh_meu_nome(nome):
    import config
    meu = str(getattr(config, "MEU_NOME", "") or "").strip().lower()
    return bool(meu) and _parecido(nome.lower(), meu)


def _parecido(a, b):
    """Igual ignorando erros pequenos de OCR (até 2 letras diferentes)."""
    a, b = re.sub(r"\s+", " ", a.strip()), re.sub(r"\s+", " ", b.strip())
    if a == b:
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


# ---------- Alarme ----------

_tocando = threading.Event()


def tocar_som(duracao=ALARME_DURACAO):
    """Bipa alternando dois tons, sem travar o bot."""
    if _tocando.is_set():
        return

    def _bipar():
        import winsound
        _tocando.set()
        fim = time.time() + duracao
        try:
            while time.time() < fim:
                winsound.Beep(1200, 250)
                winsound.Beep(800, 250)
        finally:
            _tocando.clear()

    threading.Thread(target=_bipar, daemon=True).start()


def salvar_print(sct, texto):
    """Salva um print da tela inteira em alarmes/ e registra o motivo no log."""
    agora = datetime.now()
    os.makedirs(DIR_ALARMES, exist_ok=True)
    import layout
    tela = np.array(sct.grab(layout.area_de_busca(sct)))
    cv2.imwrite(os.path.join(DIR_ALARMES, f"{agora:%Y-%m-%d_%H-%M-%S}.png"),
                cv2.cvtColor(tela, cv2.COLOR_BGRA2BGR))
    with open(os.path.join(DIR_ALARMES, "chat_log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{agora:%Y-%m-%d %H:%M:%S}  {texto}\n")


def disparar(sct, faixa=None, texto=None, motivo="mensagem no Default", pausar=None):
    """Alarme: bipe, pausa (opcional), print da tela inteira em alarmes/ e o texto em chat_log.txt."""
    if texto is None:
        texto = ler_texto(faixa) if faixa is not None else ""
    agora = datetime.now()
    os.makedirs(DIR_ALARMES, exist_ok=True)

    print("\n" + "!" * 60)
    print(f"🔔 ALARME {agora:%H:%M:%S} — {motivo}: {texto}")
    print("!" * 60)

    tocar_som()
    if (ALARME_PAUSAR_BOT if pausar is None else pausar) and not controle.esta_pausado():
        controle.pausar(motivo)

    # Print da tela inteira e registro do texto
    try:
        import layout
        tela = np.array(sct.grab(layout.area_de_busca(sct)))
        cv2.imwrite(os.path.join(DIR_ALARMES, f"{agora:%Y-%m-%d_%H-%M-%S}.png"),
                    cv2.cvtColor(tela, cv2.COLOR_BGRA2BGR))
    except Exception as e:
        print(f"[Alarme] (sem print: {e!r})")
    with open(os.path.join(DIR_ALARMES, "chat_log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{agora:%Y-%m-%d %H:%M:%S}  [{motivo}] {texto}\n")


REPETIDA_S = 15.0  # a mesma fala dentro desse tempo não toca de novo (antes tocava 2x a mesma linha)


class FiltroFalas:
    """
    Decide se uma fala nova do Default merece alarme:
      - sua própria fala (MEU_NOME) → não;  NPC ("Nome: texto", sem nível) → não;
      - a mesma fala nos últimos REPETIDA_S → não;
      - player ("Nome (nível): texto") → SIM;  não deu para ler quem falou → SIM (segurança primeiro).
    """

    def __init__(self):
        self.recentes = {}  # texto normalizado -> quando

    def decidir(self, texto, agora=None):
        agora = time.time() if agora is None else agora
        chave = re.sub(r"\W+", "", (texto or "").lower())
        self.recentes = {k: t for k, t in self.recentes.items() if agora - t < REPETIDA_S}
        if chave and chave in self.recentes:
            return False, "repetida"
        if chave:
            self.recentes[chave] = agora
        tipo, nome = quem_falou(texto)
        if tipo == "player" and eh_meu_nome(nome):
            return False, "sua fala"
        if tipo == "npc":
            return False, f"NPC ({nome})"
        return True, ("player " + nome) if tipo == "player" else "não deu para ler quem falou"


def mensagem_da_fala(texto):
    """'18:20 Jogador A (123): oi tudo bem' -> 'oi tudo bem'."""
    m = _PADRAO_FALA.match(texto or "")
    return (texto[m.end():] if m else texto or "").strip()


class MonitorChat(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.leitor = LeitorChat()
        self.abas = VigiaAbas()
        self.filtro = FiltroFalas()
        self.avisou_aba = 0.0

    def run(self):
        while not ALARME_ATIVO:  # espera ligarem no painel
            if controle.deve_parar():
                return
            time.sleep(1)
        tipo = "qualquer mensagem" if ALARME_QUALQUER_MSG else "falas de player (texto amarelo)"
        print(f"[Alarme] Vigiando o chat Default: {tipo}; mensagem privada (aba nova). Deixe a aba Default selecionada.")
        geracao = controle.GERACAO[0]
        with mss.MSS() as sct:
            while not controle.deve_parar():
                if not ALARME_ATIVO:  # desligado no painel
                    time.sleep(1)
                    continue
                if controle.trocando():  # rodízio: na tela de seleção não tem chat
                    time.sleep(0.5)
                    continue
                if geracao != controle.GERACAO[0]:  # outro personagem: abas e falas dele são a nova base
                    geracao = controle.GERACAO[0]
                    self.abas = VigiaAbas()
                    self.leitor = LeitorChat()
                    self.filtro = FiltroFalas()
                try:
                    self.passo(sct)
                except Exception as e:  # um erro numa leitura não pode desligar o alarme
                    print(f"[Alarme] Erro lendo o chat (sigo vigiando): {e!r}")
                    time.sleep(2)
                time.sleep(0.5)

    def passo(self, sct):
        barra = cv2.cvtColor(np.array(sct.grab(regiao_abas(CHAT_REGION))), cv2.COLOR_BGRA2BGR)
        abas = ler_abas(barra)
        for motivo, aba in self.abas.checar(abas):
            nome = ler_nome_aba(aba)
            if aba_ignorada(nome):
                print(f"[Alarme] Aba \"{nome}\" ({motivo}): ignorada (lista ALARME_ABAS_IGNORAR).")
                continue
            disparar(sct, texto=f"aba \"{nome}\"", motivo=f"💬 MENSAGEM PRIVADA? ({motivo})")
        # Só lê as falas com a aba Default ATIVA (21:36: estava no "Game Chat PT-BR" e o chat global
        # tocava o alarme). Sem conseguir ler a barra (layout diferente): lê como antes.
        default_ativa = not abas or abas[0]["estado"] == "ativa"
        if not default_ativa:
            self.leitor.anterior = None  # ao voltar para o Default, o que já está lá não conta
            if time.time() - self.avisou_aba > 60:
                self.avisou_aba = time.time()
                print("[Alarme] ⚠️ A aba Default não está selecionada: não consigo ler as falas (deixe no Default).")
            return
        img = cv2.cvtColor(np.array(sct.grab(CHAT_REGION)), cv2.COLOR_BGRA2BGR)
        for faixa in self.leitor.novas_linhas(img):
            if not (ALARME_QUALQUER_MSG or eh_fala(faixa)):
                continue
            texto = ler_texto(faixa)
            tocar, porque = self.filtro.decidir(texto)
            if tocar:
                disparar(sct, faixa, texto=texto, motivo=f"fala no Default ({porque})")
            elif porque != "repetida":
                print(f"[Alarme] Fala no Default sem alarme ({porque}): {texto}")
