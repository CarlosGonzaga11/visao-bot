"""Correr da box só N vezes por luta (padrão 2); luta nova zera. Sem cliques reais."""
import os, sys
PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")  # prints e imagens usados nos testes
sys.path.insert(0, PASTA); os.chdir(PASTA)
import controle, humano
humano.mover_mouse = lambda *a, **k: None  # nunca mexe o mouse de verdade
humano.clicar = lambda *a, **k: None; humano.tecla = lambda *a, **k: None
import bot, config
bot.ler_barra = lambda sct, barra: None
config.BOX_DIAGONAL_SQM = 3; config.DISTANCIA_MONSTROS = 4; config.SAIR_DA_BOX = True; config.CORRIDAS_POR_BOX = 2
bot.NAV_VIEW_DX, bot.NAV_VIEW_DY = (-9, 9), (-4, 4)
bot.MAPA.esta_bloqueado = lambda p: False
bot.MAPA.salvar = lambda: None
controle.esperar = lambda s: False
class Pos:
    def atual(self): return (1000, 1000, 7)
bot.POS = Pos()
cliques = []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": cliques.append(botao) or True
res = []
def checar(n, ok, e=""):
    res.append(bool(ok)); print(("✅" if ok else "❌") + f" {n} {e}")
pet = (0, -2)
cri = [pet, (-1, -2), (1, -2), (0, -3), (0, -1), (-1, -1), (1, -3)]  # você colado na box: perigo sempre
bot.CORRIDAS[0] = 0
# perigo (monstro a 2 sqm), mas NINGUÉM colado em você: só as 2 corridas normais
longe = [pet, (-1, -2), (1, -2), (0, -3), (1, -3), (-1, -3)]
bot.CORRIDAS[0] = 0; bot.EMERGENCIAS[0] = 0
corridas = sum(1 for _ in range(6) if bot.ir_para_diagonal(None, longe, pet))
checar("perigo sem ninguém colado: corre só 2 vezes nesta luta", corridas == 2, f"({corridas} corridas)")
checar("depois da 2ª: fica parado (sem clique)", not bot.ir_para_diagonal(None, longe, pet))
# monstro COLADO em você o tempo todo: 2 corridas + EMERGENCIAS_MAX (2) extras, depois para
bot.CORRIDAS[0] = 0; bot.EMERGENCIAS[0] = 0
corridas = sum(1 for _ in range(8) if bot.ir_para_diagonal(None, cri, pet))
checar("monstro colado: 2 corridas + 2 de emergência", corridas == 4 and bot.EMERGENCIAS[0] == 2, f"({corridas})")
# luta nova zera
bot.inimigos = lambda sct: []
bot.fazer_catch = lambda *a, **k: None
bot.ORDER_DEPOIS_LUTA = False; bot.POKESTOP_ATIVO = False
bot.efeitos.curar_se_precisar = lambda sct: False
bot.descansar = lambda sct: None
bot.combater_ate_limpar(None, bot.LOTOU)
checar("luta nova: pode correr de novo (e as emergências zeram)", bot.EMERGENCIAS[0] == 0 and bot.ir_para_diagonal(None, longe, pet))
config.CORRIDAS_POR_BOX = 3; bot.CORRIDAS[0] = 0
corridas = sum(1 for _ in range(6) if bot.ir_para_diagonal(None, longe, pet))
checar("painel com 3: corre 3 vezes", corridas == 3, f"({corridas})")
print(f"\n{sum(res)}/{len(res)} testes passaram"); os._exit(0 if all(res) else 1)
