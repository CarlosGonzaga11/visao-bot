"""
Controle do bot por teclas globais (biblioteca `keyboard`):
  F12 = pausar / continuar
  F11 = parar o bot
  F10 = ligar / desligar a rota (o bot começa com ela desligada, se você quiser)

Também centraliza cliques/teclas com um lock, para que a thread de cura
e o loop principal não misturem comandos ao mesmo tempo.
"""
import json
import os
import threading
import time

import keyboard
import pydirectinput

import humano

from config import TECLA_PAUSA, TECLA_PARAR, TECLA_ROTA, ROTA_AO_INICIAR

pydirectinput.FAILSAFE = True
pydirectinput.PAUSE = 0.02

_pausado = threading.Event()
_parar = threading.Event()
_input_lock = threading.Lock()     # mouse
_teclado_lock = threading.Lock()
segurar_pot_poke = False
ultimo_revive = 0.0
ultima_magia_buff = 0.0  # quando usou magia de buff (defesa): ícone novo logo depois é BOM  # quando apertou revive (o pet volta pra ball e sai: a barra fica vazia um instante)  # luta no modo revive: a poção do monstrinho espera (o revive cura tudo)   # teclado separado: tecla não espera o mouse terminar o trajeto
_rota = threading.Event()  # rota ligada = anda e puxa lure; desligada = só cura/medicine/alarme
if ROTA_AO_INICIAR:
    _rota.set()

# O painel liga/desliga a rota escrevendo neste arquivo (o bot roda em outro processo)
ARQ_COMANDO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comando_bot.json")
# ...e o bot conta para o painel se a rota está ligada (para o botão mostrar o estado certo)
ARQ_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado_bot.json")


def _gravar_estado():
    try:
        with open(ARQ_ESTADO, "w", encoding="utf-8") as f:
            json.dump({"rota": _rota.is_set(), "quando": time.time()}, f)
    except Exception:
        pass


class ParadaSolicitada(Exception):
    """Lançada quando o usuário aperta a tecla de parar."""


def _alternar_pausa():
    if _pausado.is_set():
        _pausado.clear()
        print(f"\n▶️  Bot RETOMADO ({TECLA_PAUSA.upper()} para pausar)")
    else:
        _pausado.set()
        print(f"\n⏸️  Bot PAUSADO ({TECLA_PAUSA.upper()} para continuar)")


def _solicitar_parada():
    print("\n⏹️  Parada solicitada...")
    _parar.set()
    _pausado.clear()


def rota_ligada():
    return _rota.is_set()


def ligar_rota(ligada, origem=""):
    if ligada == _rota.is_set():
        return
    if ligada:
        _rota.set()
        _gravar_estado()
        print(f"\n🧭 ROTA LIGADA{origem} — andando e puxando lure ({TECLA_ROTA.upper()} desliga)")
    else:
        _rota.clear()
        _gravar_estado()
        print(f"\n🛑 ROTA DESLIGADA{origem} — o bot fica parado, só cuidando de cura, medicine e alarme "
              f"({TECLA_ROTA.upper()} liga)")


def _alternar_rota():
    ligar_rota(not _rota.is_set(), f" ({TECLA_ROTA.upper()})")


def _vigiar_comandos():
    """Lê os comandos que o painel escreve em comando_bot.json (botão Ligar/Desligar rota)."""
    # comando antigo (de antes do bot abrir) não vale; qualquer um escrito depois vale
    ultimo = os.path.getmtime(ARQ_COMANDO) if os.path.exists(ARQ_COMANDO) else 0.0
    while not _parar.is_set():
        try:
            if os.path.exists(ARQ_COMANDO):
                mtime = os.path.getmtime(ARQ_COMANDO)
                if mtime != ultimo:
                    ultimo = mtime
                    with open(ARQ_COMANDO, encoding="utf-8") as f:
                        cmd = json.load(f)
                    if "rota" in cmd:
                        ligar_rota(bool(cmd["rota"]), " (painel)")
        except Exception:
            pass
        time.sleep(0.3)


def _print_do_jogo():
    """PrintScreen: salva a janela do jogo em tamanho real em diagnostico/ (para ajustar o bot)."""
    def salvar():
        try:
            import cv2
            import mss
            import numpy as np
            import layout
            j = layout.ATUAL.get("janela") or layout.janela_jogo()
            pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
            os.makedirs(pasta, exist_ok=True)
            arq = os.path.join(pasta, time.strftime("print_%H-%M-%S.png"))
            with mss.MSS() as sct:
                img = np.array(sct.grab(j or sct.monitors[0]))
            cv2.imwrite(arq, cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
            print(f"📸 Print do jogo salvo em diagnostico/{os.path.basename(arq)}")
        except Exception as e:
            print(f"📸 Não consegui salvar o print: {e!r}")
    threading.Thread(target=salvar, daemon=True).start()


def iniciar_atalhos():
    keyboard.add_hotkey(TECLA_PAUSA, _alternar_pausa)
    keyboard.add_hotkey(TECLA_PARAR, _solicitar_parada)
    keyboard.add_hotkey(TECLA_ROTA, _alternar_rota)
    try:
        keyboard.add_hotkey("print screen", _print_do_jogo)
    except Exception:
        pass
    _gravar_estado()
    threading.Thread(target=_vigiar_comandos, daemon=True).start()
    print(f"Atalhos: {TECLA_ROTA.upper()} = ligar/desligar a rota | {TECLA_PAUSA.upper()} = pausar/continuar | "
          f"{TECLA_PARAR.upper()} = parar | PrintScreen = print do jogo (diagnostico/)")
    if not _rota.is_set():
        print(f"🛑 Rota DESLIGADA: o bot só cuida de cura, medicine e alarme. "
              f"Aperte {TECLA_ROTA.upper()} (ou o botão no painel) quando quiser começar a rota.")


def encerrar():
    """Sinaliza parada para todas as threads e remove os atalhos."""
    _parar.set()
    _pausado.clear()
    _rota.clear()
    _gravar_estado()
    keyboard.unhook_all_hotkeys()


def pausar(motivo=""):
    """Pausa o bot por conta própria (ex.: alarme). O usuário continua com a tecla de pausa."""
    if not _pausado.is_set():
        _pausado.set()
        extra = f" por {motivo}" if motivo else ""
        print(f"\n⏸️  Bot PAUSADO{extra}. Aperte {TECLA_PAUSA.upper()} para continuar.")


def esta_pausado():
    """Pausado (F12/alarme) — ou trocando de personagem, para as OUTRAS threads (elas ficam quietas)."""
    return _pausado.is_set() or (_trocando.is_set() and threading.get_ident() != _dono_troca[0])


# ---------- Rodízio de personagens: enquanto troca, só a thread da troca age ----------
_trocando = threading.Event()
_dono_troca = [None]
GERACAO = [0]  # sobe a cada troca concluída: threads com memória da tela (abas do chat, posição) zeram


def iniciar_troca():
    """A partir de agora, só a thread que chamou clica/aperta; as outras veem o bot como pausado."""
    _dono_troca[0] = threading.get_ident()
    _trocando.set()


def fim_troca():
    GERACAO[0] += 1
    _trocando.clear()
    _dono_troca[0] = None


def trocando():
    """True durante a troca de personagem (o jogo pode estar na tela de seleção)."""
    return _trocando.is_set()


def deve_parar():
    return _parar.is_set()


def aguardar_se_pausado():
    """Bloqueia enquanto estiver pausado. Retorna True se chegou a pausar."""
    pausou = False
    while _pausado.is_set():
        pausou = True
        time.sleep(0.1)
    if _parar.is_set():
        raise ParadaSolicitada()
    return pausou


def esperar(segundos):
    """
    Igual a time.sleep, mas respeita pausa e parada.
    O tempo pausado não conta. Retorna True se houve pausa no meio.
    """
    pausou = False
    restante = segundos
    while restante > 0:
        if aguardar_se_pausado():
            pausou = True
        passo = min(0.05, restante)
        time.sleep(passo)
        restante -= passo
    aguardar_se_pausado()
    return pausou


# ---------- Proteção: só clica/aperta quando é o jogo que vai receber ----------
TITULO_JOGO = "PokeAlliance"
_ultimo_aviso = [0.0]


def _titulo_raiz(hwnd):
    import ctypes
    u = ctypes.windll.user32
    raiz = u.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT: a janela "de verdade" (não um pedaço dela)
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(raiz, buf, 256)
    return buf.value


def _avisar_coberto(onde):
    if time.time() - _ultimo_aviso[0] > 10:
        _ultimo_aviso[0] = time.time()
        print(f"⚠️  {onde} não é o jogo — não cliquei/apertei. Tire o console/painel de cima do jogo "
              "(deixe na outra tela) e clique no jogo. Esperando...")


def _nome_seguro(f):
    try:
        return (f() or "sem nome")[:40]
    except Exception:
        return "?"


def _titulo_ativa():
    import ctypes
    return _titulo_raiz(ctypes.windll.user32.GetForegroundWindow())


def _esperar_jogo(ok, onde):
    """
    Espera o jogo ficar livre em vez de clicar no lugar errado. Se quem cobre é o próprio
    console do bot, minimiza ele. Esperar (e não pular o clique) evita que o bot ache que
    o caminho está bloqueado e grave bloqueios falsos na memória do mapa.
    """
    if ok():
        return True
    import ctypes
    console = ctypes.windll.kernel32.GetConsoleWindow()
    if console and ctypes.windll.user32.IsWindowVisible(console):
        ctypes.windll.user32.ShowWindow(console, 6)  # minimizar
        time.sleep(0.3)
        if ok():
            return True
    # Pausou (F12) enquanto esperava o jogo: desiste da ação. Antes ele ficava esperando e
    # clicava assim que você voltava pro jogo, MESMO PAUSADO.
    while not deve_parar() and not esta_pausado():
        _avisar_coberto(onde)
        time.sleep(0.5)
        if ok():
            return True
    return False


def janela_no_ponto(x, y):
    """Título da janela que aparece no ponto (x, y) da tela."""
    import ctypes
    from ctypes import wintypes
    return _titulo_raiz(ctypes.windll.user32.WindowFromPoint(wintypes.POINT(int(x), int(y))))


def jogo_no_ponto(x, y):
    """True se o ponto (x, y) da tela mostra a janela do jogo (nada por cima)."""
    if humano.EM_TESTE:
        return True  # teste: não há jogo aberto (as ações já não saem de verdade)
    try:
        return janela_no_ponto(x, y).startswith(TITULO_JOGO)
    except Exception:
        return True  # se não der para conferir, não atrapalha


def jogo_em_foco():
    """True se a janela ativa (a que recebe o teclado) é o jogo."""
    if humano.EM_TESTE:
        return True  # teste: não há jogo aberto (as ações já não saem de verdade)
    try:
        import ctypes
        return _titulo_raiz(ctypes.windll.user32.GetForegroundWindow()).startswith(TITULO_JOGO)
    except Exception:
        return True


def acoes_bloqueadas():
    """Pausado (F12) ou parando (F11): nenhum clique/tecla pode sair, de nenhuma thread.
    Trocando de personagem: só a thread da troca pode."""
    return _pausado.is_set() or _parar.is_set() or         (_trocando.is_set() and threading.get_ident() != _dono_troca[0])


def _failsafe():
    """Mouse jogado no canto da tela (FailSafe): é o jeito de abortar, não um erro do bot."""
    print("\n🖱️  Mouse no canto da tela (FailSafe): parando o bot.")
    _solicitar_parada()
    return ParadaSolicitada()


def clicar(x, y, espalhar=(0, 0), botao="left"):
    """
    Clica em (x, y). No jeito humano, o mouse faz um trajeto e o ponto varia até `espalhar` px.
    Retorna False se não clicou (bot pausado/parando ou jogo coberto).
    """
    if acoes_bloqueadas():
        return False
    x, y = humano.espalhar(x, y, *espalhar)
    if not _esperar_jogo(lambda: jogo_no_ponto(x, y),
                         f"A janela \"{_nome_seguro(lambda: janela_no_ponto(x, y))}\" em ({int(x)}, {int(y)})"):
        return False
    with _input_lock:
        if acoes_bloqueadas():  # pausou enquanto esperava a vez do mouse
            return False
        try:
            humano.clicar(x, y, botao)
        except pydirectinput.FailSafeException:
            raise _failsafe() from None
    return True


def tecla_no_ponto(x, y, tecla, espalhar=(0, 0)):
    """
    Põe o mouse em (x, y) e aperta a tecla COM O MOUSE PARADO ALI (ex.: ball: mouse em cima do corpo + "2").
    Segura o mouse o tempo todo: nenhuma outra thread mexe nele entre mover e apertar.
    Retorna False se não fez (pausado/parando ou jogo coberto).
    """
    if acoes_bloqueadas():
        return False
    x, y = humano.espalhar(x, y, *espalhar)
    if not _esperar_jogo(lambda: jogo_no_ponto(x, y),
                         f"A janela \"{_nome_seguro(lambda: janela_no_ponto(x, y))}\" em ({int(x)}, {int(y)})"):
        return False
    with _input_lock:
        if acoes_bloqueadas():
            return False
        try:
            humano.mover_mouse(x, y)
            time.sleep(humano.variar(0.08))  # o jogo registra o mouse em cima antes da tecla
            with _teclado_lock:
                humano.tecla(tecla)
        except pydirectinput.FailSafeException:
            raise _failsafe() from None
    return True


# Botões laterais do mouse (pydirectinput não tem): enviados direto pelo Windows
_XBOTOES = {"mouse4": 1, "mouse5": 2}
TECLAS_EXTRAS = set(_XBOTOES)


def _botao_lateral(qual):
    if humano.EM_TESTE:
        return  # teste: nunca aperta botão de verdade
    import ctypes
    from ctypes import wintypes

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

    for flag in (0x0080, 0x0100):  # XDOWN, XUP
        inp = INPUT(0, MOUSEINPUT(0, 0, qual, flag, 0, None))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.03)


def apertar_combo(teclas):
    """Aperta teclas juntas (ex.: ["ctrl", "q"]): segura as primeiras e aperta a última."""
    if acoes_bloqueadas():
        return False
    if not _esperar_jogo(jogo_em_foco, f"A janela ativa \"{_nome_seguro(_titulo_ativa)}\" ({'+'.join(teclas)})"):
        return False
    with _teclado_lock:
        if acoes_bloqueadas():
            return False
        try:
            for t in teclas[:-1]:
                humano.pydirectinput.keyDown(t, _pause=False)  # (nos testes vira nada)
                time.sleep(humano.variar(0.06))
            humano.tecla(teclas[-1])
        except pydirectinput.FailSafeException:
            raise _failsafe() from None
        finally:
            for t in reversed(teclas[:-1]):
                humano.pydirectinput.keyUp(t, _pause=False)
    return True


def apertar(tecla):
    """Aperta a tecla no jogo. Retorna False se não apertou (pausado/parando ou jogo sem foco)."""
    if acoes_bloqueadas():
        return False
    if not _esperar_jogo(jogo_em_foco, f"A janela ativa \"{_nome_seguro(_titulo_ativa)}\" (tecla {tecla})"):
        return False
    with (_input_lock if tecla in _XBOTOES else _teclado_lock):
        if acoes_bloqueadas():
            return False
        try:
            if tecla in _XBOTOES:
                _botao_lateral(_XBOTOES[tecla])
            else:
                humano.tecla(tecla)
        except pydirectinput.FailSafeException:
            raise _failsafe() from None
    return True
