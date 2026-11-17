"""
Shiny automático (sem calibrar nada).

O shiny tem SEMPRE uma cor diferente dos outros da hunt (ex.: Marowak marrom, shiny azul). Então:
  1. a vigia olha a cor de cada criatura na tela (o corpo, embaixo da barrinha de vida);
  2. aprende a cor COMUM dos monstros da hunt (a maioria) e a cor do SEU pet
     (com a Battle vazia, a criatura na tela é o pet);
  3. criatura com cor RARA (poucos % dos monstros vistos), que não é a do pet, vista várias vezes
     no mesmo lugar por uns segundos = shiny;
  4. cria sozinha um perfil de catch "pelo corpo" com a cor dele (vale perto daqui): no fim da luta
     o catch procura o corpo dessa cor e taca a ball (catch.perfis_pelo_corpo).
Antes de criar o perfil confere se essa cor não existe no cenário (senão gastaria ball no chão).
A vigia só aprende e grava o perfil: não clica nem aperta nada.
"""
import threading
import time

import cv2
import numpy as np

BIN = 6                 # largura das faixas de matiz (só para achar a cor principal)
NBINS = 180 // BIN
SEM_COR = -1            # criatura sem cor forte (marrom como o chão, branco, cinza)
MESMA_COR = 3           # matizes a até isso = mesma cor (shiny Marowak 96 x Gyarados 102)
VERMELHO = (4, 172)     # matiz <= 4 ou >= 172: sangue/efeito no chão — não vira shiny
TEXTO_UI = (20, 80)     # amarelo→verde: nomes, barras de vida, estrelinhas, mato — o bot criou 2x um "shiny
                        # verde" com restos do nome. Essa faixa NUNCA vira shiny automático (faça na mão)
MIN_COR_PX = 80         # pixels coloridos para a criatura "ter cor"
MIN_AMOSTRAS = 40       # criaturas vistas antes de decidir o que é raro
RARO = 0.10             # cor de até 10% dos monstros vistos = rara
CONFIRMA_VEZES = 4      # vezes que a cor rara precisa ser vista...
CONFIRMA_SEGUNDOS = 2.0  # ...espalhadas por pelo menos isso (efeito de magia passa rápido; shiny fica)
JANELA_S = 8.0
PET_MIN = 3             # vezes que viu o pet sozinho antes de confiar na cor dele


def pixels_coloridos(hsv):
    """Pixels de cor forte que não são chão (marrom/terra), pedra/branco, nem texto/barra (cor pura)."""
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    chao = (h >= 5) & (h <= 30)
    texto = (s >= 235) & (v >= 150) & (((h <= 5) | (h >= 175)) | ((h >= 25) & (h <= 35)) | ((h >= 55) & (h <= 65)))
    return (s > 60) & (v > 50) & ~chao & ~texto


def recorte_da_criatura(img, bx, by):
    """O corpo fica embaixo da barrinha (canto da caixa preta em bx, by na imagem)."""
    x0, x1 = max(0, bx - 18), min(img.shape[1], bx + 45)
    y0, y1 = max(0, by + 3), min(img.shape[0], by + 50)
    return img[y0:y1, x0:x1]


def assinatura(crop_bgr):
    """(matiz mediana da cor principal ou SEM_COR, pixels coloridos dela em HSV)."""
    if crop_bgr.size == 0:
        return SEM_COR, None
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    px = hsv[pixels_coloridos(hsv)]
    if len(px) < MIN_COR_PX:
        return SEM_COR, None
    hist = np.bincount(px[:, 0] // BIN, minlength=NBINS)[:NBINS]
    faixa = int(hist.argmax())
    perto = px[np.abs(px[:, 0].astype(int) // BIN - faixa) <= 1]
    if len(perto) < MIN_COR_PX:
        return SEM_COR, None
    return int(np.median(perto[:, 0])), perto


def _mesma(a, b):
    return a != SEM_COR and b != SEM_COR and abs(a - b) <= MESMA_COR


class AprendizShiny:
    """A parte que pensa (sem tela nem thread: dá para testar com prints)."""

    def __init__(self):
        self.contagem = {}      # matiz -> quantas vezes um monstro com essa cor foi visto
        self.total = 0
        self.pet = {}           # matiz -> vezes vista sozinha na tela (Battle vazia)
        self.vistos = []        # [(tempo, sqm_abs, matiz, pixels)] de cores raras
        self.aprendidas = []    # matizes que já viraram perfil nesta sessão

    def faixas_do_pet(self):
        """Matizes do pet (vistas PET_MIN+ vezes com a Battle vazia, somando as parecidas)."""
        return {f for f in self.pet if sum(n for g, n in self.pet.items() if _mesma(f, g)) >= PET_MIN}

    def eh_pet(self, faixa):
        return any(_mesma(faixa, p) for p in self.faixas_do_pet())

    def frequencia(self, faixa):
        if not self.total:
            return 1.0
        return sum(n for f, n in self.contagem.items() if _mesma(f, faixa)) / self.total

    def observar(self, criaturas, qtd_battle, pos, agora):
        """
        criaturas: [(sqm_rel, faixa, pixels)] da tela agora. qtd_battle: inimigos na Battle.
        Retorna (faixa, [pixels...], sqm_abs) quando confirma um shiny novo, ou None.
        """
        if qtd_battle == 0:  # só o pet (e talvez outros jogadores) na tela: aprende a cor dele
            for _, faixa, _ in criaturas:
                if faixa != SEM_COR:
                    self.pet[faixa] = self.pet.get(faixa, 0) + 1
            return None
        monstros = [c for c in criaturas if c[1] == SEM_COR or not self.eh_pet(c[1])]
        for _, faixa, _ in monstros:
            self.contagem[faixa] = self.contagem.get(faixa, 0) + 1
            self.total += 1
        if self.total < MIN_AMOSTRAS or not self.faixas_do_pet():
            return None  # ainda não sabe o que é comum (nem qual é o pet)
        self.vistos = [v for v in self.vistos if agora - v[0] <= JANELA_S]
        for sqm, faixa, pixels in monstros:
            if (faixa == SEM_COR or faixa <= VERMELHO[0] or faixa >= VERMELHO[1]
                    or TEXTO_UI[0] <= faixa <= TEXTO_UI[1]
                    or any(_mesma(faixa, a) for a in self.aprendidas) or self.frequencia(faixa) > RARO):
                continue
            onde = (pos[0] + sqm[0], pos[1] + sqm[1], pos[2]) if pos else sqm
            self.vistos.append((agora, onde, faixa, pixels))
            iguais = [v for v in self.vistos if _mesma(v[2], faixa)
                      and max(abs(v[1][0] - onde[0]), abs(v[1][1] - onde[1])) <= 3]
            if len(iguais) >= CONFIRMA_VEZES and agora - iguais[0][0] >= CONFIRMA_SEGUNDOS:
                self.aprendidas.append(faixa)
                return faixa, [v[3] for v in iguais], onde
        return None


def perfil_da_cor(faixa, lista_pixels, local, pet_faixas):
    """Perfil de catch "pelo corpo" com a cor vista (faixa justa; tira a cor do pet). None se não der."""
    px = np.concatenate(lista_pixels)
    h = px[:, 0].astype(int)
    lo, hi = int(np.percentile(h, 10)) - 1, int(np.percentile(h, 90)) + 1
    for p in pet_faixas:  # nunca inclui a cor do pet (o Gyarados é azul também; pixels se misturam)
        p0, p1 = p - MESMA_COR, p + MESMA_COR
        if p0 <= hi and p1 >= lo:
            if p > faixa:   # pet do lado de cima da cor do shiny: corta em cima
                hi = min(hi, p0 - 1)
            else:
                lo = max(lo, p1 + 1)
    if hi - lo < 2:
        return None
    if TEXTO_UI[0] <= faixa <= TEXTO_UI[1] or not (VERMELHO[0] < faixa < VERMELHO[1]):
        return None  # cor de texto/interface/sangue: nunca vira perfil automático
    if np.percentile(px[:, 1], 10) >= 220:
        return None  # cor "pura" (saturação no máximo) = texto/interface do jogo, não corpo de monstro
    s_lo = max(60, int(np.percentile(px[:, 1], 10)) - 20)
    v_lo = max(50, int(np.percentile(px[:, 2], 10)) - 15)
    tamanho = int(np.median([len(p) for p in lista_pixels]))
    return {
        "id": f"shiny_auto_{lo}_{hi}", "nome": f"Shiny automático (cor {lo}–{hi})", "tipo": "especial",
        "h": [lo, hi], "s": [s_lo, 255], "v": [v_lo, 250], "pixels": tamanho,
        "local": list(local) if local else None, "amostra": None,
        # corpo inteiro ~ o desenho vivo; metade cobre corpo meio escondido e deixa de fora pedacinhos
        "pelo_corpo": True, "min_corpo": int(np.clip(tamanho // 2, 100, 250)), "automatico": True,
    }


def cor_no_cenario(img_view, perfil, caixas_criaturas, origem=(0, 0)):
    """
    Essa cor aparece no chão/cenário (fora das criaturas)? Aí o perfil gastaria ball à toa.
    Conta também muitos pedacinhos espalhados (mato verde): somados passam do tamanho de um corpo.
    """
    import catch
    hsv = cv2.cvtColor(img_view, cv2.COLOR_BGR2HSV)
    m = catch.mascara_perfil(hsv, perfil).astype(np.uint8)
    for bx, by in caixas_criaturas:  # apaga as criaturas (e o recorte em volta)
        x, y = bx - origem[0], by - origem[1]
        m[max(0, y - 20):y + 60, max(0, x - 30):x + 60] = 0
    m[:catch.ESTRELA_TOPO] = 0
    m[m.shape[0] - catch.ESTRELA_BAIXO:] = 0
    n, rot, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((5, 5), np.uint8)))
    return any(m[rot == i].sum() >= perfil["min_corpo"] for i in range(1, n)) or m.sum() >= perfil["min_corpo"]


def ler_criaturas(img_view, origem, player_xy, sqm_px):
    """[(sqm_rel, faixa, pixels)] e as caixas (bx, by) das barrinhas, de um print do mapa."""
    from tela import encontrar_barras_criaturas, BARRA_LARGURA
    import catch
    saida, caixas = [], []
    barras = encontrar_barras_criaturas(img_view, origem)
    # nomes e barrinhas de TODAS as criaturas apagados (pintados de cinza): o nome verde de um monstro
    # caía no recorte de outro e virava "shiny verde"
    limpa = img_view.copy()
    hsv = cv2.cvtColor(img_view, cv2.COLOR_BGR2HSV)
    limpa[catch.area_dos_nomes(limpa.shape, barras, origem) & catch.pixels_de_texto(hsv)] = (128, 128, 128)
    for bx, by, _, _ in barras:
        caixas.append((bx, by))
        faixa, px = assinatura(recorte_da_criatura(limpa, bx - origem[0], by - origem[1]))
        cx, cy = bx + BARRA_LARGURA // 2, by + 26
        sqm = (round((cx - player_xy[0]) / sqm_px), round((cy - player_xy[1]) / sqm_px))
        if sqm != (0, 0):  # o personagem não conta
            saida.append((sqm, faixa, px))
    return saida, caixas


class VigiaShiny(threading.Thread):
    """Thread: a cada ~0,5 s olha as criaturas e, achando um shiny novo, grava o perfil pelo corpo."""

    def __init__(self, pos_atual):
        super().__init__(daemon=True)
        self.pos_atual = pos_atual
        self.aprendiz = AprendizShiny()

    def ligado(self):
        import config
        return bool(config.CATCH_ATIVO and getattr(config, "CATCH_CORPO", True)
                    and getattr(config, "CATCH_SHINY_AUTO", True))

    def run(self):
        import mss
        import config
        import controle
        from tela import capturar, ler_inimigos
        with mss.MSS() as sct:
            while not controle.deve_parar():
                time.sleep(0.5)
                if controle.esta_pausado() or not self.ligado():
                    continue
                try:
                    self.uma_volta(sct, capturar, ler_inimigos, config)
                except Exception as e:  # erro numa leitura não derruba a vigia
                    print(f"[Shiny] Erro lendo a tela (sigo vigiando): {e!r}")
                    time.sleep(2)

    def uma_volta(self, sct, capturar, ler_inimigos, config):
        import catch
        img = capturar(sct, config.GAME_VIEW)
        origem = (config.GAME_VIEW["left"], config.GAME_VIEW["top"])
        criaturas, caixas = ler_criaturas(img, origem, catch.PLAYER_TILE_XY, catch.SQM_PX)
        pos = self.pos_atual()
        achou = self.aprendiz.observar(criaturas, len(ler_inimigos(sct)), pos, time.time())
        if not achou:
            return
        faixa, pixels, onde = achou
        freq = self.aprendiz.frequencia(faixa) * 100
        perfil = perfil_da_cor(faixa, pixels, pos, self.aprendiz.faixas_do_pet())
        if perfil is None:
            print(f"[Shiny] Cor rara (matiz ~{faixa}) mas igual à do pet: ignorando.")
            return
        if any(p.get("pelo_corpo") and p["h"][0] <= perfil["h"][1] and p["h"][1] >= perfil["h"][0]
               for p in catch.perfis_pelo_corpo(pos)):
            return  # já tem perfil pelo corpo dessa cor aqui
        if cor_no_cenario(img, perfil, caixas, origem):
            print(f"[Shiny] Cor rara (matiz {perfil['h'][0]}–{perfil['h'][1]}) mas ela também aparece no "
                  "cenário: não crio perfil (gastaria ball no chão).")
            return
        perfis = list(catch.carregar_perfis()) + [perfil]
        catch.salvar_perfis(perfis)
        print(f"[Shiny] ✨ Criatura de cor rara em {onde[0]}, {onde[1]} (matiz {perfil['h'][0]}–{perfil['h'][1]}, "
              f"{freq:.0f}% dos monstros desta hunt): é shiny! Perfil '{perfil['nome']}' criado — "
              "ball no corpo quando morrer.")
