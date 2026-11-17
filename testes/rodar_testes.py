"""
Roda TODOS os testes do bot (testes/teste_*.py), um por vez, e mostra o resumo.

    venv\\Scripts\\python.exe testes\\rodar_testes.py            (todos)
    venv\\Scripts\\python.exe testes\\rodar_testes.py corridas   (só os que têm "corridas" no nome)

Segurança:
  - liga BOT_TESTE=1: humano.py/controle.py nunca mexem no mouse/teclado de verdade;
  - faz backup de ajustes.json, mapa_memoria.json, rota/, hunts/ e calibracao/ e restaura no fim
    (mesmo se um teste falhar ou travar);
  - cada teste tem no máximo LIMITE_S segundos (travou = falhou).
Cada teste imprime "N/M testes passaram" e sai com código 0 se tudo passou.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

if hasattr(sys.stdout, "reconfigure"):  # emojis no console do Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.dirname(AQUI)
PYTHON = os.path.join(PASTA, "venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable
LIMITE_S = 120
DADOS_DO_USUARIO = ["ajustes.json", "mapa_memoria.json", "rota", "hunts", "calibracao"]


def backup():
    destino = tempfile.mkdtemp(prefix="bot_backup_")
    for nome in DADOS_DO_USUARIO:
        orig = os.path.join(PASTA, nome)
        if os.path.isdir(orig):
            shutil.copytree(orig, os.path.join(destino, nome))
        elif os.path.isfile(orig):
            shutil.copy2(orig, os.path.join(destino, nome))
    return destino


def _restaurar_pasta(salvo, orig):
    """
    Devolve a pasta copiando POR CIMA, arquivo por arquivo, e apaga só o que os testes criaram.
    (09/11: rmtree + copytree falhou no meio — arquivo em uso pelo painel/bot — e apagou 5 ícones de
    `calibracao/efeitos`.) Devolve a lista de erros.
    """
    erros = []
    for raiz, pastas, arquivos in os.walk(salvo):
        rel = os.path.relpath(raiz, salvo)
        destino = os.path.normpath(os.path.join(orig, rel))
        os.makedirs(destino, exist_ok=True)
        for a in arquivos:
            try:
                shutil.copy2(os.path.join(raiz, a), os.path.join(destino, a))
            except OSError as e:
                erros.append(f"{os.path.join(rel, a)}: {e}")
    for raiz, pastas, arquivos in os.walk(orig):
        rel = os.path.relpath(raiz, orig)
        for a in arquivos:
            if not os.path.exists(os.path.join(salvo, rel, a)):
                try:
                    os.remove(os.path.join(raiz, a))  # criado pelos testes
                except OSError as e:
                    erros.append(f"{os.path.join(rel, a)}: {e}")
    return erros


def restaurar(destino):
    erros = []
    for nome in DADOS_DO_USUARIO:
        salvo = os.path.join(destino, nome)
        orig = os.path.join(PASTA, nome)
        try:
            if os.path.isdir(salvo):
                erros += _restaurar_pasta(salvo, orig)
            elif os.path.isfile(salvo):
                shutil.copy2(salvo, orig)
        except OSError as e:
            erros.append(f"{nome}: {e}")
    if erros:
        print(f"\n⚠️ NÃO consegui devolver tudo (arquivo em uso?). O backup FICOU em {destino}:")
        for e in erros[:10]:
            print("   " + e)
        return False
    shutil.rmtree(destino, ignore_errors=True)
    return True


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    arquivos = sorted(f for f in glob.glob(os.path.join(AQUI, "teste_*.py")) if filtro in os.path.basename(f))
    env = dict(os.environ, BOT_TESTE="1", PYTHONIOENCODING="utf-8")
    salvo = backup()
    total_ok = total = 0
    falhas = []
    inicio = time.time()
    try:
        for f in arquivos:
            nome = os.path.basename(f)
            t0 = time.time()
            try:
                r = subprocess.run([PYTHON, "-u", f], cwd=PASTA, env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=LIMITE_S)
                saida, codigo = r.stdout + r.stderr, r.returncode
            except subprocess.TimeoutExpired as e:
                saida = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
                codigo = "TRAVOU"
            m = re.findall(r"(\d+)/(\d+) testes passaram", saida)
            ok, n = (int(m[-1][0]), int(m[-1][1])) if m else (0, 0)
            total_ok += ok
            total += n
            bom = codigo == 0 and m and ok == n
            print(f"{'✅' if bom else '❌'} {nome:28s} {ok}/{n}  ({time.time() - t0:.0f}s)"
                  + ("" if bom else f"  [saída: {codigo}]"))
            if not bom:
                falhas.append(nome)
                for linha in saida.splitlines():
                    if "❌" in linha or "Error" in linha or "Traceback" in linha:
                        print("     " + linha[:160])
    finally:
        devolvido = restaurar(salvo)
    print(f"\n{total_ok}/{total} verificações passaram em {len(arquivos)} arquivos "
          f"({time.time() - inicio:.0f}s). " + ("Dados do usuário restaurados." if devolvido else
                                               "⚠️ Dados do usuário NÃO restaurados por completo (veja acima)."))
    if falhas:
        print("Falharam: " + ", ".join(falhas))
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
