"""
Rodízio de personagens: battle pelo círculo atrás do pokémon, tela de seleção (botão Login, nome grande,
cards do carrossel), contador de voltas, ordem dos personagens e a troca simulada. Nada de clique de verdade.

Prints reais (testes/dados/):
  rodizio_battle_vermelho.png / rodizio_sem_battle_cinza.png — janela Pokémon do usuário (08/11 23:30, Steelix)
  print_22-29-23.png não serve (sem battle visível); usa diagnostico/print_18-21-13.png se existir (battle)
  rodizio_selecao_reduzida.png — tela de seleção (08/11 23:10, REDUZIDA ~0,78x; testada também ampliada)
"""
import os
import sys
import threading
import time

PASTA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "testes", "dados")
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import cv2
import numpy as np
import config
import controle
import personagens as P

resultados = []


def checar(nome, ok, extra=""):
    resultados.append(bool(ok))
    print(("✅" if ok else "❌") + f" {nome} {extra}")


def ancora_pokemon(img):
    tpl = cv2.imread(os.path.join(PASTA, "calibracao", "ancora_pokemon.png"))
    r = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, conf, _, pos = cv2.minMaxLoc(r)
    return pos if conf >= 0.9 else None


# ---------- 1) battle pelo círculo ----------
verm = cv2.imread(os.path.join(DADOS, "rodizio_battle_vermelho.png"))
cinza = cv2.imread(os.path.join(DADOS, "rodizio_sem_battle_cinza.png"))
checar("círculo VERMELHO = battle", P.battle_no_circulo(verm, ancora_pokemon(verm)) is True)
checar("círculo CINZA = pode deslogar", P.battle_no_circulo(cinza, ancora_pokemon(cinza)) is False)
cheio = os.path.join(PASTA, "diagnostico", "print_18-21-13.png")
if os.path.exists(cheio):
    img = cv2.imread(cheio)
    checar("print da tela inteira em luta (18:21, Gyarados) = battle", P.battle_no_circulo(img, ancora_pokemon(img)) is True)
checar("sem janela Pokémon = não sabe (None)", P.battle_no_circulo(cinza, None) is None)
checar("imagem preta = não sabe (None)", P.battle_no_circulo(np.zeros((200, 200, 3), np.uint8), (10, 10)) is None)

# ---------- 2) tela de seleção ----------
sel = cv2.imread(os.path.join(DADOS, "rodizio_selecao_reduzida.png"))
jogo = cv2.imread(os.path.join(DADOS, "print_22-29-23.png"))
checar("print do jogo NÃO é tela de seleção", not P.eh_tela_de_selecao(jogo))
checar("print do jogo (verde/azul) não tem botão Login", P.achar_botao_login(jogo) is None)
for escala in (1.0, 1.28):
    im = cv2.resize(sel, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
    b = P.achar_botao_login(im)
    checar(f"[{escala}x] tela de seleção reconhecida", P.eh_tela_de_selecao(im), b)
    W = im.shape[1]
    checar(f"[{escala}x] botão Login no meio, largo e baixo",
           b is not None and abs(b[0] + b[2] / 2 - W / 2) < 0.05 * W and 5 <= b[2] / b[3] <= 8)
    cs = P.cards(im, b)
    checar(f"[{escala}x] 3 cards de personagem (o \"Create Character\" fica de fora)", len(cs) == 3, cs)
    lido = P.ler_nome_grande(im, b)
    checar(f"[{escala}x] nome grande lido = Heroi Alfa", P.mesmo_nome(lido, "Heroi Alfa"), repr(lido))
    checar(f"[{escala}x] ...e não confunde com Heroi Beta", not P.mesmo_nome(lido, "Heroi Beta"))
    # cards nunca no canto de cima à direita (botão Logout = sai da CONTA)
    checar(f"[{escala}x] nenhum clique perto do Logout", all(y > im.shape[0] * 0.5 for _, y in cs))

checar("OCR com 1 letra errada ainda vale", P.mesmo_nome("Heroi Alfx", "Heroi Alfa"))
checar("nome diferente não vale", not P.mesmo_nome("Heroi Gama", "Heroi Alfa"))

# ---------- 3) contador de voltas ----------
c = P.ContadorVoltas(5, 5)  # circular 1..5
fechou = []
for passo in [0, 1, 2, 3, 4, 0]:
    fechou.append(c.passo(passo))
    c.chegou_em(passo)
checar("circular: 0→4→0 fecha 1 volta (só no fim)", fechou == [False] * 5 + [True] and c.voltas == 1)
c = P.ContadorVoltas(5, 5)
for passo in [3, 4]:
    c.passo(passo)
c.chegou_em(4)
checar("pulou para o começo sem andar a rota (luta) NÃO conta", not c.passo(0) and c.voltas == 0)
c = P.ContadorVoltas(4, 3)  # ida e volta 1,2,3,2
for passo in [0, 1, 2, 3]:
    c.passo(passo)
    c.chegou_em([0, 1, 2, 1][passo])
checar("ida e volta: fecha ao voltar ao 1", c.passo(0) and c.voltas == 1)
c = P.ContadorVoltas(8, 8)
for passo in [0, 1, 2, 3, 4, 5]:
    c.passo(passo)
    c.chegou_em(passo)
checar("voltar uns pontos depois de luta (5→3) não é volta", not c.passo(3) and c.voltas == 0)
c = P.ContadorVoltas(5, 5)
for passo in [0, 1, 2, 3]:
    c.passo(passo)
    c.chegou_em(passo)
checar("passo 0 pulado (luta levou do 3 para o 1) ainda fecha", c.passo(4) is False and c.passo(1) and c.voltas == 1)

# ---------- 4) ordem dos personagens ----------
config.RODIZIO_ATIVO = True
config.RODIZIO_PERSONAGENS = [{"nome": "Heroi Alfa", "hunt": "", "voltas": 2, "ponto": 3},
                              {"nome": "Heroi Beta", "hunt": "", "voltas": 1, "ponto": 0},
                              {"nome": " ", "hunt": "x"}]
config.MEU_NOME = "Heroi Beta"
r = P.Rodizio()
checar("linha sem nome é ignorada", len(r.personagens) == 2)
checar("começa no personagem logado (Meu nome)", r.da_vez()["nome"] == "Heroi Beta")
checar("ponto 0 = sai onde fechar a volta", r.fechou_volta(1) and r.pode_sair_aqui(7))
r.trocou()
checar("depois do último volta para o 1º", r.da_vez()["nome"] == "Heroi Alfa" and not r.quer_sair)
checar("1 de 2 voltas: ainda não sai", not r.fechou_volta(1) and not r.pode_sair_aqui(3))
checar("2 de 2 voltas: sai só no ponto 3", r.fechou_volta(2) and not r.pode_sair_aqui(2) and r.pode_sair_aqui(3))
config.RODIZIO_ATIVO = False
checar("rodízio desligado no painel: não troca", not P.Rodizio().ativo())
config.RODIZIO_ATIVO = True
config.RODIZIO_PERSONAGENS = config.RODIZIO_PERSONAGENS[:1]
checar("1 personagem só: não troca", not P.Rodizio().ativo())

# ---------- 5) controle: só a thread da troca age ----------
visto = {}


def outra():
    visto["pausado"] = controle.esta_pausado()
    visto["bloqueado"] = controle.acoes_bloqueadas()


g0 = controle.GERACAO[0]
controle.iniciar_troca()
t = threading.Thread(target=outra)
t.start()
t.join()
checar("trocando: outras threads veem pausa e não clicam", visto == {"pausado": True, "bloqueado": True})
checar("trocando: a thread da troca pode agir", not controle.esta_pausado() and not controle.acoes_bloqueadas())
controle.fim_troca()
t = threading.Thread(target=outra)
t.start()
t.join()
checar("fim da troca: todo mundo volta", visto == {"pausado": False, "bloqueado": False} and controle.GERACAO[0] == g0 + 1)

# ---------- 6) troca simulada ----------
config.RODIZIO_SEM_BATTLE_S = 0.2
config.RODIZIO_BATTLE_MAX_S = 1.5
config.RODIZIO_ESPERA_SAIR_S = 1.0
config.RODIZIO_ESPERA_LOGIN_S = 2.0
cliques, combos = [], []
controle.clicar = lambda x, y, espalhar=(0, 0), botao="left": cliques.append((x, y)) or True
controle.apertar_combo = lambda teclas: combos.append(tuple(teclas)) or True
controle.esperar = lambda s: time.sleep(min(s, 0.02))
REG = {"left": 100, "top": 50, "width": sel.shape[1], "height": sel.shape[0]}
P._imagem_janela = lambda sct: (sel, REG)
P._no_jogo = lambda sct: True
import layout
layout.detectar_e_aplicar = lambda sct, avisar=True: {}
nomes = []


def nome_falso(seq):
    it = iter(seq)
    return lambda img, b: next(it, seq[-1])


P.em_battle = lambda sct: False
checar("deslogar: sem battle → Ctrl+Q e chega na tela de seleção",
       P.deslogar(None, lambda: True) and combos == [("ctrl", "q")])

seq = iter([True, True, True, False, False, False, False, False, False, False, False, False, False])
P.em_battle = lambda sct: next(seq, False)
combos.clear()
t0 = time.time()
P.deslogar(None, lambda: True)
checar("deslogar: espera a battle sair antes do Ctrl+Q", combos == [("ctrl", "q")])

P.em_battle = lambda sct: True
combos.clear()
try:
    P.deslogar(None, lambda: True)
    checar("battle que não sai → erro", False)
except P.ErroTroca as e:
    checar("battle que não sai → erro, sem Ctrl+Q", combos == [], str(e))

P.em_battle = lambda sct: False
combos.clear()
try:
    P.deslogar(None, lambda: False)  # o bot ainda vê inimigo
    checar("com inimigo na Battle → não desloga", False)
except P.ErroTroca:
    checar("com inimigo na Battle → não desloga", combos == [])

# tela inesperada depois do Ctrl+Q (continua o jogo)
P._imagem_janela = lambda sct: (jogo, REG)
try:
    P.deslogar(None, lambda: True)
    checar("Ctrl+Q sem a tela de seleção aparecer → erro", False)
except P.ErroTroca as e:
    checar("Ctrl+Q sem a tela de seleção aparecer → erro", "não apareceu" in str(e), str(e))
P._imagem_janela = lambda sct: (sel, REG)

b = P.achar_botao_login(sel)
meio_login = (REG["left"] + b[0] + b[2] / 2, REG["top"] + b[1] + b[3] / 2)
cs = P.cards(sel, b)

cliques.clear()
P.ler_nome_grande = nome_falso(["Heroi Alfa", "Heroi Alfa", "Heroi Beta"])
P.escolher_e_entrar(None, "Heroi Beta")
checar("escolher: clica card 1, card 2 (confere o nome) e depois Login",
       len(cliques) == 3 and cliques[0] == (REG["left"] + cs[0][0], REG["top"] + cs[0][1])
       and cliques[1] == (REG["left"] + cs[1][0], REG["top"] + cs[1][1]) and cliques[2] == meio_login, cliques)

cliques.clear()
P.ler_nome_grande = nome_falso(["Heroi Beta"])
P.escolher_e_entrar(None, "Heroi Beta")
checar("já selecionado: só clica em Login", cliques == [meio_login])

cliques.clear()
P.ler_nome_grande = nome_falso(["Heroi Alfa"])
try:
    P.escolher_e_entrar(None, "Fulano Que Nao Existe")
    checar("personagem não encontrado → erro", False)
except P.ErroTroca as e:
    checar("personagem não encontrado → erro SEM clicar em Login", meio_login not in cliques and len(cliques) == 3, str(e))

cliques.clear()
P._imagem_janela = lambda sct: (jogo, REG)
try:
    P.escolher_e_entrar(None, "Heroi Alfa")
    checar("fora da tela de seleção → erro sem clicar", False)
except P.ErroTroca:
    checar("fora da tela de seleção → erro sem clicar", cliques == [])
P._imagem_janela = lambda sct: (sel, REG)

cliques.clear()
P._no_jogo = lambda sct: False
P.ler_nome_grande = nome_falso(["Heroi Alfa"])
try:
    P.escolher_e_entrar(None, "Heroi Alfa")
    checar("Login sem o jogo abrir → erro", False)
except P.ErroTroca as e:
    checar("Login sem o jogo abrir → erro", "não apareceu" in str(e))

# trocar(): erro deixa a troca ABERTA (threads quietas) até concluir; sucesso libera e ajusta o nome
P._no_jogo = lambda sct: True
P.em_battle = lambda sct: True
erro = P.trocar(None, "Heroi Alfa", lambda: True)
checar("troca com erro: devolve o texto e as threads continuam quietas", erro and controle.trocando())
P.concluir_troca(None, "Heroi Alfa")
checar("concluir: libera as threads e Meu nome vira o personagem", not controle.trocando() and config.MEU_NOME == "Heroi Alfa")
P.em_battle = lambda sct: False
P.ler_nome_grande = nome_falso(["Heroi Alfa", "Heroi Beta"])
erro = P.trocar(None, "Heroi Beta", lambda: True)
checar("troca completa: sem erro, threads livres, Meu nome novo",
       erro is None and not controle.trocando() and config.MEU_NOME == "Heroi Beta")

print(f"\n{sum(resultados)}/{len(resultados)} testes passaram")
sys.exit(0 if all(resultados) else 1)
