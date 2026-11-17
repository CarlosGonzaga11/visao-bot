"""
Posição do personagem no mapa, lida da caixinha de coordenadas do minimapa ("2956, 2311, 8").

Uma thread fica lendo (OCR) em segundo plano e guarda a última posição válida.
Só roda o OCR quando a imagem da caixinha muda (parado não gasta nada).
Leituras absurdas (pulo grande de uma vez) só são aceitas se repetirem, para um
erro de leitura não "teletransportar" o personagem.
"""
import re
import threading
import time

import cv2
import mss
import numpy as np

import controle
from config import COORD_REGION, TESSERACT_CMD

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
except ImportError:
    pytesseract = None

_PADRAO = re.compile(r"(\d{3,5}),(\d{3,5}),(\d{1,2})")


def ler_texto_coordenadas(img_bgr):
    """Lê a caixinha: primeiro com o leitor próprio de dígitos; o Tesseract fica só de reserva."""
    pos = ler_digitos(img_bgr)
    if pos:
        return pos
    return _ler_tesseract(img_bgr)


def _ler_tesseract(img_bgr):
    """OCR genérico (mais lento e erra quando o topo dos números está coberto)."""
    if pytesseract is None:
        return None
    cinza = img_bgr.max(axis=2)
    grande = cv2.resize(cinza, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    pb = np.where(grande > 150, 0, 255).astype(np.uint8)  # texto claro -> preto no branco
    pb = cv2.copyMakeBorder(pb, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    texto = pytesseract.image_to_string(
        pb, config="--psm 7 -c tessedit_char_whitelist=0123456789,").replace(" ", "")
    m = _PADRAO.search(texto)
    return tuple(int(v) for v in m.groups()) if m else None


def ler_coordenadas(sct, confirmar=False):
    """
    Leitura direta (sem thread). Com `confirmar` (ex.: para gravar um ponto da rota), lê até
    5 vezes e só aceita quando 2 leituras seguidas batem — evita gravar coordenada errada.
    """
    def ler():
        img = cv2.cvtColor(np.array(sct.grab(COORD_REGION)), cv2.COLOR_BGRA2BGR)
        return ler_texto_coordenadas(img)

    if not confirmar:
        return ler()
    anterior = None
    for _ in range(5):
        atual = ler()
        if atual and atual == anterior:
            return atual
        anterior = atual
        time.sleep(0.08)
    return None


def ponto_suspeito(pos, outros):
    """Coordenada que não combina com o resto da rota (ex.: leu '286' em vez de '2986')."""
    if not pos:
        return True
    validos = [o for o in outros if o and o is not pos]
    if not validos:
        return False
    xs = sorted(o[0] for o in validos)
    ys = sorted(o[1] for o in validos)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    return abs(pos[0] - mx) > 300 or abs(pos[1] - my) > 300


class Posicao(threading.Thread):
    """Mantém a posição atual atualizada em segundo plano."""

    def __init__(self):
        super().__init__(daemon=True)
        self._pos = None
        self._quando = 0.0
        self._lock = threading.Lock()
        self._candidata = None

    def atual(self, idade_max=3.0):
        """(x, y, z) da última leitura válida, ou None se está velha/indisponível."""
        with self._lock:
            if self._pos and time.time() - self._quando <= idade_max:
                return self._pos
        return None

    def _aceitar(self, nova):
        anterior = self._pos
        if anterior is None or (nova[2] == anterior[2]
                                and max(abs(nova[0] - anterior[0]), abs(nova[1] - anterior[1])) <= 12):
            ok = True
        else:
            # pulo grande ou mudança de andar: só aceita se a mesma leitura vier 2 vezes
            ok = nova == self._candidata
            self._candidata = nova
        if ok:
            with self._lock:
                self._pos, self._quando = nova, time.time()

    def run(self):
        ultima_img = None
        with mss.MSS() as sct:
            while not controle.deve_parar():
                try:
                    img = cv2.cvtColor(np.array(sct.grab(COORD_REGION)), cv2.COLOR_BGRA2BGR)
                    if ultima_img is not None and np.array_equal(img, ultima_img):
                        with self._lock:  # não mudou: a posição continua valendo
                            if self._pos:
                                self._quando = time.time()
                    else:
                        nova = ler_texto_coordenadas(img)
                        if nova:
                            self._aceitar(nova)
                        ultima_img = img
                except Exception as e:
                    print(f"[Posição] Erro lendo coordenadas: {e!r}")
                    time.sleep(1)
                time.sleep(0.05)


# ---------- Leitor próprio dos números do jogo (mais confiável que o Tesseract) ----------
#
# A fonte das coordenadas é sempre a mesma (pixelada, 8 px de altura). Os modelos de cada
# dígito ficam em calibracao/digitos/0.png .. 9.png. Cada dígito da tela é comparado com os
# modelos ALINHADO PELA PARTE DE BAIXO — assim funciona mesmo quando algo cobre o topo da
# caixinha (a barra de ícones do jogo cobre as 2 primeiras linhas do 1º número).

import glob as _glob
import os as _os

_DIR_DIGITOS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "calibracao", "digitos")
_modelos = {}


def _carregar_modelos():
    if not _modelos:
        for arq in _glob.glob(_os.path.join(_DIR_DIGITOS, "*.png")):
            img = cv2.imread(arq, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                _modelos[_os.path.basename(arq)[0]] = (img > 127).astype(np.uint8)
    return _modelos


def _comparar(glifo, modelo):
    """Semelhança (0..1) entre o dígito da tela e o modelo, alinhando pela base e testando deslocamentos."""
    h = glifo.shape[0]
    if h > modelo.shape[0]:
        return 0.0
    base = modelo[modelo.shape[0] - h:]  # só a parte de baixo do modelo (o topo pode estar coberto)
    largura = max(glifo.shape[1], base.shape[1]) + 2
    melhor = 0.0
    for desloc in (-1, 0, 1):
        a = np.zeros((h, largura), np.uint8)
        b = np.zeros((h, largura), np.uint8)
        a[:, 1:1 + glifo.shape[1]] = glifo
        x0 = 1 + desloc
        if x0 < 0 or x0 + base.shape[1] > largura:
            continue
        b[:, x0:x0 + base.shape[1]] = base
        soma = a.sum() + b.sum()
        if soma:
            melhor = max(melhor, 2 * (a & b).sum() / soma)
    return melhor


def ler_digitos(img_bgr, limiar=130):
    """Lê o texto da caixinha ("2971,2264,9") com os modelos. Retorna (x, y, z) ou None."""
    modelos = _carregar_modelos()
    if len(modelos) < 10:
        return None
    m = (img_bgr.max(axis=2) > limiar).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    texto = ""
    for i in sorted(range(1, n), key=lambda i: st[i][0]):
        x, y, w, h, a = st[i]
        if a < 2:
            continue
        if h <= 4:          # vírgula (pequena, embaixo)
            texto += ","
            continue
        if h < 5:
            continue
        glifo = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        nota, digito = max((_comparar(glifo, mod), d) for d, mod in modelos.items())
        if nota < 0.6:
            return None     # não parece um dígito: melhor não chutar
        texto += digito
    m = _PADRAO.search(texto)
    return tuple(int(v) for v in m.groups()) if m else None
