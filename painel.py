"""
Painel do bot — tudo num lugar só:
  Aba "Ajustes"     : liga/desliga funções e ajusta valores (salvos em ajustes.json)
  Aba "Rota"        : grava, edita e salva a rota (dá para gravar de dentro do jogo com F5/F6)
  Aba "Calibração"  : calibra as barras de HP (F9 no começo e no fim da barra)
  Rodapé            : iniciar / parar o bot
"""
import base64
import json
import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import cv2
import keyboard
import mss
import pyautogui
import pydirectinput

import catch
import chat
import efeitos
import hunts
import layout
import config
import controle
import posicao
import rota
from minimapa import capturar_minimapa, recortar_waypoint
from tela import (
    ARQ_CALIBRACAO, ler_barra, medir_barra, salvar_calibracao_barra, linhas_que_cabem,
    regiao_battle, posicao_barra,
)

PASTA = os.path.dirname(os.path.abspath(__file__))

# (chave no config, tipo, texto, mínimo, máximo, depende_de)
# tipo: "check" = marcação, "int"/"float" = número, "tecla" = hotkey
SECOES = [
    ("⚔️  Lure", [
        ("ROTA_AO_INICIAR", "check", "Já começar andando a rota ao iniciar o bot", None, None, None),
        ("COMBATE_SEM_ROTA", "check", "Rota desligada: atacar o lure que eu fizer na mão", None, None, None),
        ("PARADO_PARA_ATACAR_S", "float", "Atacar quando eu parar com o mínimo do lure por (s)", 0.5, 10, "COMBATE_SEM_ROTA"),
        ("ROTA_IDA_E_VOLTA", "check", "Rota ida e volta (1→2→3→2→1), sem pular do último pro 1º", None, None, None),
        ("LURE_ATIVO", "check", "Juntar monstros antes de lutar", None, None, None),
        ("LURE_MINIMO", "int", "Mínimo de monstros na Battle", 1, 7, "LURE_ATIVO"),
        ("LURE_ESPERA_PONTO", "float", "Espera nos pontos de lure (s)", 0, 30, "LURE_ATIVO"),
        ("LURE_MAX_VOLTAS", "int", "Lutar com o que tiver após N voltas (0 = nunca)", 0, 20, "LURE_ATIVO"),
        ("LURE_SEGURANCA_ATIVA", "check", "Lutar antes se o HP (meu ou do monstrinho) ficar baixo", None, None, "LURE_ATIVO"),
        ("LURE_HP_SEGURANCA", "int", "Meu HP de segurança (%)", 5, 95, "LURE_SEGURANCA_ATIVA"),
        ("LURE_POKE_HP_SEGURANCA", "int", "HP do monstrinho de segurança (%)", 5, 95, "LURE_SEGURANCA_ATIVA"),
        ("LURE_PRESO_S", "float", "Lutar se ficar parado/cercado por (s)", 1, 30, "LURE_ATIVO"),
    ]),
    ("❤️  Cura", [
        ("CURA_HP_ATIVA", "check", "Curar o personagem", None, None, None),
        ("HP_LIMITE", "int", "Curar abaixo de (%)", 5, 95, "CURA_HP_ATIVA"),
        ("TECLA_CURA_HP", "tecla", "Tecla de cura", None, None, "CURA_HP_ATIVA"),
        ("CURA_POKE_ATIVA", "check", "Curar o monstrinho", None, None, None),
        ("POKE_HP_LIMITE", "int", "Curar abaixo de (%)", 5, 95, "CURA_POKE_ATIVA"),
        ("TECLA_CURA_POKE", "tecla", "Tecla de cura", None, None, "CURA_POKE_ATIVA"),
        ("CURA_POKE_FORA_COMBATE", "check", "Só tomar poção sem inimigos (hit cancela)", None, None, "CURA_POKE_ATIVA"),
        ("POT_DURACAO", "float", "Duração da poção (s)", 1, 60, "CURA_POKE_ATIVA"),
        ("CAIXA_PRETA_ATIVA", "check", "Caixa-preta: salvar provas quando eu levar dano", None, None, None),
        ("CAIXA_PRETA_QUEDA", "int", "Queda de HP que vira prova (%)", 1, 50, "CAIXA_PRETA_ATIVA"),
        ("CAIXA_PRETA_MAX", "int", "Máximo de provas por sessão", 1, 100, "CAIXA_PRETA_ATIVA"),
        ("DESCANSAR_ATE", "int", "Após a luta, descansar até (%) (0 = não)", 0, 100, "CURA_POKE_ATIVA"),
        ("DESCANSO_MAX", "float", "Tempo máximo descansando (s)", 5, 300, "CURA_POKE_ATIVA"),
        ("COOLDOWN_CURA", "float", "Intervalo mínimo entre curas (s)", 0.1, 10, None),
    ]),
    ("🗡️  Combate", [
        ("MONSTRINHO_NA_BATTLE", "check", "Meu monstrinho é o 1º da Battle (ignorar)", None, None, None),
        ("IGNORAR_ROSA", "check", "Ignorar monstros de nome rosa (anti-block)", None, None, None),
        ("TECLA_ATAQUE", "tecla", "Tecla de ataque (combo)", None, None, None),
        ("INTERVALO_ATAQUE", "float", "Intervalo entre ataques (s)", 0.2, 10, None),
        ("TIMEOUT_COMBATE", "float", "Tempo máximo de combate (s)", 5, 600, None),
        ("MAGIA_AGRUPAR_ATIVA", "check", "Só soltar magia com os monstros perto", None, None, None),
        ("MODO_LUTA_ATIVO", "check", "Fight Mode: defensivo lurando, ofensivo batendo", None, None, None),
        ("TECLA_DEFENSIVO", "tecla", "Tecla do Defensive (NumpadSubtract = subtract)", None, None, "MODO_LUTA_ATIVO"),
        ("MODO_OFENSIVO_ATIVO", "check", "Apertar o ofensivo na luta (desligado: o jogo troca sozinho na magia)",
         None, None, "MODO_LUTA_ATIVO"),
        ("TECLA_OFENSIVO", "tecla", "Tecla do Offensive (NumpadAdd = add)", None, None, "MODO_OFENSIVO_ATIVO"),
        ("DEF_LURE_ATIVO", "check", "Magia de defesa enquanto lura", None, None, None),
        ("TECLA_DEF_LURE", "tecla", "Tecla da magia de defesa", None, None, "DEF_LURE_ATIVO"),
        ("DEF_LURE_MIN", "int", "Usar com pelo menos N monstros atrás", 1, 10, "DEF_LURE_ATIVO"),
        ("DEF_LURE_INTERVALO", "float", "Não repetir antes de (s)", 2, 300, "DEF_LURE_ATIVO"),
        ("LURE_QUEDA_PERIGO", "int", "Monstrinho perdeu (%) em 3 s lurando: luta já", 5, 90, None),
        ("LURE_IR_ATE_PONTO", "int", "Lure cheio perto do ponto de lure: ir até ele (sqm, 0 = não)", 0, 15, None),
        ("IGNORAR_SOBRA", "check", "Sobrou pouco depois do combo: ignora e vai pro próximo lure", None, None, None),
        ("SOBRA_MAX", "int", "Ignorar até quantos monstros que sobraram", 1, 5, "IGNORAR_SOBRA"),
        ("CLICAR_ALVO", "check", "Clicar no alvo da Battle (desligue se só usa ataque em área)", None, None, None),
        ("POKE_CACA", "texto", "Pokémon que vai caçar (nome)", None, None, "MAGIA_AGRUPAR_ATIVA"),
        ("BOX_HP_SOLTAR", "int", "Monstrinho abaixo de (%): solta sem esperar a box", 10, 95, "MAGIA_AGRUPAR_ATIVA"),
        ("BOX_RAIO_SQM", "int", "Alcance do ataque dele (sqm; 1 = box colada)", 1, 8, "MAGIA_AGRUPAR_ATIVA"),
        ("MAGIA_ESPERA_MAX", "float", "Espera máxima para agrupar (s)", 0, 30, "MAGIA_AGRUPAR_ATIVA"),
        ("POKESTOP_ATIVO", "check", "Pokestop quando o lure termina (antes de atacar)", None, None, None),
        ("TECLA_POKESTOP", "tecla", "Tecla do pokestop", None, None, "POKESTOP_ATIVO"),
        ("SAIR_DA_BOX", "check", "Personagem para na DIAGONAL da box (fora da frente dos ataques)", None, None, None),
        ("NORMAL_SEM_FUGIR", "check", "Modo normal: não correr da box (mata e já segue)", None, None, "SAIR_DA_BOX"),
        ("BOX_DIAGONAL_SQM", "int", "Distância na diagonal até o monstrinho (sqm)", 2, 8, "SAIR_DA_BOX"),
        ("DISTANCIA_MONSTROS", "int", "Ficar a pelo menos N sqm de qualquer monstro (magia em área)", 2, 8, "SAIR_DA_BOX"),
        ("CORRIDAS_POR_BOX", "int", "Correr da box no máximo N vezes por luta (depois fica parado)", 1, 10, "SAIR_DA_BOX"),
        ("ORDER_DEPOIS_LUTA", "check", "Order (bolinha do mouse) depois da luta: sai do pokestop", None, None, None),
        ("ORDER_ANDANDO", "check", "Order andando na rota: o pet acompanha o lure", None, None, None),
        ("ORDER_INTERVALO", "float", "Intervalo entre orders andando (s)", 0.5, 10, "ORDER_ANDANDO"),
    ]),
    ("🌀  Modo de hunt", [
        ("MODO_HUNT", "opcao", "Modo", ["normal", "revive", "outland", "nightmare"], None, None),
        ("COMBO_DURACAO", "float", "Tempo do combo soltar todas as magias (s)", 0.5, 15, None),
        ("SILENCIO_POS_COMBO_S", "float", "Silence/stun depois do combo (s, 0 = não tem)", 0, 10, None),
        ("CONTROLE_TIPO", "opcao", "Tipo: silence (anda, não ataca) / stun (preso)", ["silence", "stun"], None, None),
    ]),
    ("🧪  Medicine", [
        ("MEDICINE_ATIVO", "check", "Usar Medicine com efeito negativo (blind...)", None, None, None),
        ("TECLA_MEDICINE", "tecla", "Tecla da Medicine", None, None, "MEDICINE_ATIVO"),
        ("MEDICINE_ESPERA", "float", "Intervalo mínimo entre Medicines (s)", 0.5, 60, "MEDICINE_ATIVO"),
        ("MEDICINE_CLICAR_POKE", "check", "Depois da tecla, clicar no retrato do poke", None, None, "MEDICINE_ATIVO"),
        ("MEDICINE_EM_DESCONHECIDO", "check", "Usar também em efeito que o bot não conhece", None, None, "MEDICINE_ATIVO"),
    ]),
    ("💊  Revive", [
        ("REVIVE_SE_MORRER", "check", "Monstrinho morreu: usar revive na hora (qualquer modo)", None, None, None),
        ("TECLA_REVIVE", "tecla", "Tecla do revive", None, None, None),
        ("REVIVE_CLICAR_POKE", "check", "Depois da tecla, clicar no retrato do poke", None, None, None),
        ("REVIVE_ESPERA", "float", "Espera depois do revive (s)", 0.2, 10, "MODO_HUNT=revive|outland"),
        ("OUTLAND_MAX_REVIVES", "int", "Outland: revives seguidos sem matar ninguém (shiny = sem limite)", 1, 30, "MODO_HUNT=outland"),
        ("REVIVE_APOS_LURE", "check", "Usar revive também depois de matar", None, None, "MODO_HUNT=revive"),
    ]),
    ("🌙  Nightmare", [
        ("NIGHTMARE_TECLAS", "texto", "Teclas dos pokes, em ordem (ex.: 1, 2, 3)", None, None, "MODO_HUNT=nightmare"),
        ("NIGHTMARE_COOLDOWN", "float", "Cooldown das magias de cada poke (s)", 1, 600, "MODO_HUNT=nightmare"),
        ("TROCA_ESPERA", "float", "Tempo do poke sair da ball (s)", 0.3, 10, "MODO_HUNT=nightmare"),
        ("NIGHTMARE_VOLTAR_PRIMEIRO", "check", "Depois de matar, voltar pro 1º poke", None, None, "MODO_HUNT=nightmare"),
    ]),
    ("🎾  Catch", [
        ("CATCH_ATIVO", "check", "Catch especial (raros: ball assim que morre)", None, None, None),
        ("CATCH_ESTRELAS", "check", "Especial = monstrinho com estrelinhas no nome", None, None, "CATCH_ATIVO"),
        ("CATCH_CORPO", "check", "Especial pelo corpo morto (cor do perfil; ignora estrelinhas onde vale)",
         None, None, "CATCH_ATIVO"),
        ("CATCH_SHINY_AUTO", "check", "Shiny automático: cor rara na hunt vira perfil sozinha (sem calibrar)",
         None, None, "CATCH_CORPO"),
        ("CATCH_AJUSTE_X", "int", "Ajuste da ball: sqm para a direita (caiu à esquerda = +1)", -2, 2, "CATCH_ATIVO"),
        ("CATCH_AJUSTE_Y", "int", "Ajuste da ball: sqm para baixo (caiu em cima = +1)", -2, 2, "CATCH_ATIVO"),
        ("LOOT_ANTES_BALL", "check", "Pegar o loot do especial antes da ball (sem auto loot)", None, None, "CATCH_ATIVO"),
        ("TECLA_LOOT", "tecla", "Tecla de pegar loot", None, None, "LOOT_ANTES_BALL"),
        ("LOOT_ESPERA", "float", "Espera depois do loot (s)", 0.2, 5, "LOOT_ANTES_BALL"),
        ("CATCH_NORMAL_ATIVO", "check", "Catch normal (comuns: ball depois da luta)", None, None, None),
        ("TECLA_BALL", "tecla", "Tecla da ball (ex.: f7, 4, mouse5)", None, None, None),
        ("CATCH_BALL_MOUSE", "check", "Ball: mouse em cima do corpo + tecla (sem clique)", None, None, None),
        ("CATCH_TENTATIVAS", "int", "Tentativas no mesmo corpo", 1, 10, None),
        ("CATCH_TENTATIVAS_ESPECIAL", "int", "Tentativas no corpo do shiny/especial", 1, 15, None),
        ("CATCH_PROCURA_S", "float", "Procurar o corpo do shiny por até (s) (magia por cima)", 1, 15, None),
        ("CATCH_ESPERA", "float", "Espera depois de cada ball (s)", 0.5, 10, None),
        ("CATCH_DISTANCIA_MAX", "int", "Distância máxima do corpo (sqm)", 1, 10, None),
        ("CATCH_CHEGAR_PERTO", "check", "Andar até o corpo antes da ball (a mais de 2 sqm; com auto loot não precisa)",
         None, None, "CATCH_ATIVO"),
        ("CATCH_RAIO_LOCAL", "int", "Perfil com local vale até (sqm)", 10, 5000, None),
    ]),
    ("🔔  Alarme", [
        ("ALARME_ATIVO", "check", "Alarme de mensagem no chat Default", None, None, None),
        ("ALARME_QUALQUER_MSG", "check", "Qualquer mensagem (não só falas)", None, None, "ALARME_ATIVO"),
        ("ALARME_PAUSAR_BOT", "check", "Pausar o bot quando tocar", None, None, "ALARME_ATIVO"),
        ("ALARME_DURACAO", "float", "Duração do bipe (s)", 1, 60, "ALARME_ATIVO"),
        ("MEU_NOME", "texto", "Meu nome no jogo (minha fala não toca)", None, None, "ALARME_ATIVO"),
        ("ALARME_ABAS_IGNORAR", "texto", "Abas que NÃO são mensagem privada", None, None, "ALARME_ATIVO"),
        ("ALARME_PLAYER_ATIVO", "check", "Alarme de player na tela", None, None, None),
        ("ALARME_PLAYER_PAUSAR", "check", "Pausar quando chegar player", None, None, "ALARME_PLAYER_ATIVO"),
    ]),
    ("🔁  Rodízio de personagens", [
        ("RODIZIO_ATIVO", "check", "Rodízio de personagens (troca de boneco)", None, None, None),
        ("RODIZIO_SEM_BATTLE_S", "float", "Sem battle antes de deslogar (s)", 1, 30, "RODIZIO_ATIVO"),
        ("RODIZIO_BATTLE_MAX_S", "float", "Battle não sai: alarme depois de (s)", 20, 600, "RODIZIO_ATIVO"),
        ("RODIZIO_ESPERA_LOGIN_S", "float", "Espera o jogo abrir depois do Login (s)", 10, 120, "RODIZIO_ATIVO"),
    ]),
    ("🧍  Jeito humano", [
        ("HUMANO_ATIVO", "check", "Andar e clicar de um jeito natural", None, None, None),
        ("HUMANO_INTENSIDADE", "int", "Quanto variar (%)", 10, 100, "HUMANO_ATIVO"),
        ("HUMANO_PARADAS", "int", "Chance de paradinha ao chegar num ponto (%)", 0, 50, "HUMANO_ATIVO"),
    ]),
    ("⌨️  Atalhos", [
        ("TECLA_PAUSA", "tecla", "Pausar / continuar o bot", None, None, None),
        ("TECLA_PARAR", "tecla", "Parar o bot", None, None, None),
        ("TECLA_ROTA", "tecla", "Ligar / desligar a rota", None, None, None),
        ("TECLA_GRAVAR_PASSAGEM", "tecla", "Gravar ponto de passagem", None, None, None),
        ("TECLA_GRAVAR_LURE", "tecla", "Gravar ponto de lure", None, None, None),
        ("TECLA_CALIBRAR", "tecla", "Marcar barra na calibração", None, None, None),
    ]),
]

CAMPOS = {c[0]: c for _, campos in SECOES for c in campos}
# campos "texto" que são NOME/FRASE livre (os outros "texto" são listas de teclas e são validados)
TEXTO_LIVRE = {"POKE_CACA", "MEU_NOME", "ALARME_ABAS_IGNORAR"}

BARRAS = [("hp", "HP do personagem"), ("poke_hp", "HP do monstrinho")]


def imagem_tk(img_bgr, escala):
    """Converte uma imagem do OpenCV em PhotoImage (ampliada, sem borrar)."""
    grande = cv2.resize(img_bgr, None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
    ok, png = cv2.imencode(".png", grande)
    return tk.PhotoImage(data=base64.b64encode(png.tobytes()))


class Painel:
    def __init__(self, root):
        self.root = root
        self.root.title("Painel do Bot")
        self.root.resizable(True, True)
        self.root.minsize(420, 300)
        self.sct = mss.MSS()
        self._interna = {}  # aba do Notebook (com rolagem) -> frame onde fica o conteúdo
        self.proc_bot = None
        self.vars = {}
        self.widgets = {}

        # Teclas apertadas no jogo chegam por aqui (o keyboard roda em outra thread)
        self.fila_teclas = queue.Queue()
        keyboard.on_press(lambda e: self.fila_teclas.put((e.name or "").lower()))

        principal = ttk.Frame(root, padding=10)
        principal.pack(fill=tk.BOTH, expand=True)

        # rodapé (Iniciar/Parar/Rota) é empacotado primeiro, embaixo: nunca some ao diminuir a janela
        rodape = ttk.Frame(principal)
        rodape.pack(side=tk.BOTTOM, fill=tk.X)

        self.abas = ttk.Notebook(principal)
        self.abas.pack(fill=tk.BOTH, expand=True)
        self.criar_aba_ajustes()
        self.criar_aba_rota()
        self.criar_aba_calibracao()
        self.criar_aba_target()
        self.criar_aba_log()
        self.abas.bind("<<NotebookTabChanged>>", lambda e: self.ao_trocar_aba())

        self.criar_rodape(rodape)
        self.restaurar_tamanho()

        # Configuração automática da tela (acha a janela do jogo em qualquer monitor)
        try:
            self.detectar_layout()
        except Exception as e:
            print(f"[Layout] {e!r}")

        self.atualizar_dependencias()
        self.atualizar_hunt()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.root.after(50, self.processar_teclas)
        self.root.after(500, self.vigiar)

    # =====================================================================
    # Aba Ajustes
    # =====================================================================

    # Cada aba de ajustes junta seções do mesmo assunto, lado a lado
    ABAS_AJUSTES = [  # cada aba: linhas de seções (seções da mesma linha ficam lado a lado)
        ("⚔️ Caça", [["Lure", "Combate"]]),
        ("🌀 Modo de hunt", [["Modo de hunt", "Medicine"], ["Revive", "Nightmare"]]),
        ("❤️ Cura", [["Cura"]]),
        ("🎾 Catch / 🔔 Alarme", [["Catch", "Alarme"]]),
        ("🧍 Humano / ⌨️ Atalhos", [["Jeito humano", "Atalhos"]]),
        ("🔁 Rodízio", [["Rodízio"]]),
    ]

    def criar_aba_ajustes(self):
        """Cria as abas de ajustes (o botão Salvar fica no rodapé, vale para todas)."""
        for nome_aba, linhas in self.ABAS_AJUSTES:
            aba = self.nova_aba(nome_aba)
            for lin, nomes_secoes in enumerate(linhas):
              for col, nome in enumerate(nomes_secoes):
                titulo, campos = next((t, c) for t, c in SECOES if nome in t)
                coluna = ttk.Frame(aba)
                coluna.grid(row=lin, column=col, sticky="nw", padx=(0, 8),
                            columnspan=2 if len(nomes_secoes) == 1 and len(linhas) > 1 else 1)
                self.criar_secao(coluna, titulo, campos)
                if nome == "Medicine":
                    self.aba_modo = aba
                    self.efeito_ensinando = None
                    linha_botoes = ttk.Frame(coluna)
                    linha_botoes.pack(anchor="w")
                    self.btn_ensinar_ruim = ttk.Button(linha_botoes, command=lambda: self.iniciar_ensinar_efeito("neg"))
                    self.btn_ensinar_ruim.pack(side=tk.LEFT)
                    self.btn_ensinar_bom = ttk.Button(linha_botoes, command=lambda: self.iniciar_ensinar_efeito("pos"))
                    self.btn_ensinar_bom.pack(side=tk.LEFT, padx=(6, 0))
                    self.label_efeitos = ttk.Label(coluna, foreground="gray", wraplength=330, justify="left")
                    self.label_efeitos.pack(anchor="w", pady=(4, 0))
                    self.atualizar_texto_efeitos()
                if nome == "Alarme":
                    ttk.Button(coluna, text="🔔 Testar alarme",
                               command=lambda: chat.tocar_som(
                                   min(3.0, float(self.vars["ALARME_DURACAO"].get() or 3)))
                               ).pack(anchor="w")
              if "Catch" in nome_aba:
                self.aba_catch = aba
                self.criar_perfis_catch(aba, len(linhas))
              if "Rodízio" in nome_aba:
                self.criar_lista_rodizio(aba, len(linhas))

    # ---------- Rodízio de personagens ----------

    def criar_lista_rodizio(self, aba, linha):
        """Lista dos personagens do rodízio: nome (igual no jogo), hunt, voltas e ponto de saída."""
        quadro = ttk.LabelFrame(aba, text="Personagens (na ordem do rodízio; depois do último volta ao 1º)",
                                padding=8)
        quadro.grid(row=linha, column=0, columnspan=2, sticky="nwe", pady=(0, 8))
        ttk.Label(quadro, foreground="gray", wraplength=520, justify="left", text=(
            "Todos na MESMA conta (a troca é pela tela de seleção, sem senha). Inicie o bot já logado num "
            "deles: o bot sabe qual é pelo \"Meu nome\" (aba Catch/Alarme). Nome igual ao do jogo. "
            "Ponto = waypoint onde ele desloga depois das voltas (0 = onde a volta fechar).")).pack(anchor="w")
        colunas = ("nome", "hunt", "voltas", "ponto")
        self.tree_rodizio = ttk.Treeview(quadro, columns=colunas, show="headings", height=5)
        for c, t, w in zip(colunas, ("Personagem", "Hunt", "Voltas", "Ponto de saída"), (170, 170, 60, 100)):
            self.tree_rodizio.heading(c, text=t)
            self.tree_rodizio.column(c, width=w, anchor="w" if c in ("nome", "hunt") else "center")
        self.tree_rodizio.pack(fill=tk.X, pady=(6, 4))
        for p in config.RODIZIO_PERSONAGENS or []:
            self.tree_rodizio.insert("", tk.END, values=(p.get("nome", ""), p.get("hunt", ""),
                                                         p.get("voltas", 1), p.get("ponto", 1)))
        editor = ttk.Frame(quadro)
        editor.pack(fill=tk.X)
        self.rod_nome = tk.StringVar()
        self.rod_hunt = tk.StringVar()
        self.rod_voltas = tk.StringVar(value="1")
        self.rod_ponto = tk.StringVar(value="1")
        ttk.Label(editor, text="Nome").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.rod_nome, width=20).grid(row=1, column=0, padx=(0, 6))
        ttk.Label(editor, text="Hunt").grid(row=0, column=1, sticky="w")
        self.combo_rod_hunt = ttk.Combobox(editor, textvariable=self.rod_hunt, width=20, state="readonly",
                                           values=hunts.listar(),
                                           postcommand=lambda: self.combo_rod_hunt.configure(values=hunts.listar()))
        self.combo_rod_hunt.grid(row=1, column=1, padx=(0, 6))
        ttk.Label(editor, text="Voltas").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(editor, from_=1, to=99, textvariable=self.rod_voltas, width=5).grid(row=1, column=2, padx=(0, 6))
        ttk.Label(editor, text="Ponto").grid(row=0, column=3, sticky="w")
        ttk.Spinbox(editor, from_=0, to=99, textvariable=self.rod_ponto, width=5).grid(row=1, column=3, padx=(0, 6))
        botoes = ttk.Frame(quadro)
        botoes.pack(anchor="w", pady=(6, 0))
        ttk.Button(botoes, text="➕ Adicionar / atualizar", command=self.rodizio_salvar_linha).pack(side=tk.LEFT)
        ttk.Button(botoes, text="🗑 Remover", command=self.rodizio_remover).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(botoes, text="⬆", width=3, command=lambda: self.rodizio_mover(-1)).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(botoes, text="⬇", width=3, command=lambda: self.rodizio_mover(1)).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Label(quadro, foreground="gray", text="Depois de mexer na lista, clique em Salvar ajustes.").pack(
            anchor="w", pady=(4, 0))
        self.tree_rodizio.bind("<<TreeviewSelect>>", lambda e: self.rodizio_preencher())

    def rodizio_preencher(self):
        sel = self.tree_rodizio.selection()
        if sel:
            nome, hunt, voltas, ponto = self.tree_rodizio.item(sel[0], "values")
            self.rod_nome.set(nome)
            self.rod_hunt.set(hunt)
            self.rod_voltas.set(str(voltas))
            self.rod_ponto.set(str(ponto))

    def rodizio_salvar_linha(self):
        nome = self.rod_nome.get().strip()
        if not nome:
            messagebox.showerror("Rodízio", "Escreva o nome do personagem (igual no jogo).")
            return
        try:
            voltas, ponto = int(self.rod_voltas.get()), int(self.rod_ponto.get())
        except ValueError:
            messagebox.showerror("Rodízio", "Voltas e ponto precisam ser números.")
            return
        if voltas < 1 or ponto < 0:
            messagebox.showerror("Rodízio", "Voltas: 1 ou mais. Ponto: 0 ou mais.")
            return
        valores = (nome, self.rod_hunt.get().strip(), voltas, ponto)
        for item in self.tree_rodizio.get_children():  # mesmo nome: atualiza a linha
            if str(self.tree_rodizio.item(item, "values")[0]).lower() == nome.lower():
                self.tree_rodizio.item(item, values=valores)
                break
        else:
            self.tree_rodizio.insert("", tk.END, values=valores)
        self.status(f"Rodízio: {nome} na lista (clique em Salvar ajustes)")

    def rodizio_remover(self):
        for item in self.tree_rodizio.selection():
            self.tree_rodizio.delete(item)

    def rodizio_mover(self, direcao):
        for item in self.tree_rodizio.selection():
            i = self.tree_rodizio.index(item)
            self.tree_rodizio.move(item, "", max(0, i + direcao))

    def rodizio_lista(self):
        lista = []
        for item in self.tree_rodizio.get_children():
            nome, hunt, voltas, ponto = self.tree_rodizio.item(item, "values")
            lista.append({"nome": str(nome), "hunt": str(hunt), "voltas": int(voltas), "ponto": int(ponto)})
        return lista

    def criar_secao(self, pai, titulo, campos):
        quadro = ttk.LabelFrame(pai, text=titulo, padding=8)
        quadro.pack(fill=tk.X, pady=(0, 8))

        for linha, (chave, tipo, texto, minimo, maximo, depende) in enumerate(campos):
            valor = getattr(config, chave)
            recuo = 18 if depende else 0

            if tipo == "check":
                var = tk.BooleanVar(value=bool(valor))
                w = ttk.Checkbutton(quadro, text=texto, variable=var,
                                    command=self.atualizar_dependencias)
                w.grid(row=linha, column=0, columnspan=2, sticky="w", padx=(recuo, 0), pady=2)
                widgets = [w]
            else:
                rotulo = ttk.Label(quadro, text=texto)
                rotulo.grid(row=linha, column=0, sticky="w", padx=(recuo, 8), pady=2)
                var = tk.StringVar(value=str(valor))
                if tipo == "opcao":
                    w = ttk.Combobox(quadro, textvariable=var, values=minimo, width=11, state="readonly")
                    w.bind("<<ComboboxSelected>>", lambda e: self.atualizar_dependencias())
                elif tipo == "texto":
                    w = ttk.Entry(quadro, textvariable=var, width=14, justify="center")
                    if chave == "POKE_CACA":  # trocou de pokémon: puxa o alcance que ele já tinha
                        w.bind("<FocusOut>", lambda e: self.carregar_alcance_poke())
                elif tipo == "tecla":
                    w = ttk.Entry(quadro, textvariable=var, width=8, justify="center")
                else:
                    passo = 1 if tipo == "int" else 0.5
                    w = ttk.Spinbox(quadro, textvariable=var, from_=minimo, to=maximo,
                                    increment=passo, width=7, justify="center")
                w.grid(row=linha, column=1, sticky="e", pady=2)
                widgets = [w, rotulo]

            self.vars[chave] = var
            self.widgets[chave] = widgets

    def ativo(self, chave):
        """
        Um campo está ativo se todas as marcações das quais ele depende estão marcadas.
        Dependência "CAMPO=valor" = só ativo quando aquele campo tem aquele valor (ex.: modo de hunt).
        """
        depende = CAMPOS[chave][5]
        while depende:
            if "=" in depende:
                campo, valor = depende.split("=", 1)
                if str(self.vars[campo].get()) not in valor.split("|"):
                    return False
                depende = CAMPOS[campo][5]
                continue
            if not self.vars[depende].get():
                return False
            depende = CAMPOS[depende][5]
        return True

    def atualizar_dependencias(self):
        for chave, widgets in self.widgets.items():
            ativo = self.ativo(chave)
            for w in widgets:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if ativo else "disabled")
                else:
                    w.configure(state="normal" if ativo else "disabled")
        # O máximo do lure depende do tamanho da Battle e de o monstrinho ocupar uma linha
        self.widgets["LURE_MINIMO"][0].configure(to=max(1, self.max_monstros()))
        if hasattr(self, "label_battle"):
            self.atualizar_texto_battle()

    def max_monstros(self):
        """Quantos inimigos cabem na Battle."""
        pet = 1 if self.vars["MONSTRINHO_NA_BATTLE"].get() else 0
        return linhas_que_cabem(config.BATTLE_REGION["height"]) - pet

    def ler_valores(self):
        """Lê e valida os campos. Retorna dict ou None se tiver erro."""
        valores = {}
        for chave, (_, tipo, texto, minimo, maximo, _) in CAMPOS.items():
            bruto = self.vars[chave].get()
            if tipo == "check":
                valores[chave] = bool(bruto)
                continue
            if tipo == "opcao":
                valores[chave] = str(bruto)
                continue
            if chave in TEXTO_LIVRE:  # nome/frase livre, não é tecla
                valores[chave] = str(bruto).strip()
                continue
            if tipo == "texto":
                teclas = [t.strip().lower() for t in str(bruto).replace(";", ",").split(",") if t.strip()]
                invalidas = [t for t in teclas if t not in pydirectinput.KEYBOARD_MAPPING
                             and t not in controle.TECLAS_EXTRAS]
                if invalidas:
                    messagebox.showerror("Tecla inválida", f"{texto}: tecla(s) inválida(s): {', '.join(invalidas)}")
                    return None
                if self.ativo(chave) and chave == "NIGHTMARE_TECLAS" and len(teclas) < 2:
                    messagebox.showerror("Nightmare", "Coloque pelo menos 2 teclas de pokes, separadas por vírgula "
                                                      "(ex.: 1, 2, 3).")
                    return None
                valores[chave] = ", ".join(teclas)
                continue
            if tipo == "tecla":
                tecla = str(bruto).strip().lower()
                if chave == "TECLA_POKESTOP" and not tecla:
                    if self.ativo(chave):
                        messagebox.showerror("Falta a tecla do pokestop",
                                             "Preencha a tecla do pokestop (aba Caça) ou desmarque a opção.")
                        return None
                    valores[chave] = ""
                    continue
                if chave == "TECLA_MEDICINE" and not tecla:
                    if self.ativo(chave):
                        messagebox.showerror("Falta a tecla da Medicine",
                                             "Preencha a tecla da Medicine (aba Modo de hunt) ou desmarque a opção.")
                        return None
                    valores[chave] = ""
                    continue
                if chave == "TECLA_REVIVE" and not tecla:
                    if self.ativo("REVIVE_ESPERA"):  # só obrigatória no modo revive
                        messagebox.showerror("Falta a tecla do revive",
                                             "No modo revive, preencha a tecla do revive (aba Modo de hunt).")
                        return None
                    valores[chave] = ""
                    continue
                if chave == "TECLA_BALL" and not tecla:
                    if valores.get("CATCH_ATIVO") or valores.get("CATCH_NORMAL_ATIVO"):
                        messagebox.showerror("Falta a tecla da ball",
                                             "Para usar o catch, preencha a tecla da ball (aba Catch / Alarme).")
                        return None
                    valores[chave] = ""
                    continue
                if tecla not in pydirectinput.KEYBOARD_MAPPING and tecla not in controle.TECLAS_EXTRAS:
                    messagebox.showerror("Tecla inválida", f"'{bruto}' não é uma tecla válida ({texto}).\n"
                                         "Exemplos: q, f1, f12, 1, space, mouse4, mouse5")
                    return None
                valores[chave] = tecla
                continue
            try:
                numero = int(bruto) if tipo == "int" else float(str(bruto).replace(",", "."))
            except ValueError:
                messagebox.showerror("Valor inválido", f"'{bruto}' não é um número ({texto}).")
                return None
            if chave == "LURE_MINIMO" and valores.get("LURE_ATIVO", True) and numero > self.max_monstros():
                messagebox.showerror(
                    "Battle pequena",
                    f"Só cabem {self.max_monstros()} monstros na sua Battle"
                    f"{' (o monstrinho ocupa a 1ª linha)' if self.vars['MONSTRINHO_NA_BATTLE'].get() else ''}.\n\n"
                    "Para juntar mais: aumente a janela da Battle no jogo e depois clique em "
                    "'Ajustar' em Tamanho da Battle, na aba Calibração.")
                return None
            if chave == "LURE_MINIMO":
                maximo = 99  # o limite real é o tamanho da Battle (checado acima)
            if not (minimo <= numero <= maximo):
                messagebox.showerror("Valor fora do limite",
                                     f"{texto}: use um valor entre {minimo} e {maximo}.")
                return None
            valores[chave] = numero

        # atalhos do próprio bot não podem repetir (as teclas do jogo podem)
        atalhos = ["TECLA_PAUSA", "TECLA_PARAR", "TECLA_ROTA", "TECLA_GRAVAR_PASSAGEM", "TECLA_GRAVAR_LURE",
                   "TECLA_CALIBRAR"]
        teclas = [valores[k] for k in atalhos]
        if len(set(teclas)) != len(teclas):
            messagebox.showerror("Atalhos repetidos", "Cada atalho precisa de uma tecla diferente.")
            return None
        if hasattr(self, "tree_rodizio"):  # aba Rodízio
            valores["RODIZIO_PERSONAGENS"] = self.rodizio_lista()
            if valores.get("RODIZIO_ATIVO") and len(valores["RODIZIO_PERSONAGENS"]) < 2:
                messagebox.showerror("Rodízio", "O rodízio precisa de pelo menos 2 personagens na lista.")
                return None
            sem_hunt = [p["nome"] for p in valores["RODIZIO_PERSONAGENS"] if p["hunt"] and not hunts.existe(p["hunt"])]
            if sem_hunt:
                messagebox.showerror("Rodízio", f"Hunt que não existe mais para: {', '.join(sem_hunt)}.")
                return None
        if hasattr(self, "target_vars"):  # aba Target
            valores["TARGET_ATIVO"] = bool(self.var_target_ativo.get())
            valores["TARGET_DESCONHECIDOS"] = bool(self.var_target_desc.get())
            valores["TARGETS"] = [n for n, v in self.target_vars.items() if v.get()]
        return valores

    def carregar_alcance_poke(self):
        poke = str(self.vars["POKE_CACA"].get()).strip().lower() if "POKE_CACA" in self.vars else ""
        try:
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                alcances = json.load(f).get("POKES_ALCANCE") or {}
        except Exception:
            alcances = {}
        if poke in alcances and "BOX_RAIO_SQM" in self.vars:
            self.vars["BOX_RAIO_SQM"].set(str(alcances[poke]))
            self.status(f"Alcance do {poke}: {alcances[poke]} sqm")
        # silence/stun também é do pokémon (cada pet tem a sua magia de controle)
        try:
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                controles = json.load(f).get("POKES_CONTROLE") or {}
        except Exception:
            controles = {}
        if poke in controles and "SILENCIO_POS_COMBO_S" in self.vars:
            self.vars["SILENCIO_POS_COMBO_S"].set(str(controles[poke].get("s", 0)))
            if "CONTROLE_TIPO" in self.vars:
                self.vars["CONTROLE_TIPO"].set(controles[poke].get("tipo", "silence"))

    def salvar_ajustes(self, avisar=True):
        valores = self.ler_valores()
        if valores is None:
            return False

        ajustes = {}
        if os.path.exists(config.ARQ_AJUSTES):
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                ajustes = json.load(f)
        ajustes.update(valores)
        # cada pokémon de caça lembra o seu alcance
        poke = str(valores.get("POKE_CACA", "")).strip().lower()
        if poke and "BOX_RAIO_SQM" in valores:
            alcances = dict(ajustes.get("POKES_ALCANCE") or {})
            alcances[poke] = valores["BOX_RAIO_SQM"]
            ajustes["POKES_ALCANCE"] = alcances
        if poke and "SILENCIO_POS_COMBO_S" in valores:
            controles = dict(ajustes.get("POKES_CONTROLE") or {})
            controles[poke] = {"tipo": valores.get("CONTROLE_TIPO", "silence"), "s": valores["SILENCIO_POS_COMBO_S"]}
            ajustes["POKES_CONTROLE"] = controles
        with open(config.ARQ_AJUSTES, "w", encoding="utf-8") as f:
            json.dump(ajustes, f, indent=2, ensure_ascii=False)

        # algum ajuste de caça ficou diferente do que está salvo na hunt?
        nome = self.nome_hunt()
        if nome and hunts.existe(nome):
            da_hunt = hunts.info(nome).get("ajustes", {})
            if any(da_hunt.get(k) != valores.get(k) for k in hunts.CHAVES_DA_HUNT if k in valores):
                self.hunt_alterada = True
            if hasattr(self, "label_hunt"):
                self.atualizar_hunt()

        self.atualizar_textos_teclas()
        if avisar:
            self.status("Ajustes salvos ✅")
        return True

    def tecla(self, chave):
        if chave not in self.vars:  # campo de outra aba ainda não montado: usa o valor salvo
            return str(getattr(config, chave)).strip().lower()
        return str(self.vars[chave].get()).strip().lower()

    # =====================================================================
    # Aba Rota
    # =====================================================================

    def criar_aba_rota(self):
        aba = self.nova_aba("📍 Rota")
        self.aba_rota = aba

        try:
            self.pontos = rota.carregar()
        except ValueError as e:
            messagebox.showwarning("Rota", str(e))
            self.pontos = []
        self.rota_alterada = False

        # Hunts com nome: rota + perfis de catch + ajustes de caça
        barra_hunt = ttk.LabelFrame(aba, text="🗺️ Hunt", padding=6)
        barra_hunt.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.hunt_aberta = config.HUNT_ATUAL  # hunt carregada/salva por último
        self.var_hunt = tk.StringVar(value=config.HUNT_ATUAL)
        ttk.Label(barra_hunt, text="Nome:").pack(side=tk.LEFT, padx=(0, 4))
        # editável: digite o nome de uma hunt nova, ou escolha uma salva na setinha
        self.combo_hunt = ttk.Combobox(barra_hunt, textvariable=self.var_hunt, width=28,
                                       values=hunts.listar())
        self.combo_hunt.pack(side=tk.LEFT)
        ttk.Button(barra_hunt, text="📂 Carregar", command=self.carregar_hunt).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(barra_hunt, text="💾 Salvar", command=self.salvar_hunt).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(barra_hunt, text="🗑️ Apagar", command=self.apagar_hunt).pack(side=tk.LEFT, padx=(6, 0))
        self.label_hunt = ttk.Label(barra_hunt, foreground="gray")
        self.label_hunt.pack(side=tk.LEFT, padx=(10, 0))
        self.hunt_alterada = False

        self.label_instrucao_rota = ttk.Label(aba, justify="left", wraplength=640)
        self.label_instrucao_rota.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Lista de pontos
        lista_frame = ttk.Frame(aba)
        lista_frame.grid(row=1, column=0, sticky="ns")
        self.lista = tk.Listbox(lista_frame, height=14, width=34, font=("Consolas", 10),
                                activestyle="none", exportselection=False)
        barra = ttk.Scrollbar(lista_frame, orient=tk.VERTICAL, command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side=tk.LEFT, fill=tk.Y)
        barra.pack(side=tk.LEFT, fill=tk.Y)
        self.lista.bind("<<ListboxSelect>>", lambda e: self.mostrar_preview())

        # Botões
        botoes = ttk.Frame(aba)
        botoes.grid(row=1, column=1, sticky="n", padx=10)
        self.btn_gravar_passagem = tk.Button(botoes, bg="#2e7d32", fg="white", width=24,
                                             command=lambda: self.gravar_ponto(False))
        self.btn_gravar_passagem.pack(fill=tk.X, pady=2)
        self.btn_gravar_lure = tk.Button(botoes, bg="#ef6c00", fg="white", width=24,
                                         command=lambda: self.gravar_ponto(True))
        self.btn_gravar_lure.pack(fill=tk.X, pady=2)
        ttk.Separator(botoes).pack(fill=tk.X, pady=6)
        ttk.Button(botoes, text="🔁 Trocar passagem ⇄ lure", command=self.alternar_tipo).pack(fill=tk.X, pady=2)
        ttk.Button(botoes, text="⬆️ Subir", command=lambda: self.mover(-1)).pack(fill=tk.X, pady=2)
        ttk.Button(botoes, text="⬇️ Descer", command=lambda: self.mover(1)).pack(fill=tk.X, pady=2)
        ttk.Button(botoes, text="❌ Remover ponto", command=self.remover).pack(fill=tk.X, pady=2)
        ttk.Button(botoes, text="🗑️ Apagar rota toda", command=self.limpar).pack(fill=tk.X, pady=2)
        ttk.Separator(botoes).pack(fill=tk.X, pady=6)
        tk.Button(botoes, text="💾 Salvar rota", bg="#1565c0", fg="white",
                  command=self.salvar_rota).pack(fill=tk.X, pady=2)
        self.label_rota_status = ttk.Label(botoes, foreground="#c62828")
        self.label_rota_status.pack(pady=4)

        # Pré-visualização do ponto selecionado
        preview = ttk.LabelFrame(aba, text="Ponto selecionado", padding=6)
        preview.grid(row=1, column=2, sticky="n")
        self.label_preview = ttk.Label(preview, text="(nenhum)", anchor="center", width=20)
        self.label_preview.pack()
        self.thumb = None

        # Coordenada atual (lida do minimapa) — confira antes de gravar
        self.label_pos_atual = ttk.Label(aba, font=("Consolas", 10))
        self.label_pos_atual.grid(row=2, column=2, sticky="n", pady=(8, 0))
        self.ultima_leitura_pos = 0.0

        self.atualizar_textos_teclas()
        self.atualizar_lista()

    def atualizar_textos_teclas(self):
        tp = self.tecla("TECLA_GRAVAR_PASSAGEM").upper()
        tl = self.tecla("TECLA_GRAVAR_LURE").upper()
        tc = self.tecla("TECLA_CALIBRAR").upper()
        if hasattr(self, "btn_gravar_passagem"):
            self.btn_gravar_passagem.config(text=f"📍 Gravar passagem  [{tp}]")
            self.btn_gravar_lure.config(text=f"⚔️ Gravar lure  [{tl}]")
            self.label_instrucao_rota.config(
                text=f"Ande com o personagem até cada ponto e aperte {tp} (passagem) ou {tl} (lure) "
                     f"— funciona com o jogo em foco, enquanto esta aba estiver aberta.\n"
                     f"Cada ponto guarda a coordenada (zoom do minimapa não importa). Salve com um nome na barra Hunt.")
        if hasattr(self, "label_calib_instrucao") and self.calib_etapa is None:
            self.label_calib_instrucao.config(
                text=f"Clique em calibrar e siga as instruções. Use {tc} para marcar e Esc para cancelar.")

    def atualizar_lista(self, selecionar=None):
        self.lista.delete(0, tk.END)
        for i, p in enumerate(self.pontos, start=1):
            suspeito = posicao.ponto_suspeito(p.get("pos"), [q.get("pos") for q in self.pontos])
            coord = f"  ({p['pos'][0]},{p['pos'][1]},{p['pos'][2]})" if p.get("pos") else "  (sem coord.)"
            if suspeito:
                coord += " ⚠️"
            self.lista.insert(tk.END, f"{i:>3}. {'⚔️ LURE' if p['lure'] else '📍 pass.'}{coord}")
            if p["lure"]:
                self.lista.itemconfig(tk.END, foreground="#ef6c00")
        if selecionar is not None and self.pontos:
            selecionar = max(0, min(selecionar, len(self.pontos) - 1))
            self.lista.selection_set(selecionar)
            self.lista.see(selecionar)
        self.label_rota_status.config(text="⚠️ alterações não salvas" if self.rota_alterada else "")
        self.mostrar_preview()
        self.atualizar_info()

    def selecionado(self):
        sel = self.lista.curselection()
        return sel[0] if sel else None

    def mostrar_preview(self):
        i = self.selecionado()
        if i is None:
            self.label_preview.config(image="", text="(nenhum)")
            return
        self.thumb = imagem_tk(self.pontos[i]["img"], 6)
        self.label_preview.config(image=self.thumb, text="")

    def marcar_alterada(self, selecionar):
        self.rota_alterada = True
        self.hunt_alterada = True
        self.atualizar_lista(selecionar)

    def gravar_ponto(self, lure):
        img = recortar_waypoint(capturar_minimapa(self.sct))
        pos = posicao.ler_coordenadas(self.sct, confirmar=True)
        self.pontos.append({"img": img, "lure": lure, "pos": pos})
        self.marcar_alterada(len(self.pontos) - 1)
        onde = f" em {pos[0]}, {pos[1]}, {pos[2]}" if pos else " (⚠️ não li a coordenada)"
        self.status(f"Ponto {len(self.pontos)} gravado ({'lure' if lure else 'passagem'}){onde}.")

    def alternar_tipo(self):
        i = self.selecionado()
        if i is not None:
            self.pontos[i]["lure"] = not self.pontos[i]["lure"]
            self.marcar_alterada(i)

    def mover(self, direcao):
        i = self.selecionado()
        if i is None:
            return
        j = i + direcao
        if 0 <= j < len(self.pontos):
            self.pontos[i], self.pontos[j] = self.pontos[j], self.pontos[i]
            self.marcar_alterada(j)

    def remover(self):
        i = self.selecionado()
        if i is not None:
            del self.pontos[i]
            self.marcar_alterada(i)

    def limpar(self):
        if self.pontos and messagebox.askyesno("Apagar rota", "Apagar todos os pontos da rota?"):
            self.pontos = []
            self.marcar_alterada(None)

    def salvar_rota(self):
        rota.salvar(self.pontos)
        self.rota_alterada = False
        self.atualizar_lista(self.selecionado())
        self.status(f"Rota salva com {len(self.pontos)} pontos ✅")
        return True

    # =====================================================================
    # Aba Calibração
    # =====================================================================

    # ---------- Aba Target: escolher quais monstros atacar pelo nome ----------

    def criar_aba_target(self):
        import target
        aba = self.nova_aba("👾 Target")
        ttk.Label(aba, text="Escolha quais monstros o bot ataca, pelo nome que aparece na Battle.\n"
                            "1) Com os monstros na Battle, aperte \"Ler nomes da Battle\".  "
                            "2) Marque quem atacar.  3) Salvar ajustes.",
                  justify=tk.LEFT).pack(anchor="w", pady=(0, 6))
        self.var_target_ativo = tk.BooleanVar(value=bool(config.TARGET_ATIVO))
        self.var_target_desc = tk.BooleanVar(value=bool(config.TARGET_DESCONHECIDOS))
        ttk.Checkbutton(aba, text="Atacar só os monstros marcados abaixo",
                        variable=self.var_target_ativo).pack(anchor="w")
        ttk.Checkbutton(aba, text="Atacar também monstro que o bot ainda não conhece (nome não lido)",
                        variable=self.var_target_desc).pack(anchor="w")
        botoes = ttk.Frame(aba)
        botoes.pack(anchor="w", pady=6)
        ttk.Button(botoes, text="📖 Ler nomes da Battle", command=self.ler_nomes_battle).pack(side=tk.LEFT)
        ttk.Button(botoes, text="✏️ Renomear", command=self.renomear_target).pack(side=tk.LEFT, padx=4)
        ttk.Button(botoes, text="🗑️ Esquecer", command=self.esquecer_target).pack(side=tk.LEFT)
        self.target_quadro = ttk.Frame(aba)
        self.target_quadro.pack(anchor="w", fill=tk.X)
        self.target_vars = {}
        self.target_marcados = set(config.TARGETS or [])
        self.target_sel = tk.StringVar()
        self.montar_lista_target()

    def montar_lista_target(self):
        import target
        for w in self.target_quadro.winfo_children():
            w.destroy()
        marcados = {n for n, v in self.target_vars.items() if v.get()} | set(getattr(self, "target_marcados", set()))
        self.target_marcados = set()
        self.target_vars = {}
        nomes = target.nomes_conhecidos()
        if not nomes:
            ttk.Label(self.target_quadro, text="(nenhum nome aprendido ainda)").pack(anchor="w")
        for nome in nomes:
            linha = ttk.Frame(self.target_quadro)
            linha.pack(anchor="w")
            v = tk.BooleanVar(value=nome in marcados)
            self.target_vars[nome] = v
            ttk.Checkbutton(linha, text="Atacar", variable=v).pack(side=tk.LEFT)
            ttk.Radiobutton(linha, text=nome, value=nome, variable=self.target_sel).pack(side=tk.LEFT, padx=6)

    def ler_nomes_battle(self):
        import target
        from tela import ler_inimigos
        linhas = ler_inimigos(self.sct, ignorar_primeiro=True, ignorar_rosa=False)
        if not linhas:
            messagebox.showinfo("Target", "Não achei monstros na Battle. Deixe a Battle aberta com monstros nela.")
            return
        vistos = target.ensinar(linhas)
        self.montar_lista_target()
        novos = [n for n, novo in vistos if novo]
        self.status(f"Target: {len(vistos)} nome(s) na Battle" + (f", novos: {', '.join(novos)}" if novos else ""))

    def renomear_target(self):
        import target
        velho = self.target_sel.get()
        if not velho:
            messagebox.showinfo("Target", "Escolha um nome da lista (bolinha) para renomear.")
            return
        novo = self.perguntar("Renomear", f"Nome certo para \"{velho}\":", velho)
        if not novo or novo == velho:
            return
        os.replace(os.path.join(target.PASTA, velho + ".png"), os.path.join(target.PASTA, novo + ".png"))
        if velho in self.target_vars and self.target_vars[velho].get():
            self.target_marcados.add(novo)
        target.carregar_modelos(forcar=True)
        self.montar_lista_target()

    def esquecer_target(self):
        import target
        nome = self.target_sel.get()
        if not nome or not messagebox.askyesno("Target", f"Esquecer o nome \"{nome}\"?"):
            return
        arq = os.path.join(target.PASTA, nome + ".png")
        if os.path.exists(arq):
            os.remove(arq)
        target.carregar_modelos(forcar=True)
        self.montar_lista_target()

    # ---------- Aba Log: mostra o que o bot está fazendo (lê bot_log.txt) ----------

    def criar_aba_log(self):
        aba = self.nova_aba("📜 Log")
        topo = ttk.Frame(aba)
        topo.pack(fill=tk.X, pady=(0, 4))
        self.log_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(topo, text="Rolar sozinho", variable=self.log_auto).pack(side=tk.LEFT)
        ttk.Button(topo, text="Limpar", command=self.log_limpar).pack(side=tk.LEFT, padx=4)
        ttk.Button(topo, text="Abrir bot_log.txt",
                   command=lambda: os.startfile(os.path.join(PASTA, "bot_log.txt"))).pack(side=tk.LEFT)
        caixa = ttk.Frame(aba)
        caixa.pack(fill=tk.BOTH, expand=True)
        self.log_txt = tk.Text(caixa, height=22, width=90, bg="#111", fg="#ddd", insertbackground="#ddd",
                               font=("Consolas", 9), wrap=tk.WORD, state=tk.DISABLED)
        barra = ttk.Scrollbar(caixa, command=self.log_txt.yview)
        self.log_txt.config(yscrollcommand=barra.set)
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for tag, cor in (("aviso", "#ffb74d"), ("erro", "#ef5350"), ("ok", "#81c784"), ("catch", "#ce93d8")):
            self.log_txt.tag_config(tag, foreground=cor)
        arq = os.path.join(PASTA, "bot_log.txt")
        self.log_pos = os.path.getsize(arq) if os.path.exists(arq) else 0
        self.root.after(500, self.log_atualizar)

    def log_limpar(self):
        if hasattr(self, "log_txt"):
            self.log_txt.config(state=tk.NORMAL)
            self.log_txt.delete("1.0", tk.END)
            self.log_txt.config(state=tk.DISABLED)

    def log_atualizar(self):
        arq = os.path.join(PASTA, "bot_log.txt")
        try:
            tam = os.path.getsize(arq) if os.path.exists(arq) else 0
            if tam < self.log_pos:
                self.log_pos = 0  # arquivo foi apagado/recomeçou
            if tam > self.log_pos:
                with open(arq, "rb") as f:
                    f.seek(self.log_pos)
                    novo = f.read().decode("utf-8", errors="replace")
                self.log_pos = tam
                self.log_txt.config(state=tk.NORMAL)
                for linha in novo.splitlines(True):
                    tag = ("erro" if ("❌" in linha or "Traceback" in linha or "Error" in linha) else
                           "aviso" if ("⚠️" in linha or "PRESO" in linha) else
                           "catch" if "[Catch]" in linha else
                           "ok" if ("⚔️" in linha or "Chegou" in linha) else None)
                    self.log_txt.insert(tk.END, linha, tag)
                excesso = int(self.log_txt.index("end-1c").split(".")[0]) - 3000
                if excesso > 0:
                    self.log_txt.delete("1.0", f"{excesso}.0")
                self.log_txt.config(state=tk.DISABLED)
                if self.log_auto.get():
                    self.log_txt.see(tk.END)
        except Exception:
            pass
        self.root.after(500, self.log_atualizar)

    def criar_aba_calibracao(self):
        aba = self.nova_aba("🎯 Calibração")
        self.aba_calib = aba
        self.calib_etapa = None  # None | (chave, nome, "inicio") | (chave, nome, "fim", x0, y)

        self.label_calib_instrucao = ttk.Label(aba, font=("Arial", 11, "bold"),
                                               wraplength=560, justify="left")
        self.label_calib_instrucao.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.leituras = {}
        for linha, (chave, nome) in enumerate(BARRAS, start=1):
            ttk.Label(aba, text=nome, width=20).grid(row=linha, column=0, sticky="w", pady=4)
            barra = ttk.Progressbar(aba, length=220, maximum=100)
            barra.grid(row=linha, column=1, padx=8)
            texto = ttk.Label(aba, width=26)
            texto.grid(row=linha, column=2, sticky="w")
            ttk.Button(aba, text="🎯 Calibrar",
                       command=lambda c=chave, n=nome: self.iniciar_calibracao(c, n)).grid(
                row=linha, column=3, padx=(8, 0))
            self.leituras[chave] = (barra, texto)

        ttk.Label(aba, foreground="gray", wraplength=560, justify="left",
                  text="As barras acima mostram a leitura ao vivo. Se a % bater com o jogo, a calibração "
                       "está certa. Calibre sempre com a barra CHEIA.").grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))

        ttk.Separator(aba).grid(row=4, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Label(aba, text="Tamanho da Battle", width=20).grid(row=5, column=0, sticky="w")
        self.label_battle = ttk.Label(aba)
        self.label_battle.grid(row=5, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Button(aba, text="📏 Ajustar",
                   command=lambda: self.iniciar_calibracao("battle", "Battle")).grid(
            row=5, column=3, padx=(8, 0))
        ttk.Label(aba, foreground="gray", wraplength=560, justify="left",
                  text="Se você aumentar a janela da Battle no jogo para caber mais monstros, "
                       "clique em Ajustar e marque a borda de baixo da lista.").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Separator(aba).grid(row=10, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Label(aba, text="Tela do jogo", width=20).grid(row=11, column=0, sticky="w")
        self.label_layout = ttk.Label(aba, wraplength=420, justify="left")
        self.label_layout.grid(row=11, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Button(aba, text="🔍 Detectar", command=self.detectar_layout).grid(row=11, column=3, padx=(8, 0))
        ttk.Label(aba, foreground="gray", wraplength=560, justify="left",
                  text="Automático: o bot acha a janela do jogo em qualquer monitor e mede o mapa, "
                       "o sqm e o minimapa sozinho (e mede de novo se você mover a janela). "
                       "O botão é só para conferir.").grid(row=12, column=0, columnspan=4, sticky="w")


        self.atualizar_textos_teclas()

    def carregar_calib(self):
        if not os.path.exists(ARQ_CALIBRACAO):
            return {}
        with open(ARQ_CALIBRACAO, encoding="utf-8") as f:
            return json.load(f)

    def detectar_layout(self):
        res = layout.detectar_e_aplicar(self.sct, avisar=False)
        self.label_layout.config(text=layout.resumo(res))

    def atualizar_leituras(self):
        calib = self.carregar_calib()
        for chave, (barra, texto) in self.leituras.items():
            if calib.get(chave):
                pct = ler_barra(self.sct, calib[chave])
                if pct is None:
                    barra["value"] = 0
                    texto.config(text="⚠️ janela 'Pokémon' não visível")
                    continue
                x0, x1, y = posicao_barra(self.sct, calib[chave])
                barra["value"] = pct
                texto.config(text=f"{pct:.0f}%   (x {x0}–{x1}, y {y})")
            else:
                barra["value"] = 0
                texto.config(text="❌ não calibrada")

    def atualizar_texto_battle(self):
        linhas = linhas_que_cabem(config.BATTLE_REGION["height"])
        pet = self.vars["MONSTRINHO_NA_BATTLE"].get()
        self.label_battle.config(
            text=f"cabem {linhas} linhas → até {linhas - (1 if pet else 0)} monstros"
                 f"{' (1ª linha = seu monstrinho)' if pet else ''}")

    def iniciar_calibracao(self, chave, nome):
        self.calib_etapa = (chave, nome, "inicio")
        tecla = self.tecla('TECLA_CALIBRAR').upper()
        if chave == "battle":
            texto = (f"[Battle] Ponha o mouse na BORDA DE BAIXO da lista da Battle "
                     f"(logo abaixo do último monstro que cabe) e aperte {tecla}.")
        else:
            texto = (f"[{nome}] Com a barra CHEIA, ponha o mouse no COMEÇO (esquerda) da barra "
                     f"e aperte {tecla}.")
        self.label_calib_instrucao.config(foreground="#1565c0", text=texto)

    def ajustar_battle(self, y):
        regiao = regiao_battle(self.sct)
        if regiao is None:
            self.calib_etapa = None
            self.label_calib_instrucao.config(
                foreground="#c62828", text="❌ Não achei a janela da Battle na tela. Deixe o título dela visível.")
            return
        altura = y - regiao["top"]
        if altura < config.BATTLE_PRIMEIRA_BARRA_Y + 5:
            self.label_calib_instrucao.config(
                foreground="#c62828", text="❌ Muito em cima: marque a borda de BAIXO da lista da Battle.")
            self.calib_etapa = None
            return
        config.BATTLE_REGION.update(regiao)
        config.BATTLE_REGION["height"] = altura

        ajustes = {}
        if os.path.exists(config.ARQ_AJUSTES):
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                ajustes = json.load(f)
        ajustes["BATTLE_REGION"] = dict(config.BATTLE_REGION)
        with open(config.ARQ_AJUSTES, "w", encoding="utf-8") as f:
            json.dump(ajustes, f, indent=2, ensure_ascii=False)

        self.calib_etapa = None
        self.atualizar_dependencias()
        self.label_calib_instrucao.config(
            foreground="#2e7d32", text=f"✅ Battle ajustada: até {self.max_monstros()} monstros.")

    def passo_calibracao(self):
        x, y = pyautogui.position()
        chave, nome, etapa = self.calib_etapa[:3]
        if chave == "battle":
            self.ajustar_battle(y)
            return
        if etapa == "inicio":
            self.calib_etapa = (chave, nome, "fim", x, y)
            self.label_calib_instrucao.config(
                text=f"[{nome}] Agora ponha o mouse no FIM (direita) da barra "
                     f"e aperte {self.tecla('TECLA_CALIBRAR').upper()}.")
            return
        x0, y0 = self.calib_etapa[3], self.calib_etapa[4]
        barra = medir_barra(self.sct, x0, x, y0)
        salvar_calibracao_barra(chave, barra)
        self.calib_etapa = None
        self.label_calib_instrucao.config(foreground="#2e7d32",
                                          text=f"✅ {nome} calibrado! Confira a % abaixo.")
        self.atualizar_info()

    def cancelar_calibracao(self):
        self.calib_etapa = None
        self.label_calib_instrucao.config(foreground="black")
        self.atualizar_textos_teclas()


    # =====================================================================
    # Perfis de catch (calibra uma vez, fica salvo)
    # =====================================================================

    def criar_perfis_catch(self, aba, linha):
        quadro = ttk.LabelFrame(aba, text="📚 Perfis de catch (calibra uma vez, fica salvo)", padding=8)
        quadro.grid(row=linha, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.catch_amostrando = None  # "especial" / "normal" enquanto espera o F9

        self.label_catch_instrucao = ttk.Label(quadro, foreground="gray", wraplength=640, justify="left")
        self.label_catch_instrucao.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        colunas = ("nome", "tipo", "local", "aqui")
        self.tabela_catch = ttk.Treeview(quadro, columns=colunas, show="headings", height=4,
                                         selectmode="browse")
        for col, titulo, larg in (("nome", "Nome", 150), ("tipo", "Tipo", 80),
                                  ("local", "Vale em", 170), ("aqui", "Aqui?", 50)):
            self.tabela_catch.heading(col, text=titulo)
            self.tabela_catch.column(col, width=larg, anchor="w" if col == "nome" else "center")
        self.tabela_catch.grid(row=1, column=0, rowspan=4, sticky="nsew")
        self.tabela_catch.bind("<<TreeviewSelect>>", lambda e: self.mostrar_perfil_catch())

        botoes = ttk.Frame(quadro)
        botoes.grid(row=1, column=1, rowspan=4, sticky="n", padx=8)
        self.btn_add_especial = ttk.Button(botoes, command=lambda: self.iniciar_amostra_catch("especial"))
        self.btn_add_especial.pack(fill=tk.X, pady=1)
        self.btn_add_normal = ttk.Button(botoes, command=lambda: self.iniciar_amostra_catch("normal"))
        self.btn_add_normal.pack(fill=tk.X, pady=1)
        ttk.Button(botoes, text="🔁 Trocar tipo", command=self.trocar_tipo_catch).pack(fill=tk.X, pady=1)
        ttk.Button(botoes, text="📍 Local: aqui / todo lugar", command=self.trocar_local_catch).pack(fill=tk.X, pady=1)
        ttk.Button(botoes, text="🗑️ Remover", command=self.remover_perfil_catch).pack(fill=tk.X, pady=1)

        self.label_thumb_catch = ttk.Label(quadro, text="", anchor="center", width=12)
        self.label_thumb_catch.grid(row=1, column=2, rowspan=3, sticky="n")
        self.thumb_catch = None
        self.label_catch_tela = ttk.Label(quadro, wraplength=640, justify="left")
        self.label_catch_tela.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.ultima_leitura_catch = 0.0
        self.pos_catch = None
        self.atualizar_perfis_catch()

    def texto_instrucao_catch(self):
        t = self.tecla("TECLA_CALIBRAR").upper()
        if hasattr(self, "btn_add_especial"):
            self.btn_add_especial.config(text=f"➕ Especial  [{t}]")
            self.btn_add_normal.config(text=f"➕ Normal  [{t}]")
        if self.catch_amostrando:
            return (f"[{self.catch_amostrando.upper()}] Ponha o mouse BEM EM CIMA do corpo do monstrinho "
                    f"e aperte {t}. (Esc cancela)")
        return ("Calibre cada monstrinho UMA vez, em cima do corpo dele: o perfil fica salvo e lembra o "
                "lugar onde você estava — quando voltar nessa hunt, ele já vale sozinho.")

    def atualizar_perfis_catch(self, selecionar=None):
        self.label_catch_instrucao.config(text=self.texto_instrucao_catch(),
                                          foreground="#1565c0" if self.catch_amostrando else "gray")
        self.tabela_catch.delete(*self.tabela_catch.get_children())
        for p in catch.carregar_perfis():
            local = p.get("local")
            onde = f"perto de {local[0]}, {local[1]}, {local[2]}" if local else "🌍 todo lugar"
            aqui = "✅" if catch.vale_aqui(p, self.pos_catch) else "—"
            tipo = "✨ especial" if p.get("tipo") == "especial" else "🎾 normal"
            self.tabela_catch.insert("", tk.END, iid=p["id"], values=(p["nome"], tipo, onde, aqui))
        if selecionar and self.tabela_catch.exists(selecionar):
            self.tabela_catch.selection_set(selecionar)
        self.mostrar_perfil_catch()

    def perfil_catch_selecionado(self):
        sel = self.tabela_catch.selection()
        return next((p for p in catch.carregar_perfis() if sel and p["id"] == sel[0]), None)

    def mostrar_perfil_catch(self):
        p = self.perfil_catch_selecionado()
        img = cv2.imread(os.path.join(catch.DIR_CALIB, p["amostra"])) if p and p.get("amostra") else None
        if img is not None:
            self.thumb_catch = imagem_tk(img, 2)
            self.label_thumb_catch.config(image=self.thumb_catch, text="")
        else:
            self.label_thumb_catch.config(image="", text="(padrão)" if p else "")

    def iniciar_amostra_catch(self, tipo):
        self.catch_amostrando = tipo
        self.atualizar_perfis_catch()

    def passo_amostra_catch(self):
        tipo, self.catch_amostrando = self.catch_amostrando, None
        x, y = pyautogui.position()
        sugestao = f"{'Especial' if tipo == 'especial' else 'Normal'} {len(catch.carregar_perfis()) + 1}"
        nome = self.perguntar("Nome do monstrinho", "Como chamar esse monstrinho? (ex.: Rattata azul)", sugestao)
        if not nome:
            self.atualizar_perfis_catch()
            return
        local = posicao.ler_coordenadas(self.sct)
        perfil = catch.adicionar_perfil(self.sct, x, y, nome.strip(), tipo, local)
        if perfil:
            self.hunt_alterada = True
            onde = f" (vale perto de {local[0]}, {local[1]}, {local[2]})" if local else " (vale em todo lugar)"
            self.status(f"Perfil '{perfil['nome']}' salvo{onde} ✅")
            self.atualizar_perfis_catch(selecionar=perfil["id"])
        else:
            messagebox.showwarning("Catch", "Não achei um monstrinho embaixo do mouse. "
                                            "Ponha o mouse bem em cima do corpo e tente de novo.")
            self.atualizar_perfis_catch()

    def trocar_tipo_catch(self):
        self.hunt_alterada = True
        p = self.perfil_catch_selecionado()
        if p:
            catch.alterar_perfil(p["id"], tipo="normal" if p.get("tipo") == "especial" else "especial")
            self.atualizar_perfis_catch(selecionar=p["id"])

    def trocar_local_catch(self):
        self.hunt_alterada = True
        p = self.perfil_catch_selecionado()
        if not p:
            return
        if p.get("local"):
            catch.alterar_perfil(p["id"], local=None)
        else:
            local = posicao.ler_coordenadas(self.sct)
            if not local:
                messagebox.showwarning("Catch", "Não consegui ler a coordenada do minimapa agora.")
                return
            catch.alterar_perfil(p["id"], local=list(local))
        self.atualizar_perfis_catch(selecionar=p["id"])

    def remover_perfil_catch(self):
        self.hunt_alterada = True
        p = self.perfil_catch_selecionado()
        if p and messagebox.askyesno("Remover perfil", f"Remover o perfil '{p['nome']}'?"):
            catch.remover_perfil(p["id"])
            self.atualizar_perfis_catch()

    def atualizar_tela_catch(self):
        """Mostra quantos corpos de cada perfil (que vale aqui) o bot está vendo agora."""
        self.pos_catch = posicao.ler_coordenadas(self.sct) or self.pos_catch
        aqui = [p for p in catch.carregar_perfis() if catch.vale_aqui(p, self.pos_catch)]
        contagem = {}
        for *_, perfil in catch.corpos_na_tela(self.sct, aqui):
            contagem[perfil["nome"]] = contagem.get(perfil["nome"], 0) + 1
        texto = ", ".join(f"{n}× {nome}" for nome, n in contagem.items()) or "nenhum corpo de perfil"
        self.label_catch_tela.config(text=f"👁️ Na tela agora: {texto}")
        sel = self.tabela_catch.selection()
        self.atualizar_perfis_catch(selecionar=sel[0] if sel else None)


    # =====================================================================
    # Hunts com nome
    # =====================================================================

    def nome_hunt(self):
        return getattr(self, "hunt_aberta", "") or ""

    def nome_digitado(self):
        return self.var_hunt.get().strip() if hasattr(self, "var_hunt") else ""

    def atualizar_hunt(self):
        nome = self.nome_hunt()
        if not nome:
            texto = "(nenhuma hunt salva com nome ainda)"
        elif self.hunt_alterada:
            texto = "⚠️ mudou desde que foi salva"
        else:
            texto = f"salva em {hunts.info(nome)['salvo_em']}" if hunts.existe(nome) else ""
        self.label_hunt.config(text=texto)
        self.combo_hunt.config(values=hunts.listar())
        self.atualizar_info()

    def guardar_hunt_atual(self, nome):
        """Lembra qual hunt está aberta (o bot mostra o nome ao iniciar)."""
        ajustes = {}
        if os.path.exists(config.ARQ_AJUSTES):
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                ajustes = json.load(f)
        ajustes["HUNT_ATUAL"] = nome
        with open(config.ARQ_AJUSTES, "w", encoding="utf-8") as f:
            json.dump(ajustes, f, indent=2, ensure_ascii=False)


    def perguntar(self, titulo, texto, inicial=""):
        """Pede um texto numa janelinha que fica SEMPRE na frente do painel. Retorna o texto ou None."""
        win = tk.Toplevel(self.root)
        win.title(titulo)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        ttk.Label(win, text=texto, padding=(12, 10, 12, 4)).pack(anchor="w")
        var = tk.StringVar(value=inicial)
        campo = ttk.Entry(win, textvariable=var, width=42)
        campo.pack(padx=12, pady=4)
        resposta = {"texto": None}

        def ok(*_):
            resposta["texto"] = var.get()
            win.destroy()

        botoes = ttk.Frame(win, padding=(12, 4, 12, 10))
        botoes.pack(fill=tk.X)
        ttk.Button(botoes, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT)
        ttk.Button(botoes, text="OK", command=ok).pack(side=tk.RIGHT, padx=(0, 6))
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda *_: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + 120
        win.geometry(f"+{x}+{y}")
        win.lift()
        campo.focus_force()
        campo.icursor(tk.END)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        self.root.wait_window(win)
        return resposta["texto"]

    def salvar_hunt(self):
        nome = self.nome_digitado()
        if not nome or nome.lower() in ("hunt", "hunt -", "hunt-"):
            nome = self.perguntar("Salvar hunt", "Nome da hunt (ex.: Hunt - Monstrinho verde):",
                                  self.nome_hunt() or "Hunt - ")
        if not nome or not nome.strip():
            return
        nome = nome.strip()
        if hunts.existe(nome) and nome != self.nome_hunt() and not messagebox.askyesno(
                "Salvar hunt", f"Já existe uma hunt '{nome}'. Substituir?"):
            return
        valores = self.ler_valores()
        if valores is None:
            return
        if self.rota_alterada:
            self.salvar_rota()
        self.salvar_ajustes(avisar=False)
        hunts.salvar(nome, valores)
        self.var_hunt.set(nome)
        self.hunt_aberta = nome
        self.guardar_hunt_atual(nome)
        self.hunt_alterada = False
        self.atualizar_hunt()
        self.status(f"Hunt '{nome}' salva ✅ (rota, perfis de catch e ajustes de caça)")

    def carregar_hunt(self):
        nome = self.nome_digitado()
        if not nome or not hunts.existe(nome):
            messagebox.showinfo("Carregar hunt", "Escolha uma hunt salva na lista.")
            return
        if self.bot_rodando():
            messagebox.showwarning("Carregar hunt", "Pare o bot antes de trocar de hunt.")
            return
        if self.hunt_alterada and not messagebox.askyesno(
                "Carregar hunt", "A hunt aberta tem mudanças que não foram salvas como hunt. "
                                 "Carregar outra mesmo assim?"):
            return
        ajustes = hunts.carregar(nome)
        # rota
        self.pontos = rota.carregar()
        self.rota_alterada = False
        self.atualizar_lista(0 if self.pontos else None)
        # ajustes de caça
        for chave, valor in ajustes.items():
            if chave in self.vars:
                self.vars[chave].set(valor)
        if hasattr(self, "target_vars"):
            self.var_target_ativo.set(bool(ajustes.get("TARGET_ATIVO", False)))
            self.var_target_desc.set(bool(ajustes.get("TARGET_DESCONHECIDOS", True)))
            self.target_marcados = set(ajustes.get("TARGETS", []))
            self.montar_lista_target()
        self.atualizar_dependencias()
        self.salvar_ajustes(avisar=False)
        self.hunt_aberta = nome
        self.guardar_hunt_atual(nome)
        # perfis de catch
        if hasattr(self, "tabela_catch"):
            self.atualizar_perfis_catch()
        self.hunt_alterada = False
        self.atualizar_hunt()
        self.status(f"Hunt '{nome}' carregada ✅")

    def apagar_hunt(self):
        nome = self.nome_digitado()
        if nome and hunts.existe(nome) and messagebox.askyesno(
                "Apagar hunt", f"Apagar a hunt salva '{nome}'?\n(a rota aberta agora continua aqui)"):
            hunts.apagar(nome)
            if nome == self.hunt_aberta:
                self.hunt_aberta = ""
            self.var_hunt.set("")
            self.guardar_hunt_atual("")
            self.atualizar_hunt()


    # =====================================================================
    # Ensinar efeitos (ruim / bom) para a Medicine
    # =====================================================================

    def atualizar_texto_efeitos(self, aviso=None):
        t = self.tecla("TECLA_CALIBRAR").upper()
        self.btn_ensinar_ruim.config(text=f"🎓 Efeito RUIM [{t}]")
        self.btn_ensinar_bom.config(text=f"👍 Efeito BOM [{t}]")
        ruins, bons = efeitos.contar_aprendidos()
        if self.efeito_ensinando:
            texto = (f"Com o efeito ativo no monstrinho, ponha o mouse em cima do ícone dele "
                     f"(embaixo da barra F1..F7) e aperte {t}. Esc cancela.")
            self.label_efeitos.config(text=texto, foreground="#1565c0")
            return
        texto = aviso or (f"Ensinados: {ruins} ruim(ns), {bons} bom(ns). Borda vermelha já é reconhecida. "
                          f"Ícones desconhecidos ficam salvos em diagnostico/.")
        self.label_efeitos.config(text=texto, foreground="gray")

    def iniciar_ensinar_efeito(self, tipo):
        self.efeito_ensinando = tipo
        self.atualizar_texto_efeitos()

    def passo_ensinar_efeito(self):
        tipo, self.efeito_ensinando = self.efeito_ensinando, None
        x, y = pyautogui.position()
        nome = efeitos.ensinar(self.sct, x, y, negativo=(tipo == "neg"))
        if nome:
            self.atualizar_texto_efeitos(f"✅ Aprendido como efeito {'RUIM' if tipo == 'neg' else 'BOM'}. "
                                         f"(ensinados: {efeitos.contar_aprendidos()[0]} ruim, "
                                         f"{efeitos.contar_aprendidos()[1]} bom)")
        else:
            self.atualizar_texto_efeitos("❌ Não achei um ícone de efeito embaixo do mouse. Deixe a barra de "
                                         "golpes visível e ponha o mouse bem em cima do ícone.")

    # =====================================================================
    # Rodapé: iniciar / parar
    # =====================================================================

    def criar_rodape(self, pai):
        linha_info = ttk.Frame(pai)
        linha_info.pack(fill=tk.X, pady=(8, 4))
        self.label_info = ttk.Label(linha_info, foreground="gray")
        self.label_info.pack(side=tk.LEFT)
        ttk.Button(linha_info, text="💾 Salvar ajustes", command=self.salvar_ajustes).pack(side=tk.RIGHT)

        botoes = ttk.Frame(pai)
        botoes.pack(fill=tk.X)
        self.btn_iniciar = tk.Button(botoes, text="▶  Iniciar bot", bg="#2e7d32", fg="white",
                                     font=("Arial", 11, "bold"), command=self.iniciar_bot)
        self.btn_iniciar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_parar = tk.Button(botoes, text="■  Parar bot", bg="#c62828", fg="white",
                                   font=("Arial", 11, "bold"), command=self.parar_bot,
                                   state=tk.DISABLED)
        self.btn_parar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.btn_rota = tk.Button(botoes, text="🧭 Ligar rota", bg="#1565c0", fg="white",
                                  font=("Arial", 11, "bold"), command=self.alternar_rota, state=tk.DISABLED)
        self.btn_rota.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # Liga/desliga cada parte do bot, a qualquer hora (com o bot rodando, vale em ~2 s)
        modulos = ttk.Frame(pai)
        modulos.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(modulos, text="Ligar/desligar:").pack(side=tk.LEFT, padx=(0, 4))
        self.botoes_modulo = {}
        for chaves, rotulo in self.MODULOS:
            b = tk.Button(modulos, text=rotulo, width=10, relief=tk.RAISED,
                          command=lambda c=chaves: self.alternar_modulo(c))
            b.pack(side=tk.LEFT, padx=2)
            self.botoes_modulo[chaves] = b
        self.pintar_modulos()

        linha = ttk.Frame(pai)
        linha.pack(fill=tk.X, pady=(6, 0))
        self.var_topo = tk.BooleanVar(value=True)
        ttk.Checkbutton(linha, text="📌 Painel sempre por cima", variable=self.var_topo,
                        command=lambda: self.root.attributes("-topmost", self.var_topo.get())).pack(side=tk.LEFT)
        self.root.attributes("-topmost", True)
        self.var_minimizar = tk.BooleanVar(value=True)
        ttk.Checkbutton(linha, text="Minimizar ao iniciar o bot", variable=self.var_minimizar).pack(side=tk.LEFT, padx=8)
        self.label_status = ttk.Label(linha, text="Bot parado.", font=("Arial", 10, "bold"))
        self.label_status.pack(side=tk.RIGHT)

    def status(self, texto):
        self.label_status.config(text=texto)

    def atualizar_info(self):
        if not hasattr(self, "label_info"):
            return  # ainda montando a janela
        lures = sum(1 for p in self.pontos if p["lure"])
        partes = []
        if self.nome_hunt():
            partes.append(f"Hunt: {self.nome_hunt()}{' *' if getattr(self, 'hunt_alterada', False) else ''}")
        partes.append(f"Rota: {len(self.pontos)} pontos ({lures} de lure)" if self.pontos
                      else "Rota: ❌ não gravada")
        calib = self.carregar_calib()
        faltando = [nome for chave, nome in BARRAS if not calib.get(chave)]
        partes.append("Calibração: ✅" if not faltando else f"Calibração: ❌ falta {', '.join(faltando)}")
        self.label_info.config(text="   |   ".join(partes))

    def bot_rodando(self):
        return self.proc_bot is not None and self.proc_bot.poll() is None

    def iniciar_bot(self):
        if self.bot_rodando():
            return
        if not self.salvar_ajustes(avisar=False):
            return
        if self.rota_alterada:
            if messagebox.askyesno("Rota não salva", "A rota tem alterações não salvas. Salvar agora?"):
                self.salvar_rota()
        golpes = [f"f{i}" for i in range(1, 7)]
        suspeitas = []
        if self.vars["CURA_HP_ATIVA"].get() and self.tecla("TECLA_CURA_HP") in golpes:
            suspeitas.append(f"cura do personagem = {self.tecla('TECLA_CURA_HP').upper()}")
        if self.vars["CURA_POKE_ATIVA"].get() and self.tecla("TECLA_CURA_POKE") in golpes:
            suspeitas.append(f"cura do monstrinho = {self.tecla('TECLA_CURA_POKE').upper()}")
        if suspeitas and not messagebox.askyesno(
                "Tecla de cura suspeita",
                "No seu jogo, F1 a F6 são os GOLPES do monstrinho, não cura:\n  - "
                + "\n  - ".join(suspeitas)
                + "\n\nSe a cura não for essa tecla, o personagem pode MORRER.\n"
                  "Corrija na aba Cura. Iniciar mesmo assim?"):
            return
        if not self.carregar_calib().get("hp"):
            messagebox.showwarning("Falta calibrar", "Calibre o HP do personagem na aba 'Calibração'.")
            return

        self.cancelar_calibracao()
        # sem janela de console: o que o bot escreve aparece na aba "📜 Log" do painel
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.proc_bot = subprocess.Popen([sys.executable, os.path.join(PASTA, "bot.py")], cwd=PASTA, env=env,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        self.log_limpar()
        if self.var_minimizar.get():
            # o painel por cima do jogo cobre o personagem: o bot não consegue clicar nem enxergar
            self.root.after(300, self.root.iconify)
        self.btn_iniciar.config(state=tk.DISABLED)
        self.btn_parar.config(state=tk.NORMAL)
        if self.vars["ROTA_AO_INICIAR"].get():
            self.status(f"🟢 Bot rodando — foque o jogo em 4 s ({self.tecla('TECLA_PAUSA').upper()} pausa)")
        else:
            self.status(f"🟢 Bot rodando, parado — ligue a rota quando quiser ({self.tecla('TECLA_ROTA').upper()})")

    def parar_bot(self):
        if self.bot_rodando():
            self.proc_bot.terminate()

    def estado_rota_bot(self):
        """Rota ligada no bot que está rodando? (o bot escreve isso em estado_bot.json)"""
        try:
            with open(controle.ARQ_ESTADO, encoding="utf-8") as f:
                return bool(json.load(f).get("rota"))
        except Exception:
            return False

    def alternar_rota(self):
        """Pede ao bot (outro processo) para ligar/desligar a rota."""
        if not self.bot_rodando():
            return
        ligar = not self.estado_rota_bot()
        with open(controle.ARQ_COMANDO, "w", encoding="utf-8") as f:
            json.dump({"rota": ligar, "quando": time.time()}, f)
        self.status("🧭 Ligando a rota..." if ligar else "🛑 Desligando a rota...")

    MODULOS = [
        (("CACA_ATIVA",), "⚔️ Caça"),
        (("CURA_HP_ATIVA",), "💊 Cura eu"),
        (("CURA_POKE_ATIVA",), "💊 Cura pet"),
        (("MEDICINE_ATIVO",), "🧪 Medicine"),
        (("REVIVE_SE_MORRER",), "❤️ Revive"),
        (("CATCH_ATIVO",), "🎾 Catch"),
        (("ALARME_ATIVO",), "🔔 Alarme"),
    ]

    def _ajustes_arquivo(self):
        try:
            with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def modulo_ligado(self, chaves):
        aj = self._ajustes_arquivo()
        return all(bool(aj.get(k, getattr(config, k, False))) for k in chaves)

    def pintar_modulos(self):
        for chaves, b in self.botoes_modulo.items():
            ligado = self.modulo_ligado(chaves)
            b.config(bg="#2e7d32" if ligado else "#9e9e9e", fg="white", relief=tk.SUNKEN if ligado else tk.RAISED)

    def alternar_modulo(self, chaves):
        """Liga/desliga uma parte do bot. Grava direto no ajustes.json (o bot rodando aplica sozinho)."""
        if chaves == ("MEDICINE_ATIVO",) and not self.tecla("TECLA_MEDICINE"):
            messagebox.showwarning("Medicine", "Coloque a tecla da Medicine (aba Modo de hunt) antes de ligar.")
            return
        novo = not self.modulo_ligado(chaves)
        aj = self._ajustes_arquivo()
        for k in chaves:
            aj[k] = novo
            setattr(config, k, novo)
            if k in self.vars:
                self.vars[k].set(novo)
        with open(config.ARQ_AJUSTES, "w", encoding="utf-8") as f:
            json.dump(aj, f, indent=2, ensure_ascii=False)
        self.pintar_modulos()
        nome = next(r for c, r in self.MODULOS if c == chaves)
        self.status(f"{nome}: {'LIGADO' if novo else 'desligado'}")

    def atualizar_botao_rota(self):
        if not self.bot_rodando():
            self.btn_rota.config(state=tk.DISABLED, text="🧭 Ligar rota", bg="#1565c0")
            return
        t = self.tecla("TECLA_ROTA").upper()
        if self.estado_rota_bot():
            self.btn_rota.config(state=tk.NORMAL, text=f"🛑 Desligar rota [{t}]", bg="#ef6c00")
        else:
            self.btn_rota.config(state=tk.NORMAL, text=f"🧭 Ligar rota [{t}]", bg="#1565c0")

    # =====================================================================
    # Loops (teclas do jogo e atualizações periódicas)
    # =====================================================================

    def aba_atual(self):
        externa = self.abas.nametowidget(self.abas.select())
        return self._interna.get(externa, externa)

    def selecionar_aba(self, interna):
        """Abre a aba cujo conteúdo é `interna`."""
        for externa, dentro in self._interna.items():
            if dentro is interna:
                self.abas.select(externa)

    # =====================================================================
    # Janela redimensionável: abas com rolagem
    # =====================================================================

    def nova_aba(self, titulo):
        """
        Cria uma aba com barras de rolagem e devolve o frame onde vai o conteúdo.
        Se a janela ficar menor que o conteúdo, a aba rola (rodinha do mouse funciona).
        """
        externa = ttk.Frame(self.abas)
        canvas = tk.Canvas(externa, highlightthickness=0, borderwidth=0)
        rol_v = ttk.Scrollbar(externa, orient=tk.VERTICAL, command=canvas.yview)
        rol_h = ttk.Scrollbar(externa, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=rol_v.set, xscrollcommand=rol_h.set)
        rol_v.pack(side=tk.RIGHT, fill=tk.Y)
        rol_h.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        interna = ttk.Frame(canvas, padding=8)
        janela = canvas.create_window((0, 0), window=interna, anchor="nw")

        def ajustar(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # conteúdo cabe? então ocupa a largura toda (sem rolagem à toa)
            larg = max(interna.winfo_reqwidth(), canvas.winfo_width())
            canvas.itemconfigure(janela, width=larg)
            for barra, cabe in ((rol_v, interna.winfo_reqheight() <= canvas.winfo_height()),
                                (rol_h, interna.winfo_reqwidth() <= canvas.winfo_width())):
                if cabe and barra.winfo_ismapped():
                    barra.pack_forget()
                elif not cabe and not barra.winfo_ismapped():
                    barra.pack(side=tk.RIGHT if barra is rol_v else tk.BOTTOM,
                               fill=tk.Y if barra is rol_v else tk.X, before=canvas)

        interna.bind("<Configure>", ajustar)
        canvas.bind("<Configure>", ajustar)

        def rodinha(evento):
            if interna.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(int(-evento.delta / 120), "units")

        # rodinha só rola a aba que está debaixo do mouse
        externa.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", rodinha))
        externa.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        self.abas.add(externa, text=titulo)
        self._interna[externa] = interna
        self._canvas = getattr(self, "_canvas", []) + [(canvas, interna)]
        return interna

    def restaurar_tamanho(self):
        """Abre do tamanho do conteúdo (ou com o tamanho/posição que o painel tinha da última vez)."""
        self.root.update_idletasks()
        larg = max(i.winfo_reqwidth() for _, i in self._canvas)
        alt = max(i.winfo_reqheight() for _, i in self._canvas)
        for canvas, _ in self._canvas:  # tamanho natural: cabe tudo sem rolagem
            canvas.configure(width=larg, height=alt)
        geo = getattr(config, "PAINEL_GEOMETRIA", "")
        if geo:
            try:
                self.root.geometry(geo)
            except tk.TclError:
                pass

    def guardar_tamanho(self):
        try:
            ajustes = {}
            if os.path.exists(config.ARQ_AJUSTES):
                with open(config.ARQ_AJUSTES, encoding="utf-8") as f:
                    ajustes = json.load(f)
            ajustes["PAINEL_GEOMETRIA"] = self.root.geometry()
            with open(config.ARQ_AJUSTES, "w", encoding="utf-8") as f:
                json.dump(ajustes, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def ao_trocar_aba(self):
        if self.aba_atual() is not self.aba_calib and self.calib_etapa:
            self.cancelar_calibracao()

    def processar_teclas(self):
        """Trata as teclas apertadas (mesmo com o jogo em foco), conforme a aba aberta."""
        while not self.fila_teclas.empty():
            tecla = self.fila_teclas.get()
            if self.bot_rodando():
                continue  # com o bot rodando, as teclas são dele
            aba = self.aba_atual()
            if aba is self.aba_rota:
                if tecla == self.tecla("TECLA_GRAVAR_PASSAGEM"):
                    self.gravar_ponto(False)
                elif tecla == self.tecla("TECLA_GRAVAR_LURE"):
                    self.gravar_ponto(True)
            elif aba is getattr(self, "aba_modo", None) and self.efeito_ensinando:
                if tecla == self.tecla("TECLA_CALIBRAR"):
                    self.passo_ensinar_efeito()
                elif tecla in ("esc", "escape"):
                    self.efeito_ensinando = None
                    self.atualizar_texto_efeitos()
            elif aba is getattr(self, "aba_catch", None) and self.catch_amostrando:
                if tecla == self.tecla("TECLA_CALIBRAR"):
                    self.passo_amostra_catch()
                elif tecla in ("esc", "escape"):
                    self.catch_amostrando = None
                    self.atualizar_perfis_catch()
            elif aba is self.aba_calib and self.calib_etapa:
                if tecla == self.tecla("TECLA_CALIBRAR"):
                    self.passo_calibracao()
                elif tecla in ("esc", "escape"):
                    self.cancelar_calibracao()
        self.root.after(50, self.processar_teclas)

    def vigiar(self):
        if self.proc_bot is not None and self.proc_bot.poll() is not None:
            self.proc_bot = None
            self.btn_iniciar.config(state=tk.NORMAL)
            self.btn_parar.config(state=tk.DISABLED)
            self.status("Bot parado.")
        self.atualizar_botao_rota()
        if self.aba_atual() is self.aba_calib:
            self.atualizar_leituras()
        if self.aba_atual() is getattr(self, "aba_catch", None) and time.time() - self.ultima_leitura_catch > 2:
            self.ultima_leitura_catch = time.time()
            self.atualizar_tela_catch()
        if self.aba_atual() is self.aba_rota and time.time() - self.ultima_leitura_pos > 2:
            self.ultima_leitura_pos = time.time()
            pos = posicao.ler_coordenadas(self.sct)
            self.label_pos_atual.config(
                text=f"📍 Agora: {pos[0]}, {pos[1]}, {pos[2]}" if pos else "📍 Agora: (não li a coordenada)")
        self.root.after(500, self.vigiar)

    def fechar(self):
        if self.bot_rodando():
            if not messagebox.askyesno("Bot rodando", "O bot ainda está rodando. Parar e sair?"):
                return
            self.proc_bot.terminate()
        if self.rota_alterada:
            resp = messagebox.askyesnocancel("Rota não salva", "Salvar as alterações da rota antes de sair?")
            if resp is None:
                return
            if resp:
                self.salvar_rota()
        self.guardar_tamanho()
        keyboard.unhook_all()
        self.sct.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Painel(root)
    root.mainloop()
