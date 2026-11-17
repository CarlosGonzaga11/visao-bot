"""
Sobrevivência (provas de 07/11):
  - 21:05: Marowak shiny VIVO com ~1% colado no personagem: a barrinha vazia (nome cobrindo a borda
    de cima) era invisível → "fugiu", catch tacava ball no shiny vivo. Agora é vista.
  - 20:44/20:48/21:01: os 3 danos do dia foram no REVIVE com monstro a 1 sqm (pet fraco = "não corro").
    Agora: monstro colado + pet vivo → sai de perto antes do revive.
Sem cliques reais.
"""
import os
import sys

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA)
os.chdir(PASTA)
import cv2
import controle
import humano
humano.mover_mouse = lambda *a, **k: None
humano.clicar = lambda *a, **k: None
humano.tecla = lambda *a, **k: None
import bot
import catch
import config
import tela

res = []


def checar(n, ok, e=""):
    res.append(bool(ok))
    print(("✅" if ok else "❌") + f" {n} {e}")


def tela_jogo(arq):
    im = cv2.imread(os.path.join(DADOS, arq))
    return im[1:561, 50:1118] if im.shape[0] > 600 else im


# ---------- 1. barra vazia (percepção) ----------
v = tela_jogo("print_21-05-47.png")
bot.GAME_VIEW = {"left": 50, "top": 1, "width": v.shape[1], "height": v.shape[0]}
bot.PLAYER_TILE_XY, bot.SQM_PX = (584, 304), 50.9
barras = tela.encontrar_barras_criaturas(v, (50, 1))
vazia = [b for b in barras if b[2] <= 3]
checar("21:05: barrinha vazia do shiny é vista", [(b[0], b[1]) for b in vazia] == [(520, 204)], f"{barras}")
checar("21:05: barra do pet (cheia de cor) continua igual", (571, 153, 13, False) in [tuple(map(lambda z: z if not hasattr(z, 'item') else z.item(), b)) for b in barras])
cri = bot.criaturas_na_imagem(v)
checar("21:05: shiny a 1 sqm de você (-1, -1)", (-1, -1) in cri, f"{sorted(cri)}")
class _P:
    def atual(self):
        return (3462, 1937, 11)


bot.POS = _P()
bot.PET_ABS[0] = (3462, 1935, 11)  # na luta o bot lembra onde o pet ficou (pokestop): (0, -2)
pet, _ = bot.achar_pet(list(cri), 1)
checar("21:05: pet lembrado + shiny colado = perigo imediato",
       pet == (0, -2) and bool(bot.colados_em_mim(list(cri), pet)) and bot.em_perigo(list(cri), pet), f"pet {pet}")

original = tela._barras_vazias
tela._barras_vazias = lambda *a: []
sem = bot.criaturas_na_imagem(v)
tela._barras_vazias = original
checar("(prova do bug) sem a correção ele sumia: só o pet na tela → 'fugiram'", len(sem) <= 1 and (-1, -1) not in sem, f"{sorted(sem)}")

perfil = {"id": "marowak_shiny", "nome": "Marowak shiny", "tipo": "especial", "h": [93, 99], "s": [130, 255],
          "v": [55, 245], "pixels": 375, "local": [3475, 1950, 11], "amostra": None, "pelo_corpo": True, "min_corpo": 80}
catch.PLAYER_TILE_XY, catch.SQM_PX = (584, 304), 50.9
corpos = catch.encontrar_corpos(v, [perfil], (50, 1))
checar("21:05: catch NÃO vê 'corpo' no shiny vivo", corpos == [], f"{corpos}")
tela._barras_vazias = lambda *a: []
corpos_antes = catch.encontrar_corpos(v, [perfil], (50, 1))
tela._barras_vazias = original
checar("(prova do bug) sem a correção tacava ball no shiny vivo", len(corpos_antes) == 1, f"{[c[3] for c in corpos_antes]}")

checar("19:40: os 2 Marowak + Gyarados quase mortos são vistos (não 'fugiram')",
       len([b for b in tela.encontrar_barras_criaturas(tela_jogo("print_19-40-55.png")) if b[2] <= 3]) == 3)
checar("20:48 (caixa-preta): os 2 Marowak quase mortos são vistos",
       len([b for b in tela.encontrar_barras_criaturas(tela_jogo("caixa_20-48-27_q08.jpg")) if b[2] <= 3]) == 2)
falsos = []
for arq in sorted(os.listdir(DADOS)):
    if arq.startswith(("especial_", "print_17", "marowak", "shiny_vivo", "sem_corpo")):
        falsos += [(arq, b) for b in tela.encontrar_barras_criaturas(tela_jogo(arq)) if b[2] <= 3]
checar("prints sem monstro quase morto: nenhuma barra vazia inventada", not falsos, f"{falsos}")

# ---------- 2. revive com monstro colado ----------
config.SAIR_DA_BOX = True
config.BOX_DIAGONAL_SQM = 3
config.DISTANCIA_MONSTROS = 4
config.BOX_HP_SOLTAR = 60
config.CORRIDAS_POR_BOX = 2
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.MAPA.salvar = lambda: None
bot.limites_clique = lambda sct: ((-9, 9), (-4, 4))
controle.esperar = lambda s: False
controle.ultimo_revive = 0.0
bot.carregar_calibracao = lambda: {"poke_hp": {"x": 1}}
hp_pet = [40]
bot.ler_barra = lambda sct, barra: hp_pet[0]


class Pos:
    p = (1000, 1000, 7)

    def atual(self):
        return self.p


bot.POS = Pos()
acoes = []
mundo = {"cri": set()}  # criaturas em coordenada ABSOLUTA (o personagem anda, elas ficam)


def clicar(x, y, espalhar=(0, 0), botao="left"):
    d = (round((x - bot.PLAYER_TILE_XY[0]) / bot.SQM_PX), round((y - bot.PLAYER_TILE_XY[1]) / bot.SQM_PX))
    acoes.append(("clique", d))
    Pos.p = (Pos.p[0] + d[0], Pos.p[1] + d[1], 7)
    return True


controle.clicar = clicar
controle.apertar = lambda t: acoes.append(("tecla", t)) or True
bot.sqm_ocupados = lambda sct: {(a - Pos.p[0], b - Pos.p[1]) for a, b in mundo["cri"]}


def cenario(pet_rel, monstros_rel):
    Pos.p = (1000, 1000, 7)
    mundo["cri"] = {(1000 + x, 1000 + y) for x, y in [pet_rel] + monstros_rel}
    bot.PET_ABS[0] = None
    acoes.clear()


# 20:48: pet no pokestop a 4 sqm (27%), um monstro colado em você na diagonal
hp_pet[0] = 27
cenario((0, -4), [(-1, -4), (1, -4), (-1, -1)])
livre = bot.afastar_antes_do_revive("sct")
rel = {(a - Pos.p[0], b - Pos.p[1]) for a, b in mundo["cri"]}
checar("20:48: monstro colado + pet 27% → sai de perto antes do revive",
       livre and acoes and acoes[0][0] == "clique" and not bot.colados_em_mim(list(rel), (0, -4)), f"{acoes} → {sorted(rel)}")

hp_pet[0] = 0
cenario((0, -4), [(-1, -4), (-1, -1)])
checar("pet MORTO + monstro colado → revive já (não fica andando)", bot.afastar_antes_do_revive("sct") is False and not acoes, f"{acoes}")

hp_pet[0] = 50
cenario((0, -4), [(-1, -4), (1, -4), (3, -3)])
checar("ninguém perto (monstro a 3 sqm) → nem se mexe", bot.afastar_antes_do_revive("sct") is True and not acoes, f"{acoes}")

# ---------- 3. ameaça: monstro FORA da box a 2 sqm, vindo (caixa-preta 22:07 e 22:10) ----------
# 22:10, 0,25 s antes do revive: pet (-3,-4) com 1 monstro; outro a (2,-1) vindo em você
cri = [(-4, -4), (-3, -4), (2, -1)]
checar("22:10: monstro a 2 sqm fora da box = ameaça", bot.ameacas(cri, (-3, -4)) == [(2, -1)])
checar("22:10: (prova) a regra antiga (só colado) não via", bot.colados_em_mim(cri, (-3, -4)) == [])
# 22:07, 0,75 s antes do revive: pet (-2,-1); dois a 2 sqm vindo
cri = [(-2, -1), (0, -3), (0, 2), (2, 1)]
checar("22:07: os dois a 2 sqm são ameaça", sorted(bot.ameacas(cri, (-2, -1))) == [(0, 2), (2, 1)])
# monstro da box (colado no pet) a 2 sqm de você NÃO é ameaça: está brigando com o pet
checar("monstro da box a 2 sqm (colado no pet) não é ameaça", bot.ameacas([(0, -3), (1, -2)], (0, -3)) == [])

hp_pet[0] = 60
cenario((-3, -4), [(-4, -4), (2, -1)])
bot.afastar_antes_do_revive("sct")
checar("22:10 refeito: sai ANTES do revive e fica a 3+ sqm do que vinha",
       acoes and acoes[0][0] == "clique" and min(max(abs(x - (Pos.p[0] - 1000)), abs(y - (Pos.p[1] - 1000))) for x, y in [(2, -1)]) >= 3,
       f"{acoes}")

# ---------- 4. revive longe (22:26: Marowak SOLTO a 4 sqm, BONE RUSH no "Gyarados, Back!", −66%) ----------
def rel_agora():
    return [(a - Pos.p[0], b - Pos.p[1]) for a, b in mundo["cri"]]


def pet_agora(pet_abs):
    return (pet_abs[0] - Pos.p[0], pet_abs[1] - Pos.p[1])


hp_pet[0] = 49
bot.REVIVE_ADIADOS[0] = 0
cenario((0, -4), [(-1, -4), (1, -4), (0, -5), (4, 0)])  # box em cima; o solto à direita, a 4 sqm
bot.PET_ABS[0] = (1000, 996, 7)
checar("22:26: lá, revive NÃO era seguro (solto a 4 sqm)", not bot.revive_seguro_em((0, 0), rel_agora(), (0, -4)))
ok = bot.preparar_revive("sct")
pet = pet_agora((1000, 996))
dbox, dsolto = bot.situacao_revive((0, 0), rel_agora(), pet)
checar("22:26 refeito: só revive depois de ficar box ≥4 e solto ≥6 (ou adia)",
       (ok and dbox >= 4 and dsolto >= 6) or (ok is False and bot.REVIVE_ADIADOS[0] == 1),
       f"(ok={ok}, box {dbox}, solto {dsolto}, cliques {[a for a in acoes if a[0] == 'clique']})")
checar("22:26 refeito: andou para longe antes", any(a[0] == "clique" for a in acoes), f"{acoes}")

# já seguro: nem se mexe
hp_pet[0] = 60
bot.REVIVE_ADIADOS[0] = 0
cenario((0, -5), [(-1, -5), (1, -5)])
checar("box a 4+ e nenhum solto: revive na hora, sem andar", bot.preparar_revive("sct") is True and not acoes, f"{acoes}")

# pet morto: revive já (mesmo com solto perto)
hp_pet[0] = 0
cenario((0, -4), [(-1, -4), (3, 0)])
checar("pet morto: revive já, sem andar", bot.preparar_revive("sct") is True and not acoes, f"{acoes}")

# sem lugar para ir (tudo bloqueado): adia 2x e depois revive assim mesmo
hp_pet[0] = 60
bot.REVIVE_ADIADOS[0] = 0
bot.MAPA.esta_bloqueado = lambda p: True
cenario((0, -4), [(-1, -4), (3, 0)])
r = [bot.preparar_revive("sct") for _ in range(3)]
checar("preso: adia o revive 2x e na 3ª revive assim mesmo", r == [False, False, True], f"{r}")
bot.MAPA.esta_bloqueado = lambda p: False
bot.REVIVE_ADIADOS[0] = 0

# ---------- 4b. 08/11: box LONGE e "solto a 5" falso (monstro da box a 2-3 sqm do pet) ----------
config.BOX_RAIO_SQM = 3
hp_pet[0] = 80
bot.REVIVE_ADIADOS[0] = 0
cenario((0, -7), [(-1, -7), (1, -7), (0, -5), (2, -6)])  # box a 5+ sqm de você; (0,-5) está a 2 do pet
ok = bot.preparar_revive("sct")
checar("08/11: box longe (monstro a 2 sqm do PET é da box): revive na hora, sem andar e sem adiar",
       ok is True and not acoes and bot.REVIVE_ADIADOS[0] == 0, f"(ok={ok}, {acoes})")
checar("monstro a 2-3 sqm do pet conta como BOX (não solto)",
       bot.situacao_revive((0, 0), [(0, -7), (0, -5), (2, -6)], (0, -7))[1] == 99)
# 22:26 continua protegido: o Marowak do Bone Rush estava a 4 sqm do PET (fora da box) → solto
checar("22:26: monstro a 4 sqm do pet (fora da box) continua SOLTO",
       bot.situacao_revive((0, 0), [(3, -4), (4, 0)], (3, -4))[1] == 4)
# pet fraco: não adia (adiar deixava o pet morrer — 3x em 08/11)
hp_pet[0] = 40
bot.REVIVE_ADIADOS[0] = 0
bot.MAPA.esta_bloqueado = lambda p: True  # sem lugar para ir
cenario((0, -4), [(-1, -4), (3, 0)])
checar("pet com 40% e sem lugar para ir: revive agora (não adia)", bot.preparar_revive("sct") is True
       and bot.REVIVE_ADIADOS[0] == 0)
bot.MAPA.esta_bloqueado = lambda p: False
bot.REVIVE_ADIADOS[0] = 0

# ordem real dentro da luta (modo revive): o passo para longe sai ANTES da tecla do revive
hp_pet[0] = 45
cenario((0, -4), [(-1, -4), (1, -4), (0, -1)])
bot.modos.TECLA_ATAQUE, bot.modos.TECLA_REVIVE, bot.modos.REVIVE_CLICAR_POKE = "a", "r", False
bot.modos.COMBO_DURACAO, bot.modos.REVIVE_ESPERA = 0.01, 0.01
bot.modos.REVIVE_APOS_LURE = False
config.TECLA_REVIVE = "r"
config.IGNORAR_SOBRA = False
config.CLICAR_ALVO = False
bot.MAGIA_AGRUPAR_ATIVA = False
bot.POKESTOP_ATIVO = False
bot.ORDER_DEPOIS_LUTA = False
bot.fight_mode = lambda q: None
bot.checar_catch = lambda sct: None
bot.fazer_catch = lambda *a, **k: None
bot.descansar = lambda sct: None
bot.efeitos.curar_se_precisar = lambda sct: False
voltas = [0]


def inimigos(sct):
    voltas[0] += 1
    return [{"alvo": True, "xy": (5, 5)}] * 3 if voltas[0] < 9 else []


bot.inimigos = inimigos
tela.ler_inimigos = lambda sct: [1]
bot.ESTRATEGIA = bot.modos.Revive()
config.SILENCIO_POS_COMBO_S = 0  # sem silence/stun: comportamento de antes
config.POKES_CONTROLE = {}       # (o ajustes.json pode ter silence guardado por pokémon: ele valeria por cima)
bot.combater_ate_limpar("sct", bot.LOTOU)
teclas = [a for a in acoes if a[0] == "tecla"]
i_rev = next((i for i, a in enumerate(acoes) if a == ("tecla", "r")), None)
i_cli = next((i for i, a in enumerate(acoes) if a[0] == "clique"), None)
checar("luta (modo revive, sem silence): sai de perto e SÓ DEPOIS aperta o revive",
       i_rev is not None and i_cli is not None and i_cli < i_rev, f"{acoes[:6]}")

# ---------- 5. 08/11: depois do combo a box fica SILENCIADA (Gyarados ~3 s): revive na hora ----------
config.SILENCIO_POS_COMBO_S = 3.0
hp_pet[0] = 45
cenario((0, -4), [(-1, -4), (1, -4), (0, -1)])  # o monstro colado em você está na BOX (3 do pet): tomou o combo
voltas[0] = 0
bot.ESTRATEGIA = bot.modos.Revive()
bot.combater_ate_limpar("sct", bot.LOTOU)
i_rev = next((i for i, a in enumerate(acoes) if a == ("tecla", "r")), None)
cliques_antes = [a for a in acoes[:i_rev or 0] if a[0] == "clique"]
checar("com silence: combo → revive NA HORA, sem correr da box", i_rev is not None and not cliques_antes,
       f"{acoes[:6]}")

# solto (fora da box, não tomou o combo) perto de você: mesmo no silence, se afasta dele antes
bot.COMBO_FIM[0] = __import__("time").time()
cenario((0, -4), [(-1, -4), (1, -4), (3, 0)])  # (3,0) a 4 do pet: SOLTO, a 3 de você
ok = bot.preparar_revive("sct", silencio=True)
checar("com silence mas SOLTO a 3 sqm: ainda se afasta dele (Bone Rush 22:26)", any(a[0] == "clique" for a in acoes),
       f"(ok={ok}, {acoes})")
_t = __import__("time").time
bot.CONTROLE_BOX.comecar(_t(), "silence", 3.0, [(999, 996, 7)])
ativa = bot.em_silencio()
bot.CONTROLE_BOX.fim = _t() - 0.1
checar("janela de silêncio acaba depois de SILENCIO_POS_COMBO_S (menos a margem)", ativa and not bot.em_silencio())

# ---------- 6. silence x stun: só quem estava NA BOX no combo; stun confere se ficou preso ----------
config.CONTROLE_TIPO, config.SILENCIO_POS_COMBO_S, config.POKES_CONTROLE = "silence", 3.0, {}
cenario((0, -4), [(-1, -4), (1, -4), (0, -1)])  # (0,-1) colado em você, mas na box (3 do pet)
bot.iniciar_controle("sct")
cri = [(a - Pos.p[0], b - Pos.p[1]) for a, b in mundo["cri"]]
checar("silence: monstro da box colado em você NÃO é ameaça", not bot.ameacas(cri, (0, -4)), f"{bot.ameacas(cri, (0, -4))}")
checar("silence: revive pode sair parado (box silenciada)", bot.revive_seguro_em((0, 0), cri, (0, -4), True))
cri2 = cri + [(1, 1)]  # chegou DEPOIS do combo, colado em você: não tomou a magia
checar("monstro que chegou depois do combo continua sendo ameaça", (1, 1) in bot.ameacas(cri2, (0, -4)))
checar("...e o revive não sai com ele colado", not bot.revive_seguro_em((0, 0), cri2, (0, -4), True))

config.CONTROLE_TIPO = "stun"
cenario((0, -4), [(-1, -4), (1, -4), (0, -1)])
bot.iniciar_controle("sct")
cri = [(a - Pos.p[0], b - Pos.p[1]) for a, b in mundo["cri"]]
checar("stun: monstro preso no lugar não é ameaça", not bot.ameacas(cri, (0, -4)))
cri_andou = [m for m in cri if m != (0, -1)] + [(1, 0)]  # andou de (0,-1) para (1,0): stun não pegou
checar("stun: monstro que SAIU do lugar volta a ser ameaça", (1, 0) in bot.ameacas(cri_andou, (0, -4)))

config.POKES_CONTROLE, config.POKE_CACA = {"gyarados": {"tipo": "stun", "s": 4}}, "Gyarados"
checar("tipo/tempo por pokémon (POKES_CONTROLE)", bot.controle_box.parametros(config) == ("stun", 4.0))
config.SILENCIO_POS_COMBO_S, config.POKES_CONTROLE, config.POKE_CACA = 0, {}, ""
cenario((0, -4), [(-1, -4), (1, -4), (0, -1)])
bot.iniciar_controle("sct")
checar("tempo 0 = pet sem silence/stun: nada muda", not bot.em_silencio())

print(f"\n{sum(res)}/{len(res)} testes passaram")
os._exit(0 if all(res) else 1)
