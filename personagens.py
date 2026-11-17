"""
Rodízio de PERSONAGENS (bonecos da mesma conta): caça N voltas da rota com um, desloga (Ctrl+Q),
entra no próximo pela tela de seleção (carrossel + botão "Login") e caça com ele; depois volta ao 1º.

Partes (cada uma testável com print real, sem clicar):
  - em_battle / battle_no_circulo: o CÍRCULO atrás do pokémon (janela "Pokémon") fica VERMELHO com
    battle (não dá para deslogar) e CINZA sem battle (prints do usuário 08/11 23:30, Steelix).
  - tela de seleção: botão azul "Login" (achado pela cor, vale em qualquer tamanho de janela),
    nome GRANDE do personagem escolhido (OCR) e os cards do carrossel (posição relativa ao botão).
  - ContadorVoltas: volta completa = a rota "deu a volta" E o personagem chegou em pelo menos metade
    dos pontos (depois de luta o bot pula para o ponto mais perto e o passo 0 podia ser pulado).
  - Rodizio: quem é o personagem da vez, quando trocar, e a troca em si.

A senha NUNCA é usada: a troca é dentro da mesma conta (a tela de seleção já está logada).
O botão vermelho "Logout" da tela de seleção sai da CONTA: o bot NUNCA clica nele.
Qualquer surpresa → devolve o erro; o bot toca o alarme e pausa (nada de clicar às cegas).
"""
import difflib
import re
import time

import cv2
import numpy as np

import config
import controle
import humano

# ---------- Battle (círculo atrás do pokémon) ----------
# centro do círculo a partir do canto do título "Pokémon" (âncora); conferido em 3 prints: (30, 61)
CIRCULO_DX, CIRCULO_DY = 30, 61
CIRCULO_R0, CIRCULO_R1 = 28, 33   # anel medido: a borda do círculo (o desenho do pokémon fica no meio)
VERMELHO_MIN = 0.15               # battle: ≥15% do anel vermelho escuro (medido 0,23 e 0,41; sem battle 0,00)
CINZA_MIN = 0.25                  # sem battle: ≥25% cinza (medido 0,58; com battle 0,00–0,01)


def battle_no_circulo(img, ancora):
    """
    True = battle (vermelho), False = sem battle (cinza), None = não deu para ler.
    `img` é a imagem onde está a janela Pokémon; `ancora` = (x, y) do título nela.
    """
    if ancora is None:
        return None
    cx, cy = int(ancora[0] + CIRCULO_DX), int(ancora[1] + CIRCULO_DY)
    r = CIRCULO_R1
    if cy - r < 0 or cx - r < 0 or cy + r + 1 > img.shape[0] or cx + r + 1 > img.shape[1]:
        return None
    reg = img[cy - r:cy + r + 1, cx - r:cx + r + 1]
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    d = np.hypot(xx, yy)
    px = reg[(d >= CIRCULO_R0) & (d < CIRCULO_R1)]
    hsv = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    vermelho = ((hsv[:, 0] <= 8) | (hsv[:, 0] >= 170)) & (hsv[:, 1] >= 100) & (hsv[:, 2] >= 35)
    cinza = (hsv[:, 1] <= 60) & (hsv[:, 2] >= 30) & (hsv[:, 2] <= 110)
    if vermelho.mean() >= VERMELHO_MIN:
        return True
    if cinza.mean() >= CINZA_MIN:
        return False
    return None


def em_battle(sct):
    """Lê a battle na tela agora (True/False/None)."""
    from tela import capturar, localizar_ancora
    anc = localizar_ancora(sct, "pokemon", usar_cache=False)
    if anc is None:
        return None
    m = CIRCULO_R1 + 2
    regiao = {"left": int(anc[0]), "top": int(anc[1]),
              "width": CIRCULO_DX + m + 1, "height": CIRCULO_DY + m + 1}
    return battle_no_circulo(capturar(sct, regiao), (0, 0))


# ---------- Tela de seleção de personagens ----------
# Medidas tiradas do print do usuário (08/11 23:10, janela reduzida: botão Login com 193 px de largura).
# Tudo é proporcional à largura do botão, então vale para qualquer tamanho de janela.
BOTAO_REF_W = 193.0
NOME_CAIXA = (-25, -150, 205, -116)   # nome grande: (x0, y0, x1, y1) a partir do canto de cima do botão
CARD_DX0 = -263.0                     # 1º card do carrossel: x do centro a partir do MEIO do botão
CARD_PASSO = 74.5                     # distância de um card para o outro
CARD_DY = 129.0                       # y do centro dos cards a partir do canto de cima do botão
CARD_NOME_Y = (-34.0, -24.0)          # faixa do nome pequeno no alto do card (a partir do centro)
CARD_NOME_W = 22.0                    # meia largura da faixa do nome
CARD_NOME_MIN = 0.08                  # branco do nome: medido 0,16–0,22 nos 3 cards; "Create Character" 0,00
CARDS_MAX = 6                         # cards visíveis antes da seta ▶


def achar_botao_login(img):
    """(x, y, w, h) do botão azul "Login" (o maior retângulo azul largo e baixo no meio) ou None."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (95, 170, 120), (108, 255, 230))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    H, W = img.shape[:2]
    melhor = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if w < 0.10 * W or h < 12 or not (4.0 <= w / max(h, 1) <= 10.0):
            continue
        if area < 0.6 * w * h:  # retângulo cheio
            continue
        if abs((x + w / 2) - W / 2) > 0.15 * W:  # fica no meio da janela
            continue
        if melhor is None or w * h > melhor[2] * melhor[3]:
            melhor = (int(x), int(y), int(w), int(h))
    return melhor


def tem_logout_vermelho(img):
    """Botão vermelho "Logout" no canto de cima à direita (só existe na tela de seleção)."""
    H, W = img.shape[:2]
    canto = img[:max(1, int(0.12 * H)), int(0.70 * W):]
    hsv = cv2.cvtColor(canto, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (170, 80, 110), (180, 255, 255)) | cv2.inRange(hsv, (0, 80, 110), (5, 255, 255))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    return any(stats[i][2] >= 0.02 * W and 1.5 <= stats[i][2] / max(stats[i][3], 1) <= 5
               for i in range(1, n))


def eh_tela_de_selecao(img):
    return achar_botao_login(img) is not None and tem_logout_vermelho(img)


def _escala(botao):
    return botao[2] / BOTAO_REF_W


def regiao_nome(img, botao):
    s = _escala(botao)
    x0, y0, x1, y1 = NOME_CAIXA
    bx, by = botao[0], botao[1]
    H, W = img.shape[:2]
    a = (max(0, int(bx + x0 * s)), max(0, int(by + y0 * s)))
    b = (min(W, int(bx + x1 * s)), min(H, int(by + y1 * s)))
    return img[a[1]:b[1], a[0]:b[0]]


def ler_nome_grande(img, botao):
    """Nome do personagem escolhido (letra grande branca do card do meio), por OCR."""
    faixa = regiao_nome(img, botao)
    if faixa.size == 0:
        return ""
    hsv = cv2.cvtColor(faixa, cv2.COLOR_BGR2HSV)
    branco = cv2.inRange(hsv, (0, 0, 170), (180, 70, 255))
    fator = max(1.0, 60.0 / max(1, faixa.shape[0]))
    grande = cv2.resize(255 - branco, None, fx=fator, fy=fator, interpolation=cv2.INTER_CUBIC)
    grande = cv2.copyMakeBorder(grande, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        texto = pytesseract.image_to_string(grande, lang="eng", config="--psm 7")
    except Exception as e:
        print(f"[Rodízio] OCR indisponível: {e!r}")
        return ""
    return re.sub(r"[^A-Za-z0-9 ]", "", texto).strip()


def normalizar(nome):
    return re.sub(r"[^a-z0-9]", "", str(nome).lower())


def mesmo_nome(lido, esperado, minimo=0.8):
    """OCR pode trocar uma letra: aceita parecido (≥ 80%)."""
    a, b = normalizar(lido), normalizar(esperado)
    if not a or not b:
        return False
    if a.startswith(b) and len(a) - len(b) <= 2:  # sujeira no fim (ícone ao lado do nome: "heroi Alfa 7")
        return True
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= minimo


def cards(img, botao):
    """
    Centros (x, y) dos cards de PERSONAGEM no carrossel, da esquerda para a direita.
    Para no 1º card sem nome em cima ("+ Create Character" ou vazio): nunca clica nele.
    """
    s = _escala(botao)
    meio = botao[0] + botao[2] / 2
    cy = botao[1] + CARD_DY * s
    H, W = img.shape[:2]
    achados = []
    for k in range(CARDS_MAX):
        cx = meio + (CARD_DX0 + k * CARD_PASSO) * s
        # faixa do NOME pequeno no alto do card (texto branco); o card "Create Character" não tem
        x0, x1 = int(cx - CARD_NOME_W * s), int(cx + CARD_NOME_W * s)
        y0, y1 = int(cy + CARD_NOME_Y[0] * s), int(cy + CARD_NOME_Y[1] * s)
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            break
        hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        branco = ((hsv[..., 1] <= 60) & (hsv[..., 2] >= 170)).mean()
        if branco < CARD_NOME_MIN:
            break
        achados.append((int(cx), int(cy)))
    return achados


# ---------- Volta da rota ----------

class ContadorVoltas:
    """
    Conta voltas completas da rota. `passo` é a posição na ordem da rota (0..n-1).
    Volta = o passo pulou do último quarto da ordem para o primeiro quarto depois de chegar em pelo
    menos metade dos pontos da rota.
    """

    def __init__(self, tamanho_ordem, total_pontos):
        self.n = max(1, tamanho_ordem)
        self.total = max(1, total_pontos)
        self.voltas = 0
        self.chegou = set()
        self.ultimo = None

    def chegou_em(self, indice):
        self.chegou.add(indice)

    def passo(self, passo):
        """Chame a cada passo do laço da rota. Devolve True se fechou uma volta agora."""
        antes, self.ultimo = self.ultimo, passo
        q = self.n // 4
        if antes is None or passo >= antes or passo > q or antes < self.n - 1 - q:
            return False  # só conta o pulo do FIM da ordem para o COMEÇO dela
        if len(self.chegou) * 2 < self.total:
            return False  # pulou para o começo sem ter andado a rota (ex.: luta levou para perto do 1)
        self.voltas += 1
        self.chegou.clear()
        return True

    def zerar(self):
        self.voltas = 0
        self.chegou.clear()
        self.ultimo = None


# ---------- Rodízio ----------

class ErroTroca(Exception):
    """A troca deu errado (tela inesperada, personagem não encontrado...): alarme + pausa."""


def lista():
    """Personagens do rodízio, já limpos: [{"nome", "hunt", "voltas", "ponto"}]."""
    saida = []
    for p in getattr(config, "RODIZIO_PERSONAGENS", None) or []:
        nome = str(p.get("nome", "")).strip()
        if not nome:
            continue
        saida.append({"nome": nome, "hunt": str(p.get("hunt", "")).strip(),
                      "voltas": max(1, int(p.get("voltas", 1) or 1)),
                      "ponto": max(0, int(p.get("ponto", 1) or 0))})
    return saida


class Rodizio:
    """
    Quem é o personagem da vez e quando trocar. O personagem do começo é o que tem o nome de
    MEU_NOME (o bot começa no personagem que está logado); sem achar, o 1º da lista.
    """

    def __init__(self):
        self.personagens = lista()
        self.atual = 0
        meu = getattr(config, "MEU_NOME", "")
        for i, p in enumerate(self.personagens):
            if mesmo_nome(meu, p["nome"], 0.9):
                self.atual = i
                break
        self.quer_sair = False

    def ativo(self):
        return bool(getattr(config, "RODIZIO_ATIVO", False)) and len(self.personagens) >= 2

    def da_vez(self):
        return self.personagens[self.atual] if self.personagens else None

    def proximo(self):
        return self.personagens[(self.atual + 1) % len(self.personagens)]

    def fechou_volta(self, voltas):
        """Chamado quando completa uma volta. Devolve True se é hora de ir sair."""
        p = self.da_vez()
        if not self.ativo() or p is None:
            return False
        print(f"[Rodízio] {p['nome']}: {voltas}/{p['voltas']} volta(s) da rota.")
        if voltas >= p["voltas"]:
            self.quer_sair = True
            onde = f"no ponto {p['ponto']}" if p["ponto"] else "aqui"
            print(f"[Rodízio] Completou as voltas: vou deslogar {onde} e entrar no {self.proximo()['nome']}.")
        return self.quer_sair

    def pode_sair_aqui(self, numero_ponto):
        """Já quer sair e chegou no ponto de saída (0 = qualquer ponto)."""
        p = self.da_vez()
        return self.quer_sair and p is not None and p["ponto"] in (0, numero_ponto)

    def trocou(self):
        self.atual = (self.atual + 1) % len(self.personagens)
        self.quer_sair = False


# ---------- A troca (deslogar → escolher → Login) ----------

def _imagem_janela(sct):
    import layout
    from tela import capturar
    j = layout.janela_jogo()
    if j is None:
        raise ErroTroca("não acho a janela do jogo (minimizada ou fechada?)")
    regiao = {"left": j["left"], "top": j["top"], "width": j["width"], "height": j["height"]} \
        if isinstance(j, dict) else {"left": j[0], "top": j[1], "width": j[2] - j[0], "height": j[3] - j[1]}
    return capturar(sct, regiao), regiao


def _no_jogo(sct):
    from tela import localizar_ancora
    return (localizar_ancora(sct, "pokemon", usar_cache=False) is not None
            or localizar_ancora(sct, "battle", usar_cache=False) is not None)


def esperar_sem_battle(sct, livre, segundos=None, maximo=None):
    """
    Espera o círculo ficar CINZA (sem battle) e o bot sem inimigos (`livre()`) por `segundos` seguidos.
    Devolve True; passou de `maximo` → False.
    """
    segundos = getattr(config, "RODIZIO_SEM_BATTLE_S", 4.0) if segundos is None else segundos
    maximo = getattr(config, "RODIZIO_BATTLE_MAX_S", 120.0) if maximo is None else maximo
    t0 = time.time()
    limpo_desde = None
    while time.time() - t0 < maximo:
        ok = em_battle(sct) is False and livre()
        if ok:
            limpo_desde = limpo_desde or time.time()
            if time.time() - limpo_desde >= segundos:
                return True
        else:
            limpo_desde = None
        controle.esperar(0.3)
    return False


def deslogar(sct, livre):
    """Ctrl+Q sem battle e confere que chegou na tela de seleção. Erro → ErroTroca."""
    for tentativa in range(2):
        if not esperar_sem_battle(sct, livre):
            raise ErroTroca("a battle (círculo vermelho atrás do pokémon) não sai: não dá para deslogar")
        print("[Rodízio] Sem battle: deslogando (Ctrl+Q)...")
        if not controle.apertar_combo(getattr(config, "RODIZIO_TECLAS_SAIR", ["ctrl", "q"])):
            raise ErroTroca("não consegui apertar Ctrl+Q (jogo sem foco?)")
        t0 = time.time()
        while time.time() - t0 < getattr(config, "RODIZIO_ESPERA_SAIR_S", 15.0):
            controle.esperar(0.5)
            img, _ = _imagem_janela(sct)
            if eh_tela_de_selecao(img):
                return True
        if _no_jogo(sct) and em_battle(sct):
            print("[Rodízio] O jogo não deixou sair (entrou em battle). Espero e tento de novo.")
            continue
        break
    raise ErroTroca("apertei Ctrl+Q mas a tela de seleção de personagens não apareceu")


def escolher_e_entrar(sct, nome):
    """Na tela de seleção: clica no card do `nome` (confere pelo nome grande) e em Login."""
    img, reg = _imagem_janela(sct)
    botao = achar_botao_login(img)
    if botao is None or not tem_logout_vermelho(img):
        raise ErroTroca("não estou na tela de seleção de personagens")
    lido = ler_nome_grande(img, botao)
    if not mesmo_nome(lido, nome):
        achou = False
        for (cx, cy) in cards(img, botao):
            if not controle.clicar(reg["left"] + cx, reg["top"] + cy):
                raise ErroTroca("não consegui clicar no card (bot pausado ou jogo coberto)")
            controle.esperar(humano.variar(0.9))
            img, reg = _imagem_janela(sct)
            botao = achar_botao_login(img)
            if botao is None:
                raise ErroTroca("o botão Login sumiu depois de clicar num card")
            lido = ler_nome_grande(img, botao)
            if mesmo_nome(lido, nome):
                achou = True
                break
        if not achou:
            raise ErroTroca(f"não achei o personagem \"{nome}\" no carrossel (último lido: \"{lido}\")")
    print(f"[Rodízio] Personagem \"{lido}\" escolhido: clicando em Login.")
    x, y, w, h = botao
    if not controle.clicar(reg["left"] + x + w / 2, reg["top"] + y + h / 2, espalhar=(w // 4, h // 4)):
        raise ErroTroca("não consegui clicar em Login")
    t0 = time.time()
    while time.time() - t0 < getattr(config, "RODIZIO_ESPERA_LOGIN_S", 40.0):
        controle.esperar(1.0)
        if _no_jogo(sct):
            controle.esperar(2.0)  # o jogo termina de desenhar as janelas
            return True
    raise ErroTroca("cliquei em Login mas o jogo não apareceu (janelas Battle/Pokémon)")


def trocar(sct, nome, livre):
    """
    Troca para o personagem `nome`. As outras threads ficam quietas durante a troca
    (`controle.trocando`). Devolve None se deu certo ou o texto do erro.
    """
    controle.iniciar_troca()
    try:
        deslogar(sct, livre)
        escolher_e_entrar(sct, nome)
    except ErroTroca as e:
        return str(e)  # a troca continua "aberta" (threads quietas) até `concluir_troca`
    concluir_troca(sct, nome)
    return None


def concluir_troca(sct, nome):
    """Já está no jogo: mede a tela de novo, ajusta o nome e libera as threads."""
    import layout
    try:
        layout.detectar_e_aplicar(sct)
    except Exception as e:
        print(f"[Rodízio] Erro medindo a tela depois de entrar: {e!r}")
    layout._setar("MEU_NOME", nome)
    controle.fim_troca()
