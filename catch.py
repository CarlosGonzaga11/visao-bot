"""
Sistema de catch com BIBLIOTECA DE PERFIS (calibra uma vez, fica salvo).

Cada perfil é um monstrinho que você quer pegar:
  - nome   : ex. "Rattata azul"
  - tipo   : "especial" (raro: o bot vigia a Battle e taca ball assim que ele morre)
             "normal"   (comum: o bot taca ball nos corpos depois de cada luta)
  - cor    : faixa de matiz/saturação/brilho medida numa amostra (mouse em cima do corpo + F9)
  - local  : coordenada onde você calibrou. O perfil só vale perto dali (CATCH_RAIO_LOCAL),
             então cada hunt usa os perfis dela sozinha. Sem local = vale em qualquer lugar.

Fica salvo em calibracao/catch_perfis.json (+ a imagem de cada amostra).
O bot relê o arquivo sozinho se você mudar os perfis no painel com ele rodando.

Como acha o corpo: manchas da cor do perfil na tela do jogo, fora de sqm com criatura
viva (barrinha). Especiais também são reconhecidos pelo ÍCONE na Battle.
"""
import json
import os
import re
import time

import cv2
import numpy as np

import catch_modelo
import catch_resultado
import controle
import humano
from config import (
    GAME_VIEW, SQM_PX, PLAYER_TILE_XY, CALIBRACAO_DIR,
    CATCH_ATIVO, CATCH_NORMAL_ATIVO, TECLA_BALL, CATCH_TENTATIVAS, CATCH_ESPERA,
    CATCH_DISTANCIA_MAX, CATCH_RAIO_LOCAL, CATCH_ESTRELAS,
    LOOT_ANTES_BALL, TECLA_LOOT, LOOT_ESPERA,
)
from tela import capturar, encontrar_barras_criaturas, BARRA_LARGURA

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR_CALIB = os.path.join(PASTA, CALIBRACAO_DIR)
ARQ_PERFIS = os.path.join(DIR_CALIB, "catch_perfis.json")
ARQ_ANTIGO = os.path.join(DIR_CALIB, "catch_especial.json")  # versão antiga (1 perfil só)

AMOSTRA_RAIO = 22  # recorte de 45x45 px em volta do mouse

# Cores medidas no seu jogo (matiz no HSV do OpenCV):
#   Rattata azul (especial): 109–115
#   Oddish (pet azulado):    117–118   <- não pode pegar
#   Mancha de poção azul:    122–124 (saturação ~240)
#   Rattata roxo comum:      129–133
PERFIL_RATTATA_AZUL = {"id": "rattata_azul", "nome": "Rattata azul", "tipo": "especial",
                       "h": [104, 115], "s": [100, 210], "v": [90, 255], "pixels": 150,
                       "local": None, "amostra": None}

MIN_PX_ICONE = 40   # pixels da cor do perfil no ícone da Battle
MIN_PX_CORPO = 25   # pixels da cor do perfil para considerar um corpo na tela


# ---------- Perfil de cor (a partir de uma amostra) ----------

def pixels_do_monstrinho(hsv):
    """Pixels coloridos que NÃO são chão (marrom/terra) nem pedra (cinza, pouco saturado)."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    chao = (h >= 5) & (h <= 30)
    return (s > 60) & (v > 50) & ~chao


def criar_perfil(img_bgr):
    """
    Cor do monstrinho na amostra. Usa a cor PRINCIPAL (o pico de matiz), para detalhes
    como olho vermelho ou rabo amarelo não alargarem demais a faixa.
    Retorna dict com h/s/v/pixels, ou None.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    m = pixels_do_monstrinho(hsv)
    if m.sum() < 30:
        return None
    px = hsv[m]
    hist = np.bincount(px[:, 0], minlength=180)
    hist = np.convolve(hist, np.ones(5), mode="same")  # suaviza
    pico = int(hist.argmax())
    perto = px[np.abs(px[:, 0].astype(int) - pico) <= 8]
    if len(perto) < 20:
        return None
    lo = np.percentile(perto, 10, axis=0)
    hi = np.percentile(perto, 90, axis=0)
    return {
        "h": [int(lo[0]) - 2, int(hi[0]) + 1],  # faixa justa: cores vizinhas (ex.: pet azulado) ficam de fora
        "s": [max(0, int(lo[1]) - 20), min(255, int(hi[1]) + 20)],
        "v": [max(0, int(lo[2]) - 20), 255],
        "pixels": int(len(perto)),
    }


# ---------- Biblioteca de perfis ----------

_cache = {"mtime": None, "perfis": []}


def _criar_arquivo_inicial():
    perfil = dict(PERFIL_RATTATA_AZUL)
    if os.path.exists(ARQ_ANTIGO):  # aproveita a amostra feita na versão antiga
        try:
            with open(ARQ_ANTIGO, encoding="utf-8") as f:
                antigo = json.load(f)
            perfil.update({k: antigo[k] for k in ("h", "s", "v", "pixels") if k in antigo})
        except Exception:
            pass
    salvar_perfis([perfil])


def carregar_perfis():
    """Todos os perfis salvos (relê o arquivo se ele mudou)."""
    if not os.path.exists(ARQ_PERFIS):
        _criar_arquivo_inicial()
    mtime = os.path.getmtime(ARQ_PERFIS)
    if mtime != _cache["mtime"]:
        try:
            with open(ARQ_PERFIS, encoding="utf-8") as f:
                _cache["perfis"] = json.load(f)
            _cache["mtime"] = mtime
        except Exception as e:
            print(f"[Catch] Não consegui ler os perfis ({e!r}).")
    return _cache["perfis"]


def salvar_perfis(perfis):
    os.makedirs(DIR_CALIB, exist_ok=True)
    # grava num arquivo temporário e troca de uma vez: a vigia de shiny (outra thread) também grava,
    # e quem lê nunca pega o arquivo pela metade
    tmp = ARQ_PERFIS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(perfis, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARQ_PERFIS)
    _cache["mtime"] = None  # força reler


def _novo_id(nome, perfis):
    base = re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_") or "perfil"
    usados = {p["id"] for p in perfis}
    i, novo = 2, base
    while novo in usados:
        novo, i = f"{base}_{i}", i + 1
    return novo


def adicionar_perfil(sct, x, y, nome, tipo, local=None):
    """Amostra o corpo embaixo do mouse e salva como perfil novo. Retorna o perfil ou None."""
    r = AMOSTRA_RAIO
    img = capturar(sct, {"left": x - r, "top": y - r, "width": 2 * r + 1, "height": 2 * r + 1})
    cor = criar_perfil(img)
    if not cor:
        return None
    perfis = list(carregar_perfis())
    pid = _novo_id(nome, perfis)
    arquivo = f"catch_{pid}.png"
    cv2.imwrite(os.path.join(DIR_CALIB, arquivo), img)
    perfil = {"id": pid, "nome": nome, "tipo": tipo, **cor,
              "local": list(local) if local else None, "amostra": arquivo}
    if tipo == "especial":
        # especial novo: achado pelo corpo morto no fim da luta; mancha pequena (pedaço de outro
        # monstro, efeito) não conta
        perfil["pelo_corpo"] = True
        perfil["min_corpo"] = max(MIN_PX_CORPO, cor["pixels"] // 3)
    perfis.append(perfil)
    salvar_perfis(perfis)
    return perfil


def remover_perfil(pid):
    salvar_perfis([p for p in carregar_perfis() if p["id"] != pid])


def alterar_perfil(pid, **mudancas):
    perfis = [dict(p) for p in carregar_perfis()]
    for p in perfis:
        if p["id"] == pid:
            p.update(mudancas)
    salvar_perfis(perfis)


def vale_aqui(perfil, pos):
    """
    O perfil vale onde o personagem está? (sem local = vale em qualquer lugar)
    Perfil com MODELO (desenho) vale em qualquer hunt: o desenho não confunde como a cor. O `local` dele só
    decide onde as estrelinhas ficam desligadas (`corpo_substitui_estrelas`).
    """
    if perfil.get("modelo") and catch_modelo.carregar(perfil["modelo"]) is not None:
        return True
    return no_local(perfil, pos)


def no_local(perfil, pos):
    """Está no lugar onde o perfil foi calibrado? (sem local = qualquer lugar)"""
    local = perfil.get("local")
    if not local or pos is None:
        return True
    return pos[2] == local[2] and max(abs(pos[0] - local[0]), abs(pos[1] - local[1])) <= CATCH_RAIO_LOCAL


def perfis_ativos(pos, tipo=None):
    """Perfis que valem aqui, do tipo pedido (e com aquele tipo de catch ligado)."""
    # Com as estrelinhas ligadas, o especial é achado por elas: perfil de COR de especial (o jeito
    # antigo) não vale mais — a cor do "Rattata azul" batia com Magnemite/Magneton e gastava ball à toa.
    # Exceção: perfis "pelo corpo" (catch pelo corpo morto, ver perfis_pelo_corpo).
    ligados = {"especial": CATCH_ATIVO and not CATCH_ESTRELAS, "normal": CATCH_NORMAL_ATIVO}
    return [p for p in carregar_perfis()
            if (tipo is None or p.get("tipo") == tipo)
            and (ligados.get(p.get("tipo"), False) or (p.get("tipo") == "especial" and _corpo_ligado(p)))
            and vale_aqui(p, pos)]


def _corpo_ligado(perfil):
    import config
    return bool(CATCH_ATIVO and getattr(config, "CATCH_CORPO", True) and perfil.get("pelo_corpo"))


def perfis_pelo_corpo(pos):
    """
    Especiais achados PELO CORPO MORTO (cor do perfil), no fim de cada luta — sem precisar de
    estrelinha nem do ícone na Battle. Só perfis marcados `pelo_corpo` e que valem aqui (local).
    """
    return [p for p in carregar_perfis()
            if p.get("tipo") == "especial" and _corpo_ligado(p) and vale_aqui(p, pos)]


def corpo_substitui_estrelas(pos):
    """
    Aqui tem perfil "pelo corpo" LIGADO A ESTE LUGAR: as estrelinhas são ignoradas (não seguem, não tacam ball).
    Perfil com modelo (desenho) e sem local procura o corpo em qualquer hunt, mas NÃO desliga as estrelinhas
    nas outras (na hunt do Magneton elas são o único jeito de achar o especial).
    """
    return any(p.get("local") and no_local(p, pos) for p in perfis_pelo_corpo(pos))



# ---------- Especiais por ESTRELINHAS em volta do nome ----------
#
# No jogo, o monstrinho especial tem estrelinhas amarelas (forma de cruz, matiz ~24)
# piscando em volta do nome. O texto dos golpes ("ROCK THROW!") é laranja (matiz 18) e
# tem forma de letra, então não confunde. As estrelinhas aparecem em grupo (2+).
# Ignora as faixas da barra de ícones (em cima) e da hotbar (embaixo), que ficam por cima do mapa.

ESTRELA_TOPO, ESTRELA_BAIXO = 40, 60   # faixas do mapa ignoradas (px)
OFF_ESTRELA_SQM = (55, 37)             # do grupo de estrelinhas até o centro do sqm do monstrinho (px)


_prints_especial = [0]


def salvar_print_especial(sct, sqm):
    """
    (Para ajustar) Quando acha um especial, salva a tela do jogo com um quadrado no sqm dele e
    círculos nas estrelinhas achadas, em diagnostico/especial_*.png (até 10 por vez que liga o bot).
    """
    if _prints_especial[0] >= 10:
        return
    _prints_especial[0] += 1
    try:
        img = capturar(sct, GAME_VIEW).copy()
        ox, oy = GAME_VIEW["left"], GAME_VIEW["top"]
        h = img.shape[0]
        for x, y in encontrar_estrelas(img[ESTRELA_TOPO:h - ESTRELA_BAIXO], (ox, oy + ESTRELA_TOPO)):
            cv2.circle(img, (x - ox, y - oy), 9, (255, 0, 255), 1)
        cx = PLAYER_TILE_XY[0] + sqm[0] * SQM_PX - ox
        cy = PLAYER_TILE_XY[1] + sqm[1] * SQM_PX - oy
        m = SQM_PX // 2
        cv2.rectangle(img, (int(cx - m), int(cy - m)), (int(cx + m), int(cy + m)), (0, 255, 255), 2)
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
        os.makedirs(pasta, exist_ok=True)
        cv2.imwrite(os.path.join(pasta, time.strftime("especial_%H-%M-%S.png")), img)
        cv2.imwrite(os.path.join(pasta, time.strftime("especial_%H-%M-%S_limpo.png")), capturar(sct, GAME_VIEW))
    except Exception as e:
        print(f"[Catch] (não consegui salvar o print do especial: {e!r})")


def encontrar_estrelas(img, origem=(0, 0)):
    """Centros (x, y) das estrelinhas amarelas em forma de cruz."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = ((h >= 21) & (h <= 31) & (s >= 90) & (v >= 215)).astype(np.uint8)
    # amarelo "largo" em volta: a estrelinha é um ponto isolado; o choque elétrico (THUNDER SHOCK)
    # é uma mancha amarela grande com pouco amarelo forte
    largo = ((h >= 15) & (h <= 35) & (s >= 60) & (v >= 150)).astype(np.float32)
    largo_em_volta = cv2.boxFilter(largo, -1, (28, 28), normalize=False)
    forte_em_volta = cv2.boxFilter(m.astype(np.float32), -1, (28, 28), normalize=False)
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    estrelas = []
    for i in range(1, n):
        x, y, w, hh, a = st[i]
        if not (4 <= w <= 20 and 4 <= hh <= 20 and 0.6 <= w / hh <= 1.7 and 6 <= a <= 0.55 * w * hh):
            continue
        ys, xs = np.nonzero(lab[y:y + hh, x:x + w] == i)
        cx, cy = np.median(xs), np.median(ys)
        cruz = ((np.abs(xs - cx) <= 1) | (np.abs(ys - cy) <= 1)).mean()  # braços finos na cruz
        # estrela = pontas finas nos 4 lados e o mais largo no meio. Letras de texto amarelo
        # ("SMALL POTION", "MAGNEMITE!") têm barra cheia no topo/lado (T, P, L, E...) e caíam aqui.
        comp = (lab[y:y + hh, x:x + w] == i)
        linhas, colunas = comp.sum(axis=1), comp.sum(axis=0)
        pontas_finas = max(linhas[0], linhas[-1], colunas[0], colunas[-1]) <= 3
        meio = 0.2 * hh <= int(np.argmax(linhas)) <= 0.8 * hh and 0.2 * w <= int(np.argmax(colunas)) <= 0.8 * w
        px, py = int(cen[i][0]), int(cen[i][1])
        lv, fv = largo_em_volta[py, px], forte_em_volta[py, px]
        isolada = lv <= 220 and fv >= 0.35 * lv  # medido: estrela ~100-150 / 0,6-0,75; choque 316 / 0,05
        if cruz >= 0.75 and pontas_finas and meio and isolada:
            estrelas.append((int(cen[i][0]) + origem[0], int(cen[i][1]) + origem[1]))
    return estrelas


def grupos_de_estrelas(estrelas, raio=45, minimo=2):
    grupos = []
    for e in estrelas:
        for g in grupos:
            if any(abs(e[0] - o[0]) <= raio and abs(e[1] - o[1]) <= raio for o in g):
                g.append(e)
                break
        else:
            grupos.append([e])
    return [(int(np.mean([p[0] for p in g])), int(np.mean([p[1] for p in g])))
            for g in grupos if len(g) >= minimo]


def especiais_por_estrela(img_view, origem):
    """
    Monstrinhos com estrelinhas: [{"sqm": (dx, dy), "vivo": bool}] em relação ao personagem.
    Liga cada grupo de estrelinhas à criatura cuja barrinha está logo ali (o nome fica em cima da
    barra). Se a barra estiver escondida (texto de golpe por cima), estima o sqm pelas estrelinhas.
    """
    h = img_view.shape[0]
    faixa = img_view[ESTRELA_TOPO:h - ESTRELA_BAIXO]
    grupos = grupos_de_estrelas(encontrar_estrelas(faixa, (origem[0], origem[1] + ESTRELA_TOPO)))
    barras = encontrar_barras_criaturas(img_view, origem)
    achados = []
    for gx, gy in grupos:
        # a barrinha fica logo abaixo do nome (onde estão as estrelinhas); ignora a do próprio personagem
        # Barra ROSA/MAGENTA também é criatura VIVA: o SHINY aparece na tela com nome e barra magenta (na Battle a
        # barra é verde — print 18:07:35). 09/11 18:07: com `not rosa` as estrelinhas do shiny ficavam "sem
        # barra" = "corpo" → 11 balls num shiny vivo andando (cada ball em outro sqm, contador sempre 1/6).
        perto = [(abs(bx + BARRA_LARGURA // 2 - gx) + abs(by - gy), bx, by, rosa) for bx, by, _, rosa in barras
                 if abs(bx + BARRA_LARGURA // 2 - gx) <= 70 and -15 <= by - gy <= 30
                 and (round((bx + BARRA_LARGURA // 2 - PLAYER_TILE_XY[0]) / SQM_PX),
                      round((by + 26 - PLAYER_TILE_XY[1]) / SQM_PX)) != (0, 0)]
        rosa = False
        if perto:
            _, bx, by, rosa = min(perto)
            cx, cy, vivo = bx + BARRA_LARGURA // 2, by + 26, True
        else:
            cx, cy, vivo = gx + OFF_ESTRELA_SQM[0], gy + OFF_ESTRELA_SQM[1], False
        sqm = (round((cx - PLAYER_TILE_XY[0]) / SQM_PX), round((cy - PLAYER_TILE_XY[1]) / SQM_PX))
        achados.append({"sqm": sqm, "vivo": vivo, "rosa": bool(rosa)})
    return achados


def estrelas_na_tela(sct):
    return especiais_por_estrela(capturar(sct, GAME_VIEW), (GAME_VIEW["left"], GAME_VIEW["top"]))

# ---------- Reconhecer na tela ----------

def mascara_perfil(hsv, perfil):
    lo = np.clip([perfil["h"][0], perfil["s"][0], perfil["v"][0]], 0, 255).astype(np.uint8)
    hi = np.clip([perfil["h"][1], perfil["s"][1], perfil["v"][1]], 0, 255).astype(np.uint8)
    return cv2.inRange(hsv, lo, hi) > 0


def icone_bate(icone_bgr, perfis):
    """O ícone da Battle é de algum desses perfis?"""
    if icone_bgr is None or icone_bgr.size == 0:
        return False
    hsv = cv2.cvtColor(icone_bgr, cv2.COLOR_BGR2HSV)
    return any(mascara_perfil(hsv, p).sum() >= MIN_PX_ICONE for p in perfis)


def _sqm_vivos(img_view, origem):
    vivos = set()
    for bx, by, _, _ in encontrar_barras_criaturas(img_view, origem):  # já em coordenada de tela
        cx, cy = bx + BARRA_LARGURA // 2, by + 26
        vivos.add((round((cx - PLAYER_TILE_XY[0]) / SQM_PX), round((cy - PLAYER_TILE_XY[1]) / SQM_PX)))
    return vivos


def area_dos_nomes(forma, barras, origem):
    """Onde ficam o NOME (em cima da barra, centrado) e a barrinha de cada criatura (máscara True)."""
    area = np.zeros(forma[:2], bool)
    for bx, by, _, _ in barras:
        x, y = int(bx - origem[0]), int(by - origem[1])
        area[max(0, y - 16):max(0, y + 7), max(0, x - 45):max(0, x + 72)] = True
    return area


def pixels_de_texto(hsv):
    """Cores dos nomes/barras do jogo (vermelho → amarelo → verde, bem saturadas)."""
    h, s = hsv[..., 0].astype(int), hsv[..., 1].astype(int)
    return ((h <= 75) | (h >= 165)) & (s >= 120)


def apagar_nomes(mascara, barras, origem, hsv=None):
    """
    Apaga da máscara o TEXTO dos nomes e as barrinhas: nome verde/amarelo virava "corpo" de shiny
    verde (ex.: "Heroi Alfa", "Gyarados"). Só os pixels com cor de texto dentro da área do nome —
    apagar a área inteira escondia metade do corpo que fica logo acima do personagem (o corpo
    "sumia" depois de andar até o lado dele e a ball não saía).
    """
    area = area_dos_nomes(mascara.shape, barras, origem)
    if hsv is not None:
        area &= pixels_de_texto(hsv)
    mascara[area] = 0
    return mascara


COR_VIZINHA = 8  # matizes logo acima/abaixo do perfil: "parecida, mas outra" (o azul do Gyarados)


def parte_de_outra_cor(hsv, perfil, caixa):
    """
    A mancha está no meio de uma cor PARECIDA com a do perfil (ex.: borda do Gyarados, que é azul
    102 e tem alguns pixels 93–99)? Corpo do shiny de verdade quase não tem a cor vizinha em volta
    (~6%); a borda do Gyarados tem tanto quanto (~100%).
    """
    x, y, w, h = caixa
    reg = hsv[max(0, y - 10):y + h + 10, max(0, x - 10):x + w + 10]
    hh, ss = reg[..., 0].astype(int), reg[..., 1].astype(int)
    lo, hi = perfil["h"]
    forte = ss >= max(60, perfil["s"][0])
    dentro = int((forte & (hh >= lo) & (hh <= hi)).sum())
    vizinha = int((forte & (((hh >= hi + 1) & (hh <= hi + COR_VIZINHA))
                            | ((hh >= lo - COR_VIZINHA) & (hh <= lo - 1)))).sum())
    return dentro > 0 and vizinha >= 0.5 * dentro


def encontrar_corpos(img_view, perfis, origem=None):
    """
    Corpos dos perfis na tela do jogo (manchas da cor, fora de sqm com criatura viva).
    Ignora as faixas da barra de ícones (em cima) e da hotbar (embaixo), que ficam POR CIMA do mapa:
    os ícones azuis das poções na hotbar batiam com a cor de shiny azul (≈48 px, a 4 sqm de você).
    Cada perfil pode pedir um tamanho mínimo próprio (`min_corpo`, em px).
    Retorna [(x_clique, y_clique, distancia_sqm, (dx, dy), perfil)], do mais perto para o mais longe.
    """
    if origem is None:
        origem = (GAME_VIEW["left"], GAME_VIEW["top"])
    if not perfis:
        return []
    hsv = cv2.cvtColor(img_view, cv2.COLOR_BGR2HSV)
    barras = encontrar_barras_criaturas(img_view, origem)
    vivos = _sqm_vivos(img_view, origem)
    achados = {}
    # Especial com MODELO (desenho real do corpo, catch_modelo.py): a cor só aponta onde olhar e o desenho
    # decide. A cor sozinha confundia o Marowak shiny com o Gyarados/Hydro Pump/chão (08/11).
    com_modelo = [p for p in perfis if p.get("modelo") and catch_modelo.carregar(p["modelo"])]
    faixas_modelo = [tuple(catch_modelo.carregar(p["modelo"]).get("h", (0, 0))) for p in com_modelo]
    for perfil in com_modelo:
        for a in catch_modelo.achar(img_view, origem, SQM_PX, PLAYER_TILE_XY, perfil["modelo"], hsv):
            dx, dy = a["sqm"]
            cy = PLAYER_TILE_XY[1] + dy * SQM_PX - origem[1]
            if cy < ESTRELA_TOPO or cy > img_view.shape[0] - ESTRELA_BAIXO:
                continue  # barra de ícones / hotbar por cima do mapa
            if (dx, dy) in vivos or (dx, dy) in achados:
                continue  # VIVO (tem barra em cima): o corpo no jogo é igual ao vivo, só sem nome e barra
            achados[(dx, dy)] = (PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                                 max(abs(dx), abs(dy)), (dx, dy), perfil)

    def coberto_por_modelo(p):
        """Perfil só de COR na mesma cor de um especial que tem modelo (ex.: o "shiny automático" azul da
        hunt do Marowak): o desenho já decide, a cor sozinha só traria erro."""
        if p.get("modelo") or not p.get("h"):
            return False
        return any(p["h"][0] <= f[1] and f[0] <= p["h"][1] for f in faixas_modelo)

    for perfil in perfis:
        if perfil in com_modelo or coberto_por_modelo(perfil):
            continue
        original = apagar_nomes(mascara_perfil(hsv, perfil), barras, origem, hsv)
        # criatura VIVA dessa cor (o shiny ainda vivo): o desenho dela é maior que o sqm e sobra para
        # cima/esquerda — essa sobra não é corpo
        sobras = set()
        for vx, vy in vivos:
            cx = int(PLAYER_TILE_XY[0] + vx * SQM_PX - origem[0])
            cy = int(PLAYER_TILE_XY[1] + vy * SQM_PX - origem[1])
            meia = int(SQM_PX // 2)  # SQM_PX é medido (ex.: 50.9): recorte precisa de número inteiro
            if original[max(0, cy - meia):cy + meia, max(0, cx - meia):cx + meia].sum() >= 60:
                sobras |= {(vx, vy - 1), (vx - 1, vy - 1), (vx - 1, vy)}
        juntos = cv2.dilate(original.astype(np.uint8), np.ones((5, 5), np.uint8))  # junta pedacinhos
        n, rotulos, stats, centros = cv2.connectedComponentsWithStats(juntos)
        minimo = int(perfil.get("min_corpo") or MIN_PX_CORPO)
        for i in range(1, n):
            if original[rotulos == i].sum() < minimo:
                continue
            if centros[i][1] < ESTRELA_TOPO or centros[i][1] > img_view.shape[0] - ESTRELA_BAIXO:
                continue  # barra de ícones / hotbar por cima do mapa
            if parte_de_outra_cor(hsv, perfil, tuple(int(v) for v in stats[i][:4])):
                continue  # pedaço de criatura de cor parecida (o pet), não corpo
            sx, sy = centros[i][0] + origem[0], centros[i][1] + origem[1]
            dx = round((sx - PLAYER_TILE_XY[0]) / SQM_PX)
            dy = round((sy - PLAYER_TILE_XY[1]) / SQM_PX)
            if (dx, dy) in vivos or (dx, dy) in achados or (dx, dy) in sobras:
                continue
            achados[(dx, dy)] = (PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                                 max(abs(dx), abs(dy)), (dx, dy), perfil)
    return sorted(achados.values(), key=lambda a: a[2])


def corpos_na_tela(sct, perfis):
    return encontrar_corpos(capturar(sct, GAME_VIEW), perfis)


class RastreadorEspecial:
    """
    Vigia os ESPECIAIS na Battle a cada leitura (andando, agrupando, lutando).
    Quando a quantidade cai, um deles morreu: marca "pendente" para tacar ball na hora.
    `pos_atual` = função que devolve a posição (x, y, z), para saber quais perfis valem aqui.
    """

    def __init__(self, pos_atual=lambda: None):
        self.pos_atual = pos_atual
        self.viu = False
        self.viu_icone = False     # um especial de PERFIL (cor) apareceu na Battle
        self.qtd = 0
        self.pendente = False
        # especiais com estrelinhas: {id: {"pos": (x, y, z), "visto": t, "battle": qtd na Battle}}
        self.estrelados = {}
        # especiais que sumiram SEM a Battle diminuir (outro monstro em cima escondeu as estrelinhas)
        self.escondidos = {}
        self.tentados = []          # [(lugar, quando)] onde já tacou ball
        self.empilhados = set()     # corpos que podem ter um corpo normal por cima: vale 2ª ball
        self.corpos = []           # [(x, y, z)] onde um especial com estrelinhas morreu
        self._prox_id = 0
        self._ultima_olhada = 0.0
        self._qtd_battle = 0

    def vigiar_estrelas(self, sct, qtd_battle):
        """
        Olha as estrelinhas na tela (no máx. 3x por segundo) e segue cada especial.
        Quando as estrelinhas de um especial somem E a Battle diminuiu desde a última vez que
        ele foi visto, ele morreu: guarda o lugar do corpo e marca para tacar ball.
        """
        if not (CATCH_ATIVO and CATCH_ESTRELAS):
            return
        agora = time.time()
        self._qtd_battle = qtd_battle
        if agora - self._ultima_olhada < 0.33:
            return
        self._ultima_olhada = agora
        pos = self.pos_atual()
        if pos is None:
            return
        achados_tela = estrelas_na_tela(sct)
        vistos = [(pos[0] + e["sqm"][0], pos[1] + e["sqm"][1], pos[2]) for e in achados_tela]
        rosas = [bool(e.get("rosa")) and e.get("vivo") for e in achados_tela]  # vivo em anti-block
        # Liga cada especial visto a UM que já estava sendo seguido (o mais perto, até 2 sqm).
        # Um para um: 2 especiais juntos no lure continuam sendo 2 (antes viravam 1 e só 1 levava ball).
        for i, d in list(self.escondidos.items()):
            if agora - d["visto"] > 90:
                del self.escondidos[i]
        todos = {**self.escondidos, **self.estrelados}
        pares = sorted((max(abs(d["pos"][0] - o[0]), abs(d["pos"][1] - o[1])), k, i)
                       for k, o in enumerate(vistos) for i, d in todos.items()
                       if d["pos"][2] == o[2])
        dono, usados = {}, set()
        for dist, k, i in pares:
            if dist <= 2 and k not in dono and i not in usados:
                dono[k] = i
                usados.add(i)
        for k, onde in enumerate(vistos):
            ja = dono.get(k)
            if ja is not None:
                self.escondidos.pop(ja, None)  # apareceu de novo
            if ja is None:
                ja, self._prox_id = self._prox_id, self._prox_id + 1
            antes = self.estrelados.get(ja) or self.escondidos.get(ja) or {}
            vezes = antes.get("vezes", 0) + 1
            # só acredita depois de ver 2 vezes seguidas (texto amarelo passageiro não engana)
            if vezes == 2:
                print(f"[Catch] ✨ Monstrinho com estrelinhas em {onde[0]}, {onde[1]}! Vou tacar ball quando morrer.")
                self.viu = True
                salvar_print_especial(sct, (onde[0] - pos[0], onde[1] - pos[1]))
            self.estrelados[ja] = {"pos": onde, "visto": agora, "battle": qtd_battle, "vezes": vezes,
                                   "rosa": rosas[k]}
        for i, d in list(self.estrelados.items()):
            if agora - d["visto"] > 1.2:  # estrelinhas sumiram
                del self.estrelados[i]
                if d.get("vezes", 2) < 2:
                    continue  # visto 1 vez só: era engano
                rx, ry = d["pos"][0] - pos[0], d["pos"][1] - pos[1]
                if abs(rx) >= 9 or abs(ry) >= 4 or d["pos"][2] != pos[2]:
                    continue  # estava na beirada da tela: saiu da visão andando, não morreu
                if qtd_battle >= d["battle"]:
                    self.escondidos[i] = d  # outro monstro em cima: continua de olho nele
                    continue
                if qtd_battle < d["battle"]:
                    print(f"[Catch] 💀 Especial com estrelinhas morreu em {d['pos'][0]}, {d['pos'][1]} — tacando ball.")
                    self.corpos.append(d["pos"])
                    self.pendente = True

    def marcar_tentado(self, lugar):
        """Já tacou ball nesse sqm: não conta de novo o mesmo especial (ele aparecia 2-3 vezes)."""
        self.tentados.append((lugar, time.time()))

    def _repetido(self, pos, outros):
        return any(o[2] == pos[2] and max(abs(o[0] - pos[0]), abs(o[1] - pos[1])) <= 1 for o in outros)

    def luta_acabou(self):
        """
        Battle limpa = todo mundo morreu. Todo especial que estava sendo seguido (visto ou
        escondido por outro monstro) morreu ali. Antes, se o combo matava tudo de uma vez, as
        estrelinhas não tinham "sumido há 1,2 s" ainda e o especial era esquecido.
        """
        agora = time.time()
        pos = self.pos_atual()
        self.tentados = [(p, t) for p, t in self.tentados if agora - t < 60]
        ja = [p for p, _ in self.tentados] + list(self.corpos)
        for d in list(self.estrelados.values()) + list(self.escondidos.values()):
            p = d["pos"]
            if d.get("vezes", 2) < 2 or agora - d["visto"] > 30:
                continue  # engano (visto 1 vez) ou muito antigo
            if pos and (p[2] != pos[2] or max(abs(p[0] - pos[0]), abs(p[1] - pos[1])) > 10):
                continue  # longe: era de outro lure
            if self._repetido(p, ja):
                continue  # o mesmo especial contado 2 vezes, ou já levou ball
            print(f"[Catch] 💀 Especial morreu na luta: corpo em {p[0]}, {p[1]}.")
            self.corpos.append(p)
            self.empilhados.add(p)  # morreu junto com outros: pode ter corpo normal em cima
            ja.append(p)
            self.pendente = True
        self.estrelados = {}
        self.escondidos = {}

    def atualizar(self, inimigos):
        especiais = perfis_ativos(self.pos_atual(), "especial")
        n = sum(1 for l in inimigos if icone_bate(l.get("icone"), especiais)) if especiais else 0
        if n > self.qtd:
            print(f"[Catch] ✨ Especial na Battle! ({n})")
        if n < self.qtd:
            print("[Catch] 💀 Especial morreu! Vou tacar ball no corpo.")
            self.pendente = True
        self.qtd = n
        self.viu = self.viu or n > 0
        self.viu_icone = self.viu_icone or n > 0
        return n

    def catch_feito(self):
        self.pendente = False
        self.viu_icone = self.qtd > 0
        self.viu = self.qtd > 0 or bool(self.estrelados)  # ainda tem especial vivo? continua de olho



# ---------- Loot antes da ball (sem auto loot) ----------

def pegar_loot(pos_atual, sqm, lootear=True):
    """
    Chega do lado do corpo (sqm relativo ao personagem) e aperta a tecla de loot.
    Retorna True se pegou (ou tentou), False se não deu para chegar perto.
    """
    dx, dy = sqm
    pos = pos_atual() if pos_atual else None
    if max(abs(dx), abs(dy)) > 1:
        if pos is None:
            return False  # sem coordenada não dá para saber quando chegou
        # sqm vizinho do corpo, do lado de onde o personagem está
        vx = dx - (dx > 0) + (dx < 0)
        vy = dy - (dy > 0) + (dy < 0)
        print(f"[Catch] 🚶 Indo {'pegar o loot do' if lootear else 'para perto do'} especial ({max(abs(dx), abs(dy))} sqm)...")
        controle.clicar(PLAYER_TILE_XY[0] + vx * SQM_PX, PLAYER_TILE_XY[1] + vy * SQM_PX, espalhar=(10, 10))
        destino = (pos[0] + vx, pos[1] + vy)
        fim = time.time() + 4.0
        while time.time() < fim:
            controle.esperar(0.15)
            agora = pos_atual()
            if agora and max(abs(agora[0] - destino[0]), abs(agora[1] - destino[1])) <= 0:
                break
        else:
            print("[Catch] ⚠️ Não consegui chegar do lado do corpo.")
    if not lootear:
        return True
    print(f"[Catch] 💰 Pegando o loot ({TECLA_LOOT.upper()})")
    controle.apertar(TECLA_LOOT)
    controle.esperar(humano.variar(LOOT_ESPERA))
    return True

# ---------- Tacar ball ----------

_gravados = [0]


def gravar_corpo_piscando(sct, pos, corpo, quadros=16):
    """
    (Temporário, para estudar) O corpo do especial pisca: salva alguns quadros em volta dele em
    diagnostico/ para descobrir como reconhecer o piscar. Só nas 5 primeiras mortes da sessão.
    """
    if _gravados[0] >= 5:
        return
    _gravados[0] += 1
    try:
        dx, dy = corpo[0] - pos[0], corpo[1] - pos[1]
        cx, cy = PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX
        r = int(SQM_PX * 2.5)
        regiao = {"left": int(cx - r), "top": int(cy - r), "width": 2 * r, "height": 2 * r}
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
        os.makedirs(pasta, exist_ok=True)
        nome = time.strftime("corpo_especial_%H-%M-%S")
        for i in range(quadros):
            cv2.imwrite(os.path.join(pasta, f"{nome}_{i}.png"), capturar(sct, regiao))
            time.sleep(0.2)
        print(f"[Catch] (estudo) {quadros} prints do corpo piscando salvos em diagnostico/{nome}_*.png")
    except Exception as e:
        print(f"[Catch] (estudo) não consegui salvar os prints: {e!r}")


def corpo_piscando(sct, pos, corpo, raio=1, duracao=1.6, minimo=120):
    """
    O corpo do especial PISCA (fica claro/brilhante e volta ao normal). Olha os sqm a até `raio`
    do lugar estimado por `duracao` segundos e devolve o sqm (x, y, z) que mais piscou, ou None.
    Só perto do corpo: os raios das paredes também mudam, mas ficam longe.
    """
    try:
        dx0, dy0 = corpo[0] - pos[0], corpo[1] - pos[1]
        S = SQM_PX
        cx = PLAYER_TILE_XY[0] + dx0 * S
        cy = PLAYER_TILE_XY[1] + dy0 * S
        meia = int(S * (raio + 0.5))
        regiao = {"left": int(cx - meia), "top": int(cy - meia), "width": 2 * meia, "height": 2 * meia}
        quadros = []
        fim = time.time() + duracao
        while time.time() < fim:
            quadros.append(cv2.cvtColor(capturar(sct, regiao), cv2.COLOR_BGR2GRAY).astype(np.int16))
            time.sleep(0.1)
        if len(quadros) < 3:
            return None
        pilha = np.stack(quadros)
        muda = (pilha.max(0) - pilha.min(0)) > 30
        melhor, onde = 0, None
        for j in range(-raio, raio + 1):
            for k in range(-raio, raio + 1):
                y0, x0 = int((j + raio) * S), int((k + raio) * S)
                bloco = muda[y0:y0 + int(S), x0:x0 + int(S)].astype(np.uint8)
                n = int(bloco.sum()) * (3 if (j, k) == (0, 0) else 1)  # o lugar estimado vale mais
                if n <= melhor:
                    continue
                # corpo piscando = mancha larga e baixa; raio da parede = risco alto e fino
                q, _, est, _ = cv2.connectedComponentsWithStats(bloco)
                if q < 2:
                    continue
                w, h = est[1 + int(np.argmax(est[1:, 4]))][2:4]
                if w >= 1.2 * h:
                    melhor, onde = n, (corpo[0] + k, corpo[1] + j, corpo[2])
        return onde if melhor >= minimo else None
    except Exception:
        return None


# Balls já tacadas em cada corpo (coordenada do mapa), somando as lutas: o mesmo corpo não ganha
# 1 ball nova a cada luta para sempre. Esquece depois de BALLS_MEMORIA_S (o corpo já sumiu).
_balls_por_corpo = {}
BALLS_MEMORIA_S = 300.0
BALL_SEM_MSG_MAX = 3   # balls SEGUIDAS sem mensagem no chat em qualquer corpo → para o catch (alvo andando)
BALL_NAO_SAIU_MAX = 2  # balls seguidas "sem mensagem + corpo ainda lá" (= a ball nem saiu) antes de desistir
REVER_DEPOIS_BALL_S = 3.0  # corpo "sumiu" logo depois da ball: é a animação ("pokeball broke"); olha de novo


_prints_sem_corpo = [0]
_especial_sem_ball = [0.0]  # quando um especial visto morreu e ainda não levou ball


def _avisar_sem_corpo(sct, motivo):
    print(f"[Catch] ⚠️ Sem ball: {motivo}.")
    if _prints_sem_corpo[0] >= 10:
        return
    _prints_sem_corpo[0] += 1
    try:
        pasta = os.path.join(PASTA, "diagnostico")
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, time.strftime("sem_corpo_%H-%M-%S.png"))
        cv2.imwrite(arq, capturar(sct, GAME_VIEW))
        print(f"[Catch]    Print salvo em diagnostico/{os.path.basename(arq)} (me mande).")
    except Exception as e:
        print(f"[Catch]    (não consegui salvar o print: {e!r})")


TIRAR_PET = [None]  # o bot liga: função(corpo_abs) -> True se deu order tirando o pet de cima do corpo


def fazer_catch(sct, rastreador=None, fim_de_luta=True):
    """
    Taca ball nos corpos por perto:
      - especiais: se apareceu algum especial (ou se não tem rastreador);
      - normais:   só no fim da luta (`fim_de_luta`), se o catch normal estiver ligado.
    """
    if not TECLA_BALL:
        if CATCH_ATIVO or CATCH_NORMAL_ATIVO:
            print("[Catch] Falta a tecla da ball (painel, aba Catch / Alarme).")
        return
    pos = rastreador.pos_atual() if rastreador else None

    perfis = []
    # perfil de cor: só se o ícone daquele especial apareceu na Battle (senão a cor pode bater
    # com água, flores etc. e o bot gastaria ball à toa)
    viu_especial_aqui = bool(rastreador is not None and (rastreador.viu_icone or rastreador.viu))
    if viu_especial_aqui:
        _especial_sem_ball[0] = time.time()
    if rastreador is None or rastreador.viu_icone:
        perfis += perfis_ativos(pos, "especial")
    if fim_de_luta:
        perfis += perfis_ativos(pos, "normal")
        # especial pelo CORPO MORTO: procura no fim de toda luta (não depende de estrelinha/ícone)
        perfis += [p for p in perfis_pelo_corpo(pos) if p not in perfis]
        # Viu um especial MORRER nesta luta (estrelinha/ícone) longe de onde o perfil foi calibrado:
        # o lugar pela estrelinha pode errar uns sqm (07/11 22:28: 1 ball no chão vazio a 3 sqm do corpo
        # e desistiu). Com essa prova, os perfis pelo corpo valem em qualquer lugar e acham o corpo de verdade.
        if viu_especial_aqui or (rastreador is not None and rastreador.corpos):
            extra = [p for p in perfis_pelo_corpo(None) if p not in perfis]
            if extra:
                print(f"[Catch] 🔎 Especial morreu nesta luta: procurando também pela cor do corpo "
                      f"({', '.join(p['nome'] for p in extra)}).")
            perfis += extra
    so_corpo = corpo_substitui_estrelas(pos)  # aqui as estrelinhas são ignoradas
    # corpos de especiais com estrelinhas (lugar onde morreram)
    corpos_estrela = list(rastreador.corpos) if rastreador is not None else []
    viu_especial = rastreador is None or rastreador.viu  # (antes de catch_feito zerar)
    if rastreador is not None:
        rastreador.corpos = []
        rastreador.catch_feito()
    if so_corpo:
        corpos_estrela = []
    usar_estrelas = CATCH_ATIVO and CATCH_ESTRELAS and not so_corpo
    # nenhum especial apareceu na luta: não para para procurar nada (hunt mais fluida)
    if not perfis and not corpos_estrela and not (usar_estrelas and fim_de_luta and viu_especial):
        return

    controle.esperar(0.6)  # tempo do corpo aparecer
    piscou = set()          # corpos de especial confirmados pelo brilho que pisca
    ainda_piscando = {}     # depois da ball: o corpo continua piscando? (não pegou)
    if corpos_estrela and pos is not None:
        corrigidos = []
        for c in corpos_estrela:
            achado = corpo_piscando(sct, pos, c) if c[2] == pos[2] else None
            if achado:
                if achado != c:
                    print(f"[Catch] ✨ Corpo do especial achado pelo brilho em {achado[0]}, {achado[1]}.")
                piscou.add(achado)
            corrigidos.append(achado or c)
        corpos_estrela = corrigidos
    import config
    ox, oy = int(getattr(config, "CATCH_AJUSTE_X", 0)), int(getattr(config, "CATCH_AJUSTE_Y", 0))
    agora0 = time.time()
    for k in [k for k, (_, t) in _balls_por_corpo.items() if agora0 - t > BALLS_MEMORIA_S]:
        del _balls_por_corpo[k]
    tentativas = {k: n for k, (n, _) in _balls_por_corpo.items()}  # o que já foi tacado antes conta
    tacadas = 0
    ultima_ball = 0.0
    lootados = set()
    estrela = {"nome": "Especial com estrelinhas", "tipo": "especial"}
    pos_atual = rastreador.pos_atual if rastreador else (lambda: None)
    pet_tirado = [False]  # já tirou o pet de cima de um corpo neste catch
    # Resultado de cada ball pelo CHAT ("Sorry, your pokeball broke."). Corpo onde a ball QUEBROU é tentado de
    # novo no MESMO sqm (coordenada do mapa), mesmo escondido pelo pet/magia: antes o bot achava que o corpo
    # "sumiu = pegou" e desistia de shiny não pego.
    quebradas = {}          # sqm absoluto -> perfil (a ball quebrou ali: tentar de novo)
    resultados = {"quebrou": 0, "sem_quebra": 0, "desconhecido": 0}
    nao_saiu = {}  # corpo -> balls seguidas sem mensagem no chat e com o corpo ainda lá
    sem_msg_seguidas = 0  # balls seguidas sem NENHUMA mensagem no chat (qualquer corpo)

    # Especial (shiny) que o bot VIU morrer: é obrigatório tentar. Logo depois da morte o pet ainda
    # está soltando magia (Hyper Beam/Hydro Pump) em cima dos corpos e o corpo fica escondido pelo
    # efeito: continua procurando por até CATCH_PROCURA_S (18:39 olhava 1 vez, não via e desistia).
    sabe_que_morreu = viu_especial_aqui or time.time() - _especial_sem_ball[0] < 120
    procura = float(getattr(config, "CATCH_PROCURA_S", 5.0)) * (1.0 if fim_de_luta else 0.6)
    procurar_ate = time.time() + procura if sabe_que_morreu else 0.0
    avisou_procura = [False]

    def procurar_mais():
        """Shiny morreu e o corpo ainda não apareceu (efeito por cima): espera e olha de novo."""
        if tacadas or time.time() >= procurar_ate:
            return False
        if not avisou_procura[0]:
            avisou_procura[0] = True
            print(f"[Catch] 🔎 Procurando o corpo do especial (até {procura:.0f}s: efeito de magia por cima?)...")
        controle.esperar(0.4)
        return True

    def limite(a):
        """Balls por corpo: especial (shiny) tem mais tentativas — é obrigatório tentar pegar."""
        if a[4].get("tipo") == "especial":
            return max(CATCH_TENTATIVAS, int(getattr(config, "CATCH_TENTATIVAS_ESPECIAL", 6)))
        return CATCH_TENTATIVAS

    def rever():
        """
        Logo depois da ball o corpo some (animação da ball/"broke"), e logo depois de andar até ele a
        tela ainda está rolando: espera e olha de novo (até REVER_DEPOIS_BALL_S).
        """
        if not (tacadas or lootados) or time.time() - ultima_ball > REVER_DEPOIS_BALL_S:
            return False
        controle.esperar(0.4)
        return True

    while True:
        pos = pos_atual() or pos
        alvos = [a for a in corpos_na_tela(sct, perfis)] if perfis else []
        if corpos_estrela and pos is not None:
            for cx, cy, cz in corpos_estrela:
                if cz == pos[2]:
                    # o desenho do especial (estrelinhas/brilho) fica deslocado do sqm de verdade
                    dx, dy = cx + ox - pos[0], cy + oy - pos[1]
                    alvos.append((PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                                  max(abs(dx), abs(dy)), (dx, dy), estrela))
        if usar_estrelas and fim_de_luta:  # luta acabou: estrelinha sem monstro vivo = corpo especial
            for e in estrelas_na_tela(sct):
                if not e["vivo"]:
                    dx, dy = e["sqm"][0] + ox, e["sqm"][1] + oy
                    alvos.append((PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                                  max(abs(dx), abs(dy)), (dx, dy), estrela))
        # tentativas contadas pela coordenada do mapa (o personagem pode andar, ex.: para pegar o loot)
        def chave(sqm_rel):
            return (pos[0] + sqm_rel[0], pos[1] + sqm_rel[1], pos[2]) if pos else sqm_rel

        # ball QUEBROU num corpo e ele não aparece agora (escondido/animação): continua sendo alvo, pela coordenada
        if pos is not None:
            vistos_k = {chave(a[3]) for a in alvos}
            for k, perf in quebradas.items():
                if k[2] == pos[2] and k not in vistos_k:
                    dx, dy = k[0] - pos[0], k[1] - pos[1]
                    alvos.append((PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                                  max(abs(dx), abs(dy)), (dx, dy), perf))
        alvos = sorted([a for a in alvos if tentativas.get(chave(a[3]), 0) < limite(a)], key=lambda a: a[2])
        # corpo de especial LONGE DEMAIS para a ball: chega perto só o necessário (alcance, não loot).
        # Antes ele era descartado em silêncio (o personagem fica na diagonal da box, e o shiny morre
        # do outro lado dela: 7–8 sqm).
        longe = [a for a in alvos if a[2] > CATCH_DISTANCIA_MAX and a[4].get("tipo") == "especial"]
        alvos = [a for a in alvos if a[2] <= CATCH_DISTANCIA_MAX]
        if not alvos and longe and pos is not None:
            a = longe[0]
            lugar_longe = (pos[0] + a[3][0], pos[1] + a[3][1], pos[2])
            if lugar_longe not in lootados:
                lootados.add(lugar_longe)
                print(f"[Catch] 🚶 Corpo de {a[4]['nome']} a {a[2]} sqm (a ball alcança até {CATCH_DISTANCIA_MAX}): "
                      "chegando perto para tacar.")
                passo = max(1, a[2] - CATCH_DISTANCIA_MAX + 1)  # só o que falta para entrar no alcance
                fx = (a[3][0] > 0) - (a[3][0] < 0)
                fy = (a[3][1] > 0) - (a[3][1] < 0)
                destino = (fx * min(passo, abs(a[3][0])), fy * min(passo, abs(a[3][1])))
                pegar_loot(pos_atual, (destino[0] + fx, destino[1] + fy), lootear=False)
                ultima_ball = time.time()
                continue
        # corpo achado pelas estrelinhas: depois da 1ª ball, só tenta de novo se ainda tem
        # estrelinha ali (não dá para ver o corpo; se já pegou, não gasta outra ball)
        if any(a[4] is estrela and tentativas.get(chave(a[3]), 0) >= 1 for a in alvos):
            ainda = {e["sqm"] for e in estrelas_na_tela(sct) if not e["vivo"]}
            # corpo que pode ter um normal por cima: a 1ª ball vai no corpo de cima (normal) e
            # some com ele; a 2ª acerta o especial embaixo
            empilhados = rastreador.empilhados if rastreador is not None else set()
            def repetir(a):
                k = chave(a[3])
                desenho = (k[0] - ox, k[1] - oy, k[2])  # onde o corpo aparece na tela
                if k in quebradas:  # o chat disse que a ball quebrou: não pegou, tenta de novo
                    return True
                if desenho in piscou:  # sabe se pegou: ainda pisca = não pegou
                    return ainda_piscando.get(k, False)
                return (a[3][0] - ox, a[3][1] - oy) in ainda or (desenho in empilhados and tentativas.get(k, 0) < 2)
            sem_estrela = [a for a in alvos if a[4] is estrela and tentativas.get(chave(a[3]), 0) >= 1
                           and not repetir(a)]
            # Sem estrelinha pode ser "pegou"... ou o PET (desenho grande, ex.: Gyarados) por cima do
            # corpo escondendo elas (07/11 22:13: 2 balls e desistiu com o shiny embaixo do Gyarados).
            # Fim de luta: tira o pet de cima (order) 1 vez e olha de novo.
            if sem_estrela and fim_de_luta and TIRAR_PET[0] and not pet_tirado[0]:
                k = chave(sem_estrela[0][3])
                if TIRAR_PET[0]((k[0] - ox, k[1] - oy, k[2])):
                    pet_tirado[0] = True
                    ultima_ball = time.time()  # rever(): olha de novo com o corpo à mostra
                    continue
            alvos = [a for a in alvos if a not in sem_estrela]
            if not alvos and not (rever() or procurar_mais()):
                break
            if not alvos:
                continue
        if not alvos:
            if rever() or procurar_mais():
                continue
            break
        x, y, dist, sqm, perfil = alvos[0]
        # Sem auto loot: pega o loot do especial ANTES da ball (anda até o lado do corpo + espaço).
        # Depois volta ao começo do laço, porque o personagem se mexeu e o corpo mudou de lugar na tela.
        lugar = (pos[0] + sqm[0], pos[1] + sqm[1], pos[2]) if pos else None
        if LOOT_ANTES_BALL and TECLA_LOOT and perfil.get("tipo") == "especial" \
                and lugar is not None and lugar not in lootados:
            lootados.add(lugar)
            pegar_loot(pos_atual, sqm)
            ultima_ball = time.time()  # (rever: o corpo pode "sumir" enquanto a tela rola)
            continue
        # longe do corpo (ex.: 5 sqm): só anda até perto se a opção estiver ligada. Com auto loot
        # não precisa: taca a ball daqui mesmo (até CATCH_DISTANCIA_MAX)
        if (config.CATCH_CHEGAR_PERTO and perfil.get("tipo") == "especial" and dist > 2
                and lugar is not None and lugar not in lootados):
            lootados.add(lugar)
            pegar_loot(pos_atual, sqm, lootear=False)
            ultima_ball = time.time()
            continue
        tentativas[chave(sqm)] = tentativas.get(chave(sqm), 0) + 1
        _balls_por_corpo[chave(sqm)] = (tentativas[chave(sqm)], time.time())
        tacadas += 1
        if rastreador is not None and perfil is estrela:
            rastreador.marcar_tentado(chave(sqm))
        print(f"[Catch] 🎾 {perfil['nome']} ({perfil['tipo']}) a {dist} sqm — tacando ball "
              f"(tentativa {tentativas[chave(sqm)]}/{limite(alvos[0])})")
        especial_aqui = perfil.get("tipo") == "especial"
        chat_antes = catch_resultado.foto(sct) if especial_aqui else []
        if getattr(config, "CATCH_BALL_MOUSE", True):
            controle.tecla_no_ponto(x, y, TECLA_BALL, espalhar=(6, 6))  # mouse em cima do corpo + tecla da ball
        else:
            controle.apertar(TECLA_BALL)        # jeito antigo: tecla e depois clique no corpo
            controle.esperar(humano.variar(0.15))
            controle.clicar(x, y, espalhar=(6, 6))
        controle.esperar(humano.variar(CATCH_ESPERA))
        if especial_aqui:
            res = catch_resultado.resultado(chat_antes, catch_resultado.foto(sct))
            if res == "sem_quebra":  # a mensagem pode chegar atrasada: confere mais uma vez
                controle.esperar(0.8)
                res = catch_resultado.resultado(chat_antes, catch_resultado.foto(sct))
            resultados[res] += 1
            k_ball = chave(sqm)
            if res == "quebrou":
                quebradas[k_ball] = perfil
                print(f"[Catch] ❌ A ball QUEBROU (chat): não pegou — tento de novo no mesmo sqm "
                      f"({tentativas[k_ball]}/{limite(alvos[0])}).")
            elif res == "sem_quebra":
                quebradas.pop(k_ball, None)
                print("[Catch] ✅ Sem 'pokeball broke' no chat: parece que PEGOU (confiro se o corpo sumiu).")
            if res == "sem_quebra":
                sem_msg_seguidas += 1
            elif res == "quebrou":
                sem_msg_seguidas = 0
            if sem_msg_seguidas >= BALL_SEM_MSG_MAX:
                # Uma captura de verdade dá no máx. 1 "sem mensagem" (o corpo some e o catch acaba). 3 seguidas =
                # a ball não está saindo (alvo VIVO andando, mouse fora, tecla errada). 09/11 18:07: 11 balls.
                print(f"[Catch] ⚠️ {sem_msg_seguidas} balls seguidas sem NENHUMA mensagem no chat: a ball não está "
                      f"saindo (alvo vivo? tecla {TECLA_BALL}?). Paro o catch.")
                _avisar_sem_corpo(sct, "balls sem mensagem no chat (a ball não saiu)")
                break
            else:
                print("[Catch] (não consegui ler o chat — deixe a aba Default aberta; decido pelo corpo)")
        ultima_ball = time.time()
        k = chave(sqm)
        if perfil is estrela and (k[0] - ox, k[1] - oy, k[2]) in piscou:
            p = pos_atual() or pos
            ainda_piscando[k] = corpo_piscando(sct, p, (k[0] - ox, k[1] - oy, k[2]), raio=0) is not None
            if ainda_piscando[chave(sqm)]:
                print("[Catch] Corpo ainda piscando: não pegou, tentando de novo.")
                # Ball tacada SEMPRE dá mensagem ("pokeball broke" ou a de captura). Nenhuma mensagem e o corpo
                # ainda lá = a ball NEM SAIU (mouse fora do corpo / tecla errada / longe). 09/11 17:33: 6 balls
                # assim, ~30 s parado no meio da hunt. 2 seguidas → desiste deste corpo e avisa.
                if especial_aqui and res == "sem_quebra":
                    nao_saiu[k] = nao_saiu.get(k, 0) + 1
                    if nao_saiu[k] >= BALL_NAO_SAIU_MAX:
                        tentativas[k] = limite(alvos[0])
                        print(f"[Catch] ⚠️ A ball NÃO SAIU {nao_saiu[k]}x (nenhuma mensagem no chat e o corpo ainda lá): "
                              f"desisto deste corpo. Confira a tecla da ball ({TECLA_BALL}) na hotbar deste personagem.")
                        _avisar_sem_corpo(sct, "a ball não saiu (sem mensagem no chat e o corpo ainda lá)")
                else:
                    nao_saiu.pop(k, None)

    if tacadas:
        extra = ""
        if any(resultados.values()):
            extra = (f" — chat: quebrou {resultados['quebrou']}, sem quebra {resultados['sem_quebra']}, "
                     f"ilegível {resultados['desconhecido']}")
        falta = [k for k in quebradas if tentativas.get(k, 0) >= 1]
        print(f"[Catch] Fim do catch ({tacadas} ball(s) tacada(s)){extra}.")
        if falta:
            print(f"[Catch] ⚠️ A última ball QUEBROU e acabaram as tentativas em {len(falta)} corpo(s): "
                  f"shiny pode não ter sido pego.")
            _avisar_sem_corpo(sct, "a ball quebrou e acabaram as tentativas")
        _especial_sem_ball[0] = 0.0
    elif fim_de_luta and time.time() - _especial_sem_ball[0] < 120:
        _especial_sem_ball[0] = 0.0
        # viu o shiny (ícone/estrelinha) e ele morreu, mas não achou corpo: não pode passar em silêncio
        _avisar_sem_corpo(sct, "vi o especial nesta luta, mas não achei o corpo dele na tela")
    elif lootados:
        # andou até o corpo e não viu mais ele: não pode passar em silêncio (foi assim às 17:32)
        try:
            pasta = os.path.join(PASTA, "diagnostico")
            os.makedirs(pasta, exist_ok=True)
            arq = os.path.join(pasta, time.strftime("corpo_sumiu_%H-%M-%S.png"))
            cv2.imwrite(arq, capturar(sct, GAME_VIEW))
            print(f"[Catch] ⚠️ Cheguei perto do corpo do especial mas não vejo mais ele — sem ball. "
                  f"Print salvo em diagnostico/{os.path.basename(arq)} (me mande).")
        except Exception as e:
            print(f"[Catch] ⚠️ Cheguei perto do corpo mas não vejo mais ele (sem print: {e!r}).")
