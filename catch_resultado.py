"""
Resultado da ball pelo CHAT (aba Default): o jogo escreve "Sorry, your pokeball broke." quando NÃO pegou.

Antes o bot só olhava se o corpo sumiu — mas o corpo também some na animação da ball e fica escondido embaixo
do pet / Hydro Pump, e o bot desistia de shiny NÃO pego. Agora:
  "broke" apareceu  -> com certeza não pegou -> tenta de novo no MESMO sqm (corpo não anda), mesmo sem vê-lo;
  chat lido sem "broke" e o corpo sumiu -> pegou;
  chat não deu para ler (aba Default não ativa) -> volta ao jeito antigo (só pelo corpo).
Frase conferida por OCR em 5 prints reais (06/11 11:45 e 12:38, 07/11 20:58 e 21:37, preso_17-05-28).
"""
import re

import cv2

QUEBROU = re.compile(r"pok[eé]\s*ba[l1I]{2}\s*br[o0]ke|ba[l1I]{2}\s*br[o0]ke|your\s*pok", re.I)
_tess = [None]


def _tesseract():
    if _tess[0] is None:
        import pytesseract
        import config
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        _tess[0] = pytesseract
    return _tess[0]


def ler_linhas(img_chat):
    """Linhas de texto da área de mensagens do chat (imagem BGR já recortada)."""
    if img_chat is None or img_chat.size == 0:
        return []
    g = cv2.cvtColor(img_chat, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 90, 255, cv2.THRESH_BINARY_INV)
    try:
        txt = _tesseract().image_to_string(b, lang="eng", config="--psm 6")
    except Exception:  # noqa: BLE001  (sem Tesseract: resultado desconhecido)
        return []
    return [l.strip() for l in txt.splitlines() if l.strip()]


def regiao_chat():
    import config
    r = dict(config.CHAT_REGION)
    # pega 10 px a mais em cima: a última linha às vezes fica rente à borda
    return {"left": r["left"], "top": r["top"] - 10, "width": r["width"], "height": r["height"] + 10}


def foto(sct):
    """Linhas do chat agora (para comparar antes e depois da ball)."""
    from tela import capturar
    try:
        return ler_linhas(capturar(sct, regiao_chat()))
    except Exception:  # noqa: BLE001
        return []


def novas(antes, depois):
    """Linhas que apareceram depois (as que já estavam saem da conta, mesmo repetidas)."""
    sobra = list(antes)
    out = []
    for l in depois:
        if l in sobra:
            sobra.remove(l)
        else:
            out.append(l)
    return out


def quebrou(linhas):
    return any(QUEBROU.search(l) and re.search(r"br[o0]ke", l, re.I) for l in linhas)


def resultado(antes, depois):
    """'quebrou' | 'sem_quebra' (chat lido, nada de broke) | 'desconhecido' (não deu para ler o chat)."""
    if not depois:
        return "desconhecido"
    return "quebrou" if quebrou(novas(antes, depois)) else "sem_quebra"
