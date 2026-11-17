"""Ball = mouse em cima do corpo + tecla 2 (sem clique). Sem mouse/teclado de verdade."""
import os, sys
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
eventos = []
humano.mover_mouse = lambda x, y: eventos.append(("mouse", int(x), int(y)))
humano.tecla = lambda t: eventos.append(("tecla", t))
humano.clicar = lambda x, y, botao="left": eventos.append(("clique", int(x), int(y)))
controle.jogo_no_ponto = lambda x, y: True
controle.jogo_em_foco = lambda: True
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
controle.tecla_no_ponto(700, 200, "2")
checar("mouse vai para o corpo ANTES da tecla 2, sem clique",
       eventos == [("mouse", 700, 200), ("tecla", "2")], f"({eventos})")
eventos.clear(); controle._pausado.set()
checar("pausado: não mexe o mouse nem aperta", controle.tecla_no_ponto(700, 200, "2") is False and not eventos)
controle._pausado.clear()
# no catch
import cv2, config, catch
config.CATCH_TENTATIVAS_ESPECIAL = 3; config.CATCH_PROCURA_S = 1.0  # este teste conta 3 balls
controle.esperar = lambda s: False
catch.CATCH_ATIVO = True; catch.TECLA_BALL = "2"; catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 283), 50.9
v = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(v, perfis, origem=(0, 0))
catch.corpo_piscando = lambda *a, **k: None
humano.espalhar = lambda x, y, a=0, b=0: (x, y)
class R:
    viu_icone = viu = False; corpos = []; empilhados = set()
    def pos_atual(self): return (3497, 1947, 11)
    def catch_feito(self): pass
    def marcar_tentado(self, k): pass
eventos.clear(); catch._balls_por_corpo.clear(); config.CATCH_BALL_MOUSE = True
catch.fazer_catch(None, R(), fim_de_luta=True)
cliques = [e for e in eventos if e[0] == "clique"]
pares = [(eventos[i], eventos[i + 1]) for i in range(len(eventos) - 1) if eventos[i + 1] == ("tecla", "2")]
checar("catch: 3 balls com mouse em cima do corpo + 2, nenhum clique",
       len(pares) == 3 and not cliques and all(p[0] == ("mouse", 788, 130) for p in pares), f"({eventos[:4]})")
eventos.clear(); catch._balls_por_corpo.clear(); config.CATCH_BALL_MOUSE = False
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("opção desligada: jeito antigo (tecla e depois clique)", [e[0] for e in eventos[:2]] == ["tecla", "clique"] and
       any(e[0] == "clique" for e in eventos), f"({eventos[:3]})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
