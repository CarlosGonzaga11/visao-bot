"""
"Jeito humano": deixa os movimentos do bot menos mecânicos.

  - Mouse: em vez de teletransportar, faz um trajeto em curva até o alvo,
    acelerando no começo e freando no fim (como uma mão de verdade).
  - Clique: cai num ponto um pouco diferente a cada vez e segura o botão
    por um tempinho variável.
  - Teclas: ficam apertadas um tempinho variável (não é um toque instantâneo).
  - Tempos: intervalos ganham variação aleatória.

HUMANO_INTENSIDADE (10–100%) controla o quanto tudo isso varia.
"""
import ctypes
import math
import os
import random
import time

import pydirectinput

from config import HUMANO_ATIVO, HUMANO_INTENSIDADE

_user32 = ctypes.windll.user32

# Testes (testes/rodar_testes.py liga BOT_TESTE=1): NUNCA mexe no mouse/teclado de verdade, mesmo
# que um teste esqueça de substituir alguma função. Só vale com a variável; o bot normal não muda.
EM_TESTE = os.environ.get("BOT_TESTE") == "1"
if EM_TESTE:
    class _SemEntrada:
        def __getattr__(self, nome):
            return lambda *a, **k: None

    class _User32Teste:
        def __getattr__(self, nome):
            if nome == "SetCursorPos":
                return lambda *a, **k: None
            return getattr(ctypes.windll.user32, nome)

    pydirectinput = _SemEntrada()
    _user32 = _User32Teste()
I = max(0.0, min(1.0, HUMANO_INTENSIDADE / 100))  # 0..1


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def posicao_mouse():
    p = _POINT()
    _user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def variar(valor, fracao=0.3):
    """Valor com variação aleatória (ex.: 1.5 s vira algo entre ~1.3 e ~1.8 s)."""
    if not HUMANO_ATIVO or valor <= 0:
        return valor
    return valor * random.uniform(1 - fracao * I, 1 + fracao * I * 1.3)


def espalhar(x, y, raio_x, raio_y=None):
    """Ponto perto de (x, y), mais provável perto do centro (não sempre o mesmo pixel)."""
    if not HUMANO_ATIVO:
        return x, y
    raio_y = raio_x if raio_y is None else raio_y
    dx = max(-raio_x, min(raio_x, random.gauss(0, raio_x / 2)))
    dy = max(-raio_y, min(raio_y, random.gauss(0, raio_y / 2)))
    return round(x + dx * I), round(y + dy * I)


def mover_mouse(x, y):
    """Leva o mouse até (x, y): em curva e com aceleração no modo humano, direto se não."""
    x, y = int(x), int(y)
    if not HUMANO_ATIVO:
        _user32.SetCursorPos(x, y)
        return
    x0, y0 = posicao_mouse()
    dist = math.hypot(x - x0, y - y0)
    if dist < 3:
        _user32.SetCursorPos(x, y)
        return

    duracao = (0.07 + dist / 2600) * random.uniform(0.8, 1.35) * (0.6 + 0.6 * I)
    duracao = max(0.05, min(0.4, duracao))
    # ponto de controle da curva: deslocado para o lado do caminho reto
    mx, my = (x0 + x) / 2, (y0 + y) / 2
    px, py = -(y - y0) / dist, (x - x0) / dist  # perpendicular
    curva = random.uniform(-0.22, 0.22) * dist * I
    cx, cy = mx + px * curva, my + py * curva

    passos = max(6, int(duracao / 0.012))
    inicio = time.perf_counter()
    for i in range(1, passos + 1):
        t = i / passos
        t = (1 - math.cos(math.pi * t)) / 2  # acelera e freia
        bx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x
        by = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y
        _user32.SetCursorPos(round(bx), round(by))
        # dorme só o que falta para o tempo do passo (o sleep do Windows atrasa)
        falta = inicio + duracao * i / passos - time.perf_counter()
        if falta > 0:
            time.sleep(falta)
    _user32.SetCursorPos(x, y)


def clicar(x, y, botao="left"):
    mover_mouse(x, y)
    if not HUMANO_ATIVO:
        pydirectinput.click(int(x), int(y), button=botao)
        return
    time.sleep(random.uniform(0.02, 0.07))
    pydirectinput.mouseDown(button=botao, _pause=False)
    time.sleep(random.uniform(0.04, 0.11))
    pydirectinput.mouseUp(button=botao, _pause=False)


def tecla(nome):
    if not HUMANO_ATIVO:
        pydirectinput.press(nome)
        return
    pydirectinput.keyDown(nome, _pause=False)
    time.sleep(random.uniform(0.04, 0.12))
    pydirectinput.keyUp(nome, _pause=False)


def chance(probabilidade):
    """True com essa probabilidade (0..1), escalada pela intensidade. Nunca no modo normal."""
    return HUMANO_ATIVO and random.random() < probabilidade
