"""
Efeitos negativos no monstrinho (blind, etc.) e uso de Medicine.

No jogo, os efeitos ativos no seu monstrinho aparecem como iconezinhos (com o tempo
restante embaixo) logo abaixo da barra de golpes F1..F7 (achada pelo cadeado no fim dela).
Os NEGATIVOS que já vimos têm uma borda vermelho-escura em forma de "L". Como existem
vários efeitos, também dá para ENSINAR ícones no painel (ruim ou bom), e ícones que o
bot não conhece são salvos em diagnostico/ (e por padrão ele usa Medicine por garantia).

O vermelho da borda (BGR ~10,10,120) é bem diferente do vermelho vivo da barra de HP
(BGR ~62,53,208), então a barra não é confundida com um efeito.
"""
import threading
import time

import cv2
import mss
import numpy as np

import config
import controle
import humano
from config import (
    MEDICINE_ATIVO, TECLA_MEDICINE, MEDICINE_ESPERA, MEDICINE_CLICAR_POKE, MEDICINE_EM_DESCONHECIDO,
)

LADO_MIN = 11  # tamanho mínimo da borda (o ícone tem ~16 px)

_ultimo_uso = [0.0]


def borda_vermelha(img):
    """Pixels do vermelho-escuro da borda dos efeitos negativos."""
    b, g, r = (img[..., i].astype(np.int16) for i in range(3))
    return (r >= 85) & (r <= 160) & (g <= 40) & (b <= 40) & (r > 3 * g) & (r > 3 * b)


def encontrar_negativos(img, origem=(0, 0)):
    """
    Cantos (x, y) dos ícones de efeito negativo: onde começa uma linha vermelha para a
    direita E uma para baixo (o "L"), e o pixel de dentro do ícone NÃO é vermelho.
    """
    red = borda_vermelha(img).astype(np.float32)
    h, w = red.shape
    if h < LADO_MIN + 2 or w < LADO_MIN + 2:
        return []
    horiz = cv2.filter2D(red, -1, np.ones((1, LADO_MIN), np.float32), anchor=(0, 0),
                         borderType=cv2.BORDER_CONSTANT) >= LADO_MIN - 0.5
    vert = cv2.filter2D(red, -1, np.ones((LADO_MIN, 1), np.float32), anchor=(0, 0),
                        borderType=cv2.BORDER_CONSTANT) >= LADO_MIN - 0.5
    dentro_nao_vermelho = np.zeros_like(horiz)
    dentro_nao_vermelho[:-2, :-2] = red[2:, 2:] < 0.5
    cantos = np.argwhere(horiz & vert & dentro_nao_vermelho)
    achados = []
    for y, x in cantos:
        if all(abs(int(x) - ax) > 4 or abs(int(y) - ay) > 4 for ax, ay in achados):
            achados.append((int(x), int(y)))
    return [(x + origem[0], y + origem[1]) for x, y in achados]


def negativos_na_tela(sct):
    """Ícones de efeito que precisam de Medicine (veja analisar_efeitos)."""
    return [e for e in efeitos_na_tela(sct) if e["precisa"]]


# ---------- Fileira de efeitos (embaixo da barra de golpes F1..F7) ----------

import glob
import hashlib
import os
from datetime import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR_APRENDIDOS = os.path.join(PASTA, "calibracao", "efeitos")
DIR_DIAG = os.path.join(PASTA, "diagnostico")
TAM = 17  # tamanho do ícone de efeito (px)


def icones_na_fileira(img):
    """
    Ícones de efeito na imagem: quadradinhos de ~17 px um pouco mais claros que o fundo.
    A "abertura" (MORPH_OPEN) apaga as letras finas do chat que às vezes passam por trás.
    Retorna [(x, y, w, h)].
    """
    m = (img.max(axis=2) > 28).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h, a in st[1:]
            if 12 <= w <= 24 and 12 <= h <= 24 and a >= 0.6 * w * h]


def _normalizar(icone):
    return cv2.resize(icone, (TAM, TAM), interpolation=cv2.INTER_AREA)


_aprendidos = {"mtime": None, "lista": []}


def aprendidos():
    """Ícones ensinados no painel: [(tipo 'neg'/'pos', imagem)] (relê se mudou)."""
    os.makedirs(DIR_APRENDIDOS, exist_ok=True)
    mtime = max([os.path.getmtime(f) for f in glob.glob(os.path.join(DIR_APRENDIDOS, "*.png"))]
                + [os.path.getmtime(DIR_APRENDIDOS)])
    if mtime != _aprendidos["mtime"]:
        lista = []
        for arq in sorted(glob.glob(os.path.join(DIR_APRENDIDOS, "*.png"))):
            img = cv2.imread(arq)
            if img is not None:
                lista.append((os.path.basename(arq)[:3], _normalizar(img)))
        _aprendidos.update(mtime=mtime, lista=lista)
    return _aprendidos["lista"]


def _parecido(icone, modelos, limite=0.75):
    a = _normalizar(icone).astype(np.float32)
    for tipo, modelo in modelos:
        r = cv2.matchTemplate(a, modelo.astype(np.float32), cv2.TM_CCOEFF_NORMED)[0][0]
        if r >= limite:
            return tipo
    return None


def analisar_efeitos(img, origem=(0, 0)):
    """
    Classifica cada ícone da fileira de efeitos:
      - borda vermelha em "L"         -> negativo
      - parecido com um ensinado "neg" -> negativo
      - parecido com um ensinado "pos" -> bom (ignora)
      - nenhum dos dois               -> desconhecido (usa Medicine se MEDICINE_EM_DESCONHECIDO)
    Retorna [{"x", "y", "tipo", "precisa", "img"}] em coordenada de tela.
    """
    cantos = encontrar_negativos(img)
    modelos = aprendidos()
    saida = []
    usados = set()
    for x, y, w, h in icones_na_fileira(img):
        icone = img[y:y + h, x:x + w]
        tipo = None
        for i, (cx, cy) in enumerate(cantos):
            if abs(cx - x) <= 4 and abs(cy - y) <= 4:
                tipo, _ = "negativo (borda vermelha)", usados.add(i)
                break
        if tipo is None:
            ensinado = _parecido(icone, modelos)
            tipo = {"neg": "negativo (ensinado)", "pos": "bom (ensinado)"}.get(ensinado, "desconhecido")
        precisa = tipo.startswith("negativo") or (tipo == "desconhecido" and MEDICINE_EM_DESCONHECIDO)
        saida.append({"x": x + origem[0], "y": y + origem[1], "tipo": tipo, "precisa": precisa, "img": icone})
    for i, (cx, cy) in enumerate(cantos):  # borda vermelha sem o quadradinho achado
        if i not in usados:
            saida.append({"x": cx + origem[0], "y": cy + origem[1], "tipo": "negativo (borda vermelha)",
                          "precisa": True, "img": img[cy:cy + TAM, cx:cx + TAM]})
    return saida


def regiao_efeitos(sct):
    """Faixa logo embaixo da barra de golpes (achada pelo cadeado no fim dela)."""
    from tela import localizar_ancora
    cadeado = localizar_ancora(sct, "golpes")
    if not cadeado:
        return None
    return {"left": max(0, cadeado[0] - 340), "top": cadeado[1] + 28, "width": 400, "height": 42}


_diag = {"vistos": set(), "ultimo": 0.0}


def efeitos_na_tela(sct):
    reg = regiao_efeitos(sct)
    if reg is None:  # barra de golpes não visível: procura só a borda vermelha na janela toda
        import layout
        area = layout.area_de_busca(sct)
        img = cv2.cvtColor(np.array(sct.grab(area)), cv2.COLOR_BGRA2BGR)
        return [{"x": x, "y": y, "tipo": "negativo (borda vermelha)", "precisa": True, "img": None}
                for x, y in encontrar_negativos(img, (area["left"], area["top"]))]
    img = cv2.cvtColor(np.array(sct.grab(reg)), cv2.COLOR_BGRA2BGR)
    lista = analisar_efeitos(img, (reg["left"], reg["top"]))
    for e in lista:
        if e["tipo"] == "desconhecido":
            _guardar_diagnostico(e, img)
    return lista


def _guardar_diagnostico(efeito, img_fileira):
    """Ícone que o bot não conhece: salva para você/eu vermos depois (1 vez por ícone)."""
    chave = hashlib.md5(cv2.resize(efeito["img"], (8, 8)).tobytes()).hexdigest()
    if chave in _diag["vistos"] or time.time() - _diag["ultimo"] < 5:
        return
    _diag["vistos"].add(chave)
    _diag["ultimo"] = time.time()
    os.makedirs(DIR_DIAG, exist_ok=True)
    nome = f"efeito_{datetime.now():%Y-%m-%d_%H-%M-%S}"
    cv2.imwrite(os.path.join(DIR_DIAG, nome + "_icone.png"), cv2.resize(efeito["img"], None, fx=4, fy=4,
                                                                          interpolation=cv2.INTER_NEAREST))
    cv2.imwrite(os.path.join(DIR_DIAG, nome + "_fileira.png"), img_fileira)
    acao = "vou usar Medicine por garantia" if MEDICINE_EM_DESCONHECIDO else "não vou usar Medicine"
    print(f"[Medicine] ❓ Efeito que eu não conheço em ({efeito['x']}, {efeito['y']}) — {acao}. "
          f"Salvei em diagnostico/{nome}_icone.png. Ensine se é bom ou ruim no painel (aba Modo de hunt).")


def ensinar(sct, x_mouse, y_mouse, negativo=True):
    """Guarda o ícone de efeito embaixo do mouse como negativo ('neg') ou bom ('pos')."""
    reg = regiao_efeitos(sct)
    if reg is None:
        return None
    img = cv2.cvtColor(np.array(sct.grab(reg)), cv2.COLOR_BGRA2BGR)
    icones = icones_na_fileira(img)
    if not icones:
        return None
    mx, my = x_mouse - reg["left"], y_mouse - reg["top"]
    x, y, w, h = min(icones, key=lambda c: (c[0] + c[2] / 2 - mx) ** 2 + (c[1] + c[3] / 2 - my) ** 2)
    if abs(x + w / 2 - mx) > 25 or abs(y + h / 2 - my) > 25:
        return None
    os.makedirs(DIR_APRENDIDOS, exist_ok=True)
    nome = f"{'neg' if negativo else 'pos'}_{datetime.now():%Y%m%d_%H%M%S}.png"
    cv2.imwrite(os.path.join(DIR_APRENDIDOS, nome), img[y:y + h, x:x + w])
    _aprendidos["mtime"] = None
    return nome


def contar_aprendidos():
    lista = aprendidos()
    return sum(1 for t, _ in lista if t == "neg"), sum(1 for t, _ in lista if t == "pos")


_estado = {"tinha": False, "usos_seguidos": 0, "desistiu_ate": 0.0}
MEDICINE_TENTATIVAS = 2  # Medicines seguidas sem o efeito sair -> para de insistir por MEDICINE_DESISTE_S
_lock = threading.Lock()


def curar_se_precisar(sct, em_thread=False):
    """
    Se o monstrinho tem efeito negativo, usa Medicine (no máximo 1 vez a cada
    MEDICINE_ESPERA segundos). Retorna True se usou.
    `em_thread`: chamado pela vigia em segundo plano (não usa as esperas do bot).
    """
    if not (MEDICINE_ATIVO and TECLA_MEDICINE):
        return False
    dormir = time.sleep if em_thread else controle.esperar
    negativos = negativos_na_tela(sct)
    if negativos and time.time() - controle.ultima_magia_buff < 4:
        # ícone desconhecido que apareceu logo depois da magia de defesa: é o BUFF, não efeito ruim.
        # Aprende como bom (senão a Medicine tira a defesa).
        for e in [e for e in negativos if e["tipo"] == "desconhecido"]:
            os.makedirs(DIR_APRENDIDOS, exist_ok=True)
            cv2.imwrite(os.path.join(DIR_APRENDIDOS, f"pos_buff_{datetime.now():%Y%m%d_%H%M%S}.png"), e["img"])
            _aprendidos["mtime"] = None
            print("[Medicine] 🛡️ Ícone novo logo depois da magia de defesa: aprendi que é BOM (não uso Medicine nele).")
            negativos.remove(e)

    with _lock:
        if not negativos:
            if _estado["tinha"]:
                print("[Medicine] ✅ O efeito negativo saiu.")
            _estado.update(tinha=False, usos_seguidos=0, desistiu_ate=0.0)
            return False
        if not _estado["tinha"]:
            onde = ", ".join(f"{e['tipo']} em ({e['x']}, {e['y']})" for e in negativos)
            print(f"[Medicine] ⚠️ Efeito ruim no monstrinho: {onde}")
            _estado["tinha"] = True
        if time.time() - _ultimo_uso[0] < MEDICINE_ESPERA:
            return False
        if time.time() < _estado["desistiu_ate"]:
            return False  # já viu que a Medicine não resolve: não fica apertando à toa
        if _estado["usos_seguidos"] >= MEDICINE_TENTATIVAS:
            # Antes continuava apertando para sempre (Medicine acabou, tecla errada, ícone que não é
            # efeito ruim). Agora para de insistir um tempo e tenta de novo depois.
            espera = float(getattr(config, "MEDICINE_DESISTE_S", 60.0))
            print(f"[Medicine] ⚠️ Usei Medicine {MEDICINE_TENTATIVAS}x e o efeito continua: paro por {espera:.0f}s. "
                  "Confira se tem Medicine, a tecla e a opção 'clicar no retrato do poke' "
                  "(ou ensine o ícone como BOM no painel, se não for efeito ruim).")
            _estado.update(usos_seguidos=0, desistiu_ate=time.time() + espera)
            return False
        _ultimo_uso[0] = time.time()
        _estado["usos_seguidos"] += 1

    print(f"[Medicine] 💊 Usando Medicine (tecla {TECLA_MEDICINE.upper()}).")
    controle.apertar(TECLA_MEDICINE)
    if MEDICINE_CLICAR_POKE:
        from tela import localizar_ancora
        from modos import OFF_RETRATO
        titulo = localizar_ancora(sct, "pokemon")
        if titulo:
            dormir(humano.variar(0.15))
            controle.clicar(titulo[0] + OFF_RETRATO[0], titulo[1] + OFF_RETRATO[1], espalhar=(6, 6))
    dormir(humano.variar(0.4))  # dá tempo do efeito sair antes da magia
    return True


class MonitorEfeitos(threading.Thread):
    """Vigia os efeitos negativos o tempo todo (andando, lutando, parado), não só antes de atacar."""

    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        while not (MEDICINE_ATIVO and TECLA_MEDICINE):  # espera ligarem no painel
            if controle.deve_parar():
                return
            time.sleep(1)
        print(f"[Medicine] Vigiando efeitos negativos no monstrinho (tecla {TECLA_MEDICINE.upper()}).")
        with mss.MSS() as sct:
            while not controle.deve_parar():
                try:
                    if not controle.esta_pausado():
                        from tela import ler_monstros
                        if ler_monstros(sct):  # sem inimigo: o efeito não atrapalha nada agora
                            curar_se_precisar(sct, em_thread=True)
                except Exception as e:  # um erro numa leitura não pode desligar a vigia
                    print(f"[Medicine] Erro lendo a tela (sigo vigiando): {e!r}")
                    time.sleep(1)
                time.sleep(0.3)
