"""
Hunts com nome: cada hunt guarda a rota, os perfis de catch e os ajustes de caça dela.

  hunts/<nome>/hunt.json          nome, quando foi salva e os ajustes de caça
  hunts/<nome>/rota/              rota.json + imagens dos pontos
  hunts/<nome>/catch/             catch_perfis.json + imagens das amostras

O bot sempre trabalha com a "hunt aberta" (pasta rota/ e calibracao/catch_perfis.json).
Carregar uma hunt copia os arquivos dela para lá; salvar copia de lá para a pasta da hunt.
Configurações da tela e do PC (teclas de cura, atalhos, barras de HP, Battle) não entram:
valem para todas as hunts.
"""
import glob
import json
import os
import re
import shutil
from datetime import datetime

import config

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR_HUNTS = os.path.join(PASTA, "hunts")
DIR_ROTA = os.path.join(PASTA, config.ROTA_DIR)
DIR_CALIB = os.path.join(PASTA, config.CALIBRACAO_DIR)

# Ajustes que são da hunt (o resto é do seu PC/tela e vale para todas)
CHAVES_DA_HUNT = (
    "ROTA_IDA_E_VOLTA",
    "LURE_ATIVO", "LURE_MINIMO", "LURE_ESPERA_PONTO", "LURE_MAX_VOLTAS",
    "LURE_SEGURANCA_ATIVA", "LURE_HP_SEGURANCA", "LURE_POKE_HP_SEGURANCA", "LURE_PRESO_S",
    "TECLA_ATAQUE", "INTERVALO_ATAQUE", "TIMEOUT_COMBATE",
    "MAGIA_AGRUPAR_ATIVA", "MAGIA_RAIO_SQM", "BOX_RAIO_SQM", "BOX_HP_SOLTAR", "POKE_CACA", "CLICAR_ALVO", "TARGET_ATIVO", "TARGET_DESCONHECIDOS", "TARGETS", "IGNORAR_SOBRA", "SOBRA_MAX", "LURE_IR_ATE_PONTO", "LURE_QUEDA_PERIGO", "MAGIA_ESPERA_MAX", "POKESTOP_ATIVO", "TECLA_POKESTOP", "SAIR_DA_BOX", "NORMAL_SEM_FUGIR", "BOX_DIAGONAL_SQM", "DISTANCIA_MONSTROS", "CORRIDAS_POR_BOX",
    "ORDER_DEPOIS_LUTA", "ORDER_ANDANDO", "ORDER_INTERVALO",
    "MODO_HUNT", "OUTLAND_MAX_REVIVES", "MODO_LUTA_ATIVO", "MODO_OFENSIVO_ATIVO", "TECLA_OFENSIVO", "TECLA_DEFENSIVO", "DEF_LURE_ATIVO", "TECLA_DEF_LURE", "DEF_LURE_MIN", "DEF_LURE_INTERVALO", "COMBO_DURACAO", "SILENCIO_POS_COMBO_S", "TECLA_REVIVE", "REVIVE_SE_MORRER", "REVIVE_CLICAR_POKE", "REVIVE_ESPERA",
    "REVIVE_APOS_LURE", "NIGHTMARE_TECLAS", "NIGHTMARE_COOLDOWN", "TROCA_ESPERA",
    "NIGHTMARE_VOLTAR_PRIMEIRO",
    "MEDICINE_ATIVO", "TECLA_MEDICINE", "MEDICINE_ESPERA", "MEDICINE_CLICAR_POKE", "MEDICINE_EM_DESCONHECIDO",
    "CATCH_ATIVO", "CATCH_ESTRELAS", "CATCH_CORPO", "CATCH_CHEGAR_PERTO", "CATCH_BALL_MOUSE", "CATCH_SHINY_AUTO", "CATCH_AJUSTE_X", "CATCH_AJUSTE_Y", "LOOT_ANTES_BALL", "TECLA_LOOT", "LOOT_ESPERA", "CATCH_NORMAL_ATIVO", "CATCH_TENTATIVAS", "CATCH_TENTATIVAS_ESPECIAL", "CATCH_PROCURA_S", "CATCH_ESPERA",
    "CATCH_DISTANCIA_MAX", "CATCH_RAIO_LOCAL",
)


def _pasta(nome):
    slug = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or "hunt"
    return os.path.join(DIR_HUNTS, slug)


def listar():
    """Nomes das hunts salvas (mais recentes primeiro)."""
    hunts = []
    for arq in glob.glob(os.path.join(DIR_HUNTS, "*", "hunt.json")):
        try:
            with open(arq, encoding="utf-8") as f:
                info = json.load(f)
            hunts.append((info.get("salvo_em", ""), info["nome"]))
        except Exception:
            pass
    return [nome for _, nome in sorted(hunts, reverse=True)]


def existe(nome):
    return os.path.exists(os.path.join(_pasta(nome), "hunt.json"))


def info(nome):
    with open(os.path.join(_pasta(nome), "hunt.json"), encoding="utf-8") as f:
        return json.load(f)


def _copiar_arquivos(origem, destino, padroes):
    os.makedirs(destino, exist_ok=True)
    for padrao in padroes:
        for antigo in glob.glob(os.path.join(destino, padrao)):
            os.remove(antigo)
        for arq in glob.glob(os.path.join(origem, padrao)):
            shutil.copy2(arq, destino)


ARQS_ROTA = ("rota.json", "wp_*.png")
ARQS_CATCH = ("catch_perfis.json", "catch_*.png")


def salvar(nome, ajustes):
    """Salva a hunt aberta (rota + perfis de catch + ajustes de caça) com esse nome."""
    pasta = _pasta(nome)
    _copiar_arquivos(DIR_ROTA, os.path.join(pasta, "rota"), ARQS_ROTA)
    _copiar_arquivos(DIR_CALIB, os.path.join(pasta, "catch"), ARQS_CATCH)
    dados = {
        "nome": nome,
        "salvo_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ajustes": {k: v for k, v in ajustes.items() if k in CHAVES_DA_HUNT},
    }
    with open(os.path.join(pasta, "hunt.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    return pasta


def carregar(nome):
    """Abre a hunt: copia rota e perfis de catch dela para o bot usar. Retorna os ajustes dela."""
    pasta = _pasta(nome)
    dados = info(nome)
    _copiar_arquivos(os.path.join(pasta, "rota"), DIR_ROTA, ARQS_ROTA)
    _copiar_arquivos(os.path.join(pasta, "catch"), DIR_CALIB, ARQS_CATCH)
    return dados.get("ajustes", {})


def apagar(nome):
    shutil.rmtree(_pasta(nome), ignore_errors=True)
