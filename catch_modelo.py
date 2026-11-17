"""
Especial pelo DESENHO (modelo), não só pela cor.

A cor sozinha confundia o Marowak shiny (corpo azul) com o Gyarados, o Hydro Pump, ícones e o chão.
Aqui a cor só aponta ONDE olhar (manchas da cor do especial) e quem decide é o desenho inteiro
(caveira + osso + corpo), comparado com um recorte real do corpo (matchTemplate com máscara).

Modelos: calibracao/catch_modelos/<id>/
    meta.json      {"nome", "sqm": px do sqm quando o recorte foi feito, "limiar", "ancora": [dx, dy] px do
                    centro do recorte até o centro do sqm do corpo, "h": [min, max] matiz da cor-guia}
    modelo_*.png   recorte(s) do corpo em tamanho real
A máscara é calculada do próprio recorte (pixels da cor-guia + brancos), sem o chão em volta.

Medido em 33 prints reais (08/11): os 6 Marowak shiny deram nota 0,98–1,00; tudo o resto ≤ 0,74
(corpo de Marowak normal, vivos, Gyarados, Magneton, chão). Limiar 0,85.
"""
import glob
import json
import os

import cv2
import numpy as np

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibracao", "catch_modelos")
LIMIAR_PADRAO = 0.85
_cache = {}


def _mascara(tpl, faixa_h):
    hsv = cv2.cvtColor(tpl, cv2.COLOR_BGR2HSV)
    h, s, v = [hsv[..., i].astype(int) for i in range(3)]
    cor = (h >= faixa_h[0]) & (h <= faixa_h[1]) & (s >= 80) & (v >= 60)
    branco = (s <= 60) & (v >= 170)
    return cv2.dilate((cor | branco).astype(np.uint8), np.ones((3, 3), np.uint8))


def carregar(pid):
    """Modelo pelo id (pasta). None se não existe."""
    if pid in _cache:
        return _cache[pid]
    pasta = os.path.join(PASTA, pid)
    try:
        with open(os.path.join(pasta, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        _cache[pid] = None
        return None
    imgs = [cv2.imread(a) for a in sorted(glob.glob(os.path.join(pasta, "modelo_*.png")))]
    imgs = [i for i in imgs if i is not None]
    if not imgs:
        _cache[pid] = None
        return None
    faixa = tuple(meta.get("h", (85, 115)))
    meta["recortes"] = [(i, _mascara(i, faixa)) for i in imgs]
    meta["escalas"] = {}
    _cache[pid] = meta
    return meta


def _na_escala(meta, sqm_px):
    """Recortes redimensionados para o sqm atual (janela de outro tamanho = sqm diferente)."""
    esc = round(float(sqm_px) / float(meta.get("sqm", sqm_px)), 3)
    if esc not in meta["escalas"]:
        lst = []
        for tpl, mk in meta["recortes"]:
            if abs(esc - 1) > 0.01:
                tpl = cv2.resize(tpl, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
                mk = cv2.resize(mk, (tpl.shape[1], tpl.shape[0]), interpolation=cv2.INTER_NEAREST)
            lst.append((tpl, np.dstack([mk] * 3)))
        meta["escalas"][esc] = (esc, lst)
    return meta["escalas"][esc]


def _candidatos(hsv, faixa_h, area_min):
    """Caixas (x, y, w, h) das manchas da cor-guia grandes o bastante para ser um corpo."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    cor = ((h >= faixa_h[0]) & (h <= faixa_h[1]) & (s >= 80) & (v >= 60)).astype(np.uint8)
    cor = cv2.dilate(cor, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(cor)
    return [tuple(int(v) for v in stats[i][:4]) for i in range(1, n) if stats[i][4] >= area_min]


def achar(img_view, origem, sqm_px, centro, pid, hsv=None):
    """
    Corpos/criaturas do modelo `pid` na imagem do mapa.
    Retorna [{"sqm": (dx, dy), "nota": 0..1, "px": (x, y) centro do sqm na tela}], melhor nota primeiro.
    Quem decide se está VIVO (barra em cima) é quem chama (catch.encontrar_corpos).
    """
    meta = carregar(pid)
    if meta is None:
        return []
    if hsv is None:
        hsv = cv2.cvtColor(img_view, cv2.COLOR_BGR2HSV)
    esc, recortes = _na_escala(meta, sqm_px)
    limiar = float(meta.get("limiar", LIMIAR_PADRAO))
    ax, ay = (a * esc for a in meta.get("ancora", (0, 0)))
    th, tw = recortes[0][0].shape[:2]
    area_min = max(40, int(0.06 * tw * th))
    achados = {}
    for (x, y, w, h) in _candidatos(hsv, meta.get("h", (85, 115)), area_min):
        x0, y0 = max(0, x - tw), max(0, y - th)
        x1, y1 = min(img_view.shape[1], x + w + tw), min(img_view.shape[0], y + h + th)
        janela = img_view[y0:y1, x0:x1]
        for tpl, mk in recortes:
            if janela.shape[0] < tpl.shape[0] or janela.shape[1] < tpl.shape[1]:
                continue
            r = cv2.matchTemplate(janela, tpl, cv2.TM_CCOEFF_NORMED, mask=mk)
            r = np.nan_to_num(r, nan=-1.0, posinf=-1.0, neginf=-1.0)
            while True:
                _, nota, _, (mx, my) = cv2.minMaxLoc(r)
                if nota < limiar:
                    break
                cx = x0 + mx + tpl.shape[1] / 2 + origem[0] + ax
                cy = y0 + my + tpl.shape[0] / 2 + origem[1] + ay
                sqm = (round((cx - centro[0]) / sqm_px), round((cy - centro[1]) / sqm_px))
                if sqm not in achados or achados[sqm]["nota"] < nota:
                    achados[sqm] = {"sqm": sqm, "nota": round(float(nota), 3),
                                    "px": (centro[0] + sqm[0] * sqm_px, centro[1] + sqm[1] * sqm_px)}
                r[max(0, my - th // 2):my + th // 2, max(0, mx - tw // 2):mx + tw // 2] = -1
    return sorted(achados.values(), key=lambda a: -a["nota"])
