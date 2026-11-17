"""
Target: escolher QUAIS monstros atacar pelo nome que aparece na Battle.

Como funciona:
  1. Na aba "👾 Target" do painel, com os monstros na Battle, aperte "Ler nomes da Battle".
     O painel lê cada nome (OCR, devagar, só nessa hora) e guarda a "foto" do nome em
     calibracao/target/<nome>.png.
  2. Você marca quais nomes atacar.
  3. Durante a hunt o bot só compara a foto do nome de cada linha da Battle com as guardadas
     (rápido, ~1 ms) e ignora quem não está marcado: não conta no lure, não clica, e a luta
     acaba quando não sobra nenhum alvo.
"""
import os
import re

import cv2
import numpy as np

import config

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.CALIBRACAO_DIR, "target")
_modelos = {}      # {nome: imagem binária}
_cache = {}        # {bytes do recorte: nome ou None}


def binarizar(nome_img):
    """Texto do nome (cinza claro) vira branco; recorta só a parte com texto."""
    if nome_img is None or nome_img.size == 0:
        return None
    m = (nome_img.max(axis=2) > 110).astype(np.uint8)
    ys, xs = np.nonzero(m)
    if len(xs) < 8:
        return None
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def carregar_modelos(forcar=False):
    if _modelos and not forcar:
        return _modelos
    _modelos.clear()
    _cache.clear()
    if os.path.isdir(PASTA):
        for arq in os.listdir(PASTA):
            if arq.lower().endswith(".png"):
                img = cv2.imread(os.path.join(PASTA, arq), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    _modelos[arq[:-4]] = (img > 127).astype(np.uint8)
    return _modelos


def _semelhanca(a, b):
    """0..1: quanto os dois textos binários batem (testa pequenos deslocamentos)."""
    if abs(a.shape[0] - b.shape[0]) > 2 or abs(a.shape[1] - b.shape[1]) > 3:
        return 0.0
    h, w = max(a.shape[0], b.shape[0]) + 2, max(a.shape[1], b.shape[1]) + 2
    melhor = 0.0
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            A = np.zeros((h, w), np.uint8)
            Bm = np.zeros((h, w), np.uint8)
            A[1:1 + a.shape[0], 1:1 + a.shape[1]] = a
            if dy + b.shape[0] > h or dx + b.shape[1] > w:
                continue
            Bm[dy:dy + b.shape[0], dx:dx + b.shape[1]] = b
            soma = int(A.sum()) + int(Bm.sum())
            if soma:
                melhor = max(melhor, 2 * int((A & Bm).sum()) / soma)
    return melhor


def reconhecer(nome_img):
    """Nome da linha da Battle (dos que você ensinou) ou None se não conhece."""
    b = binarizar(nome_img)
    if b is None:
        return None
    chave = b.tobytes() + bytes(b.shape)
    if chave in _cache:
        return _cache[chave]
    nota, nome = max(((_semelhanca(b, m), n) for n, m in carregar_modelos().items()), default=(0.0, None))
    r = nome if nota >= 0.8 else None
    if len(_cache) > 500:
        _cache.clear()
    _cache[chave] = r
    return r


def e_alvo(linha):
    """Essa linha da Battle deve ser atacada?"""
    if not config.TARGET_ATIVO:
        return True
    nome = reconhecer(linha.get("nome_img"))
    if nome is None:
        return bool(config.TARGET_DESCONHECIDOS)
    return nome.lower() in {t.lower() for t in (config.TARGETS or [])}


def ler_nome_ocr(nome_img):
    """Lê o nome escrito (Tesseract). Lento: só para ensinar, no painel."""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    except ImportError:
        return None
    if nome_img is None or nome_img.size == 0:
        return None
    g = nome_img.max(axis=2)
    grande = cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    pb = np.where(grande > 100, 0, 255).astype(np.uint8)  # texto claro -> preto no branco
    pb = cv2.copyMakeBorder(pb, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    texto = pytesseract.image_to_string(pb, config="--psm 7").strip()
    texto = re.sub(r"[^A-Za-z0-9 .'\-]", "", texto).strip()
    return texto or None


def ensinar(linhas):
    """
    Guarda a foto do nome de cada linha da Battle. Retorna [(nome, novo?)].
    Nomes iguais (ex.: 3 Geodude) viram um só.
    """
    os.makedirs(PASTA, exist_ok=True)
    carregar_modelos()
    vistos = []
    for l in linhas:
        b = binarizar(l.get("nome_img"))
        if b is None:
            continue
        ja = reconhecer(l.get("nome_img"))
        if ja:
            if ja not in [v[0] for v in vistos]:
                vistos.append((ja, False))
            continue
        nome = ler_nome_ocr(l.get("nome_img")) or f"monstro_{len(_modelos) + 1}"
        nome = re.sub(r'[\\/:*?"<>|]', "", nome)
        cv2.imwrite(os.path.join(PASTA, nome + ".png"), b * 255)
        carregar_modelos(forcar=True)
        vistos.append((nome, True))
    return vistos


def nomes_conhecidos():
    return sorted(carregar_modelos())
