"""Shiny morreu com magia por cima do corpo (print 18:39): procura até o efeito passar e taca. Sem mouse real."""
import os, sys, time
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import cv2
import controle, humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
acoes = []
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": acoes.append(("clique", round(x), round(y))) or True
controle.tecla_no_ponto = lambda x, y, t, espalhar=(0, 0): (acoes.append(("tecla", t)), acoes.append(("clique", round(x), round(y))), True)[2]
controle.esperar = lambda s: time.sleep(min(s, 0.4)) or False
import config, catch
salvos = []
cv2.imwrite = lambda a, img: salvos.append(a) or True
catch.CATCH_ATIVO = True; catch.TECLA_BALL = "2"; catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False; config.CATCH_PROCURA_S = 5.0; config.CATCH_TENTATIVAS_ESPECIAL = 6
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 283), 50.9
catch.corpo_piscando = lambda *a, **k: None
raio = cv2.imread(os.path.join(DADOS, "sem_corpo_18-39-26.png"))
corpo = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
class R:
    def __init__(s, viu): s.viu_icone, s.viu, s.corpos, s.empilhados = viu, False, [], set()
    def pos_atual(s): return (3497, 1947, 11)
    def catch_feito(s): s.viu_icone = s.viu = False
    def marcar_tentado(s, k): pass
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
# 1) raio por cima nos primeiros 2 s, depois o corpo aparece
t0 = [0.0]
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(raio if time.time() - t0[0] < 2.0 else corpo, perfis, origem=(0, 0))
catch.capturar = lambda sct, reg: raio
acoes.clear(); catch._balls_por_corpo.clear(); catch._especial_sem_ball[0] = 0.0
t0[0] = time.time()
catch.fazer_catch(None, R(True), fim_de_luta=True)
balls = [acoes[i + 1] for i, a in enumerate(acoes[:-1]) if a == ("tecla", "2")]
checar("efeito por cima do corpo: espera passar e TACA a ball", balls and all(b[1:] == (788, 130) for b in balls),
       f"({len(balls)} balls em {sorted(set(balls))})")
checar("shiny: até 6 tentativas no corpo (não só 3)", len(balls) == 6, f"({len(balls)})")
# 2) shiny visto, corpo nunca aparece: procura ~5 s e avisa
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(raio, perfis, origem=(0, 0))
acoes.clear(); salvos.clear(); catch._balls_por_corpo.clear(); catch._especial_sem_ball[0] = 0.0
t = time.time(); catch.fazer_catch(None, R(True), fim_de_luta=True); gasto = time.time() - t
checar("corpo nunca aparece: procura ~5 s e avisa com print", 4.5 <= gasto <= 7.5 and len(salvos) == 1, f"({gasto:.1f}s)")
# 3) luta sem shiny: não espera nada
t = time.time(); catch.fazer_catch(None, R(False), fim_de_luta=True); gasto = time.time() - t
checar("luta sem shiny: não fica esperando", gasto < 1.5, f"({gasto:.1f}s)")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
