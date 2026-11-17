"""
Configuração automática da tela: descobre sozinho onde está cada coisa do jogo,
em qualquer monitor, mesmo se você mover ou redimensionar a janela.

O que é detectado:
  - Janela do jogo: pelo Windows (título "PokeAlliance"), em qualquer tela.
  - Área do mapa, tamanho do sqm e centro do personagem: pela borda direita do mapa
    (uma linha reta do topo ao fim do mapa). O mapa mostra 21 x 11 sqm, então
    sqm = altura / 11 e o personagem fica no meio.
  - Minimapa e caixinha de coordenadas: pelo título "Minimap".
  - Chat: pelo canto de baixo da janela.
  - Battle e barras de HP: já são achadas pelos títulos (tela.py).

Se alguma medida não fizer sentido (ex.: outra janela por cima), mantém a anterior.
"""
import ctypes
import json
import os
import sys
from ctypes import wintypes

import cv2
import numpy as np

import config

_user32 = ctypes.windll.user32
try:
    _user32.SetProcessDPIAware()  # coordenadas em pixels reais (telas com zoom do Windows)
except Exception:
    pass

TITULO_JANELA = "PokeAlliance"
TILES_VISIVEIS = (21, 11)  # sqm que o mapa mostra (largura x altura)

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_ANCORA_MINIMAP = os.path.join(PASTA, config.CALIBRACAO_DIR, "ancora_minimap.png")

# Posições em relação ao título "Minimap" (medidas no seu jogo)
OFF_COORD = (5, 28, 81, 19)       # caixinha "x, y, z"
OFF_MINIMAP = (-1, 48, 180, 120)  # área do minimapa
OFF_CRUZ = (88, 110)              # cruz do personagem no minimapa
# Chat: em relação ao canto de baixo-esquerdo da área da janela
OFF_CHAT = (18, -102, 600, 68)

ATUAL = {}  # último layout detectado


# ---------- Janela do jogo ----------

def janela_jogo():
    """Área interna (sem a barra de título) da janela do jogo em coordenadas de tela, ou None."""
    achadas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return True
        n = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.startswith(TITULO_JANELA):
            r = wintypes.RECT()
            _user32.GetClientRect(hwnd, ctypes.byref(r))
            p = wintypes.POINT(0, 0)
            _user32.ClientToScreen(hwnd, ctypes.byref(p))
            if r.right > 200 and r.bottom > 200:
                achadas.append({"left": p.x, "top": p.y, "width": r.right, "height": r.bottom})
        return True

    _user32.EnumWindows(cada, 0)
    return max(achadas, key=lambda j: j["width"] * j["height"]) if achadas else None


def arrumar_console():
    """
    Deixa o console do bot fora do caminho:
    - desliga o "modo de seleção" (QuickEdit): clicar no console congelava o bot;
    - se o console estiver por cima do jogo, manda ele para outra tela (ou minimiza);
    - devolve o foco para o jogo.
    """
    k32 = ctypes.windll.kernel32
    try:
        h = k32.GetStdHandle(-10)  # entrada do console
        modo = wintypes.DWORD()
        if k32.GetConsoleMode(h, ctypes.byref(modo)):
            k32.SetConsoleMode(h, (modo.value & ~0x0040) | 0x0080)  # tira QUICK_EDIT, liga EXTENDED_FLAGS
    except Exception:
        pass

    jogo_hwnd = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        n = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        if _user32.IsWindowVisible(hwnd) and buf.value.startswith(TITULO_JANELA):
            jogo_hwnd.append(hwnd)
        return True

    _user32.EnumWindows(cada, 0)
    jogo = janela_jogo()
    console = k32.GetConsoleWindow()
    if console and jogo and _user32.IsWindowVisible(console):
        r = wintypes.RECT()
        _user32.GetWindowRect(console, ctypes.byref(r))
        jx2, jy2 = jogo["left"] + jogo["width"], jogo["top"] + jogo["height"]
        cobre = r.left < jx2 and r.right > jogo["left"] and r.top < jy2 and r.bottom > jogo["top"]
        if cobre:
            telas = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
            def cada_tela(_m, _dc, rr, _p):
                t = rr.contents
                telas.append((t.left, t.top, t.right, t.bottom))
                return True

            _user32.EnumDisplayMonitors(None, None, cada_tela, 0)
            cx, cy = jogo["left"] + jogo["width"] // 2, jogo["top"] + jogo["height"] // 2
            livres = [t for t in telas if not (t[0] <= cx < t[2] and t[1] <= cy < t[3])]
            if livres:
                t = livres[0]
                w = min(r.right - r.left, t[2] - t[0] - 40)
                hgt = min(r.bottom - r.top, t[3] - t[1] - 80)
                _user32.SetWindowPos(console, 0, t[0] + 20, t[1] + 20, w, hgt, 0x0004)  # NOZORDER
                print("[Console] Estava por cima do jogo: mandei para a outra tela.")
            else:
                _user32.ShowWindow(console, 6)  # minimizar
                __import__("time").sleep(0.6)  # espera a animação: senão o console sai na medida do mapa
                print("[Console] Estava por cima do jogo: minimizei (o log continua em bot_log.txt).")
    if jogo_hwnd:
        try:
            _user32.SetForegroundWindow(jogo_hwnd[0])
        except Exception:
            pass


def area_de_busca(sct):
    """Onde procurar as coisas do jogo: a janela dele, ou todas as telas juntas."""
    return ATUAL.get("janela") or janela_jogo() or sct.monitors[0]


# ---------- Medidas ----------

def medir_mapa(img, origem):
    """
    Acha a área do mapa pela borda direita dele. Retorna dict com game_view,
    sqm e centro do personagem (coordenadas de tela), ou None se não fizer sentido.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    borda = np.abs(np.diff(g, axis=1)) > 12
    forca = borda[int(h * 0.1):int(h * 0.7)].mean(axis=0)
    candidatas = [x for x in range(w // 2, w - 1) if forca[x] > 0.9]
    if not candidatas:
        return None
    direita = candidatas[0] + 1

    # trecho contínuo mais comprido dessa borda (aceita falhas de até 3 px)
    ys = np.nonzero(borda[:, direita - 1])[0]
    if len(ys) < 2:
        return None
    melhor, ini, ant = (0, 0), ys[0], ys[0]
    for y in ys[1:]:
        if y - ant > 3:
            if ant - ini > melhor[1] - melhor[0]:
                melhor = (ini, ant)
            ini = y
        ant = y
    if ant - ini > melhor[1] - melhor[0]:
        melhor = (ini, ant)
    topo, fundo = int(melhor[0]), int(melhor[1]) + 1

    sqm = (fundo - topo) / TILES_VISIVEIS[1]
    esquerda = direita - TILES_VISIVEIS[0] * sqm
    if not (25 <= sqm <= 130) or esquerda < -sqm or fundo - topo < h * 0.4:
        return None
    cx, cy = (esquerda + direita) / 2, (topo + fundo) / 2
    return {
        "game_view": {"left": int(round(esquerda)) + origem[0], "top": topo + origem[1],
                      "width": int(round(direita - esquerda)), "height": fundo - topo},
        "sqm": round(sqm, 2),
        "centro": (int(round(cx)) + origem[0], int(round(cy)) + origem[1]),
    }


def achar_titulo_minimap(img, origem):
    tpl = cv2.imread(ARQ_ANCORA_MINIMAP)
    if tpl is None or img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]:
        return None
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, conf, _, (x, y) = cv2.minMaxLoc(res)
    return (x + origem[0], y + origem[1]) if conf >= 0.85 else None


def detectar(sct=None, img=None, janela=None):
    """
    Detecta o layout. Passe `img` + `janela` para testar com um print.
    Retorna dict com o que conseguiu achar (pode faltar algo).
    """
    if img is None:
        janela = janela or janela_jogo() or sct.monitors[0]
        img = cv2.cvtColor(np.array(sct.grab(janela)), cv2.COLOR_BGRA2BGR)
    origem = (janela["left"], janela["top"])
    res = {"janela": dict(janela)}

    mapa = medir_mapa(img, origem)
    if mapa:
        res.update(mapa)

    titulo = achar_titulo_minimap(img, origem)
    if titulo:
        tx, ty = titulo
        res["coord_region"] = {"left": tx + OFF_COORD[0], "top": ty + OFF_COORD[1],
                               "width": OFF_COORD[2], "height": OFF_COORD[3]}
        res["minimap_region"] = {"left": tx + OFF_MINIMAP[0], "top": ty + OFF_MINIMAP[1],
                                 "width": OFF_MINIMAP[2], "height": OFF_MINIMAP[3]}
        res["cruz"] = (tx + OFF_CRUZ[0], ty + OFF_CRUZ[1])

    base = janela["top"] + janela["height"]
    res["chat_region"] = {"left": janela["left"] + OFF_CHAT[0], "top": base + OFF_CHAT[1],
                          "width": OFF_CHAT[2], "height": OFF_CHAT[3]}
    return res


# ---------- Aplicar nos módulos ----------

def _setar(nome, valor):
    """Troca uma configuração em todos os módulos do bot que já a importaram."""
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "__file__", "") and \
                os.path.dirname(os.path.abspath(mod.__file__)) == PASTA and hasattr(mod, nome):
            setattr(mod, nome, valor)


def aplicar(res):
    """Usa o layout detectado no bot inteiro (sem precisar mexer no código)."""
    ATUAL.clear()
    ATUAL.update(res)
    if "game_view" in res:
        config.GAME_VIEW.update(res["game_view"])
        _setar("SQM_PX", res["sqm"])
        _setar("PLAYER_TILE_XY", res["centro"])
        # até quantos sqm dá para clicar sem sair do mapa (e sem cair na barra de baixo)
        meio_x = TILES_VISIVEIS[0] // 2 - 1
        meio_y = TILES_VISIVEIS[1] // 2 - 1
        _setar("NAV_VIEW_DX", (-meio_x, meio_x))
        _setar("NAV_VIEW_DY", (-meio_y, meio_y))
    if "coord_region" in res:
        config.COORD_REGION.update(res["coord_region"])
        config.MINIMAP_REGION.update(res["minimap_region"])
        _setar("PLAYER_SCREEN_X", res["cruz"][0])
        _setar("PLAYER_SCREEN_Y", res["cruz"][1])
        mm = sys.modules.get("minimapa")
        if mm:
            mm.recalcular_centro()
    config.CHAT_REGION.update(res["chat_region"])


def resumo(res):
    partes = []
    j = res.get("janela", {})
    partes.append(f"janela em ({j.get('left')}, {j.get('top')}) {j.get('width')}x{j.get('height')}")
    partes.append(f"sqm {res['sqm']:.1f}px, personagem em {res['centro']}" if "sqm" in res
                  else "⚠️ mapa não encontrado")
    partes.append("minimapa ✅" if "coord_region" in res else "⚠️ minimapa não encontrado")
    return " | ".join(partes)


ARQ_LAYOUT_OK = os.path.join(PASTA, config.CALIBRACAO_DIR, "layout_ok.json")
_CHAVES_MAPA = ("game_view", "sqm", "centro")


def _refs():
    try:
        with open(ARQ_LAYOUT_OK, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _parecido(a, b):
    return (abs(a["sqm"] - b["sqm"]) <= 1.5 and abs(a["centro"][0] - b["centro"][0]) <= 15
            and abs(a["centro"][1] - b["centro"][1]) <= 15)


def _plausivel(res):
    """
    A medida faz sentido? O mapa SEMPRE começa no topo da janela (game_view top = janela + ~4 px, em
    todos os prints de 07–09/11) e o sqm fica entre 40 e 60 px. A medida errada de 09/11 (45,45 px, com o
    painel na frente) punha o topo do mapa em y≈60.
    """
    gv, j = res.get("game_view"), res.get("janela")
    if not gv or not j or "sqm" not in res:
        return False
    return 40 <= res["sqm"] <= 60 and gv["top"] - j["top"] <= 10 and gv["left"] - j["left"] <= 130


def medir_pelo_personagem(img, janela):
    """
    Mede o mapa pela barrinha de vida do PRÓPRIO personagem (ele fica sempre no centro do mapa, que tem
    11 sqm de altura a partir do topo da janela): sqm = (centro_y − topo) / 5,5. Não depende da borda do
    mapa — em 09/11 a borda dava 45 px (personagem em (618, 311)) com o mapa real de 48,45 px.
    Conferido em prints: 07/11 → 50,9 (centro 584, 307); 08/11 → 49,3; 09/11 → 48,7/48,2.
    `img` = janela inteira. Devolve {sqm, centro, game_view} em coordenada de tela, ou None (sem a barra
    do personagem, ou ambíguo).
    """
    from tela import encontrar_barras_criaturas
    w = img.shape[1]
    achados = []
    for bx, by, _, _ in encontrar_barras_criaturas(img, (0, 0)):
        cx, cy = bx + 13, by + 26 + 3  # +3: o personagem é desenhado 3 px acima do centro do sqm
        # o personagem fica EXATAMENTE em x=584 em todos os prints (07–09/11); 15 px de folga pegou outra
        # criatura (09/11 18:20: x=572 → 46,55 px, errado) e estragou a hunt do Heroi Alfa
        if abs(cx - w * 584 / 1366) > 4:
            continue
        sqm = (cy - 4) / 5.5          # topo do mapa = topo da janela + 4 px (todos os prints)
        if 44 <= sqm <= 56:
            achados.append((sqm, cx, cy))
    if len(achados) != 1:
        return None
    sqm, cx, cy = achados[0]
    sqm = round(sqm, 2)
    x, y = cx + janela["left"], cy + janela["top"]
    return {"sqm": sqm, "centro": (x, y),
            "game_view": {"left": int(round(x - 10.5 * sqm)), "top": janela["top"] + 4,
                          "width": int(round(21 * sqm)), "height": int(round(11 * sqm))}}


def _pelo_personagem_ao_vivo(sct, janela):
    if sct is None:
        return None
    try:
        img = cv2.cvtColor(np.array(sct.grab({k: janela[k] for k in ("left", "top", "width", "height")})),
                           cv2.COLOR_BGRA2BGR)
        return medir_pelo_personagem(img, janela)
    except Exception:
        return None


def _guardar_ref(chave, medida):
    refs = _refs()
    refs[chave] = {k: medida[k] for k in _CHAVES_MAPA}
    try:
        with open(ARQ_LAYOUT_OK, "w", encoding="utf-8") as f:
            json.dump(refs, f, indent=2)
    except Exception:
        pass


def _conferir_mapa(sct, res):
    """
    A medida do mapa às vezes sai errada (console/painel por cima, mapa com muitas linhas retas).
    Guarda a última medida boa para cada tamanho de janela e recusa medidas muito diferentes.
    Confere com a medida PELO PERSONAGEM: borda implausível ou diferente dela (> 1 px de sqm) e o
    personagem medido igual 2x → usa a do personagem (e guarda).
    """
    j = res["janela"]
    chave = f"{j['width']}x{j['height']}"
    refs = _refs()
    ref = refs.get(chave)
    pers = _pelo_personagem_ao_vivo(sct, j)
    # Só usa o PERSONAGEM quando a BORDA não serve (faltou/implausível). Borda plausível e diferente do
    # personagem → fica com a borda (09/11 18:20: borda 48,45 certa x "personagem" 46,55 errado).
    if pers and ("sqm" not in res or not _plausivel(res)):
        import time
        time.sleep(0.3)
        pers2 = _pelo_personagem_ao_vivo(sct, j)
        if pers2 and abs(pers2["sqm"] - pers["sqm"]) <= 0.5 and abs(pers2["centro"][1] - pers["centro"][1]) <= 3:
            if "sqm" in res:
                print(f"[Layout] 📏 Borda do mapa deu {res['sqm']}px (personagem em {res['centro']}), mas pelo "
                      f"PERSONAGEM o sqm é {pers['sqm']}px (centro {pers['centro']}): usando a do personagem.")
            else:
                print(f"[Layout] 📏 Mapa medido pelo personagem: sqm {pers['sqm']}px, centro {pers['centro']}.")
            res.update(pers)
            _guardar_ref(chave, pers)
            return res
    if pers and "sqm" in res and _plausivel(res) and abs(pers["sqm"] - res["sqm"]) <= 1.0:
        # borda e personagem concordam: medida confirmada (a borda é mais precisa)
        if not ref or not _parecido(res, ref):
            print(f"[Layout] 🔄 Mapa confirmado pela borda e pelo personagem: sqm {res['sqm']}px, centro {res['centro']}.")
            _guardar_ref(chave, res)
        return res
    if "sqm" in res:
        if ref and not _parecido(res, ref):
            # O tamanho do mapa MUDA de verdade (barra de ícones do jogo, chat maior, outro personagem):
            # 09/11 o mapa era 48,45 px e o bot recusava e usava 50,9 (cliques/distâncias errados). Medida
            # plausível (mapa começa no topo da janela, sqm 40–60) e repetida igual 0,5 s depois → aceita.
            res2 = None
            if _plausivel(res):
                import time
                time.sleep(0.5)
                res2 = detectar(sct)
            if res2 and "sqm" in res2 and _plausivel(res2) and _parecido(res, res2):
                print(f"[Layout] 🔄 O mapa mudou de tamanho (sqm {ref['sqm']} → {res['sqm']}px, personagem em "
                      f"{res['centro']}): usando a medida NOVA.")
                refs[chave] = {k: res[k] for k in _CHAVES_MAPA}
                try:
                    with open(ARQ_LAYOUT_OK, "w", encoding="utf-8") as f:
                        json.dump(refs, f, indent=2)
                except Exception:
                    pass
                return res
            print(f"[Layout] ⚠️ Medi o mapa estranho (sqm {res['sqm']}px, personagem em {res['centro']}): "
                  "usando a última medida boa.")
            res.update({k: (tuple(ref[k]) if k == "centro" else ref[k]) for k in _CHAVES_MAPA})
        elif not ref:
            import time
            time.sleep(0.5)
            res2 = detectar(sct)
            if "sqm" in res2 and _parecido(res, res2):  # 2 medidas iguais: confia e guarda
                refs[chave] = {k: res[k] for k in _CHAVES_MAPA}
                try:
                    with open(ARQ_LAYOUT_OK, "w", encoding="utf-8") as f:
                        json.dump(refs, f, indent=2)
                except Exception:
                    pass
            else:
                for k in _CHAVES_MAPA:
                    res.pop(k, None)
    elif ref:
        res.update({k: (tuple(ref[k]) if k == "centro" else ref[k]) for k in _CHAVES_MAPA})
    return res


def detectar_e_aplicar(sct, avisar=True):
    res = _conferir_mapa(sct, detectar(sct))
    # se não achou o mapa ou o minimapa agora, mantém o que já tinha
    for chave in ("game_view", "sqm", "centro", "coord_region", "minimap_region", "cruz"):
        if chave not in res and chave in ATUAL:
            res[chave] = ATUAL[chave]
    aplicar(res)
    if avisar:
        print(f"[Layout] {resumo(res)}")
    return res


def janela_mudou():
    """True se a janela do jogo mudou de lugar ou de tamanho desde a última detecção."""
    j = janela_jogo()
    return j is not None and j != ATUAL.get("janela")


class VigiaLayout:
    """Thread que refaz a detecção sozinha quando a janela do jogo muda de lugar/tamanho."""

    def __init__(self, intervalo=3.0):
        import threading
        self.intervalo = intervalo
        self.thread = threading.Thread(target=self._rodar, daemon=True)

    def start(self):
        self.thread.start()

    def _rodar(self):
        import time
        import mss
        import controle
        with mss.MSS() as sct:
            while not controle.deve_parar():
                time.sleep(self.intervalo)
                if controle.trocando():  # rodízio: a troca mede de novo quando entra no jogo
                    continue
                try:
                    if janela_mudou():
                        time.sleep(0.8)  # espera terminar de arrastar/redimensionar
                        print("[Layout] A janela do jogo mudou — medindo de novo...")
                        detectar_e_aplicar(sct)
                except Exception as e:
                    print(f"[Layout] Erro ao medir a tela: {e!r}")
