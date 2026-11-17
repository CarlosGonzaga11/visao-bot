"""
Funções compartilhadas entre o painel e o bot para trabalhar com o minimapa.

Ideia: um waypoint é um recorte pequeno do minimapa tirado em volta do personagem.
Para voltar até ele, procuramos esse recorte no minimapa atual (cv2.matchTemplate).
A diferença entre onde o recorte aparece e o centro (personagem) diz para onde andar.

Cuidado com a cruz branca do personagem: ela fica SEMPRE no centro do minimapa.
Se ela entrar na comparação, todo waypoint "parece" estar no centro. Por isso:
  - no recorte gravado, os pixels da cruz são ignorados (máscara em forma de +);
  - no minimapa ao vivo, a cruz é apagada e preenchida com o terreno em volta.
"""
import cv2
import numpy as np

from config import (
    MINIMAP_REGION, PLAYER_SCREEN_X, PLAYER_SCREEN_Y,
    TEMPLATE_SIZE, CRUZ_BRACO, CRUZ_LARGURA,
)

# Posição do personagem DENTRO da imagem do minimapa
PLAYER_MM_X = PLAYER_SCREEN_X - MINIMAP_REGION["left"]
PLAYER_MM_Y = PLAYER_SCREEN_Y - MINIMAP_REGION["top"]


def pixels_da_cruz(altura, largura, cx, cy):
    """
    Máscara (uint8, 255 = cruz) com a cruz do personagem centrada em (cx, cy).
    A cruz tem 12x12 px com contorno: os pixels brancos centrais são (cx, cx+1)
    e (cy, cy+1). CRUZ_BRACO/CRUZ_LARGURA já incluem 1 px de folga.
    """
    mask = np.zeros((altura, largura), dtype=np.uint8)
    b, l = CRUZ_BRACO, CRUZ_LARGURA
    # barra vertical e horizontal (o +1 é porque o centro tem 2 px)
    mask[max(0, cy - b):cy + b + 2, max(0, cx - l):cx + l + 2] = 255
    mask[max(0, cy - l):cy + l + 2, max(0, cx - b):cx + b + 2] = 255
    return mask


_MASCARA_MINIMAPA = pixels_da_cruz(MINIMAP_REGION["height"], MINIMAP_REGION["width"],
                                   PLAYER_MM_X, PLAYER_MM_Y)


def recalcular_centro():
    """Chamado pela configuração automática quando o minimapa muda de lugar."""
    global PLAYER_MM_X, PLAYER_MM_Y, _MASCARA_MINIMAPA
    PLAYER_MM_X = PLAYER_SCREEN_X - MINIMAP_REGION["left"]
    PLAYER_MM_Y = PLAYER_SCREEN_Y - MINIMAP_REGION["top"]
    _MASCARA_MINIMAPA = pixels_da_cruz(MINIMAP_REGION["height"], MINIMAP_REGION["width"],
                                       PLAYER_MM_X, PLAYER_MM_Y)


def capturar_minimapa(sct, apagar_cruz=True):
    """Retorna o minimapa atual como imagem BGR (numpy), sem a cruz do personagem."""
    img = cv2.cvtColor(np.array(sct.grab(MINIMAP_REGION)), cv2.COLOR_BGRA2BGR)
    if apagar_cruz:
        img = cv2.inpaint(img, _MASCARA_MINIMAPA, 3, cv2.INPAINT_TELEA)
    return img


def recortar_waypoint(minimapa):
    """Recorta o quadrado TEMPLATE_SIZE x TEMPLATE_SIZE centrado no personagem."""
    meio = TEMPLATE_SIZE // 2
    y0, x0 = PLAYER_MM_Y - meio, PLAYER_MM_X - meio
    return minimapa[y0:y0 + TEMPLATE_SIZE, x0:x0 + TEMPLATE_SIZE].copy()


_mascaras = {}


def _mascara_template(tamanho):
    """Máscara do recorte: tudo vale, menos a cruz no centro (255 = usar o pixel)."""
    if tamanho not in _mascaras:
        meio = tamanho // 2
        _mascaras[tamanho] = cv2.bitwise_not(pixels_da_cruz(tamanho, tamanho, meio, meio))
    return _mascaras[tamanho]


def localizar_waypoint(minimapa, template):
    """
    Procura o template no minimapa (já sem a cruz).
    Retorna (dx, dy, confianca): deslocamento em px do personagem até o waypoint.
    dx > 0 = waypoint à direita, dy > 0 = waypoint abaixo.
    """
    tamanho = template.shape[0]  # aceita rotas gravadas com tamanhos diferentes
    res = cv2.matchTemplate(minimapa, template, cv2.TM_CCOEFF_NORMED,
                            mask=_mascara_template(tamanho))
    res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, conf, _, (x, y) = cv2.minMaxLoc(res)

    centro_x = x + tamanho // 2
    centro_y = y + tamanho // 2
    return centro_x - PLAYER_MM_X, centro_y - PLAYER_MM_Y, conf


def deslocamento_para_tela(dx, dy):
    """Converte o deslocamento no minimapa em coordenada absoluta de clique na tela."""
    return PLAYER_SCREEN_X + dx, PLAYER_SCREEN_Y + dy
