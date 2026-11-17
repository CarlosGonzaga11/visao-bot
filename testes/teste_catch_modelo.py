"""
Especial pelo DESENHO (catch_modelo.py): Marowak shiny morto achado pelo modelo, não só pela cor.
Prints reais em tamanho real; nenhum clique de verdade.
"""
import glob
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import cv2
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None

import catch
import catch_modelo
import layout

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


def preparar(arq):
    """Mapa do print com o layout medido nele (como o bot faz na hora)."""
    img = cv2.imread(arq)
    h, w = img.shape[:2]
    det = layout.detectar(img=img, janela={"left": 0, "top": 0, "width": w, "height": h})
    if "game_view" not in det:  # medida falhou neste print: última medida boa (calibracao/layout_ok.json)
        det = {"game_view": {"left": 50, "top": 27, "width": 1069, "height": 560}, "sqm": 50.9, "centro": (584, 307)}
    gv = det["game_view"]
    catch.SQM_PX, catch.PLAYER_TILE_XY = det["sqm"], tuple(det["centro"])
    return img[gv["top"]:gv["top"] + gv["height"], gv["left"]:gv["left"] + gv["width"]], (gv["left"], gv["top"])


perfis = catch.carregar_perfis()
marowak = [p for p in perfis if p["id"] == "marowak_shiny"]
auto = [p for p in perfis if p.get("automatico")]
checar("perfil do Marowak shiny usa o modelo (desenho)", bool(marowak) and marowak[0].get("modelo") == "marowak_shiny")
checar("modelo carregado (2 recortes reais)", catch_modelo.carregar("marowak_shiny") is not None
       and len(catch_modelo.carregar("marowak_shiny")["recortes"]) == 2)

# 22:29: 1 shiny morto entre 3 Marowak normais mortos, Marowak vivos e o Gyarados
view, org = preparar(os.path.join(DADOS, "print_22-29-23.png"))
corpos = catch.encontrar_corpos(view, marowak + auto, org)
checar("22:29: acha SÓ o corpo do shiny, no sqm certo (-3, 0)", [c[3] for c in corpos] == [(-3, 0)],
       f"{[(c[3], c[4]['id']) for c in corpos]}")
checar("22:29: o perfil só de cor (shiny automático azul) não entra mais", all(c[4]["id"] == "marowak_shiny" for c in corpos))

for nome, esperado in [("print_17-06-03.png", (-1, 1)), ("print_17-33-12.png", (5, -3))]:
    view, org = preparar(os.path.join(DADOS, nome))
    corpos = catch.encontrar_corpos(view, marowak, org)
    checar(f"{nome[6:14]}: shiny morto ao lado de um Marowak normal -> só o shiny {esperado}",
           [c[3] for c in corpos] == [esperado], f"{[c[3] for c in corpos]}")

# sem shiny: nenhum falso (corpos normais, Gyarados, Hydro Pump, outras hunts)
falsos = []
for arq in sorted(glob.glob(os.path.join(DADOS, "print_*.png")) + glob.glob(os.path.join(DADOS, "alarme_*.png"))):
    if any(s in arq for s in ("22-29-23", "17-06-03", "17-33-12")):
        continue
    view, org = preparar(arq)
    if catch.encontrar_corpos(view, marowak, org):
        falsos.append(os.path.basename(arq))
checar("prints sem shiny: nenhum corpo falso", not falsos, f"{falsos}")
for arq in sorted(glob.glob(os.path.join(DADOS, "especial_*_limpo.png")) + [os.path.join(DADOS, "sem_corpo_18-39-26.png")]):
    catch.SQM_PX, catch.PLAYER_TILE_XY = 50.9, (534, 280)
    if catch.encontrar_corpos(cv2.imread(arq), marowak, (0, 0)):
        falsos.append(os.path.basename(arq))
checar("Magneton/Gyarados+Hydro Pump: nenhum corpo falso", not falsos, f"{falsos}")

# vivo: o mesmo desenho COM barra em cima não é corpo
view, org = preparar(os.path.join(DADOS, "print_22-29-23.png"))
catch._sqm_vivos_original = catch._sqm_vivos
catch._sqm_vivos = lambda img, o: {(-3, 0)}
checar("shiny VIVO (barra em cima) não vira corpo", not catch.encontrar_corpos(view, marowak, org))
catch._sqm_vivos = catch._sqm_vivos_original

catch.CATCH_ATIVO = True
checar("modelo sem local NÃO desliga as estrelinhas em outra hunt (Magneton)",
       not catch.corpo_substitui_estrelas((3480, 1950, 11)) or any(
           p.get("local") and catch.vale_aqui(p, (3480, 1950, 11)) for p in catch.perfis_pelo_corpo((3480, 1950, 11))))
checar("...e na hunt do Marowak (perfil com local) continua como antes",
       catch.corpo_substitui_estrelas((531, 1472, 6)) == any(p.get("local") for p in catch.perfis_pelo_corpo((531, 1472, 6))))

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
sys.exit(0 if all(resultados) else 1)
