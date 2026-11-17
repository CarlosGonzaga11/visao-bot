"""
Catch do especial com o resultado lido no CHAT ("Sorry, your pokeball broke.").
Corpo real (print 17:33, Marowak shiny a 5 sqm). Nenhum mouse/teclado de verdade.
"""
import os, sys
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
eventos = []
humano.mover_mouse = lambda x, y: eventos.append(("mouse", int(x), int(y)))
humano.tecla = lambda t: eventos.append(("tecla", t))
humano.clicar = lambda x, y, botao="left": eventos.append(("clique", int(x), int(y)))
humano.espalhar = lambda x, y, a=0, b=0: (x, y)
controle.jogo_no_ponto = lambda x, y: True
controle.jogo_em_foco = lambda: True
controle.esperar = lambda s: False
res = []


def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}", flush=True)


import cv2, config, catch, catch_resultado
config.CATCH_TENTATIVAS_ESPECIAL = 6; config.CATCH_PROCURA_S = 1.0
catch.CATCH_ATIVO = True; catch.TECLA_BALL = "2"; catch.LOOT_ANTES_BALL = False
config.CATCH_CHEGAR_PERTO = False; config.CATCH_BALL_MOUSE = True
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 283), 50.9
catch.corpo_piscando = lambda *a, **k: None
catch.REVER_DEPOIS_BALL_S = 0.0
v = cv2.imread(os.path.join(DADOS, "print_17-33-12.png"))[1:561, 50:1118]
marowak = next(p for p in catch.carregar_perfis() if p["id"] == "marowak_shiny")
catch.carregar_perfis = lambda: [marowak]

# 1) o mundo: depois da 1ª ball o corpo SOME da imagem (animação / Gyarados por cima)
balls = lambda: sum(1 for e in eventos if e == ("tecla", "2"))
catch.corpos_na_tela = lambda sct, perfis: catch.encontrar_corpos(v, perfis, origem=(0, 0)) if balls() == 0 else []


class R:
    viu_icone = viu = False; corpos = []; empilhados = set()
    def pos_atual(self): return (3497, 1947, 11)
    def catch_feito(self): pass
    def marcar_tentado(self, k): pass


def chat(sequencia):
    """Linhas do chat a cada leitura (antes/depois de cada ball)."""
    it = iter(sequencia)
    ultimo = [[]]
    def foto(sct):
        try:
            ultimo[0] = next(it)
        except StopIteration:
            pass
        return list(ultimo[0])
    return foto


VELHO = ["18:01 Loot of Marowak: 9 earth balls and Bone."]
QUEBROU = VELHO + ["18:02 Sorry, your pokeball broke."]
PEGOU = QUEBROU + ["18:02 Loot of Marowak: 8 earth balls and Bone."]

# ball 1 quebra (chat), corpo some da imagem; ball 2 sem quebra -> para
eventos.clear(); catch._balls_por_corpo.clear()
catch_resultado.foto = chat([VELHO, QUEBROU, QUEBROU, PEGOU, PEGOU])
catch.fazer_catch(None, R(), fim_de_luta=True)
alvos = [eventos[i] for i in range(len(eventos) - 1) if eventos[i + 1] == ("tecla", "2")]
checar("ball quebrou e o corpo sumiu da imagem: taca de NOVO no mesmo sqm", balls() == 2
       and alvos[0] == alvos[1], f"({alvos})")

# sem quebra no chat e o corpo sumiu: 1 ball só (pegou)
eventos.clear(); catch._balls_por_corpo.clear()
catch_resultado.foto = chat([VELHO, VELHO + ["18:02 Loot of Marowak: 8 earth balls and Bone."]] * 2)
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("chat sem 'broke' e o corpo sumiu: pegou, 1 ball só", balls() == 1, f"({balls()} balls)")

# quebra sempre: vai até o limite (6) e não para antes
eventos.clear(); catch._balls_por_corpo.clear()
seq = [VELHO]
linhas = list(VELHO)
for i in range(8):
    linhas = linhas + [f"18:0{i} Sorry, your pokeball broke."]
    seq += [linhas, linhas, linhas]
catch_resultado.foto = chat(seq)
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("quebra toda vez: usa as 6 tentativas do especial", balls() == 6, f"({balls()} balls)")

# chat ilegível (outra aba aberta): jeito antigo — corpo sumiu, para
eventos.clear(); catch._balls_por_corpo.clear()
catch_resultado.foto = lambda sct: []
catch.fazer_catch(None, R(), fim_de_luta=True)
checar("chat ilegível: decide pelo corpo como antes (1 ball)", balls() == 1, f"({balls()} balls)")

# leitor de verdade nos prints com a mensagem
import glob
img = cv2.imread(os.path.join(DADOS, "print_22-29-23.png"))
linhas = catch_resultado.ler_linhas(img[595:670, 15:640])
checar("OCR acha 'Sorry, your pokeball broke.' no print real 22:29", catch_resultado.quebrou(linhas), f"{linhas[-2:]}")
checar("'Loot of Marowak: 9 earth balls' NÃO é ball quebrada",
       not catch_resultado.quebrou(["18:21 Loot of Marowak: 9 earth balls and Bone"]))
checar("broke que JÁ estava no chat não conta de novo",
       catch_resultado.resultado(QUEBROU, QUEBROU + ["18:03 Loot of Marowak: 2 earth balls"]) == "sem_quebra")
checar("mesma frase no mesmo minuto conta (2ª quebra)",
       catch_resultado.resultado(QUEBROU, QUEBROU + ["18:02 Sorry, your pokeball broke."]) == "quebrou")

print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
