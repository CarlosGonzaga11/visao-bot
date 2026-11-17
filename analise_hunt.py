"""
Análise de uma hunt pelo bot_log.txt (e pela caixa-preta): onde o tempo vai, perigos, travas e o que melhorar.

    venv\\Scripts\\python.exe analise_hunt.py "remoraid farm"          (todas as sessões dessa hunt)
    venv\\Scripts\\python.exe analise_hunt.py "remoraid farm" 2026-11-09  (só as sessões desse dia)

Escreve o relatório na tela e em diagnostico/analise_<hunt>_<data>.md. Só LÊ arquivos.
"""
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime

PASTA = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(PASTA, "bot_log.txt")
HORA = re.compile(r"^(\d\d):(\d\d):(\d\d) ")


def seg(linha):
    m = HORA.match(linha)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def sessoes(linhas, hunt, dia=None):
    """[(data, [linhas])] das sessões da hunt (cada "bot iniciado" começa uma)."""
    todas, atual = [], None
    for l in linhas:
        m = re.search(r"===== (\S+) (\S+) bot iniciado", l)
        if m:
            atual = {"data": m.group(1), "hora": m.group(2), "linhas": [], "hunt": None, "modo": None}
            todas.append(atual)
            continue
        if atual is None:
            continue
        atual["linhas"].append(l)
        h = re.match(r"\d\d:\d\d:\d\d Hunt: (.+)", l)
        if h:
            atual["hunt"] = h.group(1).strip()
        mo = re.search(r"modo (\w+)\) com", l)
        if mo:
            atual["modo"] = mo.group(1)
    return [s for s in todas if s["hunt"] and s["hunt"].lower() == hunt.lower() and (not dia or s["data"] == dia)]


def tempo_ativo(linhas):
    """Segundos com o bot rodando (sem as pausas F12/alarme)."""
    total, ini, pausado_em = 0, None, None
    ultimo = None
    for l in linhas:
        t = seg(l)
        if t is None:
            continue
        if ini is None:
            ini = t
        if "Bot PAUSADO" in l and pausado_em is None:
            pausado_em = t
        elif "Bot RETOMADO" in l and pausado_em is not None:
            total -= t - pausado_em
            pausado_em = None
        ultimo = t
    if ini is None:
        return 0
    if pausado_em is not None:
        total -= ultimo - pausado_em
    return max(0, total + (ultimo - ini))


def analisar(sess):
    r = collections.Counter()
    lutas = []           # dicts por luta
    tempos_lure = []     # fim da luta → começo da próxima
    pontos_trava = collections.Counter()
    pontos_luta = collections.Counter()
    jogadores = collections.Counter()
    motivos_luta = collections.Counter()
    ativo = 0
    for s in sess:
        L = s["linhas"]
        ativo += tempo_ativo(L)
        luta, fim_anterior, wp_atual = None, None, None
        for l in L:
            t = seg(l)
            if t is None:
                continue
            w = re.search(r"Indo para o waypoint (\d+)/", l)
            if w:
                wp_atual = int(w.group(1))
            if "Iniciando combate" in l:
                if fim_anterior is not None:
                    tempos_lure.append(t - fim_anterior)
                m = re.search(r"⚔️\s+(.+?) Iniciando", l)
                motivos_luta[(m.group(1) if m else "?")[:45]] += 1
                pontos_luta[wp_atual] += 1
                luta = {"ini": t, "combo": None, "fim": None, "revives": 0, "corridas": 0, "pet_morreu": 0,
                        "como": None, "monstros_ini": None}
                lutas.append(luta)
            if luta and luta["fim"] is None:
                if luta["combo"] is None and ("Box fechada" in l or "soltando" in l or "assim mesmo" in l):
                    luta["combo"] = t
                if "Usando revive" in l:
                    luta["revives"] += 1
                if "Indo para a diagonal" in l or "Sem canto seguro" in l or "saindo para" in l or "me afasto" in l:
                    luta["corridas"] += 1
                if "Monstrinho morreu" in l:
                    luta["pet_morreu"] += 1
                for chave, como in (("Battle limpa", "limpou"), ("fora da tela: seguindo", "fugiram"),
                                    ("fora de alcance: seguindo", "fora de alcance"), ("ignorando e indo", "sobra"),
                                    ("não esvaziou em", "timeout")):
                    if chave in l:
                        luta["fim"], luta["como"] = t, como
                        fim_anterior = t
            # contadores gerais
            for chave, nome in (
                    ("Monstrinho morreu", "pet morreu"), ("CaixaPreta] 💥", "dano em você"),
                    ("Travado em", "travou andando"), ("Recalculando caminho", "recalculou caminho"),
                    ("Não saí do lugar", "canto sem caminho"), ("Não consegui ir", "canto sem caminho"),
                    ("Sem canto seguro", "sem canto seguro"), ("corrida extra", "corrida de emergência"),
                    ("adio o revive", "revive adiado"), ("Esperando os monstros alcançarem", "esperou o trem no ponto"),
                    ("Ninguém no alcance", "combo segurado (ninguém no alcance)"), ("Não agruparam", "combo sem box completa"),
                    ("fugiram?", "monstros fora da tela/fugiram"), ("levando o monstrinho", "levou o pet até os monstros"),
                    ("PLAYER NA TELA", "alarme de player"), ("Na tela e fora da Battle", "players vistos"),
                    ("ALARME", "alarmes (todos)"), ("Bot PAUSADO", "pausas"), ("Traceback", "ERRO (traceback)"),
                    ("tacando ball", "balls"), ("QUEBROU", "ball quebrou"), ("Especial na Battle", "especial visto"),
                    ("Monstrinho com estrelinhas", "especial visto (estrelinhas)"), ("Medi o mapa estranho", "layout estranho"),
                    ("minimapa não encontrado", "minimapa não encontrado"), ("não é o jogo", "tecla/clique bloqueado (janela na frente)"),
                    ("Medicine", "medicine"), ("HP baixo (você", "lure parado por HP baixo"),
                    ("Lure cheio", "lure cheio"), ("voltas sem completar", "lure incompleto (voltas)"),
                    ("Retomando pelo ponto", "retomou a rota"), ("SILENCE em", "silence aplicado")):
                if chave in l:
                    r[nome] += 1
            tr = re.search(r"Travado em (\d+), (\d+)", l)
            if tr:
                pontos_trava[(int(tr.group(1)), int(tr.group(2)))] += 1
            pl = re.search(r"Na tela e fora da Battle: (.+)", l)
            if pl:
                for n in pl.group(1).split(","):
                    jogadores[n.strip()[:20]] += 1
    return r, lutas, tempos_lure, pontos_trava, pontos_luta, jogadores, motivos_luta, ativo


def media(v):
    return sum(v) / len(v) if v else 0


def relatorio(hunt, dia=None):
    linhas = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    sess = sessoes(linhas, hunt, dia)
    if not sess:
        return f"Nenhuma sessão da hunt '{hunt}' no log."
    r, lutas, lure, travas, pontos, jogadores, motivos, ativo = analisar(sess)
    h = ativo / 3600 or 1e-9
    fechadas = [x for x in lutas if x["fim"]]
    dur = [x["fim"] - x["ini"] for x in fechadas]
    ate_combo = [x["combo"] - x["ini"] for x in lutas if x["combo"]]
    como = collections.Counter(x["como"] or "não terminou" for x in lutas)
    modos = collections.Counter(s["modo"] for s in sess)
    out = []
    p = out.append
    p(f"# Análise da hunt: {hunt}" + (f" ({dia})" if dia else ""))
    p(f"Sessões: {len(sess)} ({', '.join(s['data'] + ' ' + s['hora'][:5] for s in sess)}) | modos: {dict(modos)}")
    p(f"Tempo rodando (sem pausas): {ativo / 60:.0f} min")
    p("")
    p("## Ritmo")
    p(f"- Lutas: {len(lutas)} → **{len(lutas) / h:.0f} lutas/hora**")
    p(f"- Duração da luta: média {media(dur):.0f} s (máx {max(dur or [0])} s)")
    p(f"- Do começo da luta até o 1º combo: média {media(ate_combo):.1f} s (máx {max(ate_combo or [0])} s)")
    p(f"- Do fim de uma luta até a próxima (andar + lure): média {media(lure):.0f} s (máx {max(lure or [0])} s)")
    gasto_luta = sum(dur)
    gasto_lure = sum(lure)
    p(f"- Tempo total: luta {gasto_luta / 60:.0f} min | entre lutas {gasto_lure / 60:.0f} min | resto (início/pausas/catch) "
      f"{max(0, ativo - gasto_luta - gasto_lure) / 60:.0f} min")
    p(f"- Como as lutas terminaram: {dict(como)}")
    p(f"- Por que as lutas começaram: {dict(motivos.most_common(5))}")
    p("")
    p("## Luta")
    p(f"- Revives por luta: {media([x['revives'] for x in lutas]):.1f} | corridas/afastamentos por luta: "
      f"{media([x['corridas'] for x in lutas]):.1f}")
    for k in ("combo sem box completa", "combo segurado (ninguém no alcance)", "levou o pet até os monstros",
              "monstros fora da tela/fugiram", "silence aplicado", "revive adiado", "corrida de emergência",
              "sem canto seguro", "canto sem caminho", "medicine"):
        if r[k]:
            p(f"- {k}: {r[k]}")
    p("")
    p("## Perigo")
    for k in ("dano em você", "lure parado por HP baixo", "pet morreu"):
        p(f"- {k}: {r[k]}")
    p("")
    p("## Rota e lure")
    for k in ("lure cheio", "lure incompleto (voltas)", "esperou o trem no ponto", "travou andando", "recalculou caminho",
              "retomou a rota"):
        p(f"- {k}: {r[k]}")
    if travas:
        p(f"- Onde mais trava (coordenada: vezes): {dict(travas.most_common(5))}")
    if pontos:
        p(f"- Waypoint onde as lutas começam (wp: lutas): {dict(sorted(pontos.items(), key=lambda kv: -kv[1])[:8])}")
    p("")
    p("## Catch")
    for k in ("especial visto", "especial visto (estrelinhas)", "balls", "ball quebrou"):
        if r[k]:
            p(f"- {k}: {r[k]}")
    p("")
    p("## Segurança e problemas")
    for k in ("alarme de player", "players vistos", "alarmes (todos)", "pausas", "tecla/clique bloqueado (janela na frente)",
              "layout estranho", "minimapa não encontrado", "ERRO (traceback)"):
        if r[k]:
            p(f"- {k}: {r[k]}")
    if jogadores:
        p(f"- Nomes lidos como 'player' (OCR): {dict(jogadores.most_common(6))}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    hunt = sys.argv[1]
    dia = sys.argv[2] if len(sys.argv) > 2 else None
    texto = relatorio(hunt, dia)
    print(texto)
    nome = re.sub(r"\W+", "_", hunt.lower()).strip("_")
    arq = os.path.join(PASTA, "diagnostico", f"analise_{nome}_{datetime.now():%Y-%m-%d_%H-%M}.md")
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    open(arq, "w", encoding="utf-8").write(texto + "\n")
    print(f"\n(salvo em {os.path.relpath(arq, PASTA)})")
