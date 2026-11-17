# Configurações do bot (resolução 1366x768)
# Estes são os valores PADRÃO. O painel.py salva suas escolhas em "ajustes.json",
# que sobrescreve os valores daqui (veja o fim do arquivo).
import json as _json
import os as _os

# --- Battle ---
# A janela da Battle é achada pelo título (calibracao/ancora_battle.png).
# A lista começa nesse deslocamento em relação ao título; "height" = tamanho da lista.
BATTLE_ANCORA_OFFSET = (-17, -16)
BATTLE_REGION = {"top": 345, "left": 14, "width": 191, "height": 315}
# Detecção dos monstros pelas barras de vida (posições relativas à BATTLE_REGION)
BATTLE_BARRA_X = 48            # coluna onde começa a barra de vida de cada monstro
BATTLE_CLIQUE_X = 70           # onde clicar (em cima do nome do monstro)
BATTLE_CLIQUE_OFFSET_Y = -13   # nome fica 13 px acima da barra
BATTLE_PRIMEIRA_BARRA_Y = 107  # onde fica a barra da 1ª linha da Battle
BATTLE_ALTURA_LINHA = 30       # distância entre uma linha e outra da Battle
MONSTRINHO_NA_BATTLE = True    # seu monstrinho aparece em 1º na Battle -> ignora a 1ª linha
IGNORAR_ROSA = True            # ignora monstros de nome/barra rosa (anti-block: não podem ser atacados)

# --- Tela do jogo (onde as criaturas andam) ---
GAME_VIEW = {"left": 50, "top": 24, "width": 1068, "height": 560}
SQM_PX = 51                    # tamanho de 1 sqm em pixels na sua tela
PLAYER_TILE_XY = (584, 304)    # centro do sqm do personagem (ele fica sempre no meio)

# --- Minimapa ---
MINIMAP_REGION = {"top": 76, "left": 1177, "width": 180, "height": 120}
# Cruz branca do personagem (coordenada absoluta na tela)
PLAYER_SCREEN_X = 1266
PLAYER_SCREEN_Y = 138

# --- Posição por coordenadas (lidas da caixinha "x, y, z" do minimapa) ---
COORD_REGION = {"left": 1183, "top": 56, "width": 81, "height": 19}
NAV_VIEW_DX = (-7, 8)          # até quantos sqm para o lado dá para clicar na tela do jogo
NAV_VIEW_DY = (-4, 4)          #   (sem cair em cima da Battle ou da hotbar)
NAV_TRAVADO_S = 2.5            # sem sair do lugar esse tempo = caminho bloqueado -> recalcula
NAV_PRESO_S = 25.0             # sem sair do lugar esse tempo (sem monstros) = preso -> alarme e pausa
NAV_FALHAS_MAX = 4             # tentativas seguidas sem chegar em ponto nenhum -> alarme e pausa (0 = nunca)
NAV_CHEGADA_SQM = 1            # distância (sqm) para considerar que chegou no ponto

# --- Waypoints por imagem ---
ROTA_DIR = "rota"              # pasta onde ficam wp_001.png ... e rota.json
TEMPLATE_SIZE = 32             # lado do recorte salvo em volta do personagem (px, par)
CRUZ_BRACO = 6                 # meio-comprimento da cruz do personagem no minimapa (com folga)
CRUZ_LARGURA = 3               # meia-largura da barra da cruz (com contorno e folga)
MATCH_THRESHOLD = 0.80         # confiança mínima para aceitar que achou o waypoint
CHEGADA_TOLERANCIA = 2         # distância (px do minimapa) para considerar "chegou"
RECLIQUE_INTERVALO = 0.8       # segundos entre cliques enquanto anda (corrige rota)
TIMEOUT_WAYPOINT = 20.0        # desiste do waypoint depois desse tempo (s)
ROTA_IDA_E_VOLTA = True        # True: 1→2→3→2→1 ... | False: 1→2→3→1 (circular)

# --- Catch (tacar ball no monstrinho especial depois da luta) ---
CATCH_ATIVO = False            # ligue no painel depois de tirar a amostra e definir a tecla
TECLA_BALL = ""                # tecla da pokébola na hotbar (ex.: "f7", "4", "mouse5")
CATCH_TENTATIVAS = 3           # quantas balls tenta no mesmo corpo
CATCH_TENTATIVAS_ESPECIAL = 6  # ...no corpo de especial/shiny (é obrigatório tentar: "exhausted" faz perder ball)
CATCH_PROCURA_S = 5.0          # shiny morreu e o corpo não aparece (magia do pet por cima): procura por até N s
CATCH_ESPERA = 1.5             # espera depois de cada ball (s)
CATCH_DISTANCIA_MAX = 6        # só taca em corpos até essa distância (sqm)
CATCH_BALL_MOUSE = True        # ball: mouse EM CIMA do corpo + tecla da ball (sem clique). Desligado: tecla e depois clique
CATCH_CHEGAR_PERTO = False     # especial a mais de 2 sqm: anda até o lado antes da ball (com auto loot não precisa)
CATCH_NORMAL_ATIVO = False     # catch normal: taca ball nos corpos dos perfis "normal" depois de cada luta
CATCH_ESTRELAS = True          # especial = monstrinho com estrelinhas em volta do nome (sem precisar de perfil)
CATCH_CORPO = True             # especial pelo CORPO MORTO: perfis especiais "pelo corpo" (cor) no fim de cada luta;
                               # onde um perfil desses vale, as estrelinhas são ignoradas
CATCH_SHINY_AUTO = True        # shiny automático: criatura de cor RARA na hunt (não a do pet) vira perfil
                               # pelo corpo sozinha (shiny.py) — não precisa calibrar
CATCH_AJUSTE_X = 0             # monstro grande (Magneton = 1) é desenhado deslocado: a ball vai N sqm para a direita do desenho
CATCH_AJUSTE_Y = 0             # ...e N sqm para baixo (negativo = esquerda/cima)
LOOT_ANTES_BALL = True         # sem auto loot: chega do lado do corpo especial e aperta a tecla de loot antes da ball
TECLA_LOOT = "space"           # tecla de pegar loot
LOOT_ESPERA = 1.0              # espera depois de pegar o loot (s)
CATCH_RAIO_LOCAL = 150         # um perfil com local só vale até essa distância (sqm) de onde foi calibrado

# --- Alarme de mensagens no chat Default ---
CHAT_REGION = {"left": 18, "top": 626, "width": 600, "height": 68}  # área das mensagens
ALARME_ATIVO = True
ALARME_QUALQUER_MSG = False    # False = só quando alguém fala (texto amarelo)
ALARME_PAUSAR_BOT = True       # pausa o bot quando o alarme tocar (F12 continua)
ALARME_DURACAO = 10.0          # segundos de bipe
MEU_NOME = ""                  # seu nome no jogo: a sua própria fala no Default não toca o alarme
ALARME_ABAS_IGNORAR = "NPCs, Game Chat, Trade, Help"  # abas novas que NÃO são mensagem privada
ALARME_PLAYER_ATIVO = True     # alarme quando OUTRO player (criatura sem caveira que não é o seu pet) chega na tela
ALARME_PLAYER_PAUSAR = False   # ...e pausa o bot (09/11: desligado — parar a hunt quando chega alguém é ruim)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # para ler o texto da mensagem

# --- Jeito humano (movimentos menos mecânicos) ---
HUMANO_ATIVO = True
HUMANO_INTENSIDADE = 60        # 10–100%: quanto o mouse, cliques e tempos variam
HUMANO_PARADAS = 15            # % de chance de dar uma paradinha ao chegar num ponto da rota

# --- Atalhos globais ---
TECLA_PAUSA = "f12"            # pausa / continua o bot
TECLA_PARAR = "f11"            # encerra o bot
TECLA_ROTA = "f10"             # liga / desliga a rota (andar e puxar lure) com o bot rodando
ROTA_AO_INICIAR = False        # False: o bot começa parado (só cura, medicine, alarme) até você ligar a rota
CACA_ATIVA = True              # liga/desliga a CAÇA (atacar lure, com ou sem rota) — botão no painel
COMBATE_SEM_ROTA = True        # rota desligada: ataca o lure que você fizer na mão
PARADO_PARA_ATACAR_S = 1.5     # ...quando você fica parado esse tempo com monstros na Battle
TECLA_GRAVAR_PASSAGEM = "f5"   # (painel, aba Rota) grava ponto de passagem sem sair do jogo
TECLA_GRAVAR_LURE = "f6"       # (painel, aba Rota) grava ponto de lure sem sair do jogo
TECLA_CALIBRAR = "f9"          # (painel, aba Calibração) marca começo/fim da barra

# --- Calibração (gerada pelo calibrar.py) ---
CALIBRACAO_DIR = "calibracao"
TOLERANCIA_COR_BARRA = 40      # quanto a cor do pixel pode variar e ainda contar como barra

# --- Combate ---
TECLA_ATAQUE = "q"             # combo de magias
INTERVALO_ATAQUE = 1.5         # segundos entre ciclos de ataque
TIMEOUT_COMBATE = 60.0         # desiste do lure se a Battle não esvaziar nesse tempo (s)
MAGIA_AGRUPAR_ATIVA = True     # só solta a magia quando os monstros estiverem perto
MAGIA_RAIO_SQM = 4             # ...a até essa distância (sqm) do personagem
MODO_LUTA_ATIVO = False        # Fight Mode do jogo: defensivo lurando, ofensivo batendo
TECLA_OFENSIVO = "add"         # Offensive Fight Mode (NumpadAdd = "add")
TECLA_DEFENSIVO = "subtract"   # Defensive Fight Mode (NumpadSubtract = "subtract")
MODO_OFENSIVO_ATIVO = False    # apertar o ofensivo no começo da luta (desligado: o jogo já troca sozinho
                               # quando usa a magia; o bot só volta pro defensivo no fim da luta)
DEF_LURE_ATIVO = False         # magia de defesa enquanto lura (ex.: F1 do pet)
TECLA_DEF_LURE = "f1"
DEF_LURE_MIN = 2               # usa quando tiver pelo menos tantos monstros atrás
DEF_LURE_INTERVALO = 20.0      # não repete antes desse tempo (s)
LURE_QUEDA_PERIGO = 25         # monstrinho perdeu essa % de vida em 3 s lurando -> luta na hora
LURE_IR_ATE_PONTO = 6          # lure encheu a até essa distância (sqm) do ponto de lure: vai até ele antes de lutar
IGNORAR_SOBRA = True           # matou o lure e sobraram poucos: ignora e vai para o próximo lure
SOBRA_MAX = 2                  # até quantos monstros que sobraram são ignorados
TARGET_ATIVO = False           # Target: atacar só os monstros marcados na aba Target
TARGET_DESCONHECIDOS = True    # Target: atacar monstro cujo nome o bot ainda não aprendeu
TARGETS = []                   # Target: nomes que podem ser atacados
CLICAR_ALVO = True             # clica no 1º da Battle para escolher alvo (desligue se só usa ataque em área)
POKE_CACA = ""                 # nome do pokémon que está caçando (cada um tem seu alcance)
POKES_ALCANCE = {}             # {nome: alcance em sqm} guardado pelo painel
BOX_HP_SOLTAR = 60             # monstrinho abaixo disso: solta o combo com quem já está no alcance (não espera a box)
BOX_RAIO_SQM = 1               # box fechada = inimigos a até essa distância (sqm) do MONSTRINHO
MAGIA_ESPERA_MAX = 5.0         # se não agruparem nesse tempo (s), solta mesmo assim
POKESTOP_ATIVO = True          # quando o lure termina (começo da luta), aperta o pokestop: o monstrinho para de andar
TECLA_POKESTOP = "p"           # tecla do pokestop
SAIR_DA_BOX = True
NORMAL_SEM_FUGIR = True       # modo NORMAL (hunt sem risco de morrer): não corre/posiciona na luta — mata e segue
CORRIDAS_POR_BOX = 2           # em cada luta, o personagem se afasta da box no máximo N vezes (depois fica parado)
DISTANCIA_MONSTROS = 4         # na luta: ficar a pelo menos N sqm de QUALQUER monstro (eles têm magia em área)
BOX_DIAGONAL_SQM = 3           # distância (sqm, na diagonal) do personagem até o monstrinho na luta             # depois do pokestop, o personagem sai de perto do monstrinho para os monstros fecharem a box nele
ORDER_DEPOIS_LUTA = True       # order (bolinha do mouse) no personagem quando a luta acaba: tira o pet do pokestop
ORDER_ANDANDO = True           # order no destino enquanto anda na rota: o pet acompanha o lure
ORDER_INTERVALO = 2.0          # intervalo mínimo entre orders andando (s)

# --- Medicine (tira efeito negativo do monstrinho, ex.: blind, antes de atacar) ---
MEDICINE_ATIVO = False
TECLA_MEDICINE = ""            # tecla da Medicine na hotbar
MEDICINE_ESPERA = 3.0          # intervalo mínimo entre duas Medicines (s)
MEDICINE_DESISTE_S = 60.0      # Medicine não tirou o efeito (2x): para de insistir por esse tempo (s)
MEDICINE_CLICAR_POKE = False   # depois da tecla, clicar no retrato do monstrinho
MEDICINE_EM_DESCONHECIDO = True  # efeito que o bot não conhece: usa Medicine por garantia

# --- Modo de hunt ---
HUNT_ATUAL = ""                # nome da hunt aberta (o painel cuida disso)
PAINEL_GEOMETRIA = ""          # tamanho/posição do painel (o painel lembra sozinho)

# --- Rodízio de personagens (bonecos da MESMA conta; sem senha: a tela de seleção já está logada) ---
RODIZIO_ATIVO = False          # caça N voltas com um personagem, desloga (Ctrl+Q) e entra no próximo, sem fim
RODIZIO_PERSONAGENS = []       # [{"nome": "Heroi Alfa", "hunt": "marowak-stn-8", "voltas": 2, "ponto": 1}]
                               # ponto = waypoint onde desloga depois das voltas (0 = onde fechar a volta)
RODIZIO_SEM_BATTLE_S = 4.0     # círculo atrás do pokémon CINZA (sem battle) por esse tempo antes do Ctrl+Q
RODIZIO_BATTLE_MAX_S = 120.0   # battle não sai em tanto tempo → alarme + pausa
RODIZIO_ESPERA_SAIR_S = 15.0   # depois do Ctrl+Q, tempo máximo até a tela de seleção aparecer
RODIZIO_ESPERA_LOGIN_S = 40.0  # depois do Login, tempo máximo até o jogo aparecer
RODIZIO_TECLAS_SAIR = ["ctrl", "q"]  # deslogar no PokeAlliance
MODO_HUNT = "normal"           # "normal", "revive", "outland" ou "nightmare"
OUTLAND_MAX_REVIVES = 6        # outland: revives seguidos SEM matar ninguém antes de desistir (shiny/especial vivo: sem limite)
COMBO_DURACAO = 2.5            # tempo que o combo leva para soltar todas as magias (s)
SILENCIO_POS_COMBO_S = 3.0     # depois do combo os monstros da box ficam silenciados/stun (Gyarados: silence ~3 s):
                               # nessa janela eles não contam como perigo e o revive sai na hora (0 = desliga)
CONTROLE_TIPO = "silence"      # "silence" (andam, não atacam) ou "stun" (presos: o bot confere se ficaram no lugar)
POKES_CONTROLE = {}            # {pokémon: {"tipo": ..., "s": ...}} cada pet de caça lembra o seu (o painel guarda)
CONTROLE_MARGEM_S = 0.5        # a janela acaba esse tanto ANTES do tempo configurado (segurança)
TECLA_REVIVE = ""              # revive: tecla do revive na hotbar
REVIVE_SE_MORRER = True       # em qualquer modo: monstrinho morreu (HP 0%) -> revive na hora
REVIVE_CLICAR_POKE = False     # revive: depois da tecla, clicar no retrato do monstrinho
REVIVE_ESPERA = 1.0            # revive: espera depois de usar (s)
REVIVE_APOS_LURE = True        # revive: usar também depois de matar (sai com as magias prontas)
NIGHTMARE_TECLAS = ""          # nightmare: teclas para chamar cada poke, em ordem (ex.: "1, 2, 3, 4")
NIGHTMARE_COOLDOWN = 30.0      # nightmare: cooldown das magias de cada poke (s)
TROCA_ESPERA = 1.5             # nightmare: tempo para o poke trocado sair da ball (s)
NIGHTMARE_VOLTAR_PRIMEIRO = True  # nightmare: depois de matar, volta pro 1º poke

# --- Lure (juntar monstros antes de lutar) ---
LURE_ATIVO = True              # False = luta assim que aparecer 1 monstro
LURE_MINIMO = 7                # só para para lutar quando tiver pelo menos isso na Battle
LURE_SEGURANCA_ATIVA = True    # luta antes de juntar tudo se o HP ficar baixo
LURE_HP_SEGURANCA = 50         # ...abaixo dessa % de HP do personagem
LURE_POKE_HP_SEGURANCA = 40    # ...ou se o HP do MONSTRINHO cair abaixo dessa %
LURE_PRESO_S = 4.0             # parado esse tempo (cercado/bloqueado) com monstros atrás -> luta
LURE_ESPERA_PONTO = 6.0        # nos pontos marcados como lure, espera o "trem" alcançar (s)
LURE_MAX_VOLTAS = 2            # depois de N voltas na rota sem completar, luta com o que tiver (0 = nunca)

# --- Cura automática ---
CURA_HP_ATIVA = True
HP_LIMITE = 60                 # cura o personagem quando o HP ficar abaixo dessa %
TECLA_CURA_HP = "f1"           # AJUSTE para a hotkey de cura do personagem
CURA_POKE_ATIVA = True
POKE_HP_LIMITE = 50            # cura o monstrinho quando o HP dele ficar abaixo dessa %
TECLA_CURA_POKE = "f2"         # AJUSTE para a hotkey de cura do monstrinho
COOLDOWN_CURA = 1.0            # intervalo mínimo entre duas curas (s)
CURA_POKE_FORA_COMBATE = True  # a poção do monstrinho cancela se ele levar hit: só usa sem inimigos
POT_DURACAO = 8.0              # tempo que a poção leva curando (não aperta de novo nesse meio tempo)
DESCANSAR_ATE = 80             # depois da luta, espera o monstrinho chegar nessa % antes de seguir (0 = não espera)
DESCANSO_MAX = 40.0            # tempo máximo descansando (s)

# --- Caixa-preta (só observa: grava provas quando o personagem leva dano) ---
CAIXA_PRETA_ATIVA = True       # salva tela + HP + criaturas + log em diagnostico/caixa_preta/ quando você apanha
CAIXA_PRETA_QUEDA = 5          # queda mínima do HP do personagem (%) entre duas leituras para virar evento
CAIXA_PRETA_MAX = 20           # no máximo N eventos salvos por sessão (cada um ~2 MB)

# --- Ajustes salvos pelo painel.py (sobrescrevem os padrões acima) ---
ARQ_AJUSTES = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ajustes.json")
if _os.path.exists(ARQ_AJUSTES):
    with open(ARQ_AJUSTES, encoding="utf-8") as _f:
        for _chave, _valor in _json.load(_f).items():
            if _chave.isupper() and _chave in globals():
                globals()[_chave] = _valor
