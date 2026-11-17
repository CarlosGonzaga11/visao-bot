"""
Janela de CONTROLE da box (silence / stun do pet) — lógica pura, usada pela V1 (bot.py) e pela V2.

Alguns pets soltam no combo uma magia que deixa os monstros atingidos:
  - SILENCE: podem andar, mas NÃO atacam;
  - STUN:    ficam PRESOS no lugar e não atacam.
Enquanto isso dura, esses monstros não são perigo: o revive sai na hora e ninguém precisa correr da box
(antes o bot corria/adiava sem necessidade e a hunt ficava lenta).

Segurança (personagem morre com 1 golpe):
  - só vale para quem estava NA BOX quando o combo saiu (foto das posições); monstro que chegou depois
    ou monstro SOLTO não tomou a magia e continua sendo perigo;
  - a janela termina `margem` segundos ANTES do tempo configurado;
  - STUN é conferido: o monstro tem que continuar no MESMO sqm. Se não está mais lá, o stun não pegou
    (ou acabou) e ele volta a ser perigo. SILENCE não dá para conferir pela tela e o monstro anda: cada um é
    SEGUIDO leitura a leitura (`conferir_stun` atualiza onde ele está).
"""

TIPOS = ("silence", "stun")


def parametros(cfg, poke=""):
    """(tipo, duração em s) para o pokémon de caça. Por pokémon (POKES_CONTROLE) ou o padrão do config."""
    poke = str(poke or getattr(cfg, "POKE_CACA", "") or "").strip().lower()
    por_poke = getattr(cfg, "POKES_CONTROLE", None) or {}
    if poke and poke in por_poke:
        p = por_poke[poke] or {}
        tipo = p.get("tipo", "silence")
        return (tipo if tipo in TIPOS else "silence"), float(p.get("s", 0) or 0)
    tipo = getattr(cfg, "CONTROLE_TIPO", "silence")
    return (tipo if tipo in TIPOS else "silence"), float(getattr(cfg, "SILENCIO_POS_COMBO_S", 0) or 0)


def _cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class JanelaControle:
    def __init__(self, margem=0.5):
        self.margem = margem
        self.tipo = ""
        self.inicio = 0.0
        self.fim = 0.0
        self.alvos = set()       # sqm ABSOLUTOS (x, y, z) dos monstros que tomaram a magia
        self.sem_pos = False     # sem coordenada: não dá para saber quem é quem -> vale para a box toda

    def comecar(self, agora, tipo, duracao, alvos_abs, sem_pos=False):
        """Combo acabou de sair. alvos_abs = posições absolutas dos monstros da box naquele instante."""
        if duracao <= 0 or tipo not in TIPOS:
            self.parar()
            return False
        self.tipo, self.inicio = tipo, agora
        self.fim = agora + max(0.0, duracao - self.margem)
        self.alvos = {tuple(a) for a in alvos_abs}
        self.sem_pos = sem_pos
        return True

    def parar(self):
        self.fim = 0.0
        self.alvos = set()

    def ativa(self, agora):
        return agora < self.fim and (bool(self.alvos) or self.sem_pos)

    def restante(self, agora):
        return max(0.0, self.fim - agora)

    def controlado(self, sqm_abs, agora):
        """O monstro neste sqm (absoluto) está silenciado/stunado AGORA?"""
        if not self.ativa(agora) or sqm_abs is None:
            return False
        if self.sem_pos:
            return True
        # stun: preso no MESMO sqm; silence: o alvo é seguido a cada leitura (conferir_stun), então também é o sqm exato
        return tuple(sqm_abs) in self.alvos

    def conferir_stun(self, ocupados_abs, agora):
        """
        Atualiza os alvos com a leitura de agora. Devolve quantos STUN saíram (andaram = não estavam presos).
          STUN   : alvo que não está mais no MESMO sqm sai da lista (o stun não pegou ou acabou).
          SILENCE: o monstro ANDA (só não ataca): segue cada alvo até a criatura mais perto a ≤ 2 sqm de onde
                   ele estava (uma leitura a cada ~0,25–0,5 s, o monstro anda 1 sqm a cada ~0,5 s); sem
                   ninguém perto, sai da lista (morreu ou sumiu da leitura).
        """
        if not self.ativa(agora) or self.sem_pos:
            return 0
        ocup = {tuple(o) for o in ocupados_abs}
        if self.tipo == "stun":
            fora = {a for a in self.alvos if a not in ocup}
            self.alvos -= fora
            return len(fora)
        # 1ª passada: quem continua no mesmo sqm; 2ª: quem andou (não pode "roubar" o sqm de outro alvo parado)
        novos = {a for a in self.alvos if a in ocup}
        usados = set(novos)
        for a in sorted(self.alvos - novos):
            perto = [o for o in ocup if o not in usados and len(o) == 3 and o[2] == a[2] and _cheb(o, a) <= 2]
            if perto:
                o = min(perto, key=lambda o: _cheb(o, a))
                novos.add(o)
                usados.add(o)
        self.alvos = novos
        return 0
