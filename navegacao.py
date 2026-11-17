"""
Navegação por coordenadas: memória de obstáculos + cálculo de caminho (A*).

Memória do mapa (salva em mapa_memoria.json, por andar "z"):
  - "livres":     sqm onde o personagem já pisou (com certeza dá para andar)
  - "bloqueados": sqm onde ele travou tentando passar. Bloqueio novo pode ser só
                  um monstro no caminho, então ele "esfria" com o tempo; se travar
                  várias vezes no mesmo lugar, fica marcado como parede.

Para andar, o bot calcula um caminho do personagem até o ponto preferindo sqm
livres conhecidos, evitando os bloqueados, e clica no sqm mais distante desse
caminho que ainda aparece na tela do jogo (o próprio jogo anda até ele).
"""
import heapq
import json
import math
import os
import threading
import time

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_MAPA = os.path.join(PASTA, "mapa_memoria.json")

BLOQUEIO_TEMPORARIO_S = 90   # bloqueio visto 1–2 vezes some depois desse tempo
BLOQUEIO_PERMANENTE = 3      # travou 3+ vezes no mesmo sqm = parede

VIZINHOS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


class MemoriaMapa:
    def __init__(self, arquivo=ARQ_MAPA):
        self.arquivo = arquivo
        self.livres = set()        # {(x, y, z)}
        self.bloqueados = {}       # {(x, y, z): [vezes, ultima_vez]}
        self.passagens = []        # [((x, y, z) antes, (x, y, z) depois)] escadas/buracos já usados
        self._lock = threading.Lock()
        self._alterado = False
        self.carregar()

    # ---------- arquivo ----------

    def carregar(self):
        if not os.path.exists(self.arquivo):
            return
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                dados = json.load(f)
            self.livres = {tuple(p) for p in dados.get("livres", [])}
            self.bloqueados = {tuple(b[:3]): [b[3], 0.0] for b in dados.get("bloqueados", [])
                               if b[3] >= BLOQUEIO_PERMANENTE}  # temporários não valem de um dia pro outro
            self.passagens = [(tuple(a), tuple(b)) for a, b in dados.get("passagens", [])]
        except Exception as e:
            print(f"[Mapa] Não consegui ler a memória do mapa ({e!r}), começando do zero.")

    def salvar(self):
        with self._lock:
            if not self._alterado:
                return
            dados = {"livres": sorted(self.livres),
                     "bloqueados": [[*p, v[0]] for p, v in self.bloqueados.items()],
                     "passagens": [[list(a), list(b)] for a, b in self.passagens]}
            self._alterado = False
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f)

    # ---------- aprender ----------

    def pisou(self, pos):
        with self._lock:
            if pos not in self.livres:
                self.livres.add(pos)
                self._alterado = True
            if pos in self.bloqueados:  # se pisou, não é parede
                del self.bloqueados[pos]
                self._alterado = True

    def registrar_passagem(self, antes, depois):
        """O personagem mudou de andar: guarda onde estava antes e onde apareceu."""
        if antes[2] == depois[2] or max(abs(antes[0] - depois[0]), abs(antes[1] - depois[1])) > 3:
            return False  # não é escada/buraco (ou foi teleporte)
        with self._lock:
            for a, b in self.passagens:
                if (distancia(a, antes) <= 1 and distancia(b, depois) <= 1) or                         (distancia(a, depois) <= 1 and distancia(b, antes) <= 1):
                    return False  # já conhecida (nos dois sentidos)
            self.passagens.append((antes, depois))
            self._alterado = True
        return True

    def passagem(self, pos, z_destino, alvo):
        """
        Passagem conhecida do andar de `pos` para `z_destino` (vale nos dois sentidos:
        quem desceu por uma escada sobe por ela). Retorna (lado_daqui, lado_de_la) ou None.
        Escolhe a de menor caminho: até a passagem + da passagem até o alvo.
        """
        candidatas = []
        for a, b in self.passagens:
            for daqui, de_la in ((a, b), (b, a)):
                if daqui[2] == pos[2] and de_la[2] == z_destino:
                    custo = distancia(pos, daqui) + max(abs(de_la[0] - alvo[0]), abs(de_la[1] - alvo[1]))
                    candidatas.append((custo, daqui, de_la))
        if not candidatas:
            return None
        _, daqui, de_la = min(candidatas)
        return daqui, de_la

    def bloquear(self, pos):
        with self._lock:
            if pos in self.livres and self.bloqueados.get(pos, [0])[0] < 1:
                vezes = 1  # já pisou ali antes: provavelmente era um monstro no caminho
            else:
                vezes = self.bloqueados.get(pos, [0])[0] + 1
            self.bloqueados[pos] = [vezes, time.time()]
            self._alterado = True
            return vezes

    def esta_bloqueado(self, pos, agora=None):
        b = self.bloqueados.get(pos)
        if not b:
            return False
        if b[0] >= BLOQUEIO_PERMANENTE:
            return True
        return (agora or time.time()) - b[1] < BLOQUEIO_TEMPORARIO_S

    # ---------- caminho ----------

    def caminho(self, inicio, fim):
        """
        A* de `inicio` até `fim` (mesmo andar). Sqm conhecidos custam menos que
        desconhecidos; bloqueados são proibidos. Procura numa área pequena primeiro
        e, se não achar (a passagem pode estar mais longe), aumenta a área.
        Retorna a lista de sqm (sem o inicial) ou None se não achou caminho.
        """
        for margem, max_nos in ((12, 6000), (30, 25000)):
            rota = self._astar(inicio, fim, margem, max_nos)
            if rota is not None:
                return rota
        return None

    def _astar(self, inicio, fim, margem, max_nos):
        z = inicio[2]
        x0, x1 = sorted((inicio[0], fim[0]))
        y0, y1 = sorted((inicio[1], fim[1]))
        x0, x1, y0, y1 = x0 - margem, x1 + margem, y0 - margem, y1 + margem
        agora = time.time()

        def h(p):
            dx, dy = abs(p[0] - fim[0]), abs(p[1] - fim[1])
            return max(dx, dy) + 0.4 * min(dx, dy)

        abertos = [(h(inicio), 0.0, inicio)]
        veio = {inicio: None}
        custo = {inicio: 0.0}
        nos = 0
        while abertos and nos < max_nos:
            _, g, atual = heapq.heappop(abertos)
            nos += 1
            if atual[:2] == fim[:2]:
                rota = []
                while atual != inicio:
                    rota.append(atual)
                    atual = veio[atual]
                return rota[::-1]
            if g > custo.get(atual, math.inf):
                continue
            for dx, dy in VIZINHOS:
                viz = (atual[0] + dx, atual[1] + dy, z)
                if not (x0 <= viz[0] <= x1 and y0 <= viz[1] <= y1):
                    continue
                if viz[:2] != fim[:2] and self.esta_bloqueado(viz, agora):
                    continue
                passo = (1.0 if viz in self.livres else 1.6) * (1.4 if dx and dy else 1.0)
                novo = g + passo
                if novo < custo.get(viz, math.inf):
                    custo[viz] = novo
                    veio[viz] = atual
                    heapq.heappush(abertos, (novo + h(viz), novo, viz))
        return None


def proximo_destino(memoria, pos, alvo, limite_dx, limite_dy, ocupados=(), rota=None, max_passos=None):
    """
    Sqm para clicar agora: o ponto mais adiante do caminho calculado que ainda
    aparece na tela (dentro de limite_dx/limite_dy em volta do personagem) e não
    tem criatura em cima. Com `max_passos`, não vai além desse tanto de sqm no caminho.
    Retorna (x, y, z) ou None.
    """
    if rota is None:
        rota = memoria.caminho(pos, alvo)
    if not rota:
        # sem caminho conhecido: mira reto, limitado à tela
        dx = max(limite_dx[0], min(limite_dx[1], alvo[0] - pos[0]))
        dy = max(limite_dy[0], min(limite_dy[1], alvo[1] - pos[1]))
        return (pos[0] + dx, pos[1] + dy, pos[2]) if (dx or dy) else None

    escolhido = None
    if max_passos:  # logo depois de travar: mira perto, contornando o obstáculo passo a passo
        rota = rota[:max_passos]
    for p in rota:
        dx, dy = p[0] - pos[0], p[1] - pos[1]
        if not (limite_dx[0] <= dx <= limite_dx[1] and limite_dy[0] <= dy <= limite_dy[1]):
            break  # saiu da tela: para no último que estava visível
        if (dx, dy) not in ocupados:
            escolhido = p
    return escolhido or rota[0]


def primeiro_passo(memoria, pos, alvo, rota=None):
    """Próximo sqm vizinho no caminho (é nele que o personagem travou)."""
    if rota is None:
        rota = memoria.caminho(pos, alvo)
    if rota:
        return rota[0]
    sx = (alvo[0] > pos[0]) - (alvo[0] < pos[0])
    sy = (alvo[1] > pos[1]) - (alvo[1] < pos[1])
    return (pos[0] + sx, pos[1] + sy, pos[2])


def distancia(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
