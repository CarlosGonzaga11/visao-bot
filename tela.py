"""
Leitura de informações da tela: barras de HP (personagem e monstrinho) e monstros na Battle.

As janelas do jogo podem mudar de lugar (ao mover/redimensionar), então o bot acha
cada janela pelo TÍTULO dela ("âncora"): uma imagem pequena do título, procurada na tela.
As posições da Battle e das barras são guardadas RELATIVAS a essas âncoras.
"""
import json
import os
import threading
import time

import cv2
import numpy as np

from config import (
    BATTLE_REGION, CALIBRACAO_DIR, TOLERANCIA_COR_BARRA,
    BATTLE_BARRA_X, BATTLE_CLIQUE_X, BATTLE_CLIQUE_OFFSET_Y,
    BATTLE_PRIMEIRA_BARRA_Y, BATTLE_ALTURA_LINHA, MONSTRINHO_NA_BATTLE,
    BATTLE_ANCORA_OFFSET, GAME_VIEW, SQM_PX, PLAYER_TILE_XY, IGNORAR_ROSA,
)

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR_CALIB = os.path.join(PASTA, CALIBRACAO_DIR)
ARQ_CALIBRACAO = os.path.join(DIR_CALIB, "calibracao.json")

# Título de cada janela (imagens em calibracao/)
ANCORAS = {
    "battle": "ancora_battle.png",    # título "Battle"
    "pokemon": "ancora_pokemon.png",  # título "Pokémon" (onde ficam as barras de HP)
    "golpes": "ancora_golpes.png",    # cadeado no fim da barra de golpes F1..F7
}
ANCORA_CONFIANCA = 0.85
ANCORA_CACHE_S = 2.0  # procura de novo a cada 2 s (a janela pode ter mudado de lugar)


def capturar(sct, regiao):
    img = np.array(sct.grab(regiao))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


# ---------- Âncoras (achar janelas pelo título) ----------

_templates = {}
_cache = {}
_lock = threading.Lock()


def _template(nome):
    if nome not in _templates:
        _templates[nome] = cv2.imread(os.path.join(DIR_CALIB, ANCORAS[nome]))
    return _templates[nome]


def localizar_ancora(sct, nome, usar_cache=True):
    """Retorna (x, y) do canto do título da janela na tela, ou None se não achou."""
    agora = time.time()
    with _lock:
        if usar_cache and nome in _cache and agora - _cache[nome][0] < ANCORA_CACHE_S:
            return _cache[nome][1]

    tpl = _template(nome)
    if tpl is None:
        return None
    import layout  # aqui dentro para não dar import circular
    monitor = layout.area_de_busca(sct)  # só a janela do jogo, em qualquer tela
    th, tw = tpl.shape[:2]

    def procurar(regiao):
        res = cv2.matchTemplate(capturar(sct, regiao), tpl, cv2.TM_CCOEFF_NORMED)
        _, conf, _, (x, y) = cv2.minMaxLoc(res)
        return (x + regiao["left"], y + regiao["top"]) if conf >= ANCORA_CONFIANCA else None

    # Rápido: procura só em volta de onde a janela estava da última vez (~2 ms).
    # Se ela mudou de lugar, aí sim procura na tela inteira (~130 ms).
    pos = None
    anterior = _cache.get(nome, (0, None))[1]
    if anterior:
        m = 40
        x0 = max(monitor["left"], anterior[0] - m)
        y0 = max(monitor["top"], anterior[1] - m)
        x1 = min(monitor["left"] + monitor["width"], anterior[0] + tw + m)
        y1 = min(monitor["top"] + monitor["height"], anterior[1] + th + m)
        pos = procurar({"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0})
    if pos is None:
        pos = procurar(monitor)

    with _lock:
        _cache[nome] = (agora, pos)
    return pos


# ---------- Calibração ----------

def carregar_calibracao():
    if not os.path.exists(ARQ_CALIBRACAO):
        raise SystemExit("Calibração não encontrada. Calibre na aba 'Calibração' do painel.")
    with open(ARQ_CALIBRACAO, encoding="utf-8") as f:
        return json.load(f)


def salvar_calibracao_barra(nome, barra):
    """Grava (ou atualiza) uma barra no calibracao.json sem apagar as outras."""
    calib = {}
    if os.path.exists(ARQ_CALIBRACAO):
        with open(ARQ_CALIBRACAO, encoding="utf-8") as f:
            calib = json.load(f)
    calib[nome] = barra
    os.makedirs(DIR_CALIB, exist_ok=True)
    with open(ARQ_CALIBRACAO, "w", encoding="utf-8") as f:
        json.dump(calib, f, indent=2)


def medir_barra(sct, x0, x1, y):
    """
    Mede uma barra entre x0 e x1 na linha y (de preferência CHEIA).
    A cor da barra é a cor mais comum na linha (ignora o texto por cima).
    Se achar a janela "Pokémon", guarda a posição relativa a ela.
    """
    if x1 < x0:
        x0, x1 = x1, x0
    linha = capturar(sct, {"left": x0, "top": y, "width": x1 - x0 + 1, "height": 1})
    cores, contagem = np.unique(linha.reshape(-1, 3), axis=0, return_counts=True)
    cor = [int(c) for c in cores[contagem.argmax()]]
    barra = {"x0": int(x0), "x1": int(x1), "y": int(y), "cor": cor}

    ancora = localizar_ancora(sct, "pokemon", usar_cache=False)
    if ancora:
        barra.update({"ancora": "pokemon", "dx0": int(x0 - ancora[0]),
                      "dx1": int(x1 - ancora[0]), "dy": int(y - ancora[1])})
    return barra


# ---------- Barras de HP ----------

def porcentagem_barra(linha_bgr, cor_cheia, tolerancia=TOLERANCIA_COR_BARRA):
    """
    Recebe uma linha de pixels da barra (1 x N) e a cor da barra cheia.
    A barra enche da esquerda para a direita, então o pixel mais à direita
    com a cor da barra indica o quanto ela está cheia.
    (Usar o mais à direita evita erro quando há texto tipo "350/500" em cima da barra.)
    """
    pixels = linha_bgr.reshape(-1, 3).astype(int)
    diff = np.abs(pixels - np.array(cor_cheia, dtype=int)).max(axis=1)
    preenchidos = np.nonzero(diff <= tolerancia)[0]
    if len(preenchidos) == 0:
        return 0.0
    return (preenchidos[-1] + 1) / len(pixels) * 100


def posicao_barra(sct, barra):
    """Posição atual (x0, x1, y) da barra, seguindo a janela se ela mudou de lugar."""
    if barra.get("ancora"):
        ancora = localizar_ancora(sct, barra["ancora"])
        if ancora is None:
            return None  # janela não está visível
        return ancora[0] + barra["dx0"], ancora[0] + barra["dx1"], ancora[1] + barra["dy"]
    return barra["x0"], barra["x1"], barra["y"]


def ler_barra(sct, barra):
    """Retorna a % da barra, ou None se a janela dela não estiver na tela."""
    pos = posicao_barra(sct, barra)
    if pos is None:
        return None
    x0, x1, y = pos
    regiao = {"left": x0, "top": y, "width": x1 - x0 + 1, "height": 1}
    return porcentagem_barra(capturar(sct, regiao), barra["cor"])


# ---------- Cor rosa (anti-block) ----------

def eh_rosa(bgr):
    """
    Monstro que NÃO dá para atacar: barra ROSA (anti-block de respawn, matiz ~150) ou ROXA/violeta
    (~110–135, também mais escura). Antes só o rosa claro contava: os roxos entravam na conta do
    lure e o bot atacava do nada. Barra de vida normal nunca é azul/roxa/rosa: vai do vermelho (0)
    ao verde (60) — então a faixa 105–170 é segura.
    """
    h, s, v = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0]
    return 105 <= h <= 170 and s > 80 and v > 70


# ---------- Battle ----------

def regiao_battle(sct):
    """Região atual da lista da Battle (segue a janela), ou None se não achou."""
    ancora = localizar_ancora(sct, "battle")
    if ancora is None:
        return None
    return {
        "left": ancora[0] + BATTLE_ANCORA_OFFSET[0],
        "top": ancora[1] + BATTLE_ANCORA_OFFSET[1],
        "width": BATTLE_REGION["width"],
        "height": BATTLE_REGION["height"],
    }


def _cor_da_barra(img_battle, forte, y):
    """
    Cor do PREENCHIMENTO da barra (o 1º pixel forte do começo dela). Antes lia 2 px depois do
    começo: num monstro com 1–2% de vida esse pixel é a parte VAZIA da barra (cinza-azulado,
    matiz ~105) e ele virava "roxo/não atacável".
    """
    for x in range(BATTLE_BARRA_X, BATTLE_BARRA_X + 5):
        if forte[y, x]:
            return img_battle[y, x]
    return img_battle[y, BATTLE_BARRA_X]


def analisar_battle(img_battle, regiao):
    """
    Lê cada linha da Battle procurando as barras de vida.

    Cada monstro tem uma barra colorida (verde/amarela/vermelha conforme a vida)
    que SEMPRE começa na mesma coluna (BATTLE_BARRA_X). O fundo da Battle é
    transparente, mas é escuro/apagado, então só a barra tem pixels fortes e
    saturados nessa coluna.

    Retorna uma lista (de cima para baixo) com, para cada linha:
      "xy"    : ponto ABSOLUTO na tela para clicar no monstro
      "rosa"  : barra rosa (anti-block, não dá para atacar)
      "alvo"  : está com a moldura vermelha de "atacando"
      "icone" : recorte do ícone do monstro (para reconhecer o especial)
    """
    hsv = cv2.cvtColor(img_battle, cv2.COLOR_BGR2HSV)
    forte = (hsv[..., 1] > 120) & (hsv[..., 2] > 100)
    vermelho = (img_battle[..., 2] > 170) & (img_battle[..., 1] < 80) & (img_battle[..., 0] < 80)

    # Linha é "de barra" se o começo da barra está colorido...
    inicio_barra = forte[:, BATTLE_BARRA_X:BATTLE_BARRA_X + 5].sum(axis=1) >= 3
    # ...e logo antes dela é escuro (a barra começa ali; a borda vermelha de alvo
    # atravessa a linha toda, então não passa nesse teste)
    antes_barra = forte[:, BATTLE_BARRA_X - 5:BATTLE_BARRA_X - 1].sum(axis=1) == 0
    ys = np.nonzero(inicio_barra & antes_barra)[0]

    # grupos de linhas coloridas (cada barra tem 3–8 px de altura)
    grupos = []
    inicio = None
    for i, y in enumerate(ys):
        if inicio is None:
            inicio = y
        if i == len(ys) - 1 or ys[i + 1] != y + 1:
            if 3 <= y - inicio + 1 <= 8:
                grupos.append((int(inicio), int(y - inicio + 1)))
            inicio = None
    # As linhas da Battle ficam a cada BATTLE_ALTURA_LINHA px (grade a partir da 1ª = o seu pet). O NOME
    # VERMELHO do monstro marcado como alvo cruza a coluna da barra e virava 2 "barras" a mais
    # (alarme 19:21: 8 linhas lidas com 6 na Battle → o lure achava que tinha mais monstros).
    # Também aparecia uma "barra" no cabeçalho (y≈2) que virava a 1ª linha. A grade começa na 1ª barra
    # (BATTLE_PRIMEIRA_BARRA_Y, = 107 em todos os prints); recorte diferente (testes): na 1ª barra achada.
    # Grupo VERMELHO fora da grade ~15 px acima de uma linha SEM barra = nome do ALVO com a barra vazia
    # (22:29: Marowak a ~1%): a linha conta (antes ele só era contado por acaso, pelo nome vermelho).
    alvo_pelo_nome = set()
    if grupos:
        L = BATTLE_ALTURA_LINHA
        perto_do_padrao = [g for g in grupos if abs(g[0] - BATTLE_PRIMEIRA_BARRA_Y) <= 4]
        base = BATTLE_PRIMEIRA_BARRA_Y if perto_do_padrao else grupos[0][0]
        por_linha, nome_alvo = {}, set()
        for g in grupos:
            d = g[0] - base
            k = int(round(d / L))
            resto = d - k * L
            if k >= 0 and abs(resto) <= 4:
                if k not in por_linha or abs(resto) < por_linha[k][1]:
                    por_linha[k] = (g, abs(resto))  # 2 grupos na mesma linha: fica o mais alinhado
                continue
            k2 = int(round((d + 15) / L))  # nome fica ~15 px acima da barra da sua linha
            linhas_g = vermelho[g[0]:g[0] + g[1], BATTLE_BARRA_X:BATTLE_BARRA_X + 5]
            if k2 >= 0 and abs(d + 15 - k2 * L) <= 6 and linhas_g.sum() >= 3:
                nome_alvo.add(k2)
        for k in nome_alvo - set(por_linha):
            por_linha[k] = ((base + k * L, 5), 0)  # linha do alvo com a barra vazia
            alvo_pelo_nome.add(base + k * L)
        grupos = [por_linha[k][0] for k in sorted(por_linha)]

    linhas = []
    h = img_battle.shape[0]
    for inicio, altura in grupos:
        topo, fundo = max(0, inicio - 24), min(h, inicio + 7)  # a linha inteira da Battle
        linhas.append({
            "xy": (regiao["left"] + BATTLE_CLIQUE_X, regiao["top"] + inicio + BATTLE_CLIQUE_OFFSET_Y),
            "rosa": bool(eh_rosa(_cor_da_barra(img_battle, forte, inicio + altura // 2))),
            # moldura de alvo: vermelho na beirada esquerda da linha (barra e ícone não chegam lá);
            # linha achada só pelo nome vermelho também é o alvo
            "alvo": inicio in alvo_pelo_nome or bool(vermelho[topo:fundo, 0:12].sum() >= 8),
            "icone": img_battle[max(0, inicio - 22):inicio + 3, 14:BATTLE_BARRA_X - 6].copy(),
            # nome escrito em cima da barra (para o Target reconhecer quem é)
            "nome_img": img_battle[max(0, inicio - 16):max(0, inicio - 1), BATTLE_BARRA_X - 2:BATTLE_BARRA_X + 110].copy(),
        })
    return linhas


def encontrar_monstros(img_battle, regiao, ignorar_rosa=IGNORAR_ROSA):
    """Pontos (x, y) para clicar em cada monstro da Battle, de cima para baixo."""
    return [l["xy"] for l in analisar_battle(img_battle, regiao) if not (ignorar_rosa and l["rosa"])]


_avisou_battle = False


def ler_inimigos(sct, ignorar_primeiro=MONSTRINHO_NA_BATTLE, ignorar_rosa=IGNORAR_ROSA):
    """
    Linhas da Battle que são inimigos (dicts de analisar_battle).
    Se o seu monstrinho aparece sempre em 1º, a primeira linha é descartada.
    Monstros rosa (anti-block) são filtrados.
    """
    global _avisou_battle
    regiao = regiao_battle(sct)
    if regiao is None:
        if not _avisou_battle:
            print("⚠️  Não achei a janela da Battle na tela (está coberta ou fechada?).")
            _avisou_battle = True
        return []
    _avisou_battle = False
    linhas = analisar_battle(capturar(sct, regiao), regiao)
    if ignorar_primeiro:
        linhas = linhas[1:]
    return [l for l in linhas if not (ignorar_rosa and l["rosa"])]


def ler_monstros(sct, ignorar_primeiro=MONSTRINHO_NA_BATTLE):
    """Pontos de clique dos inimigos na Battle (sem o seu monstrinho e sem os rosa)."""
    return [l["xy"] for l in ler_inimigos(sct, ignorar_primeiro)]


def linhas_que_cabem(altura_battle):
    """Quantas linhas (com a barra inteira) cabem numa Battle dessa altura."""
    livre = altura_battle - (BATTLE_PRIMEIRA_BARRA_Y + 5)
    return max(0, livre // BATTLE_ALTURA_LINHA + 1)


# ---------- Criaturas na tela do jogo ----------

BARRA_LARGURA = 27  # caixa preta da barra de vida em cima de cada criatura (27 x 4 px)


def encontrar_barras_criaturas(img, origem=(0, 0)):
    """
    Acha as barrinhas de vida em cima das criaturas na tela do jogo.

    Cada barra é uma caixa PRETA de 27x4 px com o preenchimento colorido
    (2 px de altura) começando na esquerda. Detectar pela caixa preta funciona
    com qualquer cor (verde, amarela, vermelha, rosa...).
    Retorna [(x, y, preenchimento_px, rosa)] com o canto da caixa em coordenada de tela.
    """
    L = BARRA_LARGURA
    preto = img.max(axis=2) < 40
    soma = cv2.filter2D(preto.astype(np.float32), -1, np.ones((1, L), np.float32),
                        anchor=(0, 0), borderType=cv2.BORDER_CONSTANT)
    linha_preta = soma >= L - 0.5  # L pixels pretos seguidos a partir de (x, y)

    h, w = preto.shape
    barras = []
    # Filtros feitos na imagem inteira de uma vez (rápido), para o loop abaixo
    # só olhar os poucos lugares que já parecem uma caixinha de barra.
    Y, X = slice(1, h - 4), slice(1, w - L - 1)

    def em(dy, dx):  # preto deslocado: em(dy, dx)[y, x] == preto[y + dy, x + dx]
        return preto[1 + dy:h - 4 + dy, 1 + dx:w - L - 1 + dx]

    # borda de cima: o NOME do monstro às vezes cobre o canto dela (ex.: "Magnemite"), então
    # aceita até 6 px não pretos ali; a borda de baixo tem que estar inteira
    topo_quase = soma >= L - 6
    candidatos = (topo_quase[Y, X] & linha_preta[4:h - 1, X]           # borda de cima e de baixo
                  # caixa com exatamente 27 px: basta em cima OU embaixo (o corpo escuro do monstro
                  # encosta na barra e "emenda" o preto de um dos lados; barra da Battle é bem maior)
                  & ((~em(0, -1) & ~em(0, L)) | (~em(3, -1) & ~em(3, L)))
                  & em(1, 0) & em(2, 0) & em(1, L - 1) & em(2, L - 1)  # bordas dos lados
                  & ~em(1, 1))                                         # tem cor logo no começo
    ys, xs = np.nonzero(candidatos)
    for y, x in zip(ys + 1, xs + 1):
        preench = []
        for yy in (y + 1, y + 2):
            colorido = ~preto[yy, x + 1:x + L - 1]
            if not colorido[:3].any():                       # a cor começa na esquerda
                break
            k = int(np.nonzero(colorido)[0][-1]) + 1         # até onde vai a cor
            if (~colorido[:k]).sum() > 3:                    # letra do nome pode cobrir até 3 px
                break
            preench.append(k)
        if len(preench) == 2 and abs(preench[0] - preench[1]) <= 2:
            rosa = eh_rosa(img[y + 1, x + 1])
            barras.append((int(x) + origem[0], int(y) + origem[1], preench[0], rosa))
    barras += _barras_vazias(preto, soma, linha_preta, origem, barras)
    return barras


BARRA_VAZIA_TOPO = 40  # barra VAZIA nos 40 px de cima da imagem = ícone da barra de ícones (prints 08/11)


def _barras_vazias(preto, soma, linha_preta, origem, achadas):
    """
    Barra VAZIA (monstro com 0–3% de vida): quase não tem cor dentro e o NOME do monstro (vermelho,
    desenhado mais baixo) cobre a borda de cima INTEIRA. Antes ela não era vista: o monstro sumia
    para o bot (21:05: Marowak shiny vivo colado no personagem virou "fugiu" e "corpo" para a ball).
    Procura pela borda de BAIXO (27 px pretos exatos) + as 2 linhas de dentro pretas (até 3 px de cor
    no começo = 1–3% de vida), com as laterais pretas e largura exata em pelo menos uma linha de dentro.
    Devolve no mesmo formato, com o canto de cima (b - 3) e preenchimento 0–3.
    """
    L = BARRA_LARGURA
    h, w = preto.shape
    # 1º filtro (barato): linha preta de 27 com as pontas NÃO pretas (largura exata)
    sub = linha_preta[3:h - 1, 1:w - L - 1] & ~preto[3:h - 1, 0:w - L - 2] & ~preto[3:h - 1, 1 + L:w - 1]
    bs, xs = np.nonzero(sub)
    bs, xs = bs + 3, xs + 1  # b = linha da borda de baixo
    if not len(bs):
        return []
    # resto só nesses pontos: dentro preto (até 3 px de cor no começo = 1–3% de vida), laterais pretas,
    # largura exata em uma linha de dentro (não é pedaço de área preta maior) e nada preto embaixo
    quase = soma >= L - 3.5
    ok = (quase[bs - 1, xs] & quase[bs - 2, xs]
          & preto[bs - 1, xs] & preto[bs - 2, xs] & preto[bs - 1, xs + L - 1] & preto[bs - 2, xs + L - 1]
          & ((~preto[bs - 1, xs - 1] & ~preto[bs - 1, xs + L]) | (~preto[bs - 2, xs - 1] & ~preto[bs - 2, xs + L]))
          & ~linha_preta[bs + 1, xs])
    novas = []
    for b, x in zip(bs[ok], xs[ok]):
        b, x = int(b), int(x)
        y = b - 3
        if y < BARRA_VAZIA_TOPO:
            continue  # barra de ícones do jogo (por cima do mapa): um ícone virava "barra vazia" fixa em (4,-5)
        if any(abs(ax - origem[0] - x) <= 2 and abs(ay - origem[1] - y) <= 2 for ax, ay, _, _ in achadas):
            continue  # já achada pelo jeito normal (barra com cor e borda de cima visível)
        cor = ~preto[b - 2, x + 1:x + 4]
        novas.append((x + origem[0], y + origem[1], int(cor.sum()), False))
    return novas


def distancias_criaturas(barras, ignorar_rosa=IGNORAR_ROSA):
    """
    Converte as barras em distâncias (sqm) até o personagem, ignorando ele mesmo.
    Distância em sqm = maior entre |dx| e |dy| (igual ao jogo: diagonal conta 1).
    """
    px, py = PLAYER_TILE_XY
    dists = []
    for x, y, _, rosa in barras:
        if ignorar_rosa and rosa:
            continue  # anti-block: não dá para atacar, não entra na conta
        cx, cy = x + BARRA_LARGURA // 2, y + 26   # centro do sqm da criatura
        dx, dy = (cx - px) / SQM_PX, (cy - py) / SQM_PX
        if abs(dx) < 0.3 and abs(dy) < 0.3:
            continue  # é o próprio personagem
        dists.append(max(abs(round(dx)), abs(round(dy))))
    return dists


def criaturas_ao_redor(sct):
    """Distâncias (sqm) de todas as criaturas visíveis até o personagem."""
    img = capturar(sct, GAME_VIEW)
    return distancias_criaturas(encontrar_barras_criaturas(img, (GAME_VIEW["left"], GAME_VIEW["top"])))
