"""
CaveBot com lure: anda pela rota juntando monstros e só para para lutar
quando a Battle tiver pelo menos LURE_MINIMO monstros (ou se o HP ficar perigoso).
"""
import math
import random
import threading
import time
import json
import numpy as np
import cv2
import os
import config
import target

import mss
import mss.exception

import controle
import humano
import efeitos
import layout
import modos
import rota
from config import (
    MATCH_THRESHOLD, CHEGADA_TOLERANCIA, RECLIQUE_INTERVALO, TIMEOUT_WAYPOINT,
    TECLA_ATAQUE, INTERVALO_ATAQUE, TIMEOUT_COMBATE, TECLA_PARAR,
    LURE_ATIVO, LURE_MINIMO, LURE_SEGURANCA_ATIVA, LURE_HP_SEGURANCA,
    LURE_POKE_HP_SEGURANCA, LURE_PRESO_S,
    LURE_ESPERA_PONTO, LURE_MAX_VOLTAS, BATTLE_REGION, MONSTRINHO_NA_BATTLE,
    MAGIA_AGRUPAR_ATIVA, MAGIA_RAIO_SQM, MAGIA_ESPERA_MAX,
    CURA_POKE_ATIVA, DESCANSAR_ATE, DESCANSO_MAX, ROTA_IDA_E_VOLTA,
    HUMANO_ATIVO, HUMANO_PARADAS, COMBATE_SEM_ROTA, PARADO_PARA_ATACAR_S,
    POKESTOP_ATIVO, TECLA_POKESTOP, ORDER_DEPOIS_LUTA, ORDER_ANDANDO, ORDER_INTERVALO,
    SQM_PX, PLAYER_TILE_XY, NAV_VIEW_DX, NAV_VIEW_DY, NAV_TRAVADO_S, NAV_PRESO_S, NAV_CHEGADA_SQM,
)
import caixa_preta
import controle_box
import players
import catch
import chat
import shiny
import personagens
from catch import fazer_catch, RastreadorEspecial
from chat import MonitorChat
from navegacao import MemoriaMapa, proximo_destino, primeiro_passo, distancia
from posicao import Posicao
from cura import MonitorCura, MonitorRevive
from seguranca import MonitorSeguranca
from minimapa import capturar_minimapa, localizar_waypoint, deslocamento_para_tela
from tela import (
    carregar_calibracao, ler_monstros, ler_inimigos, ler_barra, linhas_que_cabem, criaturas_ao_redor,
    encontrar_barras_criaturas, capturar, BARRA_LARGURA, GAME_VIEW, regiao_battle,
)

_avisou_battle = [None]


def minimo_para_lutar():
    """
    Quantos monstros juntar antes de lutar. Lido do config A CADA chamada: mudar o tamanho do
    lure no painel com o bot rodando vale na hora (antes era calculado 1 vez ao abrir o bot e o
    "Mudanças aplicadas" do log não valia para o lure).
    Com o lure desligado, luta assim que aparecer 1 monstro. Nunca pede mais do que cabe na Battle.
    """
    minimo = int(config.LURE_MINIMO) if config.LURE_ATIVO else 1
    cabem = linhas_que_cabem(config.BATTLE_REGION["height"]) - (1 if config.MONSTRINHO_NA_BATTLE else 0)
    if minimo > cabem:
        if _avisou_battle[0] != (minimo, cabem):
            _avisou_battle[0] = (minimo, cabem)
            print(f"⚠️  Só cabem {cabem} monstros na Battle, mas o lure pede {minimo}. "
                  f"Usando {cabem}. Aumente a Battle e ajuste o tamanho na aba Calibração.")
        minimo = cabem
    return minimo

# Resultados possíveis de andar_ate
CHEGOU, TIMEOUT, LOTOU, PERIGO, PRESO = "chegou", "timeout", "lotou", "perigo", "preso"
RETOMAR = "retomar"  # houve pausa/interrupção: recalcular de qual ponto da rota continuar
MUDOU_ANDAR = "mudou_andar"  # (interno) chegou no andar que queria

POS = Posicao()        # posição (x, y, z) lida do minimapa, em segundo plano
ESTRATEGIA = modos.criar()  # como lutar: normal, revive ou nightmare
TROCAR_MODO = [False]       # o modo mudou no painel com o bot rodando: recria a ESTRATEGIA no próximo ciclo

# chaves que mudam COMO a luta funciona (a ESTRATEGIA guarda o modo quando é criada)
CHAVES_DO_MODO = {"MODO_HUNT", "OUTLAND_MAX_REVIVES", "REVIVE_APOS_LURE", "COMBO_DURACAO", "TECLA_REVIVE"}


def aplicar_modo_novo():
    """
    09/11 18:22: trocou para o modo REVIVE no painel no meio da hunt; o log disse "aplicadas sem reiniciar", mas a
    ESTRATEGIA (criada só no início) continuou NORMAL: combo em recarga 8x seguidas com o pet indo de 59% a 3%, e
    saiu para o lure sem reviver (sem magias). Agora o modo novo vale a partir do próximo ciclo.
    """
    global ESTRATEGIA
    if not TROCAR_MODO[0]:
        return False
    TROCAR_MODO[0] = False
    antigo = getattr(ESTRATEGIA, "nome", "?")
    ESTRATEGIA = modos.criar()
    if hasattr(ESTRATEGIA, "tem_especial"):
        ESTRATEGIA.tem_especial = lambda: bool(RASTREADOR.estrelados or RASTREADOR.escondidos or RASTREADOR.qtd)
    controle.segurar_pot_poke = ESTRATEGIA.nome == "outland" or (
        ESTRATEGIA.nome == "revive" and bool(config.REVIVE_APOS_LURE))
    print(f"[Ajustes] ⚔️ Modo de hunt agora: {ESTRATEGIA.nome} (antes: {antigo}) — já vale nesta luta.")
    return True
MAPA = MemoriaMapa()   # sqm livres e bloqueados que o bot já conhece


def carregar_rota():
    """Pontos da rota. Sem rota o bot abre do mesmo jeito (lure feito na mão)."""
    return rota.carregar()


# ---------- Battle + especial ----------

RASTREADOR = RastreadorEspecial(lambda: POS.atual())  # vigia os especiais em TODA leitura da Battle


def chat_livre():
    """Dá para mexer no chat (clicar em aba, digitar)? Só sem luta e com a Battle vazia."""
    if EM_LUTA[0]:
        return False
    try:
        with mss.MSS() as s:
            return not ler_inimigos(s)
    except Exception:
        return False


def inimigos(sct):
    """Lê os inimigos da Battle e atualiza o rastreador do especial."""
    linhas = ler_inimigos(sct)
    RASTREADOR.atualizar(linhas)
    if not catch.corpo_substitui_estrelas(POS.atual()):  # aqui o especial é achado pelo corpo morto
        RASTREADOR.vigiar_estrelas(sct, len(linhas))  # especiais com estrelinhas no nome
    if config.TARGET_ATIVO:  # aba Target: só os monstros marcados contam (lure, alvo, luta)
        linhas = [l for l in linhas if target.e_alvo(l)]
    return linhas


EM_LUTA = [False]
URGENTE = [False]


def catch_seguro(sct, fim_de_luta=True):
    """
    Catch sem derrubar a hunt: um erro no catch (ex.: recorte com número quebrado) parava o bot
    inteiro no meio da luta, com o pet no pokestop. Agora o erro aparece COMPLETO no log e a
    luta/hunt segue. Pausa (F12) e parada (F11) continuam funcionando normalmente.
    """
    antes = caixa_preta.estado_do_bot()
    try:
        caixa_preta.estado("CATCHING")
        fazer_catch(sct, RASTREADOR, fim_de_luta=fim_de_luta)
        caixa_preta.estado(antes)
    except (controle.ParadaSolicitada, mss.exception.ScreenShotError):
        raise
    except Exception:
        import traceback
        print("[Catch] ❌ Erro no catch (a hunt continua). Me mande este trecho do log:")
        traceback.print_exc()


def checar_catch(sct):
    """
    Se um especial acabou de morrer, taca a ball agora (antes do corpo sumir).
    No meio de uma luta grande NÃO: ir pegar loot/tacar ball parava os ataques e o monstrinho
    apanhava sozinho (morria). Aí o catch fica para o fim da luta (o corpo continua lá).
    """
    if RASTREADOR.pendente and EM_LUTA[0] and len(ler_inimigos(sct)) > 2:
        return
    if RASTREADOR.pendente:
        catch_seguro(sct, fim_de_luta=False)


# ---------- Decisão do lure ----------

def decidir_lure(qtd_monstros, hp_pct, hp_poke_pct=None):
    """
    Decide se é hora de parar e lutar.
    Retorna LOTOU (juntou o suficiente), PERIGO (HP baixo com monstros atrás) ou None.
    """
    if qtd_monstros >= minimo_para_lutar():
        return LOTOU
    if qtd_monstros > 0 and LURE_SEGURANCA_ATIVA:
        if hp_pct is not None and 0 < hp_pct < LURE_HP_SEGURANCA:
            return PERIGO
        if hp_poke_pct is not None and 0 < hp_poke_pct < LURE_POKE_HP_SEGURANCA:
            return PERIGO  # o monstrinho está apanhando: luta antes de ele morrer
    return None


RASTRO = []        # [(tempo, (x, y, z))] das últimas posições (para saber de onde o personagem veio)
VEIO_DE = [None]   # direção (dx, dy) de onde veio, fixada no começo de cada luta


def anotar_rastro():
    p = POS.atual()
    agora = time.time()
    if p and (not RASTRO or RASTRO[-1][1] != p):
        RASTRO.append((agora, p))
    while RASTRO and agora - RASTRO[0][0] > 15:
        RASTRO.pop(0)


def direcao_de_onde_veio():
    """
    Direção (dx, dy) de onde o personagem veio (o caminho já limpo, atrás dele), pelas posições dos
    últimos segundos; None se não andou o bastante. À frente ainda tem monstro: ir para a diagonal
    de lá puxava mais bicho para cima do personagem.
    """
    agora = POS.atual()
    if not agora:
        return None
    for _, p in RASTRO:  # a mais antiga que está a 3+ sqm daqui, no mesmo andar
        if p[2] == agora[2] and cheb(p, agora) >= 3:
            dx, dy = p[0] - agora[0], p[1] - agora[1]
            n = math.hypot(dx, dy)
            return (dx / n, dy / n)
    return None


def lado_de_tras(d, centro):
    """Quanto o lugar `d` (relativo a você) fica do lado de onde você veio, olhando da box (pet)."""
    v = VEIO_DE[0]
    if not v:
        return 0
    rx, ry = d[0] - centro[0], d[1] - centro[1]
    return round(rx * v[0] + ry * v[1], 1)


class Lure:
    """Lê a Battle e o HP e mostra no terminal quando a quantidade muda."""

    ultima_def = 0.0  # quando usou a magia de defesa do lure

    def __init__(self, sct, calib):
        self.sct = sct
        self.barra_hp = calib.get("hp")
        self.barra_poke = calib.get("poke_hp")
        self.ultima_qtd = -1

    def checar(self):
        anotar_rastro()
        qtd = len(inimigos(self.sct))
        checar_catch(self.sct)
        hp = ler_barra(self.sct, self.barra_hp) if self.barra_hp else None
        hp_poke = ler_barra(self.sct, self.barra_poke) if self.barra_poke else None
        if qtd != self.ultima_qtd:
            print(f"[Lure] Monstros na Battle: {qtd}/{minimo_para_lutar()}")
            self.ultima_qtd = qtd
        motivo = decidir_lure(qtd, hp, hp_poke) if config.CACA_ATIVA else None
        # Monstrinho perdendo vida RÁPIDO no lure (ex.: outland): não espera chegar no mínimo de
        # vida nem no tamanho do lure — luta agora com as magias que tem
        agora = time.time()
        if hp_poke is not None and hp_poke > 0:
            self.hist_poke = [(t, v) for t, v in getattr(self, "hist_poke", []) if agora - t <= 3.0]
            self.hist_poke.append((agora, hp_poke))
            queda = max(v for _, v in self.hist_poke) - hp_poke
            if (config.CACA_ATIVA and not motivo and qtd >= 2
                    and queda >= config.LURE_QUEDA_PERIGO and hp_poke < 85):
                print(f"[Lure] ⚠️ Monstrinho perdeu {queda:.0f}% em 3 s ({hp_poke:.0f}% agora): lutando já!")
                self.hist_poke = []
                motivo = PERIGO
        # Lurando com alguns monstros atrás: magia de defesa (ex.: F1) para aguentar o lure
        if (config.DEF_LURE_ATIVO and config.TECLA_DEF_LURE and config.CACA_ATIVA and not motivo
                and qtd >= config.DEF_LURE_MIN and time.time() - self.ultima_def >= config.DEF_LURE_INTERVALO):
            self.ultima_def = time.time()
            print(f"[Lure] 🛡️ {qtd} monstro(s) atrás: magia de defesa ({config.TECLA_DEF_LURE.upper()})")
            controle.ultima_magia_buff = time.time()
            controle.apertar(config.TECLA_DEF_LURE)
        if motivo == PERIGO:
            print(f"[Lure] ⚠️ HP baixo (você {hp or 0:.0f}%, monstrinho {hp_poke or 0:.0f}%) "
                  f"com {qtd} monstro(s) atrás!")
        return qtd, hp, motivo


# ---------- Movimento ----------

def ponto_no_caminho(dx, dy):
    """
    Onde clicar no minimapa para ir até (dx, dy).
    No jeito humano, quando o ponto ainda está longe, o clique cai um pouco para o
    lado do caminho reto (a pessoa não mira no pixel exato), e a rota fica menos "régua".
    Perto do ponto, mira certinho para chegar.
    """
    if not HUMANO_ATIVO:
        return dx, dy
    dist = math.hypot(dx, dy)
    if dist > 8:
        lado = random.uniform(-3, 3) * humano.I
        dx, dy = dx - dy / dist * lado, dy + dx / dist * lado  # desvio perpendicular ao caminho
    return round(dx), round(dy)


def andar_ate(sct, wp, numero, lure, ignorar_preso=False):
    """
    Anda até o waypoint olhando o minimapa, e no caminho fica de olho na Battle.
    Retorna CHEGOU, TIMEOUT, LOTOU ou PERIGO.
    """
    inicio = time.time()
    ultimo_clique = 0.0
    proximo_clique = 0.0
    ultima_pos, parado_desde = None, time.time()
    # cada ponto aceita uma "chegada" um pouco diferente (nem sempre o mesmo pixel)
    tolerancia = CHEGADA_TOLERANCIA + (1 if humano.chance(0.5) else 0)

    while time.time() - inicio < TIMEOUT_WAYPOINT:
        if not controle.rota_ligada():
            return RETOMAR  # desligaram a rota no meio do caminho
        if controle.aguardar_se_pausado():
            inicio, ultimo_clique = time.time(), 0.0  # tempo pausado não conta
            parado_desde = time.time()

        qtd, _, motivo = lure.checar()
        if motivo:
            return motivo

        dx, dy, conf = localizar_waypoint(capturar_minimapa(sct), wp["img"])

        # Preso: o personagem não sai do lugar (cercado/bloqueado) e já tem monstro atrás
        if conf >= MATCH_THRESHOLD and (dx, dy) != ultima_pos:
            ultima_pos, parado_desde = (dx, dy), time.time()
        if qtd > 0 and time.time() - parado_desde >= LURE_PRESO_S and config.CACA_ATIVA and not ignorar_preso:
            print(f"[Lure] Parado há {LURE_PRESO_S:.0f}s com {qtd} monstro(s) — devo estar cercado.")
            return PRESO

        if conf >= MATCH_THRESHOLD:
            if abs(dx) <= tolerancia and abs(dy) <= tolerancia:
                print(f"[CaveBot] Chegou no waypoint {numero}.")
                return CHEGOU

            # Clica de novo de tempos em tempos, recalculando a posição (corrige desvios)
            if time.time() - ultimo_clique >= proximo_clique:
                controle.clicar(*deslocamento_para_tela(*ponto_no_caminho(dx, dy)))
                ultimo_clique = time.time()
                proximo_clique = humano.variar(RECLIQUE_INTERVALO, 0.6)

        if controle.esperar(0.1):
            inicio, ultimo_clique = time.time(), 0.0

    print(f"[CaveBot] ⚠️ Não chegou no waypoint {numero} em {TIMEOUT_WAYPOINT:.0f}s. Pulando.")
    return TIMEOUT


# ---------- Movimento por coordenadas ----------

SETAS = {(0, -1): "up", (0, 1): "down", (-1, 0): "left", (1, 0): "right"}


def sqm_ocupados(sct):
    """Sqm (dx, dy em relação ao personagem) com criatura em cima — não clicar neles."""
    return criaturas_na_imagem(capturar(sct, GAME_VIEW))


def criaturas_na_imagem(img):
    """O mesmo que sqm_ocupados, sobre uma tela do jogo já capturada (a caixa-preta usa)."""
    ocupados = set()
    for bx, by, _, _ in encontrar_barras_criaturas(img, (GAME_VIEW["left"], GAME_VIEW["top"])):
        cx, cy = bx + BARRA_LARGURA // 2, by + 26
        ocupados.add((round((cx - PLAYER_TILE_XY[0]) / SQM_PX), round((cy - PLAYER_TILE_XY[1]) / SQM_PX)))
    ocupados.discard((0, 0))
    return ocupados


def limites_clique(sct):
    """
    Até quantos sqm para cada lado dá para clicar na tela do jogo sem cair em cima
    da janela da Battle (que fica por cima do mapa, do lado esquerdo).
    """
    dx0, dx1 = NAV_VIEW_DX
    reg = regiao_battle(sct)
    if reg:
        esquerda_battle, direita_battle = reg["left"], reg["left"] + reg["width"]
        if esquerda_battle < PLAYER_TILE_XY[0] < direita_battle:
            pass  # Battle em cima do personagem? não dá para decidir, mantém
        elif direita_battle < PLAYER_TILE_XY[0]:  # Battle à esquerda do personagem
            dx0 = max(dx0, math.ceil((direita_battle + SQM_PX / 2 - PLAYER_TILE_XY[0]) / SQM_PX))
        else:                                     # Battle à direita
            dx1 = min(dx1, math.floor((esquerda_battle - SQM_PX / 2 - PLAYER_TILE_XY[0]) / SQM_PX))
    return (dx0, dx1), NAV_VIEW_DY


ULTIMO_ORDER = 0.0  # quando foi o último order (o pet pode estar no caminho logo depois)


def tirar_pet_do_corpo(corpo):
    """
    Catch (fim de luta): o pet está colado no corpo do especial e o desenho dele (Gyarados é grande,
    desenhado para cima/esquerda) esconde as estrelinhas — o catch achava que já tinha pegado e
    desistia (07/11 22:13, 2 balls). Manda o pet 3 sqm para longe do corpo (para baixo/direita
    quando está em cima dele) e espera ele sair. True se deu o order.
    """
    pos, pet = POS.atual(), PET_ABS[0]
    if not pos or not pet or pet[2] != corpo[2] or cheb(pet[:2], corpo[:2]) > 1:
        return False
    vx = (pet[0] > corpo[0]) - (pet[0] < corpo[0])
    vy = (pet[1] > corpo[1]) - (pet[1] < corpo[1])
    if not vx and not vy:
        vx, vy = 1, 1  # em cima do corpo: o desenho cobre para cima/esquerda → sai para baixo/direita
    destino = (corpo[0] + 3 * vx, corpo[1] + 3 * vy, corpo[2])
    if destino[:2] == pos[:2]:  # nunca no personagem (seria RIDE)
        destino = (destino[0] + vx, destino[1], destino[2])
    rel = (destino[0] - pos[0], destino[1] - pos[1])
    if abs(rel[0]) > MEIA_TELA[0] - 1 or abs(rel[1]) > MEIA_TELA[1] - 1:
        return False  # fora da tela: não dá para clicar
    dar_order(pos, destino, motivo="tirando o pet de cima do corpo do especial (escondia as estrelinhas)")
    PET_ABS[0] = destino
    controle.esperar(humano.variar(1.0))
    return True


def dar_order(pos=None, destino=None, motivo="", valido=None):
    """
    Order = clique com a bolinha do mouse (botão do meio): manda o monstrinho para o sqm.
    Sem destino: no próprio personagem (tira o pet do pokestop / chama ele de volta).
    `valido`: (orders em thread) função que diz se o order ainda faz sentido — se uma luta
    começou, o order atrasado tiraria o pet do pokestop. Retorna False se não deu o order.
    """
    global ULTIMO_ORDER
    if valido is not None and not valido():
        return False
    ULTIMO_ORDER = time.time()
    # NUNCA order no próprio personagem: no jogo isso é RIDE (montar no pokémon) — em hunt mata.
    # Sem destino, manda o pet para um sqm colado no personagem (tira do pokestop do mesmo jeito).
    if destino is None or pos is None or destino[:2] == pos[:2]:
        dx, dy = random.choice([(-1, 0), (1, 0), (0, 1), (0, -1)])
        controle.clicar(PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                        espalhar=(8, 8), botao="middle")
    else:
        clicar_sqm(pos, destino, botao="middle")
    if motivo:
        print(f"[CaveBot] 👉 Order ({motivo})")
    return True


# ---------- Orders em thread (podem ser cancelados) ----------
# Orders andando e o order depois da luta rodam em thread, com esperas de até ~1 s entre eles.
# Se o lure lotar nesse meio-tempo, o bot aperta pokestop e o order atrasado TIRAVA o pet do
# pokestop (a box não fechava). Agora cada thread nasce presa a um "sinal de cancelamento":
# quando a luta começa (cancelar_orders), o sinal dispara, as esperas acabam na hora e nenhum
# order sai depois disso.
_cancelar_orders = [threading.Event()]
_threads_order = []


def _order_em_thread(func):
    """Roda func(esperar, valido) numa thread de order cancelável."""
    sinal = _cancelar_orders[0]

    def valido():
        return not sinal.is_set() and not EM_LUTA[0] and not controle.acoes_bloqueadas()

    def esperar(segundos):
        sinal.wait(segundos)  # acorda na hora se a luta começar

    def rodar():
        try:
            func(esperar, valido)
        except controle.ParadaSolicitada:
            pass
        except Exception as e:
            print(f"[Order] erro: {e!r}")

    t = threading.Thread(target=rodar, daemon=True)
    _threads_order[:] = [x for x in _threads_order if x.is_alive()] + [t]
    t.start()
    return t


def cancelar_orders():
    """A luta vai começar: nenhum order antigo pode sair (espera o clique que já está no meio)."""
    _cancelar_orders[0].set()
    _cancelar_orders[0] = threading.Event()
    ORDER_AO_ANDAR[0] = False
    for t in list(_threads_order):
        t.join(timeout=1.0)


def proximo_intervalo_order():
    """Intervalo até o próximo order andando: bem variado (≈0,5x a 1,8x do configurado)."""
    return ORDER_INTERVALO * random.uniform(0.5, 1.8)


_order_rodando = threading.Event()


def orders_em_paralelo(pos, destino):
    """Roda os orders numa thread: o loop de andar continua lendo a tela e clicando."""
    if _order_rodando.is_set():
        return
    _order_rodando.set()

    def rodar(esperar, valido):
        try:
            orders_andando(pos, destino, esperar=esperar, valido=valido)  # em thread: nada de controle.esperar
        finally:
            _order_rodando.clear()
    _order_em_thread(rodar)


def abertura(p):
    """
    Quanto o sqm `p` (x, y, z) é aberto para a box fechar em volta do pet, pela memória do mapa:
    vizinhos já pisados (chão) contam +1; parede/bloqueio conhecido perto pesa muito contra.
    Sem informação nenhuma dá 0 (não sabe).
    """
    if MAPA.esta_bloqueado(p):
        return -99
    nota = 0
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            if a or b:
                v = (p[0] + a, p[1] + b, p[2])
                if MAPA.esta_bloqueado(v):
                    nota -= 6
                elif v in MAPA.livres:
                    nota += 1
    return nota


def melhor_lugar(candidatos):
    """O candidato mais aberto (empate: sorteio, para não ficar repetitivo)."""
    return max(candidatos, key=lambda p: (abertura(p), random.random()))


def orders_andando(pos, destino, esperar=None, valido=None):
    """
    Orders enquanto anda puxando o lure, do jeito que uma pessoa faz para ajustar o monstrinho:
    o lugar varia (no destino, no meio do caminho ou 1 sqm para o lado) e às vezes vêm 2 seguidos.
    """
    # NUNCA no caminho do personagem: o pet chega antes e fecha a passagem (o bot "travava",
    # desviava e ficava rodando). O pet vai para trás ou para o lado do personagem.
    dx, dy = destino[0] - pos[0], destino[1] - pos[1]
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)   # direção em que está andando
    # candidatos atrás e dos lados; vai o mais ABERTO (longe de parede: a box precisa caber)
    candidatos = [(pos[0] - sx * k, pos[1] - sy * k, pos[2]) for k in (1, 2)]
    for lado in (1, -1):
        candidatos.append((pos[0] + (-sy or 1) * lado * (sy != 0 or sx == 0), pos[1] + sx * lado, pos[2]))
        candidatos.append((pos[0] - sx + (-sy or 1) * lado * (sy != 0 or sx == 0), pos[1] - sy + sx * lado, pos[2]))
    candidatos = [c for c in candidatos if c[:2] != pos[:2]]
    alvo = melhor_lugar(candidatos)
    esperar = esperar or controle.esperar
    esperar(humano.variar(0.12, 0.6))
    if not dar_order(pos, alvo, valido=valido):
        return
    if random.random() < 0.2:  # de vez em quando, um segundo order para "corrigir" (ainda atrás)
        esperar(random.uniform(0.2, 0.6))
        dar_order(pos, (alvo[0] - sx, alvo[1] - sy, pos[2]), valido=valido)


ORDER_AO_ANDAR = [False]  # tirar o pet do pokestop no 1º clique de andar (sem parar o boneco)
DIRECAO_ANDAR = [None]    # (dx, dy) do último clique de andar: o pet vai para TRÁS/do lado, nunca na frente

VIZINHOS8 = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (1, -1), (-1, 1)]


def vizinhos_atras(direcao=None):
    """
    Sqm colados em você que NÃO ficam no caminho: atrás ou do lado de para onde você vai andar.
    09/11: as 11 travadas da sessão 21:39 foram o pet parado na frente (order depois da luta caía em qualquer
    lado) — os pontos 5 e 7 levavam 15–17 s em vez de 3–4 s.
    """
    if not direcao or direcao == (0, 0):
        return list(VIZINHOS8)
    sx = (direcao[0] > 0) - (direcao[0] < 0)
    sy = (direcao[1] > 0) - (direcao[1] < 0)
    ok = [v for v in VIZINHOS8 if v[0] * sx + v[1] * sy < 0]      # atrás
    return ok or [v for v in VIZINHOS8 if v[0] * sx + v[1] * sy <= 0]


def pedir_order_depois_da_luta():
    """Com a rota ligada, o order sai junto com o 1º passo; sem rota, na hora."""
    if controle.rota_ligada():
        ORDER_AO_ANDAR[0] = True
    else:
        orders_depois_da_luta()


def order_ao_andar_se_pendente():
    """Chamado logo depois de um clique de andar: dá o order em paralelo, andando."""
    if not ORDER_AO_ANDAR[0]:
        return
    ORDER_AO_ANDAR[0] = False

    def rodar(esperar, valido):
        esperar(random.uniform(0.12, 0.35))
        orders_depois_da_luta(esperar=esperar, valido=valido)
    _order_em_thread(rodar)


def orders_depois_da_luta(esperar=None, valido=None):
    """1 a 3 orders: o 1º no personagem (sai do pokestop), às vezes mais 1–2 em volta."""
    esperar = esperar or controle.esperar
    atras = vizinhos_atras(DIRECAO_ANDAR[0])
    pos = POS.atual()
    if pos is not None:
        v = random.choice(atras)
        primeiro = (pos[0] + v[0], pos[1] + v[1], pos[2])
    else:
        primeiro = None
    if not dar_order(pos, primeiro, motivo="tirando o monstrinho do pokestop", valido=valido):
        return
    extras = random.choices((0, 1, 2), weights=(45, 40, 15))[0]
    for _ in range(extras):
        esperar(random.uniform(0.25, 0.9))
        if valido is not None and not valido():
            return  # começou outra luta (ou pausou): order agora tiraria o pet do pokestop
        dx, dy = random.choice(vizinhos_atras(DIRECAO_ANDAR[0]))
        controle.clicar(PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                        espalhar=(12, 12), botao="middle")


def clicar_sqm(pos, destino, botao="left"):
    """Clica no sqm `destino` na tela do jogo (o personagem fica sempre no meio)."""
    dx, dy = destino[0] - pos[0], destino[1] - pos[1]
    controle.clicar(PLAYER_TILE_XY[0] + dx * SQM_PX, PLAYER_TILE_XY[1] + dy * SQM_PX,
                    espalhar=(12, 12), botao=botao)


CRIATURA_TRAVA_S = 0.9  # parado com criatura no sqm da frente: desvia depois disso (parede continua NAV_TRAVADO_S)


def criatura_no_caminho(pos, destino, ocupados):
    """Tem criatura (relativa a você, `ocupados`) no sqm da frente, indo de `pos` para `destino`?"""
    if not destino:
        return False
    frente = passo_reto(pos, destino)
    return frente[:2] != pos[:2] and (frente[0] - pos[0], frente[1] - pos[1]) in ocupados


def passo_reto(pos, destino):
    """O sqm vizinho na direção de `destino` (para onde o personagem estava tentando ir)."""
    sx = (destino[0] > pos[0]) - (destino[0] < pos[0])
    sy = (destino[1] > pos[1]) - (destino[1] < pos[1])
    return (pos[0] + sx, pos[1] + sy, pos[2])


def seta_de_desvio(pos, rota, alvo, tentativa):
    """
    Seta do teclado para sair de onde travou, seguindo o caminho calculado (que já
    evita os bloqueios conhecidos). Sem caminho: tenta os lados e depois para trás.
    """
    opcoes = []
    if rota:
        dx, dy = rota[0][0] - pos[0], rota[0][1] - pos[1]
        for d in ((dx, 0), (0, dy)):
            viz = (pos[0] + d[0], pos[1] + d[1], pos[2])
            if d != (0, 0) and not MAPA.esta_bloqueado(viz):
                opcoes.append(d)
    if not opcoes:
        sx = (alvo[0] > pos[0]) - (alvo[0] < pos[0])
        sy = (alvo[1] > pos[1]) - (alvo[1] < pos[1])
        frente = (sx, 0) if abs(alvo[0] - pos[0]) >= abs(alvo[1] - pos[1]) else (0, sy)
        frente = frente if frente != (0, 0) else (0, 1)
        opcoes = [(-frente[1], frente[0]), (frente[1], -frente[0]), (-frente[0], -frente[1])]
    return SETAS[opcoes[tentativa % len(opcoes)]]


def esperar_mudar_andar(z_destino, segundos):
    """Espera até `segundos` o personagem aparecer em `z_destino`. Retorna a posição nova ou None."""
    fim = time.time() + segundos
    while time.time() < fim:
        controle.esperar(0.1)
        pos = POS.atual()
        if pos and pos[2] == z_destino:
            return pos
    return None


def trocar_de_andar(sct, pos, alvo, numero, lure):
    """
    O próximo ponto está em outro andar: vai até a escada/buraco e passa por ela.

    1. Se já conhece uma passagem para o andar seguinte (aprendida antes), vai direto nela.
       Senão, anda pelo andar atual na direção do ponto (é por ali que a pessoa passou
       quando gravou a rota) — pisando na escada/buraco no caminho, já troca.
    2. Chegando lá sem ter trocado: testa pisar nos sqm em volta (na direção do outro lado)
       e, por fim, clica com o botão direito ("usar") — para escada de mão/corda.
    Retorna MUDOU_ANDAR, um motivo de luta/pausa (LOTOU, PERIGO, PRESO, RETOMAR) ou TIMEOUT.
    """
    z_destino = pos[2] + (1 if alvo[2] > pos[2] else -1)
    passagem = MAPA.passagem(pos, z_destino, alvo)
    if passagem:
        daqui, de_la = passagem
        print(f"[Rota] Andar {pos[2]} → {z_destino}: indo pela passagem conhecida em {daqui[0]}, {daqui[1]}.")
    else:
        daqui = (alvo[0], alvo[1], pos[2])
        de_la = (alvo[0], alvo[1], z_destino)
        print(f"[Rota] Andar {pos[2]} → {z_destino}: procurando a escada/buraco perto de {alvo[0]}, {alvo[1]}.")

    # Passagem conhecida, ou o ponto ainda está longe: anda até lá primeiro.
    # (Se o ponto está a até 3 sqm, a escada fica no meio do caminho: não precisa andar.)
    if passagem or distancia(pos, daqui) > 3:
        r = andar_ate_coord(sct, {"pos": daqui}, numero, lure, z_final=z_destino)
        if r in (MUDOU_ANDAR, LOTOU, PERIGO, PRESO, RETOMAR):
            return r

    # Não trocou de andar: testa pisar nos sqm do caminho reto até o outro lado
    # (é por ali que a pessoa passou ao gravar) e depois os sqm em volta.
    pos = POS.atual() or daqui
    if pos[2] == z_destino:
        return MUDOU_ANDAR
    candidatos = []
    atual = pos
    while atual[:2] != de_la[:2] and len(candidatos) < 4:  # sqm a sqm na direção do outro lado
        atual = passo_reto(atual, de_la)
        candidatos.append((atual[0], atual[1], pos[2]))
    vizinhos = [(pos[0] + dx, pos[1] + dy, pos[2]) for dx, dy in VIZINHOS_8]
    vizinhos.sort(key=lambda v: max(abs(v[0] - de_la[0]), abs(v[1] - de_la[1])))
    candidatos += [v for v in vizinhos if v not in candidatos]
    for botao, tentativas in (("left", candidatos[:8]), ("right", candidatos[:4])):
        for sqm in tentativas:
            antes = POS.atual() or pos
            clicar_sqm(antes, sqm, botao)
            novo = esperar_mudar_andar(z_destino, 1.6)
            if botao == "right":
                controle.apertar("esc")  # fecha menu, se abrir algum
            if novo:
                nova = MAPA.registrar_passagem(antes, novo)
                print(f"[Rota] Mudei de andar ({'usando' if botao == 'right' else 'pisando em'} "
                      f"{sqm[0]}, {sqm[1]}).{' Passagem guardada para as próximas voltas.' if nova else ''}")
                return MUDOU_ANDAR
    print(f"[Rota] ⚠️ Não achei a passagem para o andar {z_destino} perto de {alvo[0]}, {alvo[1]}.")
    return TIMEOUT


VIZINHOS_8 = [(0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)]


def alarmar_e_pausar(sct, texto, motivo, prefixo):
    """Alarme + print da tela em diagnostico/ + pausa (F12 continua)."""
    print("\n" + "#" * 60)
    print(texto)
    print("Bot PAUSADO. Resolva no jogo e aperte F12 para continuar.")
    print("#" * 60)
    try:  # print da tela para entender o motivo depois
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, time.strftime(f"{prefixo}_%H-%M-%S.png"))
        cv2.imwrite(arq, cv2.cvtColor(np.array(sct.grab(sct.monitors[0])), cv2.COLOR_BGRA2BGR))
        print(f"(print da tela salvo em diagnostico/{os.path.basename(arq)})")
    except Exception as e:
        print(f"(não consegui salvar o print: {e!r})")
    chat.tocar_som(15)
    controle.pausar(motivo)


class MemoriaRota:
    """
    Memória curta do que deu errado andando, para não repetir a mesma falha para sempre:
      - tentativas seguidas sem chegar em NENHUM ponto (timeout, escada não achada, sem coordenada)
        -> depois de NAV_FALHAS_MAX: alarme + pausa (antes pulava de ponto em ponto em silêncio);
      - "cercado" que virou luta sem ninguém no alcance (monstro atrás de parede) no mesmo lugar
        -> depois de 2x ali: para de lutar por "cercado" e deixa o desvio/alarme de preso agir
        (antes: preso -> luta vazia -> preso -> luta vazia... sem fim).
    Chegar em qualquer ponto zera tudo.
    """
    PERTO_SQM = 3
    PRESOS_PARA_IGNORAR = 2

    def __init__(self):
        self.falhas = 0
        self.presos_inuteis = []  # posições (x, y, z) onde lutar por "cercado" não adiantou

    def chegou(self):
        self.falhas = 0
        self.presos_inuteis.clear()

    def falhou(self, numero, motivo):
        """Conta uma falha. True = chegou no limite (o chamador alarma e pausa)."""
        self.falhas += 1
        maximo = int(getattr(config, "NAV_FALHAS_MAX", 4))
        print(f"[Rota] Falha {self.falhas}/{maximo} seguida sem chegar em ponto nenhum "
              f"(ponto {numero}: {motivo}).")
        if maximo and self.falhas >= maximo:
            self.falhas = 0  # depois da pausa recomeça a contar
            return True
        return False

    def preso_inutil(self, pos):
        self.presos_inuteis.append(pos)
        self.presos_inuteis = self.presos_inuteis[-10:]

    def ignorar_preso(self, pos):
        if pos is None:
            return len(self.presos_inuteis) >= self.PRESOS_PARA_IGNORAR
        perto = [p for p in self.presos_inuteis
                 if p and p[2] == pos[2] and distancia(p, pos) <= self.PERTO_SQM]
        return len(perto) >= self.PRESOS_PARA_IGNORAR


def andar_ate_coord(sct, wp, numero, lure, z_final=None, ignorar_preso=False):
    """
    Anda até a coordenada do waypoint, desviando de bloqueios.

    - Calcula o caminho (A*) com a memória do mapa e clica no sqm mais adiante
      desse caminho que aparece na tela; o jogo anda até lá.
    - Travou (não saiu do lugar por NAV_TRAVADO_S): marca o sqm à frente como
      bloqueado e recalcula. A partir do 3º desvio, tenta também dar um passo
      com as setas do teclado para os lados.
    - Com monstros atrás e parado: luta (PRESO).
    - Sem monstros e parado por NAV_PRESO_S: alarme + pausa (preso de verdade).
    - Ponto em outro andar: vai pela escada/buraco (trocar_de_andar) e continua.
    `z_final`: usado ao procurar uma escada — se o personagem chegar nesse andar, retorna MUDOU_ANDAR.
    `ignorar_preso`: não devolve PRESO por ter monstro atrás (a memória da rota viu que lutar ali
    não adiantou: monstro fora de alcance). Aí vale o desvio normal e, no fim, o alarme de preso.
    """
    alvo = wp["pos"]
    pos_anterior = None
    inicio = time.time()
    ultima_pos, ultimo_movimento, ultimo_desvio = None, time.time(), 0.0
    proximo_clique, desvios = 0.0, 0
    sem_posicao_desde = None
    ultimo_destino = None
    proximo_order = time.time() + random.uniform(0.2, ORDER_INTERVALO)
    historico = []  # [(tempo, pos)] para saber se está andando de verdade ou indo e voltando
    # progresso = quanto falta de caminho até o ponto; "preso" é ficar sem progredir
    # (andar de um lado pro outro sem chegar mais perto também conta como preso)
    menor_restante, ultimo_progresso = None, time.time()

    destinos_ruins = set()  # sqm clicados em que o personagem nem saiu do lugar
    perdoado = None  # sqm em que o travamento já foi atribuído ao pet
    avisou_ponto = False
    while time.time() - inicio < TIMEOUT_WAYPOINT * 3:
        if not controle.rota_ligada():
            return RETOMAR  # desligaram a rota no meio do caminho
        if controle.aguardar_se_pausado():
            return RETOMAR  # pode ter se mexido na pausa: recalcula de onde continuar

        qtd, _, motivo = lure.checar()
        if motivo == LOTOU and wp.get("lure") and z_final is None:
            # lure cheio a caminho de um ponto de lure: termina lá (lugar aberto), não colado em parede
            p = POS.atual()
            falta = distancia(p, alvo) if p and p[2] == alvo[2] else 99
            if 0 < falta <= config.LURE_IR_ATE_PONTO:
                if not avisou_ponto:
                    print(f"[Lure] Lure cheio: terminando no ponto de lure ({falta} sqm).")
                    avisou_ponto = True
                motivo = None
        if motivo:
            return motivo

        pos = POS.atual()
        if pos is None:
            sem_posicao_desde = sem_posicao_desde or time.time()
            if time.time() - sem_posicao_desde > 8:
                print("[Rota] ⚠️ Não consigo ler as coordenadas do minimapa (coberto?).")
                return TIMEOUT
            controle.esperar(0.1)
            continue
        sem_posicao_desde = None

        # Mudou de andar andando (escada/buraco): aprende onde fica a passagem
        if pos_anterior and pos[2] != pos_anterior[2]:
            if MAPA.registrar_passagem(pos_anterior, pos):
                print(f"[Rota] Passagem de andar guardada: {pos_anterior[0]}, {pos_anterior[1]} "
                      f"(andar {pos_anterior[2]}) → andar {pos[2]}.")
        pos_anterior = pos

        if z_final is not None and pos[2] == z_final:
            return MUDOU_ANDAR
        if pos[2] != alvo[2]:
            if z_final is not None:
                return TIMEOUT  # procurando escada e foi parar num andar inesperado
            r = trocar_de_andar(sct, pos, alvo, numero, lure)
            if r != MUDOU_ANDAR:
                return r
            inicio = time.time()  # trocou de andar: recomeça a contar para este ponto
            ultima_pos, ultimo_movimento, menor_restante, ultimo_progresso = None, time.time(), None, time.time()
            historico = []
            continue

        MAPA.pisou(pos)
        if distancia(pos, alvo) <= NAV_CHEGADA_SQM + (1 if z_final is not None else 0):
            print(f"[CaveBot] Chegou no waypoint {numero} ({pos[0]}, {pos[1]}).")
            return CHEGOU

        agora = time.time()
        if pos != ultima_pos:
            ultima_pos, ultimo_movimento = pos, agora
        parado = agora - ultimo_movimento

        rota = MAPA.caminho(pos, alvo)
        restante = len(rota) if rota else distancia(pos, alvo)
        if menor_restante is None or restante < menor_restante:
            menor_restante, ultimo_progresso = restante, agora
        sem_progresso = agora - ultimo_progresso
        historico.append((agora, pos))
        historico = [(t, p) for t, p in historico if agora - t <= NAV_PRESO_S]
        lugares_recentes = len({p for _, p in historico})

        if qtd > 0 and parado >= LURE_PRESO_S and config.CACA_ATIVA and not ignorar_preso:
            print(f"[Lure] Parado há {LURE_PRESO_S:.0f}s com {qtd} monstro(s) — devo estar cercado.")
            return PRESO

        # Preso: não chega mais perto há NAV_PRESO_S E ficou rodando no mesmo cantinho
        # (um desvio comprido, andando por vários sqm, não conta como preso)
        if z_final is not None and sem_progresso >= min(NAV_PRESO_S, 8):
            return TIMEOUT  # procurando escada: não pausa, deixa o trocar_de_andar testar em volta
        if sem_progresso >= NAV_PRESO_S and lugares_recentes <= 4:
            alarmar_e_pausar(sct, f"🧱 PRESO em {pos[0]}, {pos[1]}, {pos[2]} há {NAV_PRESO_S:.0f}s, "
                                  f"sem conseguir chegar no ponto {numero}.", "personagem preso", "preso")
            return RETOMAR

        # Criatura (quase sempre o seu pet) parada no sqm da frente: desvia já (~0,9 s) em vez de esperar
        # NAV_TRAVADO_S (2,5 s) — e não marca parede no mapa, porque ela sai dali.
        criatura_na_frente = False
        if CRIATURA_TRAVA_S <= parado < NAV_TRAVADO_S and ultimo_destino \
                and agora - ultimo_desvio >= CRIATURA_TRAVA_S:
            criatura_na_frente = criatura_no_caminho(pos, ultimo_destino, sqm_ocupados(sct))

        # Travou: marca o bloqueio, recalcula o caminho e, se insistir, usa as setas
        if (parado >= NAV_TRAVADO_S and agora - ultimo_desvio >= NAV_TRAVADO_S) or criatura_na_frente:
            # o bloqueio é o sqm para onde ele estava tentando ir
            bloqueio = passo_reto(pos, ultimo_destino) if ultimo_destino else primeiro_passo(MAPA, pos, alvo, rota)
            if bloqueio[:2] == pos[:2] or MAPA.esta_bloqueado(bloqueio):
                bloqueio = primeiro_passo(MAPA, pos, alvo, rota)
            # logo depois de order pode ser o pet no caminho: perdoa só 1 vez por sqm
            pet = criatura_na_frente or (agora - ULTIMO_ORDER < 4.0 and bloqueio != perdoado)
            perdoado = bloqueio if pet else perdoado
            vezes = 0 if pet else MAPA.bloquear(bloqueio)  # logo depois de order: era o pet, não parede
            desvios += 1
            ultimo_desvio = agora
            # o sqm clicado (às vezes longe) pode ser um lugar onde não dá para pisar: o jogo
            # recusa ("There is no way") e o personagem nem sai do lugar. Não clica mais nele.
            if ultimo_destino and distancia(pos, ultimo_destino) > 1:
                destinos_ruins.add(ultimo_destino[:2])
            extra = " (parede)" if vezes >= 3 else " (deve ser o monstrinho)" if pet else ""
            print(f"[Rota] Travado em {pos[0]}, {pos[1]} — bloqueio em {bloqueio[0]}, {bloqueio[1]}{extra}. "
                  f"Recalculando caminho (desvio {desvios}).")
            if desvios >= 3:
                tecla = seta_de_desvio(pos, MAPA.caminho(pos, alvo), alvo, desvios - 3)
                controle.apertar(tecla)
                print(f"[Rota] Tentando sair com a seta {tecla.upper()}.")
                proximo_clique = agora + 0.7  # deixa o passo da seta terminar (um clique logo depois cancelava)
            else:
                proximo_clique = 0.0

        if agora >= proximo_clique:
            if desvios and agora - ultimo_desvio < 0.05:
                rota = MAPA.caminho(pos, alvo)  # acabou de marcar bloqueio: caminho novo
            perto = None
            if desvios and agora - ultimo_desvio < 3 * NAV_TRAVADO_S:
                perto = 1 if desvios >= 2 else 3  # travou de novo: só o sqm do lado (sempre dá para andar)
            lim_dx, lim_dy = limites_clique(sct)
            evitar = sqm_ocupados(sct) | {(x - pos[0], y - pos[1]) for x, y in destinos_ruins}
            destino = proximo_destino(MAPA, pos, alvo, lim_dx, lim_dy, evitar, rota, perto)
            if destino:
                clicar_sqm(pos, destino)
                ultimo_destino = destino
                DIRECAO_ANDAR[0] = (destino[0] - pos[0], destino[1] - pos[1])
                order_ao_andar_se_pendente()
                if ORDER_ANDANDO and agora >= proximo_order and agora - ultimo_desvio > 6:  # travado: sem order
                    orders_em_paralelo(pos, destino)  # o monstrinho acompanha o lure, sem parar de andar
                    proximo_order = agora + proximo_intervalo_order()
            proximo_clique = agora + humano.variar(RECLIQUE_INTERVALO, 0.6)

        if controle.esperar(0.1):
            return RETOMAR

    print(f"[CaveBot] ⚠️ Não chegou no waypoint {numero}. Pulando.")
    return TIMEOUT


def passo_mais_proximo(pontos, ordem, passo_atual):
    """
    Depois de uma interrupção (luta, catch, descanso, pausa): de qual ponto da rota continuar.
    Escolhe o waypoint mais perto de onde o personagem está e, se ele aparece mais de uma
    vez na ordem (ida e volta), a ocorrência mais próxima à frente.
    """
    pos = POS.atual()
    if pos is None:
        return passo_atual
    candidatos = [i for i, p in enumerate(pontos) if p.get("pos") and p["pos"][2] == pos[2]]
    if not candidatos:
        return passo_atual
    mais_perto = min(candidatos, key=lambda i: distancia(pos, pontos[i]["pos"]))
    # Continua indo para o ponto que já estava indo, se ele não está muito mais longe que o mais
    # perto: senão o bot voltava para o ponto que acabou de passar e depois seguia (ida e volta à toa).
    atual = pontos[ordem[passo_atual]].get("pos")
    if atual and atual[2] == pos[2] and distancia(pos, atual) <= distancia(pos, pontos[mais_perto]["pos"]) + 8:
        return passo_atual
    posicoes = [k for k, i in enumerate(ordem) if i == mais_perto]
    novo = min(posicoes, key=lambda k: (k - passo_atual) % len(ordem))
    if novo != passo_atual:
        print(f"[Rota] Retomando pelo ponto mais perto: {mais_perto + 1} "
              f"({distancia(pos, pontos[mais_perto]['pos'])} sqm daqui).")
    return novo


def lugar_aberto_para_o_pet(pos):
    """
    Sqm perto do personagem onde o pet pode ficar com espaço para a box fechar em volta:
    já pisado (chão) e com o máximo de vizinhos livres e nenhum bloqueio conhecido.
    Sem informação, manda o pet para o próprio personagem (ele fica do lado).
    """
    opcoes = []
    for d in [(-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (1, -1), (-1, 1)]:
        p = (pos[0] + d[0], pos[1] + d[1], pos[2])
        if p not in MAPA.livres or MAPA.esta_bloqueado(p):
            continue
        viz = [(p[0] + a, p[1] + b, p[2]) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
        if any(MAPA.esta_bloqueado(v) for v in viz):
            continue
        opcoes.append((sum(1 for v in viz if v in MAPA.livres) + random.random(), p))
    if opcoes:
        return max(opcoes)[1]
    d = random.choice([(-1, 0), (1, 0), (0, 1), (0, -1)])  # sem informação: do lado (nunca no personagem)
    return (pos[0] + d[0], pos[1] + d[1], pos[2])


def esperar_trem(lure):
    """
    Num ponto marcado como lure: fica parado um pouco para os monstros
    que vêm atrás alcançarem. Retorna o motivo para lutar, ou None.
    """
    order_ao_andar_se_pendente()  # parado no ponto: o pet não pode ficar no pokestop
    qtd, _, motivo = lure.checar()
    if motivo:
        return motivo
    if qtd == 0:
        return None  # ninguém vindo atrás: esperar seria perda de tempo
    print(f"[Lure] Esperando os monstros alcançarem (até {LURE_ESPERA_PONTO:.0f}s)...")
    fim = time.time() + LURE_ESPERA_PONTO
    proximo_order = time.time() + random.uniform(0.5, 1.5)
    ultimo_qtd, mudou = qtd, time.time()
    while time.time() < fim:
        if not controle.rota_ligada():
            return None
        qtd, _, motivo = lure.checar()
        if motivo:
            return motivo
        if qtd > ultimo_qtd:
            ultimo_qtd, mudou = qtd, time.time()
        elif time.time() - mudou > 1.2:
            return None  # não está chegando mais ninguém: segue lurando em vez de ficar parado
        if ORDER_ANDANDO and time.time() >= proximo_order:  # ajusta o monstrinho enquanto espera
            pos = POS.atual()
            if pos:
                dar_order(pos, lugar_aberto_para_o_pet(pos))
            proximo_order = time.time() + proximo_intervalo_order()
        if controle.esperar(0.1):
            fim = time.time() + LURE_ESPERA_PONTO
    return None


# ---------- Combate ----------

def descansar(sct):
    """
    Depois da luta: se o monstrinho está com pouca vida, fica parado esperando a
    poção curar (a thread de cura toma a poção, já que não tem inimigo batendo).
    Se aparecer monstro, para de descansar e volta para a rota/luta.
    """
    if not (CURA_POKE_ATIVA and DESCANSAR_ATE > 0):
        return
    barra = carregar_calibracao().get("poke_hp")
    if not barra:
        return
    pct = ler_barra(sct, barra)
    if pct is None or pct >= DESCANSAR_ATE:
        return

    print(f"[Cura] 💤 Monstrinho em {pct:.0f}%: descansando até {DESCANSAR_ATE}% (máx. {DESCANSO_MAX:.0f}s)...")
    inicio = time.time()
    while time.time() - inicio < DESCANSO_MAX:
        if controle.esperar(0.5):
            inicio = time.time()
        if inimigos(sct):
            print("[Cura] Apareceu monstro, parando o descanso.")
            return
        pct = ler_barra(sct, barra)
        if pct is not None and pct >= DESCANSAR_ATE:
            print(f"[Cura] Monstrinho recuperado ({pct:.0f}%).")
            return
    print(f"[Cura] Descansei {DESCANSO_MAX:.0f}s e o monstrinho está em {pct or 0:.0f}%. Seguindo assim mesmo.")


def cheb(a, b):
    """Distância em sqm (diagonal conta 1), entre dois sqm relativos (dx, dy)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


PET_ABS = [None]  # onde o pet (centro da box) foi visto por último, em coordenada absoluta (x, y, z)


def achar_pet(criaturas, raio):
    """
    Qual criatura na tela é o monstrinho: a que tem mais monstros a até `raio` sqm. Empate (ex.:
    ninguém colado ainda): a mais perto de onde o pet foi visto por último e depois a mais perto do
    personagem. Antes o empate caía em qualquer uma — às vezes o monstro colado em VOCÊ virava "o pet".
    Devolve (centro, quantos colados).
    """
    pos = POS.atual()
    lembrado = None
    if PET_ABS[0] and pos and PET_ABS[0][2] == pos[2]:
        lembrado = (PET_ABS[0][0] - pos[0], PET_ABS[0][1] - pos[1])

    def vizinhos(c):
        return sum(1 for o in criaturas if o != c and cheb(o, c) <= raio)

    # O pet está no POKESTOP: não anda sozinho. Se tem criatura onde ele estava (até 1 sqm), é ele —
    # antes, a cada leitura uma criatura diferente virava "o pet" e o personagem pulava de um canto
    # da box para o canto oposto ATRAVESSANDO os monstros (magia em área: morreu).
    # (só mantém enquanto ele continua entre os mais cercados: se a box se forma claramente em volta de
    # outra criatura, a memória estava errada e troca)
    if lembrado is not None:
        perto = [c for c in criaturas if cheb(c, lembrado) <= 1]
        if perto:
            centro = min(perto, key=lambda c: (cheb(c, lembrado), -vizinhos(c)))
            if vizinhos(centro) >= max(vizinhos(c) for c in criaturas) - 1:
                return centro, vizinhos(centro)

    centro = max(criaturas, key=lambda c: (vizinhos(c), -cheb(c, lembrado) if lembrado else 0,
                                           -(c[0] ** 2 + c[1] ** 2)))
    n = vizinhos(centro)
    if pos and n >= 1:
        PET_ABS[0] = (pos[0] + centro[0], pos[1] + centro[1], pos[2])
    return centro, n


def colados_em_mim(criaturas, centro):
    """Monstros (não o pet) a 1 sqm do personagem: estão batendo em VOCÊ, não vão para a box."""
    return [c for c in criaturas if c != centro and cheb(c, (0, 0)) <= 1]


AMEACA_SQM = 2  # monstro FORA da box a até isso de você está vindo para você


def ameacas(criaturas, centro):
    """
    Perigo imediato: monstro colado em você (1 sqm) OU a até AMEACA_SQM de você sem estar colado no
    pet (não está brigando com ele: está vindo para VOCÊ). Provas da caixa-preta 07/11 22:07 e 22:10:
    o monstro estava a 2 sqm, fora da box, quando o bot conferiu antes do revive (só olhava 1 sqm);
    meio segundo depois chegou a 1 sqm e bateu (−21% cada).
    """
    ctl = controlados(criaturas)  # silenciado/stunado pelo combo não ataca: não é ameaça
    return [c for c in criaturas if c != centro and c != (0, 0) and c not in ctl
            and (cheb(c, (0, 0)) <= 1 or (cheb(c, (0, 0)) <= AMEACA_SQM
                                          and (centro is None or cheb(c, centro) > 1)))]


def lugar_seguro(criaturas, centro):
    """
    Sqm (relativo ao personagem, até 2 passos) longe dos monstros: o mais longe deles (2+ sqm),
    fora da box do pet e, entre esses, o mais perto do canto da box (BOX_DIAGONAL_SQM na diagonal).
    None se nenhum lugar é melhor que onde está.
    """
    monstros = [c for c in criaturas if c != centro]
    k = int(config.BOX_DIAGONAL_SQM)
    pos = POS.atual()

    def folga(d):
        return min([cheb(d, m) for m in monstros] or [9])

    opcoes = []
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            d = (dx, dy)
            if d == (0, 0) or d in criaturas or cheb(d, centro) < 2:
                continue
            if pos and MAPA.esta_bloqueado((pos[0] + dx, pos[1] + dy, pos[2])):
                continue
            diagonal = abs(d[0] - centro[0]) == abs(d[1] - centro[1])
            opcoes.append((min(folga(d), 3), -abs(cheb(d, centro) - k), diagonal, -cheb(d, (0, 0)), d))
    if not opcoes:
        return None
    melhor = max(opcoes)
    return melhor[-1] if melhor[0] > min(folga((0, 0)), 3) else None


def sair_de_perto(sct, criaturas=None, centro=None):
    """
    Monstro colado no personagem: anda para um sqm longe deles. Colado, você apanha — e no revive
    (o pet volta pra ball ~1 s) os monstros batem só em você. Retorna True se andou.
    """
    if criaturas is None:
        criaturas = list(sqm_ocupados(sct))
        if not criaturas:
            return False
        centro, _ = achar_pet(criaturas, config.BOX_RAIO_SQM)
    colados = colados_em_mim(criaturas, centro)
    if not colados:
        return False
    d = lugar_seguro(criaturas, centro)
    if d is None:
        return False
    print(f"[CaveBot] 🏃 {len(colados)} monstro(s) colado(s) em você: saindo para ({d[0]:+d}, {d[1]:+d} sqm).")
    controle.clicar(PLAYER_TILE_XY[0] + d[0] * SQM_PX, PLAYER_TILE_XY[1] + d[1] * SQM_PX, espalhar=(10, 10))
    controle.esperar(humano.variar(0.45))
    return True


def folga_min():
    """Distância mínima (sqm) entre o personagem e QUALQUER monstro na luta: eles têm magia em área."""
    return max(2, int(getattr(config, "DISTANCIA_MONSTROS", 4)))


def _folga(d, monstros):
    return min([cheb(d, m) for m in monstros] or [99])


def em_perigo(criaturas, centro):
    """Tem monstro (ou o pet, no meio da box) a menos de folga_min() sqm de você?"""
    return _folga((0, 0), [c for c in criaturas if c != (0, 0)]) < folga_min()


def na_diagonal(criaturas, centro):
    """Já está num lugar bom: longe de todos (folga_min) e na diagonal da box (ou pelo menos longe)."""
    k = int(config.BOX_DIAGONAL_SQM)
    rx, ry = -centro[0], -centro[1]  # onde o personagem está em relação ao pet
    return abs(rx) == abs(ry) and abs(rx) >= k and not em_perigo(criaturas, centro)


CANTOS_RUINS = set()  # cantos (coordenada do mapa) onde o personagem não conseguiu chegar nesta luta
MAX_PASSOS_CANTO = 10


def passos_ate(destino, criaturas, pos):
    """
    Quantos passos (8 direções) até `destino` (relativo ao personagem), desviando das criaturas
    (monstros e pet trancam o sqm) e das paredes conhecidas. None = não tem caminho: o canto pode
    estar livre mas a box/parede fecha a passagem (o personagem ficava preso tentando ir).
    """
    ocupado = set(criaturas)
    # não atravessa a box: sqm colado em monstro/pet é proibido no caminho (só o próprio destino vale)
    perto_deles = {(c[0] + a, c[1] + b) for c in criaturas for a in (-1, 0, 1) for b in (-1, 0, 1)}
    fila, visto = [((0, 0), 0)], {(0, 0)}
    while fila:
        (x, y), n = fila.pop(0)
        if (x, y) == destino:
            return n
        if n >= MAX_PASSOS_CANTO:
            continue
        for ax, ay in VIZINHOS_8:
            v = (x + ax, y + ay)
            if v in visto or abs(v[0]) > 10 or abs(v[1]) > 6 or (v in ocupado and v != destino):
                continue
            if v in perto_deles and v != destino:
                continue
            if pos and MAPA.esta_bloqueado((pos[0] + v[0], pos[1] + v[1], pos[2])):
                continue
            visto.add(v)
            fila.append((v, n + 1))
    return None


def canto_da_box(sct, criaturas, centro):
    """
    O melhor canto DIAGONAL da box (relativo ao personagem): na diagonal do pet a BOX_DIAGONAL_SQM
    (ou +1/+2 se precisar para ficar longe), a 2+ sqm de todo monstro (eles têm ataque em área e
    ataque frontal em linha reta — na diagonal e longe nenhum pega), sem parede conhecida, dentro
    da área clicável da tela. Entre os bons, o mais perto de você. None se nenhum serve.
    """
    k = int(config.BOX_DIAGONAL_SQM)
    monstros = [c for c in criaturas if c != centro]
    pos = POS.atual()
    (dx0, dx1), (dy0, dy1) = limites_clique(sct) if sct is not None else (NAV_VIEW_DX, NAV_VIEW_DY)
    opcoes = []
    for dist in range(k, k + 7):
        for sx in (-1, 1):
            for sy in (-1, 1):
                d = (centro[0] + sx * dist, centro[1] + sy * dist)
                if d in criaturas or not (dx0 <= d[0] <= dx1 and dy0 <= d[1] <= dy1):
                    continue
                if not pet_continua_na_tela(d, centro):  # longe demais: o pet teletransportaria
                    continue
                if pos and MAPA.esta_bloqueado((pos[0] + d[0], pos[1] + d[1], pos[2])):
                    continue
                if pos and (pos[0] + d[0], pos[1] + d[1], pos[2]) in CANTOS_RUINS:
                    continue  # já tentou ir e não chegou (sem caminho)
                if atravessa_a_box(d, centro):
                    continue  # canto do outro lado do pet: o caminho passa pelo meio da box
                passos = passos_ate(d, criaturas, pos)
                if passos is None:
                    continue  # a box/parede fecha o caminho até lá
                folga = _folga(d, criaturas)  # longe de todos (pet incluso: ele está no meio da box)
                # 1º: longe o bastante (magia em área); 2º: menos passos (mesmo lado, sem atravessar);
                # 3º: o mais perto da distância pedida
                # 1º seguro (longe); 2º do lado de onde VEIO (atrás: caminho limpo, não puxa mais bicho);
                # 3º menos passos; 4º perto da distância pedida
                opcoes.append((folga >= folga_min(), lado_de_tras(d, centro) > 0, -passos, -abs(dist - k), d))
    if not opcoes:
        caixa_preta.anotar(f"canto_da_box: nenhum canto (pet {centro}, {len(monstros)} monstros)")
        return None
    melhor = max(opcoes)
    # o porquê da escolha (só na caixa-preta): (seguro, lado de trás, -passos, -diferença, sqm)
    caixa_preta.anotar(f"canto_da_box: pet {centro}, monstros {sorted(monstros)}, "
                       f"melhores opções {sorted(opcoes, reverse=True)[:4]} -> "
                       f"{melhor[-1] if melhor[0] else 'nenhum seguro'}")
    return melhor[-1] if melhor[0] else None


PET_NA_TELA = (8, 4)  # o mapa mostra 21x11 (meia tela 10x5): pet a até 8 x 4 sqm de você, com folga


def pet_continua_na_tela(d, centro):
    """
    Indo para `d` (relativo a você), o pet (`centro`) continua dentro da tela? Se o personagem se
    afasta demais, o pet sai da tela e o jogo TELETRANSPORTA ele para perto de você: a box se desfaz.
    """
    if centro is None:
        return True
    return abs(centro[0] - d[0]) <= PET_NA_TELA[0] and abs(centro[1] - d[1]) <= PET_NA_TELA[1]


def fuga(criaturas, centro=None):
    """
    Sem canto seguro: o sqm alcançável (sem atravessar a box) mais LONGE de todos os monstros,
    sem deixar o pet sair da tela.
    """
    pos = POS.atual()
    atual = _folga((0, 0), criaturas)
    opcoes = []
    for dx in range(-6, 7):
        for dy in range(-4, 5):
            d = (dx, dy)
            if d == (0, 0) or d in criaturas or not pet_continua_na_tela(d, centro):
                continue
            if pos and (pos[0] + d[0], pos[1] + d[1], pos[2]) in CANTOS_RUINS:
                continue  # já tentou e não chegou
            if atravessa_a_box(d, centro):
                continue  # do outro lado do pet: atravessaria a box
            f = _folga(d, criaturas)
            if f <= atual:
                continue
            passos = passos_ate(d, criaturas, pos)
            if passos is not None:
                opcoes.append((min(f, folga_min()), centro is not None and lado_de_tras(d, centro) > 0, -passos, d))
    return max(opcoes)[-1] if opcoes else None


CORRIDAS = [0]  # vezes que o personagem já correu da box NESTA luta
_avisou_pet = [0.0]


EMERGENCIAS = [0]   # corridas EXTRAS desta luta (monstro colado em você depois do limite de corridas)
EMERGENCIAS_MAX = 2


def ler_pet_pct(sct):
    """% de vida do pet agora (None = não dá para ler)."""
    if sct is None:
        return None
    barra = carregar_calibracao().get("poke_hp")
    return anotar_pet(ler_barra(sct, barra)) if barra else None


def pet_precisa_de_ajuda(sct, emergencia=False):
    """
    Pet morto (barra vazia) ou com menos de BOX_HP_SOLTAR %: a prioridade é o revive/combo, não
    posicionar o personagem. Antes ele corria para a diagonal com o pet morto e os monstros vinham
    todos para cima de você.
    EXCEÇÃO (`emergencia`: monstro COLADO em você): com o pet VIVO, mesmo fraco, você sai de perto.
    Provas da caixa-preta (20:48): pet com 27–57% → "não corro" → monstro a 1 sqm → revive → você
    foi de 100% a 11%. Sobreviver vem antes do pet. Pet MORTO continua: revive primeiro.
    """
    pct = ler_pet_pct(sct)
    if pct is None or time.time() - controle.ultimo_revive < 2:
        return False  # não dá para ler / acabou de reviver (Back!/Go!)
    if emergencia and pct > 3:
        if pct < config.BOX_HP_SOLTAR:
            print(f"[Perigo] 🚨 Monstro colado/vindo em você: saio de perto mesmo com o pet com {pct:.0f}%.")
        return False
    if pct <= 3 or pct < config.BOX_HP_SOLTAR:
        if time.time() - _avisou_pet[0] > 5:
            _avisou_pet[0] = time.time()
            print(f"[CaveBot] ⚠️ Pet {'caído' if pct <= 3 else f'com {pct:.0f}%'}: não corro agora (revive/combo primeiro).")
        return True
    return False


def ir_para_diagonal(sct, criaturas=None, centro=None, motivo="", bloquear=True):
    """
    `bloquear`: True = espera chegar antes de devolver (padrão); "auto" = só espera se houver perigo
    para você (`ameacas`). Sem perigo, clica e devolve NA HORA: a luta continua (box/combo) enquanto
    você anda — 08/11: esperar chegar atrasava o 1º combo 6,8 s em média e o pet apanhava sem soltar
    skill. Enquanto essa caminhada não termina (`ainda_andando`), ninguém escolhe outro canto.

    Põe o personagem num canto diagonal da box, longe dos monstros. Se nenhum canto serve
    (tudo ocupado/fora da tela), ao menos sai de perto de quem está colado. Retorna True se andou.
    Só CORRIDAS_POR_BOX vezes por luta (padrão 2): depois disso fica parado até a luta acabar —
    MENOS com monstro COLADO em você (perigo imediato): até EMERGENCIAS_MAX corridas extras.
    """
    limite = int(getattr(config, "CORRIDAS_POR_BOX", 2))
    if CORRIDAS[0] >= limite and EMERGENCIAS[0] >= EMERGENCIAS_MAX:
        return False
    if criaturas is None:
        criaturas = list(sqm_ocupados(sct))
        if not criaturas:
            return False
        centro, _ = achar_pet(criaturas, 1)
    emergencia = bool(ameacas(criaturas, centro))  # colado ou vindo (2 sqm, fora da box): o próximo golpe é em você
    if CORRIDAS[0] >= limite and not emergencia:
        return False
    if pet_precisa_de_ajuda(sct, emergencia):
        return False  # pet morto ou com pouca vida: revive/combo primeiro (correr agora quase matou você)
    if na_diagonal(criaturas, centro):
        return False
    if bloquear == "auto":
        bloquear = emergencia
    caixa_preta.estado("POSITIONING")
    d = canto_da_box(sct, criaturas, centro)
    if CORRIDAS[0] >= limite:
        EMERGENCIAS[0] += 1  # passou do limite: só por perigo imediato
        print(f"[Perigo] 🚨 Monstro colado/vindo em você depois de {limite} corridas: corrida extra "
              f"{EMERGENCIAS[0]}/{EMERGENCIAS_MAX}.")
    else:
        CORRIDAS[0] += 1  # vai andar (canto ou fuga): conta 1 corrida desta box
    if d is None or d == (0, 0):
        d = fuga(criaturas, centro)
        if d is None:
            return False
        print(f"[CaveBot] 🏃 Sem canto seguro: me afastando dos monstros ({d[0]:+d}, {d[1]:+d} sqm){motivo}")
        antes = POS.atual()
        controle.clicar(PLAYER_TILE_XY[0] + d[0] * SQM_PX, PLAYER_TILE_XY[1] + d[1] * SQM_PX, espalhar=(10, 10))
        if bloquear:
            esperar_chegar(antes, d)  # decide de novo só parado (com a posição certa)
        else:
            iniciar_caminhada(antes, d)  # sem perigo: a luta segue enquanto anda
        return True
    rel = (d[0] - centro[0], d[1] - centro[1])
    print(f"[CaveBot] 🚶 Indo para a diagonal da box ({rel[0]:+d}, {rel[1]:+d} do pet){motivo}")
    antes = POS.atual()
    controle.clicar(PLAYER_TILE_XY[0] + d[0] * SQM_PX, PLAYER_TILE_XY[1] + d[1] * SQM_PX, espalhar=(10, 10))
    if not bloquear:
        iniciar_caminhada(antes, d)  # sem perigo: a luta segue enquanto anda ("sem caminho" é visto depois)
        return True
    chegou = esperar_chegar(antes, d)  # sem coordenada: espera pelo tempo
    if antes and not chegou:
        # não saiu do lugar: o jogo não acha caminho até lá. Esse canto não vale mais nesta luta
        CANTOS_RUINS.add((antes[0] + d[0], antes[1] + d[1], antes[2]))
        print(f"[CaveBot] ⚠️ Não consegui ir para ({rel[0]:+d}, {rel[1]:+d} do pet): sem caminho. Vou tentar outro canto.")
        d2 = canto_da_box(sct, criaturas, centro) or fuga(criaturas, centro)
        if d2 is None or d2 == (0, 0):
            return False
        rel = (d2[0] - centro[0], d2[1] - centro[1])
        print(f"[CaveBot] 🚶 Indo para a diagonal da box ({rel[0]:+d}, {rel[1]:+d} do pet)")
        controle.clicar(PLAYER_TILE_XY[0] + d2[0] * SQM_PX, PLAYER_TILE_XY[1] + d2[1] * SQM_PX, espalhar=(10, 10))
        if not esperar_chegar(antes, d2):
            CANTOS_RUINS.add((antes[0] + d2[0], antes[1] + d2[1], antes[2]))
    return True


def sair_da_ameaca(sct, quando, tentativas=2, cri=None):
    """
    Monstro colado em você ou vindo para você (`ameacas`) com o pet VIVO → sai para longe (o mais
    longe possível: `fuga`; reserva: `lugar_seguro`), sem atravessar a box, e espera chegar.
    Pet morto → não anda (revive é urgente). Sem limite de corridas: é o golpe certo.
    `quando` vai no log ("antes do revive", "no combo"). Retorna True se ficou livre (ou já estava).
    """
    for _ in range(tentativas):
        if cri is None:
            cri = list(sqm_ocupados(sct))
        if not cri:
            return True
        c, _ = achar_pet(cri, 1)
        perigo = ameacas(cri, c)
        if not perigo:
            return True
        pct = ler_pet_pct(sct)
        if pct is not None and pct <= 3:
            print(f"[Perigo] Pet caído: não saio ({quando}) — revive primeiro.")
            return False
        d = fuga(cri, c) or lugar_seguro(cri, c)
        if d is None or d == (0, 0) or atravessa_a_box(d, c):
            print(f"[Perigo] ⚠️ {len(perigo)} monstro(s) vindo em você ({quando}) e nenhum lugar livre para sair.")
            caixa_preta.anotar(f"{quando}: ameaças {perigo}, pet {c}, criaturas {sorted(cri)}, sem saída")
            return False
        caixa_preta.estado("DODGING")
        ANDANDO[0] = None  # fuga de perigo substitui a caminhada sem travar
        caixa_preta.anotar(f"{quando}: ameaças {perigo}, pet {c}, criaturas {sorted(cri)} -> saio para {d}")
        dist = min(cheb(m, (0, 0)) for m in perigo)
        print(f"[Perigo] 🚨 {len(perigo)} monstro(s) {'colado(s)' if dist <= 1 else f'vindo (a {dist} sqm)'} "
              f"em você {quando}: saindo para ({d[0]:+d}, {d[1]:+d}).")
        antes = POS.atual()
        controle.clicar(PLAYER_TILE_XY[0] + d[0] * SQM_PX, PLAYER_TILE_XY[1] + d[1] * SQM_PX, espalhar=(10, 10))
        esperar_chegar(antes, d)
        cri = None  # depois de andar: lê a tela de novo
    return False


def afastar_antes_do_revive(sct, tentativas=2):
    """
    No revive o pet volta pra ball (~1 s) e o monstro perto de você bate em VOCÊ. Provas da
    caixa-preta (07/11): TODOS os 5 danos do dia foram no revive — 20:44, 20:48, 21:01 com monstro
    colado; 22:07 e 22:10 com monstro a 2 sqm fora da box, vindo. Sai de perto ANTES de reviver.
    """
    return sair_da_ameaca(sct, "antes do revive", tentativas)


REVIVE_ADIADOS = [0]   # revives adiados NESTA luta por falta de distância (zera em _combater)
REVIVE_ADIAR_MAX = 2
REVIVE_FOLGA_SOLTO = 6  # monstro SOLTO (não colado no pet) acerta de longe no revive (Bone Rush a 4 sqm)


def situacao_revive(d, cri, c):
    """
    Distâncias de `d` até os monstros da BOX (a até BOX_RAIO_SQM do pet: brigando com ele) e até os
    SOLTOS (fora da box, como o Marowak do Bone Rush das 22:26, a 4 sqm do pet).
    Antes "box" era só colado no pet (1 sqm): monstro da box a 2–3 sqm do pet virava "solto" e o bot
    andava 1 sqm e ADIAVA o revive em quase toda luta (08/11: 20 afastamentos e 8 adiamentos em 8 lutas,
    o pet morreu 3x esperando), sem perigo nenhum.
    """
    raio = max(1, int(getattr(config, "BOX_RAIO_SQM", 3)))
    box = [m for m in cri if m != c and m != d and c is not None and cheb(m, c) <= raio]
    soltos = [m for m in cri if m != c and m != d and m not in box]
    ctl = controlados(cri)
    # da box só conta quem NÃO tomou o silence/stun (quem chegou depois do combo ainda ataca)
    return _folga(d, [m for m in box if m not in ctl]), _folga(d, soltos)


COMBO_FIM = [0.0]  # quando o último combo terminou de sair
CONTROLE_BOX = controle_box.JanelaControle(margem=float(getattr(config, "CONTROLE_MARGEM_S", 0.5)))


def foto_da_box(sct):
    """(posição, [sqm relativos da box]) agora — tirada ANTES do combo, com as barrinhas ainda visíveis."""
    cri = list(sqm_ocupados(sct))
    pos = POS.atual()
    if not cri:
        return pos, []
    c, _ = achar_pet(cri, 1)
    raio = max(1, int(getattr(config, "BOX_RAIO_SQM", 3)))
    return pos, [m for m in cri if m != c and cheb(m, c) <= raio]


def iniciar_controle(sct, foto=None):
    """
    Combo acabou de sair: se o pet tem silence/stun (painel: tempo + tipo, por pokémon), guarda QUEM estava
    na box (posição absoluta). Só esses ficam sem atacar; quem chegar depois ou estiver solto continua perigo.
    `foto` = foto_da_box de ANTES do combo: depois dele as magias (Hydro Pump...) cobrem as barrinhas e a box
    aparecia vazia — 21 de 21 lutas de 08/11 21:39 deram "SILENCE em 0 monstro(s)" e a janela nem valia.
    """
    tipo, dur = controle_box.parametros(config)
    if dur <= 0:
        CONTROLE_BOX.parar()
        return
    pos, box = foto if foto and foto[1] else foto_da_box(sct)
    if not box:
        CONTROLE_BOX.parar()
        return
    alvos = [(pos[0] + m[0], pos[1] + m[1], pos[2]) for m in box] if pos else []
    if CONTROLE_BOX.comecar(time.time(), tipo, dur, alvos, sem_pos=pos is None and bool(box)):
        print(f"[Magia] 🤐 {tipo.upper()} em {len(box)} monstro(s) da box por ~{CONTROLE_BOX.restante(time.time()):.1f}s "
              f"(não contam como perigo; quem chegar depois conta).")


def controlados(cri):
    """Sqm RELATIVOS (da lista `cri`) com monstro silenciado/stunado agora. Stun: confere se continua preso."""
    agora = time.time()
    if not CONTROLE_BOX.ativa(agora):
        return set()
    pos = POS.atual()
    if pos is None:
        return set(cri) if CONTROLE_BOX.sem_pos else set()
    saiu = CONTROLE_BOX.conferir_stun([(pos[0] + m[0], pos[1] + m[1], pos[2]) for m in cri], agora)
    if saiu:
        print(f"[Magia] ⚠️ {saiu} monstro(s) saiu do lugar: o stun não pegou nele — volta a ser perigo.")
    return {m for m in cri if CONTROLE_BOX.controlado((pos[0] + m[0], pos[1] + m[1], pos[2]), agora)}


def em_silencio():
    """
    Logo depois do combo os monstros da box ficam SILENCIADOS/atordoados (Gyarados: silence ~3 s — relato
    do usuário 08/11): não atacam. Nessa janela a box não é perigo e o revive deve sair NA HORA (antes o
    bot corria/adiava: combo→revive levava 5,6 s em média, 6 de 11 com corrida). Monstro SOLTO (fora da
    box) não tomou o combo: continua sendo perigo.
    """
    return CONTROLE_BOX.ativa(time.time())


def revive_seguro_em(d, cri, c, silencio=False):
    dbox, dsolto = situacao_revive(d, cri, c)
    # silencio: a box controlada já saiu da conta em situacao_revive (só sobra quem chegou depois)
    return dbox >= folga_min() and dsolto >= REVIVE_FOLGA_SOLTO


def lugar_para_revive(cri, c, silencio=False):
    """
    O melhor sqm para esperar o revive: seguro (box ≥ folga_min, soltos ≥ REVIVE_FOLGA_SOLTO) e, entre
    os seguros, o de menos passos; sem nenhum seguro, o que mais se afasta dos soltos e da box.
    Só sqm alcançável sem passar colado em criatura, sem atravessar a box e com o pet na tela.
    """
    pos = POS.atual()
    atual = situacao_revive((0, 0), cri, c)
    nota_atual = (min(atual[1], REVIVE_FOLGA_SOLTO), min(atual[0], folga_min()))
    opcoes = []
    for dx in range(-6, 7):
        for dy in range(-4, 5):
            d = (dx, dy)
            if d == (0, 0) or d in cri or not pet_continua_na_tela(d, c) or atravessa_a_box(d, c):
                continue
            if pos and ((pos[0] + dx, pos[1] + dy, pos[2]) in CANTOS_RUINS
                        or MAPA.esta_bloqueado((pos[0] + dx, pos[1] + dy, pos[2]))):
                continue
            dbox, dsolto = situacao_revive(d, cri, c)
            nota = (min(dsolto, REVIVE_FOLGA_SOLTO), min(dbox, folga_min()))
            if nota <= nota_atual:
                continue  # não melhora nada
            passos = passos_ate(d, cri, pos)
            if passos is not None:
                opcoes.append((revive_seguro_em(d, cri, c, silencio), nota, -passos, d))
    return max(opcoes)[-1] if opcoes else None


def preparar_revive(sct, tentativas=2, silencio=None):
    """
    No revive o pet some ~1 s e os monstros acertam VOCÊ — inclusive DE LONGE. Prova (07/11 22:26,
    quadros da caixa-preta): um Marowak SOLTO (vida cheia, fora da box) a 4 sqm soltou BONE RUSH no
    "Gyarados, Back!" e tirou 668 de HP (−66%). Antes de reviver, PARADO e longe: box a ≥ folga_min
    (DISTANCIA_MONSTROS) e soltos a ≥ REVIVE_FOLGA_SOLTO. Não está → anda (`lugar_para_revive`) e espera
    chegar. Ainda não dá → ADIA o revive (o solto entra na box enquanto o pet está lá), no máx.
    REVIVE_ADIAR_MAX vezes por luta; depois revive assim mesmo. Pet morto → revive já.
    Retorna True se pode reviver agora.
    """
    if silencio is None:
        silencio = em_silencio()
    if not silencio:
        terminar_caminhada()  # revive só com você PARADO (caminhada sem travar ainda em andamento)
    situacao = None
    for vez in range(tentativas + 1):  # a última volta só confere (depois de andar)
        cri = list(sqm_ocupados(sct))
        if not cri:
            return True
        c, _ = achar_pet(cri, 1)
        if not [m for m in cri if m != c and m != (0, 0)]:
            return True
        pct = ler_pet_pct(sct)
        if pct is not None and pct <= 3:
            return True  # pet caído: revive é urgente
        if revive_seguro_em((0, 0), cri, c, silencio):
            return True
        situacao = situacao_revive((0, 0), cri, c)
        if vez == tentativas:
            break
        d = lugar_para_revive(cri, c, silencio)
        if d is None:
            caixa_preta.anotar(f"revive: box {situacao[0]} / solto {situacao[1]} sqm, sem lugar melhor "
                               f"(criaturas {sorted(cri)}, pet {c})")
            break
        caixa_preta.estado("DODGING")
        ANDANDO[0] = None  # fuga de perigo substitui a caminhada sem travar
        caixa_preta.anotar(f"revive: box {situacao[0]} / solto {situacao[1]} sqm, pet {c}, criaturas {sorted(cri)} -> {d}")
        print(f"[Perigo] 🛡️ Antes do revive: monstro da box a {situacao[0]} e solto a {situacao[1]} sqm de você — "
              f"me afasto para ({d[0]:+d}, {d[1]:+d}) (no revive eles acertam de longe).")
        antes = POS.atual()
        controle.clicar(PLAYER_TILE_XY[0] + d[0] * SQM_PX, PLAYER_TILE_XY[1] + d[1] * SQM_PX, espalhar=(10, 10))
        esperar_chegar(antes, d)
    if situacao is None:
        return True
    pct = ler_pet_pct(sct)
    if pct is not None and pct < config.BOX_HP_SOLTAR:
        # pet fraco: adiar o revive deixava ele MORRER (08/11, 3x) e aí o revive de emergência saía
        # na pior hora. Já me afastei o que deu: revive agora.
        print(f"[Perigo] Pet com {pct:.0f}%: não adio o revive (box {situacao[0]}, solto {situacao[1]} sqm).")
        return True
    if REVIVE_ADIADOS[0] < REVIVE_ADIAR_MAX:
        REVIVE_ADIADOS[0] += 1
        print(f"[Perigo] ⏳ Monstro perto demais para o revive (box {situacao[0]}, solto {situacao[1]} sqm): "
              f"adio o revive ({REVIVE_ADIADOS[0]}/{REVIVE_ADIAR_MAX}).")
        controle.esperar(0.5)
        return False
    print(f"[Perigo] ⚠️ Ainda perto (box {situacao[0]}, solto {situacao[1]} sqm), mas já adiei "
          f"{REVIVE_ADIAR_MAX}x: revive assim mesmo.")
    return True


ULTIMA_VIGIA = [0.0]
VIGIA_INTERVALO_S = 0.3
VIGIA_SAIDAS = [0]   # saídas da vigia do combo NESTA luta (zera em _combater)
VIGIA_MAX = 4        # monstro que persegue sem parar: não fica correndo para sempre (e a box não se desfaz)


def vigiar_no_combo(sct):
    """
    Chamado pelo combo (modos.esperar_combo) a cada ~0,15 s: antes, nos ~2,5 s do combo o bot não
    olhava em volta (22:10: o monstro veio de 3 → 2 → 1 sqm durante o combo). Ameaça → sai de perto
    (as magias do pet continuam saindo enquanto você anda).
    """
    if not fugir_da_box() or time.time() - ULTIMA_VIGIA[0] < VIGIA_INTERVALO_S:
        return
    ULTIMA_VIGIA[0] = time.time()
    cri = list(sqm_ocupados(sct))
    if not cri:
        return
    c, _ = achar_pet(cri, 1)
    if ameacas(cri, c):
        if VIGIA_SAIDAS[0] >= VIGIA_MAX:
            if VIGIA_SAIDAS[0] == VIGIA_MAX:
                VIGIA_SAIDAS[0] += 1
                print(f"[Perigo] ⚠️ Monstro continua vindo em você: já saí {VIGIA_MAX}x nesta luta, fico parado.")
            return
        VIGIA_SAIDAS[0] += 1
        estado = caixa_preta.estado_do_bot()
        try:
            sair_da_ameaca(sct, "no combo", tentativas=1, cri=cri)
        except controle.ParadaSolicitada:
            raise
        except Exception as e:  # a vigia nunca derruba o combo
            print(f"[Perigo] erro na vigia do combo (ignorado): {e!r}")
        caixa_preta.estado(estado)


def atravessa_a_box(d, centro):
    """
    Ir para `d` (relativo a você) é cruzar para o lado OPOSTO do pet? (você está num quadrante em
    volta dele e `d` fica no quadrante contrário: o caminho passa pelo meio da box). O jogo escolhe o
    caminho sozinho, então isso nunca é seguro. Log de 07/11: 21:39:10 (+4,-4) e 1 s depois (-4,+4).
    """
    if centro is None:
        return False
    rx, ry = -centro[0], -centro[1]          # onde você está em relação ao pet
    nx, ny = d[0] - centro[0], d[1] - centro[1]  # onde vai ficar em relação ao pet

    def sinal(v):
        return (v > 0) - (v < 0)
    return bool(rx and ry and nx and ny and sinal(nx) == -sinal(rx) and sinal(ny) == -sinal(ry))


ANDANDO = [None]  # caminhada sem travar em andamento


def iniciar_caminhada(antes, d):
    agora = time.time()
    n = max(abs(d[0]), abs(d[1]))
    ANDANDO[0] = {"antes": antes, "d": d, "inicio": agora, "limite": agora + min(4.0, 1.0 + 0.4 * n),
                  "ultima": antes[:2] if antes else None, "mudou": agora, "saiu": False}


def ainda_andando():
    """
    A caminhada sem travar ainda está acontecendo? (chegou, parou 0,6 s depois de andar, passou do
    tempo, ou nem saiu do lugar em 1 s → acabou). Não saiu do lugar = sem caminho: o canto vai para
    CANTOS_RUINS, como no jeito que espera.
    """
    a = ANDANDO[0]
    if a is None:
        return False
    agora = time.time()
    antes = a["antes"]
    if agora >= a["limite"] or not antes:
        ANDANDO[0] = None
        return False
    p = POS.atual()
    if not p:
        return True
    p = p[:2]
    if p == (antes[0] + a["d"][0], antes[1] + a["d"][1]):
        ANDANDO[0] = None
        return False
    if p != a["ultima"]:
        a["ultima"], a["mudou"] = p, agora
        a["saiu"] = a["saiu"] or p != antes[:2]
        return True
    if a["saiu"] and agora - a["mudou"] >= 0.6:
        ANDANDO[0] = None  # andou e parou antes (caminho mudou / sqm ocupado)
        return False
    if not a["saiu"] and agora - a["inicio"] >= 1.0:
        CANTOS_RUINS.add((antes[0] + a["d"][0], antes[1] + a["d"][1], antes[2]))
        print(f"[CaveBot] ⚠️ Não saí do lugar indo para ({a['d'][0]:+d}, {a['d'][1]:+d}): sem caminho.")
        ANDANDO[0] = None
        return False
    return True


def terminar_caminhada(max_s=3.0):
    """Espera a caminhada sem travar acabar (o revive só sai com você PARADO)."""
    fim = time.time() + max_s
    while ainda_andando() and time.time() < fim:
        controle.esperar(0.1)


def esperar_chegar(antes, d, espera_inicio=1.0):
    """
    Depois do clique: espera o personagem CHEGAR (ou parar) antes de qualquer nova decisão.
    Antes esperava só 0,5 s e decidia de novo andando, com a posição atrasada: em 11 de 16 lutas
    (07/11 21:37) as 2 corridas iam embora no 1º segundo, às vezes para o canto oposto.
    Devolve True se saiu do lugar. Sem coordenada: espera pelo tempo (~0,3 s por sqm).
    """
    n = max(abs(d[0]), abs(d[1]))
    limite = time.time() + min(4.0, 1.0 + 0.4 * n)
    if not antes:
        controle.esperar(humano.variar(min(2.5, 0.3 * n + 0.3)))
        return True
    alvo = (antes[0] + d[0], antes[1] + d[1])
    inicio = time.time()
    ultima, parado_desde, saiu = antes[:2], None, False
    while time.time() < limite:
        controle.esperar(0.1)
        agora = POS.atual()
        if not agora:
            continue
        p = agora[:2]
        if p != antes[:2]:
            saiu = True
        if p == alvo:
            controle.esperar(0.15)  # termina o passo
            return True
        if p != ultima:
            ultima, parado_desde = p, None
        elif saiu:
            parado_desde = parado_desde or time.time()
            if time.time() - parado_desde >= 0.6:
                return True  # andou e parou antes (caminho mudou / sqm ocupado)
        elif time.time() - inicio >= espera_inicio:
            return False  # nem saiu do lugar: o jogo não achou caminho
    return saiu


def _andou(antes, espera=1.0):
    """O personagem saiu de `antes` (coordenada) em até `espera` s?"""
    fim = time.time() + espera
    while True:
        agora = POS.atual()
        if agora and agora[:2] != antes[:2]:
            return True
        if time.time() >= fim:
            return False
        controle.esperar(0.1)


def pet_cercado(criaturas, centro):
    """
    O pet está fechado na box: não tem sqm livre em volta (monstro, você ou parede conhecida) —
    aí o order NÃO funciona (ele não tem caminho para andar). Monstros empilhados escondem
    barrinhas, então 6+ monstros visíveis colados nele também contam como cercado.
    """
    pos = POS.atual()
    livres = colados = 0
    for dx, dy in VIZINHOS_8:
        v = (centro[0] + dx, centro[1] + dy)
        if v in criaturas:
            colados += 1
        elif v == (0, 0):
            continue  # o personagem também tranca o sqm
        elif pos and MAPA.esta_bloqueado((pos[0] + v[0], pos[1] + v[1], pos[2])):
            continue
        else:
            livres += 1
    return livres == 0 or colados >= 6


class _SemLure:
    """Para andar sem parar por causa do lure (ex.: puxando o pet pela tela)."""

    def checar(self):
        return 0, None, None


MEIA_TELA = (10, 5)  # o mapa mostra 21 x 11 sqm: o personagem no meio


def puxar_pet_pela_tela(sct, pet_rel, motivo):
    """
    Pet preso (cercado na box, sem caminho): order não adianta. O personagem anda até o pet sair
    da tela — aí o jogo teletransporta o pet para perto de você. Anda para cima/baixo (6+ sqm) ou
    para os lados (11+ sqm), o que tiver o caminho mais curto. Retorna True se o pet saiu da tela.
    """
    pos = POS.atual()
    if pos is None or not controle.rota_ligada():
        return False  # rota desligada: o mouse é seu
    pet = (pos[0] + pet_rel[0], pos[1] + pet_rel[1], pos[2])
    opcoes = []
    for eixo, lado in ((1, -1), (1, 1), (0, -1), (0, 1)):
        alvo = list(pos)
        alvo[eixo] = pet[eixo] + lado * (MEIA_TELA[eixo] + 2)
        alvo = tuple(alvo)
        if MAPA.esta_bloqueado(alvo):
            continue
        cam = MAPA.caminho(pos, alvo)
        custo = len(cam) if cam else distancia(pos, alvo) + 10  # caminho desconhecido custa mais
        opcoes.append((custo, alvo))
    if not opcoes:
        return False
    alvo = min(opcoes)[1]
    print(f"[CaveBot] 🧲 Pet preso na box ({motivo}): andando até ele sair da tela para ele vir até você "
          f"(indo para {alvo[0]}, {alvo[1]}).")
    andar_ate_coord(sct, {"pos": alvo, "lure": False}, "pet", _SemLure())
    agora = POS.atual()
    if agora is None:
        return False
    fora = abs(pet[0] - agora[0]) > MEIA_TELA[0] or abs(pet[1] - agora[1]) > MEIA_TELA[1]
    if fora:
        controle.esperar(humano.variar(1.0))  # o pet aparece do seu lado
        print("[CaveBot] 🧲 Pet saiu da tela: ele vem para perto de você.")
    else:
        print("[CaveBot] ⚠️ Não consegui tirar o pet da tela andando.")
    return fora


def sair_da_box(sct):
    """
    Depois do pokestop: o personagem vai para um canto DIAGONAL da box, longe dos monstros (eles
    têm ataque em área e frontal). Assim a box fecha inteira em volta do pet e, se o pet voltar
    pra ball (revive), ele sai do seu lado ainda perto dos monstros.
    """
    if not fugir_da_box():
        return  # modo normal rápido (ou opção desligada): fica onde está
    ocupados = list(sqm_ocupados(sct))
    if not ocupados:
        return
    centro, _ = achar_pet(ocupados, 1)  # o pet: quem tem mais monstros colados
    ir_para_diagonal(sct, ocupados, centro, bloquear="auto")  # sem perigo: box/combo seguem enquanto anda


def box_ja_pronta(sct):
    """
    A box já está feita em volta do pet (mesma conta de `esperar_agrupar`: todos os inimigos a até
    BOX_RAIO_SQM do pet, ou bolo grande sem ninguém longe com metade+ visível)? Aí o 1º combo vem ANTES de
    sair da box (pedido do usuário 09/11).
    """
    try:
        qtd = len(inimigos(sct))
        criaturas = list(sqm_ocupados(sct))
    except Exception:
        return False
    if qtd == 0 or len(criaturas) < 2:
        return False
    raio = config.BOX_RAIO_SQM
    centro, _ = achar_pet(criaturas, 1)
    perto = sum(1 for o in criaturas if o != centro and cheb(o, centro) <= raio)
    longe = len(criaturas) - 1 - perto
    precisa = min(qtd, 8 if raio == 1 else 24)
    return perto >= precisa or (precisa >= 3 and longe == 0 and perto >= max(2, precisa // 2))


def unica_e_monstro(sct):
    """
    Só 1 criatura na tela (fora você): é um MONSTRO, não o pet? Provas: barra ROSA/MAGENTA (o pet nunca tem
    barra magenta — o shiny aparece assim na tela, print 18:07:35) ou a vida da barrinha muito diferente da
    vida do pet na janela Pokémon (> 25%). Sem prova → False (pode ser o pet: vale a regra antiga).
    """
    try:
        img = capturar(sct, GAME_VIEW)
    except Exception:
        return False  # sem tela (teste) / erro de captura: sem prova
    barras = []
    for bx, by, preench, rosa in encontrar_barras_criaturas(img, (GAME_VIEW["left"], GAME_VIEW["top"])):
        rel = (round((bx + BARRA_LARGURA // 2 - PLAYER_TILE_XY[0]) / SQM_PX), round((by + 26 - PLAYER_TILE_XY[1]) / SQM_PX))
        if rel != (0, 0):
            barras.append((preench, rosa))
    if len(barras) != 1:
        return False
    preench, rosa = barras[0]
    if rosa:
        return True
    pct = ler_pet_pct(sct)
    return pct is not None and pct > 3 and abs(preench / 25 * 100 - pct) > 25


def esperar_agrupar(sct):
    """
    Segura a magia até os monstros chegarem perto (até MAGIA_RAIO_SQM sqm).

    Compara quantas criaturas estão perto na tela com quantos inimigos há na Battle
    (+1 se o seu monstrinho estiver junto). Também libera se nenhuma criatura
    visível estiver longe. Se demorar mais que MAGIA_ESPERA_MAX, libera mesmo assim
    (por exemplo, se dois monstros ficarem um em cima do outro e esconderem a barra).
    """
    caixa_preta.estado("WAITING_BOX")
    inicio = time.time()
    ultimo_texto = None
    sumidos_desde = None  # desde quando os monstros da Battle não aparecem na tela (fugiram)
    so_monstro_desde = None  # desde quando a única criatura na tela é o monstro (pet tapado)
    movidas, ultima_movida = 0, 0.0
    fugas, ultima_fuga = 0, 0.0  # vezes que o personagem saiu de perto de monstro colado nele
    perto, longe, hp_pet = 0, 0, None
    barra_pet = carregar_calibracao().get("poke_hp")

    def continuar():
        t = time.time() - inicio
        if t < MAGIA_ESPERA_MAX:
            return True
        aguenta = hp_pet is None or hp_pet >= config.BOX_HP_SOLTAR
        # passou do tempo: ninguém no alcance = combo seria no vazio -> espera mais;
        # ainda tem monstro chegando e o monstrinho AGUENTA -> espera a box ficar completa
        return t < 3 * MAGIA_ESPERA_MAX and (perto == 0 or (longe > 0 and aguenta))

    while continuar():
        caixa_preta.estado("WAITING_BOX")
        qtd_inimigos = len(inimigos(sct))
        checar_catch(sct)
        if qtd_inimigos == 0:
            return False  # todo mundo morreu enquanto esperava
        # A box é em volta do MONSTRINHO (não do personagem): o centro é a criatura que tem
        # mais vizinhos colados (o monstrinho parado no pokestop, com os monstros em volta).
        raio = config.BOX_RAIO_SQM
        criaturas = list(sqm_ocupados(sct))
        # Battle diz que tem monstro, mas na tela só tem o pet (ou ninguém): fugiram (monstro com
        # pouca vida foge) ou estão fora da tela. Antes esperava 2 x 14 s parado (19:40).
        if len(criaturas) == 1 and unica_e_monstro(sct):
            # a única criatura na tela é o MONSTRO (o pet está escondido): não fugiram. 09/11 18:07: shiny
            # colado em você, barra do pet tapada por "ICE BEAM!/MISS!" → 4 lutas abertas e largadas em 20 s.
            # O pet está brigando com ele (só não aparece): depois de 1 s assim, solta o combo.
            sumidos_desde = None
            so_monstro_desde = so_monstro_desde or time.time()
            if time.time() - so_monstro_desde >= 1.0:
                print("[Magia] Só o monstro aparece na tela (o pet está tapado por efeito/texto): soltando o combo.")
                return True
            controle.esperar(0.1)
            continue
        so_monstro_desde = None
        if len(criaturas) <= 1:
            sumidos_desde = sumidos_desde or time.time()
            if time.time() - sumidos_desde >= 3.0:
                print(f"[Magia] Os {qtd_inimigos} monstro(s) da Battle não aparecem na tela (fugiram?): não espero.")
                return "sumiram"
            controle.esperar(0.1)
            continue
        sumidos_desde = None
        # o pet = quem tem mais monstros COLADOS (1 sqm); com o alcance (3-4 sqm) numa box pequena
        # todo mundo empatava e um monstro virava "o pet"
        centro, _ = achar_pet(criaturas, 1)
        perto = sum(1 for o in criaturas if o != centro and cheb(o, centro) <= raio)
        # Monstro colado em VOCÊ (não no pet): ele não vai para a box, fica batendo em você. Sai de
        # perto (ele vem atrás, para o lado da box). Antes o bot achava que ele estava "vindo" e
        # levava o PET na direção dele — ou seja, para cima de você.
        colados = colados_em_mim(criaturas, centro)
        # Monstro chegou perto de você (magia em área): se afasta. Longe, NÃO se mexe (antes trocava de
        # canto a cada leitura e atravessava a box)
        precisa = min(qtd_inimigos, 8 if raio == 1 else 24)
        longe = len(criaturas) - 1 - perto

        # vários monstros no mesmo sqm aparecem como 1: se não tem ninguém longe e a maioria está
        # em volta do monstrinho, a box está feita
        # Só solta quando VÊ os monstros perto. Monstro que o bot não enxerga (barrinha escondida)
        # NÃO conta como perto: antes ele soltava o combo com monstro ainda chegando e errava tudo.
        # Vida do monstrinho: se está caindo e já tem monstro no alcance, solta AGORA (não dá para
        # esperar o resto chegar); se está alta, ele aguenta esperar a box completa.
        hp_pet = anotar_pet(ler_barra(sct, barra_pet)) if barra_pet else None
        if URGENTE[0] and perto >= 1:
            URGENTE[0] = False  # só o 1º combo é "na hora"; depois volta a esperar a box
            print(f"[Magia] Perigo: soltando já com {perto} no alcance.")
            return True
        # (≤3% = pet morto ou voltando para a ball no revive: combo agora seria perdido — 09/11 18:22:58)
        if hp_pet is not None and 3 < hp_pet < config.BOX_HP_SOLTAR and perto >= 1:
            print(f"[Magia] Monstrinho com {hp_pet:.0f}%: soltando já com {perto} no alcance.")
            return True
        visiveis = len(criaturas) - 1  # sem o monstrinho
        # "quase todos" (1 escondido/empilhado) só vale com bolo de verdade: com 1–2 monstros
        # tem que VER cada um no alcance (antes soltava com 0 no alcance = combo no vazio)
        # Bolo grande: os monstros ficam EMPILHADOS no pet e as barrinhas se escondem umas atrás
        # das outras (vê 3–6 de 8). Se ninguém está longe, metade ou mais visível colada já é box feita.
        quase_todos = (precisa >= 3 and longe == 0 and perto >= max(2, precisa // 2)
                       and time.time() - inicio > 1.0)
        if perto >= precisa or quase_todos:
            print(f"[Magia] Box fechada! {perto} monstro(s) a até {raio} sqm do monstrinho.")
            return True

        # Só AGORA (box ainda não pronta) pensa em correr. Antes corria primeiro e soltava o combo depois,
        # com a box já feita em volta do pet (09/11 18:20 Heroi Alfa: "2/3 colados" → 2 corridas → combo;
        # "me afastando" → só depois "Box fechada!"). Pedido do usuário: box pronta = bater a magia direto;
        # o combo silencia a box (SILENCIO_POS_COMBO_S) e o posicionamento vem depois.
        andando = ainda_andando()
        if andando and ameacas(criaturas, centro):
            ANDANDO[0] = None  # apareceu perigo no meio do caminho: decide de novo (esperando chegar)
            andando = False
        if fugir_da_box() and not andando and fugas < 4 and time.time() - ultima_fuga > 1.5 \
                and em_perigo(criaturas, centro):
            fugas += 1
            ultima_fuga = time.time()
            if ir_para_diagonal(sct, criaturas, centro, bloquear="auto"):
                ultima_fuga = time.time()  # conta a partir de quando CHEGOU (não de quando clicou)
                continue

        # Tem monstro vindo e ainda não chegou: em vez de ficar parado, leva o pet um pouco na
        # direção deles (até 2 sqm), para o combo pegar quem já está aqui E quem está chegando.
        longes = [o for o in criaturas if o != centro and cheb(o, centro) > raio
                  and o not in colados]  # nunca leva o pet para cima do personagem
        if (longes and movidas < 2 and time.time() - inicio > 0.8 and time.time() - ultima_movida > 1.5
                and not pet_cercado(criaturas, centro)):  # cercado: o order não tem caminho
            mx = sum(o[0] for o in longes) / len(longes) - centro[0]
            my = sum(o[1] for o in longes) / len(longes) - centro[1]
            dist = max(abs(mx), abs(my))
            if dist <= 6:
                passo = min(2, max(1, int(dist) - raio))
                sx = (mx > 0.4) - (mx < -0.4)
                sy = (my > 0.4) - (my < -0.4)
                alvo = (centro[0] + sx * passo, centro[1] + sy * passo)
                p = POS.atual()
                if p and (sx or sy):
                    # entre os sqm na direção deles, o mais aberto (pet em parede = box não fecha)
                    opcoes = []
                    for ps in sorted({1, passo}):
                        for ex, ey in ((0, 0), (sy, sx), (-sy, -sx)):
                            r = (centro[0] + sx * ps + ex, centro[1] + sy * ps + ey)
                            if r != (0, 0):
                                opcoes.append((p[0] + r[0], p[1] + r[1], p[2]))
                    if opcoes:
                        m = melhor_lugar(opcoes)
                        if abertura(m) < 0:
                            opcoes = []  # tudo encostado em parede conhecida: não mexe o pet
                        else:
                            alvo = (m[0] - p[0], m[1] - p[1])
                    if not opcoes:
                        sx = sy = 0
                if (sx or sy) and alvo != (0, 0):
                    print(f"[Magia] {len(longes)} vindo: levando o monstrinho {passo} sqm na direção deles.")
                    controle.clicar(PLAYER_TILE_XY[0] + alvo[0] * SQM_PX, PLAYER_TILE_XY[1] + alvo[1] * SQM_PX,
                                    espalhar=(8, 8), botao="middle")
                    if p:
                        PET_ABS[0] = (p[0] + alvo[0], p[1] + alvo[1], p[2])  # o pet vai para lá
                    controle.esperar(humano.variar(0.6))
                    if POKESTOP_ATIVO and TECLA_POKESTOP:
                        controle.apertar(TECLA_POKESTOP)  # o order tira do pokestop: para de novo lá
                    movidas += 1
                    ultima_movida = time.time()
                    ultima_fuga = 0.0  # pet mudou de lugar: a diagonal é outra
                    continue

        texto = f"[Magia] Esperando a box: {perto}/{precisa} colados no monstrinho, {longe} longe"
        if texto != ultimo_texto:
            print(texto)
            ultimo_texto = texto
        if controle.esperar(0.1):
            inicio = time.time()

    if perto == 0:
        # ninguém no alcance o tempo todo: combo aqui seria no vazio (e o revive depois, desperdício)
        print(f"[Magia] Ninguém no alcance em {time.time() - inicio:.0f}s: não solto o combo.")
        return "vazio"
    print(f"[Magia] Não agruparam em {time.time() - inicio:.0f}s, soltando a magia assim mesmo.")
    return True


def pet_preso_na_saida(sct):
    """
    Saindo da luta com monstro sobrando: se eles cercam o pet, o order para tirá-lo do pokestop
    não funciona — puxa o pet andando para fora da tela. Retorna True se fez isso.
    """
    criaturas = list(sqm_ocupados(sct))
    if len(criaturas) < 2:
        return False
    centro, _ = achar_pet(criaturas, 1)
    if not pet_cercado(criaturas, centro):
        return False
    return puxar_pet_pela_tela(sct, centro, "saindo da luta com monstro em volta")


def terminar_luta(sct, sobrou=False):
    """Depois da luta: catch, fim do modo, order (sai do pokestop) e descanso."""
    catch_seguro(sct)
    ESTRATEGIA.fim(sct)  # revive: reseta as magias | nightmare: volta pro 1º poke
    if sobrou:
        pet_preso_na_saida(sct)  # cercado: traz o pet andando pra fora da tela (depois o order tira do pokestop)
    if ORDER_DEPOIS_LUTA:
        pedir_order_depois_da_luta()  # sai andando e dá o order no caminho
    if ESTRATEGIA.descansa and not sobrou:  # com monstro atrás não dá para descansar
        descansar(sct)
    print("[CaveBot] Voltando a juntar.\n")


_modo_luta = [None]  # "ofensivo"/"defensivo": último Fight Mode apertado


def fight_mode(qual):
    """Troca o Fight Mode do jogo (só aperta se mudou): defensivo lurando, ofensivo batendo."""
    if not config.MODO_LUTA_ATIVO or _modo_luta[0] == qual:
        return
    if qual == "ofensivo" and not config.MODO_OFENSIVO_ATIVO:
        # o jogo troca sozinho para o ofensivo quando a magia sai: não aperta nada, mas anota que
        # agora está no ofensivo — assim o defensivo é apertado de novo no fim da luta
        _modo_luta[0] = qual
        return
    tecla = config.TECLA_OFENSIVO if qual == "ofensivo" else config.TECLA_DEFENSIVO
    if not tecla:
        return
    _modo_luta[0] = qual
    print(f"[CaveBot] {'⚔️' if qual == 'ofensivo' else '🛡️'} Fight Mode {qual} ({tecla})")
    controle.apertar(tecla)


PET_VIVO_EM = [0.0]  # última vez que QUALQUER leitura viu a barra do pet com vida


def anotar_pet(pct):
    """Toda leitura da barra do pet passa aqui: com vida (> 3%) = pet visto vivo agora."""
    if pct is not None and pct > 3:
        PET_VIVO_EM[0] = time.time()
    return pct


SEM_PET_CARENCIA_S = 1.5  # barra do pet vazia por menos que isso: pode ser a troca/"Back!/Go!"
SEM_PET_ALARME_S = 8.0    # sem monstrinho na luta por isso: alarme + pausa


# Como a luta terminou (combater_ate_limpar devolve um destes)
LUTA_LIMPOU, LUTA_SOBRA, LUTA_FORA_DE_ALCANCE, LUTA_TIMEOUT = "limpou", "sobra", "fora_de_alcance", "timeout"


def fugir_da_box():
    """
    O personagem corre/se posiciona na luta? (`SAIR_DA_BOX`). No modo NORMAL não, com `NORMAL_SEM_FUGIR`
    (pedido do usuário 09/11: hunt fraca, sem risco de morrer — "matar e já ir pro próximo lure").
    Revive, outland e nightmare continuam com toda a proteção.
    """
    if not config.SAIR_DA_BOX:
        return False
    if getattr(ESTRATEGIA, "nome", "") == "normal" and getattr(config, "NORMAL_SEM_FUGIR", True):
        return False
    return True


def reviver_pet(sct, motivo):
    """
    Revive do pet caído no meio da luta, em QUALQUER modo. Antes só os modos revive/outland tinham esse
    revive de reserva: no modo NORMAL, se as tentativas do vigia (`cura.MonitorRevive`) falhassem (09/11
    15:40: painel na frente do jogo, tecla presa 10 s), o bot só esperava e alarmava. Modos com
    `usar_revive` usam o deles (contadores do outland etc.).
    """
    if hasattr(ESTRATEGIA, "usar_revive"):
        return ESTRATEGIA.usar_revive(sct, motivo)
    if not (config.TECLA_REVIVE and getattr(config, "REVIVE_SE_MORRER", True)):
        return False
    if time.time() - controle.ultimo_revive < 5:
        return False  # acabou de usar revive ("Back!/Go!")
    print(f"[Revive] 💊 Usando revive ({motivo}) — modo {getattr(ESTRATEGIA, 'nome', '?')}")
    controle.ultimo_revive = time.time()
    controle.apertar(config.TECLA_REVIVE)
    if getattr(config, "REVIVE_CLICAR_POKE", False):
        from tela import localizar_ancora
        titulo = localizar_ancora(sct, "pokemon") if sct is not None else None
        if titulo:
            controle.esperar(humano.variar(0.15))
            controle.clicar(titulo[0] + modos.OFF_RETRATO[0], titulo[1] + modos.OFF_RETRATO[1], espalhar=(6, 6))
    return controle.esperar(humano.variar(float(getattr(config, "REVIVE_ESPERA", 1.0))))


def combater_ate_limpar(sct, motivo):
    """Luta; no modo revive com revive depois do lure, segura a poção do monstrinho (o revive já cura)."""
    EM_LUTA[0] = True
    caixa_preta.estado("FIGHTING")
    cancelar_orders()  # order atrasado de uma thread tiraria o pet do pokestop
    fight_mode("ofensivo")  # vai bater
    URGENTE[0] = motivo == PERIGO  # luta por perigo: solta o combo com quem já estiver no alcance
    controle.segurar_pot_poke = ESTRATEGIA.nome == "outland" or (ESTRATEGIA.nome == "revive" and bool(config.REVIVE_APOS_LURE))
    try:
        return _combater(sct, motivo)
    finally:
        controle.segurar_pot_poke = False
        EM_LUTA[0] = False
        caixa_preta.estado("NAVIGATING")
        fight_mode("defensivo")  # volta a lurar


def _combater(sct, motivo):
    """Ataca o primeiro monstro da Battle até a lista ficar vazia."""
    textos = {
        LOTOU: f"{minimo_para_lutar()}+ monstro(s) na Battle!",
        PERIGO: f"HP abaixo de {LURE_HP_SEGURANCA}%, lutando antes de juntar mais!",
        "voltas": f"{LURE_MAX_VOLTAS} voltas sem completar o lure, lutando com o que tem.",
        "manual": "Você parou com o lure — atacando!",
        PRESO: "Cercado/bloqueado, lutando com o que tem.",
        TIMEOUT: "Não consegui chegar no ponto, lutando com o que tem.",
    }
    print(f"\n[CaveBot] ⚔️  {textos.get(motivo, '')} Iniciando combate...")

    # Luta nova: zera a memória da luta ANTES do 1º posicionamento (antes era depois: se a luta
    # anterior gastou as corridas, o personagem nem saía de perto da box no pokestop)
    PET_ABS[0] = None  # o pet de antes não vale
    CANTOS_RUINS.clear()  # nem os cantos sem caminho da luta anterior
    CORRIDAS[0] = 0       # box nova: pode correr de novo (CORRIDAS_POR_BOX vezes)
    EMERGENCIAS[0] = 0
    VIGIA_SAIDAS[0] = 0
    REVIVE_ADIADOS[0] = 0
    ANDANDO[0] = None
    VEIO_DE[0] = direcao_de_onde_veio()  # para correr para TRÁS (caminho limpo), não para a frente
    if VEIO_DE[0]:
        print(f"[CaveBot] ↩️ Vim de ({VEIO_DE[0][0]:+.1f}, {VEIO_DE[0][1]:+.1f}): fujo para esse lado (caminho limpo).")

    # Lure terminou: pokestop para o monstrinho parar de andar antes da luta
    if POKESTOP_ATIVO and TECLA_POKESTOP:
        print(f"[CaveBot] ✋ Pokestop ({TECLA_POKESTOP.upper()})")
        controle.apertar(TECLA_POKESTOP)
        controle.esperar(humano.variar(0.2))
        if fugir_da_box() and motivo != "manual":
            if box_ja_pronta(sct):
                print("[Magia] Box já pronta no pokestop: combo primeiro, posição depois.")
            else:
                sair_da_box(sct)

    inicio = time.time()
    ciclos = 0
    qtd_antes = None
    qtd_inicial = None
    vazios = 0
    primeiro_antes = None
    barra_pet = carregar_calibracao().get("poke_hp")
    sem_pet_desde, avisou_sem_pet, revive_sem_pet = None, False, False
    PET_VIVO_EM[0] = time.time()  # luta nova: conta a partir de agora
    limite = max(TIMEOUT_COMBATE, getattr(ESTRATEGIA, "timeout_min", 0))  # nightmare espera cooldowns
    while time.time() - inicio < limite:
        aplicar_modo_novo()  # trocou o modo no painel no meio da luta: já vale neste ciclo
        lista = inimigos(sct)
        checar_catch(sct)
        if not lista:
            # Confirma depois de um instante (a lista pode piscar entre um monstro e outro)
            controle.esperar(0.25)
            if not inimigos(sct):
                print(f"[CaveBot] Battle limpa após {ciclos} ciclos.")
                RASTREADOR.luta_acabou()
                terminar_luta(sct)
                return LUTA_LIMPOU
            continue
        if qtd_inicial is None:
            qtd_inicial = len(lista)

        # Sem monstrinho fora (morreu e o revive não voltou, ou está guardado): o combo sairia no
        # vazio e o personagem apanha sozinho. Não gasta o combo; nos modos com revive tenta 1
        # revive; continuando sem pet, alarme + pausa (antes apertava o combo até o timeout).
        pct_pet = anotar_pet(ler_barra(sct, barra_pet)) if barra_pet else None  # None = não sei (não conta)
        agora = time.time()
        if pct_pet is not None and pct_pet > 3:
            sem_pet_desde, avisou_sem_pet, revive_sem_pet = None, False, False
        elif pct_pet is not None:
            # Barra vazia há SEM_PET_ALARME_S, mesmo contando o "Back!/Go!" dos revives (o modo
            # revive ficava revivendo e combando sem pet, sem nunca ver que ele não voltava).
            # (nunca nos 5 s depois de um revive: o "Back!/Go!" esvazia a barra — 19:17 alarmou 1 s
            # depois do revive, e a conta não andava durante os 14 s da espera da box)
            # (mas se os revives não trazem o pet de volta — acabou o revive —, a folga não segura o
            # alarme para sempre: no máximo 6 s a mais)
            sem_vida = agora - PET_VIVO_EM[0]
            if sem_vida >= SEM_PET_ALARME_S and (agora - controle.ultimo_revive >= 5
                                                  or sem_vida >= SEM_PET_ALARME_S + 6):
                alarmar_e_pausar(sct, f"🐾 Sem monstrinho na luta há {SEM_PET_ALARME_S:.0f}s "
                                      f"(morreu/guardado e não voltou).", "sem monstrinho", "sem_pet")
                PET_VIVO_EM[0] = time.time()
                sem_pet_desde, avisou_sem_pet, revive_sem_pet = None, False, False
                if controle.esperar(0.3):  # (pausado pelo alarme: espera o F12 aqui)
                    inicio = time.time()
                continue  # volta a olhar a Battle e o pet antes de qualquer combo
            # Fora do "Back!/Go!" de um revive (até 5 s depois a barra fica vazia): pet fora mesmo
            elif agora - controle.ultimo_revive >= 5:
                sem_pet_desde = sem_pet_desde or agora
                if agora - sem_pet_desde >= SEM_PET_CARENCIA_S:
                    if not avisou_sem_pet:
                        print("[CaveBot] ⚠️ Monstrinho fora da luta (morto/guardado): não gasto o combo.")
                        avisou_sem_pet = True
                    if config.TECLA_REVIVE and not revive_sem_pet:
                        revive_sem_pet = True
                        reviver_pet(sct, "monstrinho fora no meio da luta")
                # pet fora: nunca solta combo (a carência só atrasa o aviso/revive)
                if controle.esperar(0.3):
                    inicio = time.time()
                continue
            else:
                # até 5 s depois de um revive com a barra vazia: o pet ainda está voltando ("Back!/Go!").
                # Espera ele aparecer — antes combava com o pet na ball (combo perdido).
                if controle.esperar(0.2):
                    inicio = time.time()
                continue

        ciclos += 1

        # Só clica para escolher alvo quando precisa. Clicar de novo no monstro que
        # já está sendo atacado CANCELA o ataque ("You need a target to use this spell").
        atacando = any(l["alvo"] for l in lista)
        primeiro = lista[0]["xy"]
        if config.CLICAR_ALVO and not atacando and (qtd_antes is None or len(lista) < qtd_antes or primeiro != primeiro_antes):
            controle.clicar(*primeiro, espalhar=(8, 3))
            controle.esperar(0.1)
        qtd_antes, primeiro_antes = len(lista), primeiro

        agrupou = esperar_agrupar(sct) if MAGIA_AGRUPAR_ATIVA else True
        if not agrupou:
            continue  # a Battle esvaziou enquanto esperava
        if agrupou == "sumiram":
            # fora da tela (fugiram com pouca vida): não dá para bater; segue a hunt na hora
            print(f"[CaveBot] ↪️ {len(inimigos(sct))} monstro(s) na Battle fora da tela: seguindo a hunt.")
            terminar_luta(sct, sobrou=True)
            return LUTA_FORA_DE_ALCANCE
        if agrupou == "vazio":
            vazios += 1
            if vazios >= 2:
                # monstro na Battle que não chega (atrás de parede, preso, longe): não dá para bater nele
                print(f"[CaveBot] ↪️ {len(inimigos(sct))} monstro(s) na Battle fora de alcance: seguindo a hunt.")
                terminar_luta(sct, sobrou=True)
                return LUTA_FORA_DE_ALCANCE
            continue  # sem combo e sem revive: ninguém para acertar
        vazios = 0  # achou alguém no alcance: o "2x seguidas sem ninguém" recomeça
        # Blind ou outro efeito negativo no monstrinho? As magias dariam MISS: usa Medicine antes
        efeitos.curar_se_precisar(sct)
        foto_box = foto_da_box(sct) if controle_box.parametros(config)[1] > 0 else None
        if ESTRATEGIA.atacar(sct):
            inicio = time.time()  # houve pausa: o tempo não conta
        COMBO_FIM[0] = time.time()  # começa a janela de silence/stun da box
        iniciar_controle(sct, foto_box)

        # Hunt normal: o combo matou o lure e sobraram poucos -> não perde tempo, vai pro próximo
        # lure (eles vêm atrás e entram no próximo). Não larga se tem especial vivo/escondido.
        sobra = len(inimigos(sct))
        if (config.IGNORAR_SOBRA and ESTRATEGIA.nome != "outland" and controle.rota_ligada() and motivo != "manual"
                and 0 < sobra <= config.SOBRA_MAX and qtd_inicial > config.SOBRA_MAX
                and not RASTREADOR.estrelados and not RASTREADOR.escondidos):
            print(f"[CaveBot] ↪️  Sobrou {sobra} monstro(s): ignorando e indo para o próximo lure.")
            terminar_luta(sct, sobrou=True)
            return LUTA_SOBRA

        # Não matou tudo? (revive: usa revive | nightmare: a troca acontece no próximo ataque)
        # Antes do revive (o pet some ~1 s): personagem na diagonal da box, longe dos monstros.
        if inimigos(sct) and hasattr(ESTRATEGIA, "usar_revive") and fugir_da_box():
            silencio = em_silencio()
            if silencio:
                print(f"[Magia] 🤐 Box silenciada pelo combo: revive na hora (sem correr da box).")
            else:
                cri = list(sqm_ocupados(sct))
                if cri:
                    c, _ = achar_pet(cri, 1)
                    if em_perigo(cri, c):
                        ir_para_diagonal(sct, cri, c, motivo=" antes do revive")
            if fugir_da_box():
                if not silencio:
                    afastar_antes_do_revive(sct)
                if not preparar_revive(sct, silencio=silencio):
                    continue  # longe o bastante não deu: adia o revive (próximo ciclo tenta de novo)
        if inimigos(sct) and ESTRATEGIA.nao_matou(sct):
            inicio = time.time()

    print(f"[CaveBot] ⚠️ Battle não esvaziou em {limite:.0f}s. Seguindo mesmo assim.")
    # Fecha a luta igual às outras saídas com sobra: catch do que já morreu, fim do modo (outland/
    # revive: revive + zera os contadores da luta; nightmare: volta pro 1º) e order. Antes só dava o
    # order: os contadores do outland passavam para a próxima luta e o catch pendente se perdia.
    terminar_luta(sct, sobrou=True)
    return LUTA_TIMEOUT



# ---------- Lure feito na mão (rota desligada) ----------

class LureManual:
    """
    Com a rota desligada, você puxa o lure andando e o bot ataca quando:
      - você fica parado PARADO_PARA_ATACAR_S segundos com pelo menos o mínimo do lure ("manual"), ou
      - seu HP / o do monstrinho fica baixo com monstros atrás (PERIGO).
    Enquanto você está andando com os monstros atrás, ele não ataca (não atrapalha o lure).
    Só se não conseguir ler sua posição é que usa o mínimo do lure (LOTOU) como reserva.
    """

    def __init__(self):
        self.ultima_pos = None
        self.parado_desde = time.time()

    def checar(self, lure):
        qtd, _, motivo = lure.checar()
        if motivo == PERIGO:
            return motivo  # HP baixo: luta na hora
        pos = POS.atual()
        if pos is None:
            return motivo  # sem saber se você parou: usa o mínimo do lure como reserva
        # Com a posição: quem decide o tamanho do lure é você — ataca quando você PARA
        # (não ataca no meio do caminho só porque bateu o mínimo).
        agora = time.time()
        if pos is None or pos != self.ultima_pos:
            self.ultima_pos, self.parado_desde = pos, agora
        # Parado com o lure pronto (pelo menos o mínimo do lure). Com 1–2 monstros não ataca:
        # você ainda está puxando (ou acabou de matar e está começando o próximo).
        if qtd >= minimo_para_lutar() and agora - self.parado_desde >= PARADO_PARA_ATACAR_S:
            return "manual"
        return None

# ---------- Loop principal ----------

def ordem_da_rota(total, ida_e_volta):
    """
    Ordem dos waypoints numa volta completa.
    Circular:    1, 2, 3            (do último volta direto para o 1)
    Ida e volta: 1, 2, 3, 2         (e recomeça no 1: 1→2→3→2→1→2→3...)
    """
    ida = list(range(total))
    if not ida_e_volta or total <= 2:
        return ida
    return ida + list(range(total - 2, 0, -1))


def vigiar_ajustes():
    """
    Salvou os ajustes no painel com o bot rodando: aplica na hora (sem reiniciar o bot).
    Vale para o que o bot consulta durante a hunt (ex.: clicar no alvo, alcance, lure, catch).
    """
    arq = config.ARQ_AJUSTES
    try:
        visto = os.path.getmtime(arq)
    except OSError:
        visto = 0
    while not controle.deve_parar():
        time.sleep(2)
        try:
            agora = os.path.getmtime(arq)
            if agora == visto:
                continue
            visto = agora
            time.sleep(0.3)  # o painel termina de escrever
            with open(arq, encoding="utf-8") as f:
                novos = json.load(f)
            mudou = []
            for k, v in novos.items():
                if k.isupper() and hasattr(config, k) and getattr(config, k) != v and k != "PAINEL_GEOMETRIA":
                    layout._setar(k, v)
                    mudou.append(k)
            if mudou:
                print(f"[Ajustes] Mudanças aplicadas sem reiniciar: {', '.join(mudou)}")
                if CHAVES_DO_MODO & set(mudou):
                    TROCAR_MODO[0] = True  # a ESTRATEGIA é recriada no próximo ciclo (luta ou rota)
        except Exception as e:
            print(f"[Ajustes] Não consegui ler os ajustes novos: {e!r}")


MEMORIA = MemoriaRota()  # falhas recentes andando (zera ao chegar em qualquer ponto)


class ErroDeTela:
    """
    Captura de tela falhando no laço principal (Windows bloqueado, UAC, resolução mudando).
    Espera a tela voltar; se continuar falhando por PAUSA_APOS_S, toca o alarme e pausa.
    """
    PAUSA_APOS_S = 60.0
    NOVO_EPISODIO_S = 10.0  # passou isso sem erro: o próximo erro é uma falha nova

    def __init__(self):
        self.desde, self.ultimo, self.avisou = None, 0.0, False

    def aconteceu(self, e):
        agora = time.time()
        if self.desde is None or agora - self.ultimo > self.NOVO_EPISODIO_S:
            self.desde, self.avisou = agora, False
            print(f"[Tela] ⚠️ Não consegui capturar a tela ({e!r}). Esperando ela voltar...")
        self.ultimo = agora
        if not self.avisou and agora - self.desde >= self.PAUSA_APOS_S:
            self.avisou = True
            print(f"[Tela] ⚠️ A tela não volta há {self.PAUSA_APOS_S:.0f}s.")
            chat.tocar_som(10)
            controle.pausar("captura de tela falhando")
        controle.esperar(2.0)


def abrir_hunt_do_personagem(p):
    """Rodízio: carrega a hunt do personagem (rota + catch + ajustes de caça) sem reiniciar o bot."""
    global ESTRATEGIA
    import hunts
    nome = p.get("hunt") or ""
    if not nome:
        print(f"[Rodízio] {p['nome']} sem hunt marcada: sigo com a hunt aberta ({config.HUNT_ATUAL or 'sem nome'}).")
        return
    if not hunts.existe(nome):
        raise personagens.ErroTroca(f"a hunt \"{nome}\" do {p['nome']} não existe mais (aba Rota do painel)")
    if nome != config.HUNT_ATUAL:
        for k, v in hunts.carregar(nome).items():
            layout._setar(k, v)
        layout._setar("HUNT_ATUAL", nome)
        ESTRATEGIA = modos.criar()
        if hasattr(ESTRATEGIA, "tem_especial"):
            ESTRATEGIA.tem_especial = lambda: bool(RASTREADOR.estrelados or RASTREADOR.escondidos or RASTREADOR.qtd)
    print(f"[Rodízio] Personagem {p['nome']} → hunt {nome} ({p['voltas']} volta(s), "
          f"desloga {'no ponto ' + str(p['ponto']) if p['ponto'] else 'onde fechar a volta'}).")


def trocar_personagem(sct, rod):
    """
    Desloga, entra no próximo personagem e abre a hunt dele. Deu errado → alarme + pausa; ao continuar
    (F12), se o jogo estiver na tela (você entrou na mão), segue com o personagem da vez.
    """
    alvo = rod.proximo()
    print(f"\n🔁 [Rodízio] Trocando de personagem: {rod.da_vez()['nome']} → {alvo['nome']}")
    erro = personagens.trocar(sct, alvo["nome"], livre=lambda: not EM_LUTA[0] and not inimigos(sct))
    while erro:
        alarmar_e_pausar(sct, f"🔁 Rodízio: a troca de personagem deu errado: {erro}.\n"
                              f"Entre no personagem {alvo['nome']} na mão e aperte F12.",
                         "rodizio", "rodizio")
        controle.aguardar_se_pausado()
        if personagens._no_jogo(sct):
            print(f"[Rodízio] Jogo na tela: sigo como {alvo['nome']} (confira se é ele mesmo).")
            personagens.concluir_troca(sct, alvo["nome"])
            erro = None
        else:
            erro = "o jogo ainda não está na tela"
    rod.trocou()
    try:
        abrir_hunt_do_personagem(alvo)
    except personagens.ErroTroca as e:
        alarmar_e_pausar(sct, f"🔁 Rodízio: {e}.", "rodizio", "rodizio")


def rodar_cavebot():
    global ESTRATEGIA
    rod = personagens.Rodizio()
    if rod.ativo():
        print(f"🔁 Rodízio de personagens ligado: {' → '.join(p['nome'] for p in rod.personagens)} (e volta). "
              f"Agora: {rod.da_vez()['nome']} (pelo Meu nome / 1º da lista).")
        try:
            abrir_hunt_do_personagem(rod.da_vez())
        except personagens.ErroTroca as e:
            print(f"⚠️  {e}")
    elif getattr(config, "RODIZIO_ATIVO", False):
        print("⚠️  Rodízio ligado, mas precisa de 2+ personagens na lista (aba Rodízio do painel).")
    pontos = carregar_rota()
    calib = carregar_calibracao()
    total = len(pontos)

    ordem = ordem_da_rota(total, ROTA_IDA_E_VOLTA) if total else []
    modo = (f"lure de {LURE_MINIMO}+ monstros" if LURE_ATIVO else "luta a cada monstro")         + f", modo {ESTRATEGIA.nome}"
    print(f"=== CaveBot ({modo}) com {total} waypoints ===")
    if config.HUNT_ATUAL:
        print(f"Hunt: {config.HUNT_ATUAL}")
    if ordem:
        print("Rota: " + " → ".join(str(i + 1) for i in ordem + [ordem[0]])
              + (" (ida e volta)" if ROTA_IDA_E_VOLTA else " (circular)"))
    else:
        print("Sem rota gravada: o bot só ataca o lure que você fizer na mão (e cuida de cura, medicine, alarme).")
    controle.iniciar_atalhos()
    print("Você tem 4 segundos para focar na janela do jogo!")
    print("(Também dá para abortar jogando o mouse no canto superior esquerdo.)")
    time.sleep(4.0)

    # Configuração automática: acha a janela do jogo (em qualquer tela) e mede tudo
    layout.arrumar_console()
    with mss.MSS() as sct_layout:
        layout.detectar_e_aplicar(sct_layout)
    layout.VigiaLayout().start()
    threading.Thread(target=vigiar_ajustes, daemon=True).start()

    if hasattr(ESTRATEGIA, "tem_especial"):  # outland: com especial/shiny vivo, revive sem limite
        ESTRATEGIA.tem_especial = lambda: bool(RASTREADOR.estrelados or RASTREADOR.escondidos or RASTREADOR.qtd)
    fight_mode("defensivo")  # começa lurando: defensivo
    MonitorCura(calib).start()
    MonitorRevive(calib).start()
    MonitorChat().start()
    players.VigiaPlayers(calib).start()  # outro player (criatura fora da Battle) na tela → alarme
    MonitorSeguranca(calib, pos_atual=POS.atual).start()
    modos.VIGIA[0] = vigiar_no_combo  # durante o combo: monstro vindo em você → sai de perto
    catch.TIRAR_PET[0] = tirar_pet_do_corpo  # catch: pet em cima do corpo do especial → tira ele de lá
    # só observa: grava a tela/HP/criaturas quando o personagem leva dano (diagnostico/caixa_preta)
    caixa_preta.CaixaPreta(calib, POS.atual, criaturas_na_imagem, EM_LUTA).start()
    shiny.VigiaShiny(POS.atual).start()  # aprende a cor rara (shiny) e cria o perfil pelo corpo
    efeitos.MonitorEfeitos().start()

    # Navegação por coordenadas se todos os pontos têm coordenada e dá para ler a posição
    POS.start()  # posição sempre: navegação e saber quando você parou no lure manual
    import posicao
    ruins = [i + 1 for i, p in enumerate(pontos)
             if posicao.ponto_suspeito(p.get("pos"), [q.get("pos") for q in pontos])]
    por_coordenada = bool(pontos) and not ruins
    if ruins:
        print(f"⚠️  ROTA COM PONTOS RUINS: {ruins} (sem coordenada ou coordenada lida errado).\n"
              "    Regrave esses pontos na aba Rota do painel (eles aparecem com ⚠️).\n"
              "    Enquanto isso a rota fica DESLIGADA; o lure feito na mão continua funcionando.")
        pontos = []
        ordem = []
        total = 0
    if por_coordenada:
        t0 = time.time()
        while POS.atual() is None and time.time() - t0 < 5:
            time.sleep(0.2)
        if POS.atual() is None:
            print("⚠️  Não consegui ler as coordenadas do minimapa. Usando a navegação antiga (por imagem).")
            por_coordenada = False
        else:
            print(f"[Rota] Navegação por coordenadas. Estou em {POS.atual()}.")
    andar = andar_ate_coord if por_coordenada else andar_ate

    passo = 0  # posição dentro da ordem da rota
    if por_coordenada:
        passo = passo_mais_proximo(pontos, ordem, 0)  # começa pelo ponto mais perto
    voltas_sem_lutar = 0
    voltas = personagens.ContadorVoltas(len(ordem), total)
    ultimo_salvamento = time.time()
    with mss.MSS() as sct:
        lure = Lure(sct, calib)
        manual = LureManual()
        try:
            rota_estava_ligada = controle.rota_ligada()
            erro_tela = ErroDeTela()
            avisou_ignorar = False
            while True:
                try:
                    aplicar_modo_novo()  # modo trocado no painel: vale antes do próximo lure
                    # Rota desligada: não anda. Ataca o lure que você fizer na mão (se ligado).
                    # Cura, medicine, alarme e segurança seguem rodando nas threads.
                    if not controle.rota_ligada():
                        rota_estava_ligada = False
                        if COMBATE_SEM_ROTA and config.CACA_ATIVA:
                            motivo = manual.checar(lure)
                            if motivo:
                                combater_ate_limpar(sct, motivo)
                                manual = LureManual()
                                continue
                        controle.esperar(0.2)
                        continue
                    if not pontos:
                        print("⚠️  Não tem rota gravada. Grave a rota na aba Rota do painel. Desligando a rota.")
                        controle.ligar_rota(False)
                        continue
                    if not rota_estava_ligada:  # acabou de ligar: continua pelo ponto mais perto
                        rota_estava_ligada = True
                        if por_coordenada:
                            passo = passo_mais_proximo(pontos, ordem, passo)
                    if voltas.passo(passo) and rod.ativo():
                        rod.fechou_volta(voltas.voltas)
                    indice = ordem[passo]
                    wp = pontos[indice]
                    numero = indice + 1
                    tipo = "ponto de lure" if wp["lure"] else "passagem"
                    print(f"[CaveBot] Indo para o waypoint {numero}/{total} ({tipo})")

                    pos_antes = POS.atual()
                    ignorar = MEMORIA.ignorar_preso(pos_antes)
                    if ignorar and not avisou_ignorar:
                        print("[Rota] Aqui lutar por 'cercado' não adiantou (monstro fora de alcance): "
                              "sigo desviando em vez de parar para lutar.")
                    avisou_ignorar = ignorar
                    resultado = andar(sct, wp, numero, lure, ignorar_preso=ignorar)
                    if resultado == CHEGOU:
                        MEMORIA.chegou()
                        voltas.chegou_em(indice)

                    if time.time() - ultimo_salvamento > 30:
                        MAPA.salvar()
                        ultimo_salvamento = time.time()

                    if resultado == RETOMAR:
                        if por_coordenada:
                            passo = passo_mais_proximo(pontos, ordem, passo)
                        continue

                    # Lutar onde está: juntou o suficiente, HP baixo, cercado, ou não conseguiu
                    # chegar no ponto com monstro atrás. Depois tenta o MESMO waypoint de novo.
                    if resultado in (LOTOU, PERIGO, PRESO) or (resultado == TIMEOUT and inimigos(sct)):
                        pos_luta = POS.atual()
                        fim_luta = combater_ate_limpar(sct, resultado)
                        voltas_sem_lutar = 0
                        if resultado in (PRESO, TIMEOUT):
                            luta_inutil = fim_luta in (LUTA_FORA_DE_ALCANCE, LUTA_TIMEOUT)
                            if luta_inutil:  # lutar aqui não achou ninguém no alcance: marca o lugar
                                MEMORIA.preso_inutil(pos_luta)
                            if (resultado == TIMEOUT or luta_inutil) \
                                    and MEMORIA.falhou(numero, f"{resultado}, luta: {fim_luta}"):
                                alarmar_e_pausar(sct, f"🧭 A rota está falhando: {config.NAV_FALHAS_MAX} tentativas "
                                                      f"seguidas sem chegar em ponto nenhum (agora no ponto {numero}).",
                                                 "rota falhando", "rota_falhando")
                        if por_coordenada:  # a luta pode ter levado o personagem para longe
                            passo = passo_mais_proximo(pontos, ordem, passo)
                        continue

                    if resultado == TIMEOUT and MEMORIA.falhou(numero, "não chegou"):
                        alarmar_e_pausar(sct, f"🧭 A rota está falhando: {config.NAV_FALHAS_MAX} pontos seguidos "
                                              f"sem conseguir chegar (agora no ponto {numero}).",
                                         "rota falhando", "rota_falhando")

                    # Jeito humano: de vez em quando dá uma paradinha ao chegar (sem monstro atrás)
                    if resultado == CHEGOU and humano.chance(HUMANO_PARADAS / 100) and not inimigos(sct):
                        controle.esperar(humano.variar(1.3, 0.9))

                    if resultado == CHEGOU and wp["lure"] and LURE_ATIVO:
                        motivo = esperar_trem(lure)
                        if motivo:
                            combater_ate_limpar(sct, motivo)
                            voltas_sem_lutar = 0

                    # Rodízio: completou as voltas e chegou no ponto de saída → troca de personagem
                    if resultado == CHEGOU and rod.ativo() and rod.pode_sair_aqui(numero):
                        trocar_personagem(sct, rod)
                        pontos = carregar_rota()
                        total = len(pontos)
                        ordem = ordem_da_rota(total, ROTA_IDA_E_VOLTA) if total else []
                        ruins = [i + 1 for i, p in enumerate(pontos)
                                 if posicao.ponto_suspeito(p.get("pos"), [q.get("pos") for q in pontos])]
                        if ruins or not pontos:
                            print(f"⚠️  [Rodízio] Rota da hunt nova sem pontos bons ({ruins or 'vazia'}): rota desligada.")
                            pontos, ordem, total = [], [], 0
                            controle.ligar_rota(False)
                        voltas = personagens.ContadorVoltas(len(ordem), total)
                        MEMORIA.__init__()
                        lure = Lure(sct, calib)
                        manual = LureManual()
                        voltas_sem_lutar = 0
                        t0 = time.time()
                        while time.time() - t0 < 5 and POS.atual() is None:
                            controle.esperar(0.2)
                        controle.esperar(1.5)  # a posição do personagem novo chega pelo OCR
                        passo = passo_mais_proximo(pontos, ordem, 0) if (pontos and por_coordenada) else 0
                        continue

                    passo = (passo + 1) % len(ordem)

                    # Completou uma volta na rota
                    if passo == 0 and LURE_ATIVO:
                        voltas_sem_lutar += 1
                        if LURE_MAX_VOLTAS and voltas_sem_lutar >= LURE_MAX_VOLTAS:
                            qtd, _, _ = lure.checar()
                            if qtd > 0:
                                combater_ate_limpar(sct, "voltas")
                            voltas_sem_lutar = 0
                except mss.exception.ScreenShotError as e:
                    # Windows bloqueado, UAC, troca de resolução...: a captura falha. Antes o bot MORRIA
                    # no meio da hunt; agora espera a tela voltar e recalcula de onde continuar.
                    erro_tela.aconteceu(e)
                    rota_estava_ligada = False  # ao voltar: retoma pelo ponto mais perto
                    manual = LureManual()
                    continue

        except (controle.ParadaSolicitada, KeyboardInterrupt):
            print(f"\n=== CaveBot encerrado ({TECLA_PARAR.upper()} / Ctrl+C) ===")
        finally:
            MAPA.salvar()
            controle.encerrar()  # encerra a thread de cura também


class _Log:
    """Escreve tudo que aparece no console também em bot_log.txt (com horário)."""

    def __init__(self, tela, arquivo):
        self.tela, self.arquivo, self.inicio_linha = tela, arquivo, True

    def write(self, texto):
        self.tela.write(texto)
        for parte in texto.splitlines(True):
            if self.inicio_linha and parte.strip():
                self.arquivo.write(time.strftime("%H:%M:%S "))
            self.arquivo.write(parte)
            if self.inicio_linha:
                caixa_preta.guardar_linha(parte)  # o evento de dano leva junto o que o bot decidiu
            self.inicio_linha = parte.endswith("\n")
        self.arquivo.flush()

    def flush(self):
        self.tela.flush()


if __name__ == "__main__":
    import os
    import sys
    import traceback
    _arq = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_log.txt"), "a", encoding="utf-8")
    _arq.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} bot iniciado =====\n")
    sys.stdout = _Log(sys.stdout, _arq)
    sys.stderr = _Log(sys.stderr, _arq)
    try:
        rodar_cavebot()
    except Exception:
        print("\n❌ O bot deu um erro e parou:")
        traceback.print_exc()
        print("\n(o erro também foi salvo em bot_log.txt)")
        try:
            input("Aperte Enter para fechar esta janela...")
        except Exception:
            pass  # rodando pelo painel (sem console): o erro aparece na aba Log
