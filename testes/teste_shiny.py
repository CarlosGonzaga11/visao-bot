"""Shiny automático (cor rara). Usa as cores tiradas dos prints reais; não grava nada em disco."""
import glob
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import cv2
import numpy as np
import shiny
_LER = shiny.ler_criaturas  # original (um teste troca por uma falsa)
import catch

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(ok)
    print(("✅" if ok else "❌") + f" {nome} {extra}")


# ---- assinaturas reais tiradas dos prints ----
amostras = {"shiny": [], "pet": [], "sem": 0}
for f in sorted(glob.glob(os.path.join(DADOS, "especial_16-4*_limpo.png"))):
    cr, _ = shiny.ler_criaturas(cv2.imread(f), (0, 0), (534, 280), 51)
    for sqm, faixa, px in cr:
        if faixa == shiny.SEM_COR:
            amostras["sem"] += 1
        elif 94 <= faixa <= 97:
            amostras["shiny"].append((faixa, px))
        elif faixa >= 101 and faixa <= 104:
            amostras["pet"].append((faixa, px))
checar("prints: Marowak normal = sem cor, shiny ~96, Gyarados ~102",
       amostras["sem"] >= 3 and len(amostras["shiny"]) >= 5 and len(amostras["pet"]) >= 4,
       f"(sem cor {amostras['sem']}, shiny {[a[0] for a in amostras['shiny']]}, pet {[a[0] for a in amostras['pet']]})")
PET = amostras["pet"][0]
SHINY = amostras["shiny"][0]
NORMAL = (shiny.SEM_COR, None)


def hunt(aprendiz, rodadas, t0=0.0, com_pet_sozinho=5, shiny_em=None, shiny_vezes=0, cor_shiny=SHINY):
    """Simula a hunt: pet sozinho entre lures, lures com 5 Marowak normais + pet, e talvez um shiny."""
    t = t0
    achou = None
    for _ in range(com_pet_sozinho):
        aprendiz.observar([((1, 0), *PET)], 0, (3480, 1950, 11), t)
        t += 0.5
    for i in range(rodadas):
        criaturas = [((k - 2, 2), *NORMAL) for k in range(5)] + [((1, 0), *PET)]
        if shiny_em is not None and i >= shiny_em and i < shiny_em + shiny_vezes:
            criaturas.append(((-3, -1), *cor_shiny))
        r = aprendiz.observar(criaturas, 5, (3480, 1950, 11), t)
        achou = achou or r
        t += 0.5
    return achou


a = shiny.AprendizShiny()
r = hunt(a, 30)
checar("hunt sem shiny: nada", r is None)
checar("pet aprendido (cor do Gyarados)", a.eh_pet(PET[0]) and not a.eh_pet(SHINY[0]), f"(pet {a.faixas_do_pet()})")
r = hunt(a, 12, t0=100, com_pet_sozinho=0, shiny_em=2, shiny_vezes=8)
checar("shiny aparece (fica uns segundos): detectado", r is not None and abs(r[0] - 96) <= 2, f"({r and r[0]})")

a2 = shiny.AprendizShiny()
hunt(a2, 30)
r = hunt(a2, 12, t0=100, com_pet_sozinho=0, shiny_em=2, shiny_vezes=2)
checar("cor rara só 1 s (efeito de magia): NÃO vira shiny", r is None)

a3 = shiny.AprendizShiny()
r = hunt(a3, 30, com_pet_sozinho=0, shiny_em=10, shiny_vezes=8)
checar("sem saber a cor do pet: não decide nada", r is None)

a4 = shiny.AprendizShiny()
hunt(a4, 30)
vermelho = (1, SHINY[1])
r = hunt(a4, 12, t0=100, com_pet_sozinho=0, shiny_em=2, shiny_vezes=8, cor_shiny=vermelho)
checar("vermelho (sangue/efeito): não vira shiny", r is None)

a5 = shiny.AprendizShiny()
hunt(a5, 30)
r = hunt(a5, 12, t0=100, com_pet_sozinho=0, shiny_em=2, shiny_vezes=8, cor_shiny=PET)
checar("criatura da cor do pet: não vira shiny", r is None)

# ---- perfil criado a partir do shiny ----
pixels = [px for f, px in amostras["shiny"]]
perfil = shiny.perfil_da_cor(96, pixels, (3480, 1950, 11), a.faixas_do_pet())
checar("perfil: pega a cor do shiny e deixa a do Gyarados de fora",
       perfil and perfil["h"][0] <= 96 <= perfil["h"][1] and perfil["h"][1] <= 99, f"({perfil and perfil['h']})")
checar("perfil: pelo corpo, com local e mínimo de pixels", perfil["pelo_corpo"] and perfil["local"] == [3480, 1950, 11]
       and perfil["min_corpo"] >= 60)

# o perfil automático acha os 2 corpos azuis do print do usuário colados num print do jogo
S = DADOS
catch.PLAYER_TILE_XY, catch.SQM_PX = (534, 280), 50.9
img = cv2.imread(os.path.join(DADOS, "especial_16-41-54_limpo.png"))
img2 = img.copy()
corpos = cv2.imread(os.path.join(S, "marowak_shiny.png"))[120:225, 20:200]
img2[300:300 + corpos.shape[0], 594:594 + corpos.shape[1]] = corpos
achados = catch.encontrar_corpos(img2, [perfil], origem=(0, 0))
checar("perfil automático acha os 2 corpos do shiny", len(achados) == 2, f"({[a[3] for a in achados]})")
falsos = []
for f in sorted(glob.glob(os.path.join(DADOS, "especial_16-4*_limpo.png"))):
    falsos += catch.encontrar_corpos(cv2.imread(f), [perfil], origem=(0, 0))
checar("perfil automático: nada de corpo falso nos prints (Gyarados/hotbar/shiny vivo)", not falsos,
       f"({[a[3] for a in falsos]})")

# cenário: a cor não existe no chão da caverna -> pode criar
_, caixas = shiny.ler_criaturas(img, (0, 0), (534, 280), 51)
checar("cor do shiny não existe no cenário da caverna", not shiny.cor_no_cenario(img, perfil, caixas))
# cenário com essa cor (ex.: cristal azul no chão, longe das criaturas) -> não cria
img3 = img.copy()
img3[150:190, 900:960] = corpos[40:80, 40:100]
checar("cor que existe no cenário: perfil recusado", shiny.cor_no_cenario(img3, perfil, caixas))

# ---- vigia completa (sem disco): grava o perfil só 1 vez ----
gravados = []
catch.carregar_perfis = lambda: []
catch.salvar_perfis = lambda ps: gravados.append(ps)
v = shiny.VigiaShiny(lambda: (3480, 1950, 11))
v.aprendiz = a5  # já sabe pet e cores comuns
seq = iter([[((-3, -1), *SHINY)]] * 10)


class Cfg:
    GAME_VIEW = {"left": 0, "top": 0, "width": 1069, "height": 560}


shiny.ler_criaturas = lambda img, o, p, q: (next(seq) + [((k - 2, 2), *NORMAL) for k in range(5)], caixas)
relogio = [200.0]
shiny.time.time = lambda: relogio[0]
for _ in range(10):
    v.uma_volta(None, lambda sct, reg: img, lambda sct: [1] * 6, Cfg)
    relogio[0] += 0.5
checar("vigia: cria o perfil do shiny 1 vez só", len(gravados) == 1 and gravados[0][-1]["automatico"],
       f"({len(gravados)} gravações)")

# ---- nomes verdes não entram na cor das criaturas (17:25 o bot criou "shiny verde" pelo nome) ----
p1727 = cv2.imread(os.path.join(DADOS, "print_17-27-49.png"))[1:561, 50:1118]
cr, _ = _LER(p1727, (0, 0), (534, 283), 50.9)
checar("17:27: nenhuma criatura com cor verde (só o Gyarados ~103)", all(f == shiny.SEM_COR or f > 90 for _, f, _ in cr),
       f"({[(s, f) for s, f, _ in cr]})")
texto = np.zeros((200, 3), np.uint8); texto[:, 0] = 60; texto[:, 1] = 250; texto[:, 2] = 200
checar("cor pura de texto (saturação no máximo) não vira perfil",
       shiny.perfil_da_cor(60, [texto, texto], (1, 1, 1), set()) is None)

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
os._exit(0 if all(resultados) else 1)
