"""
Carregar e salvar a rota (waypoints por imagem do minimapa).
Formato: pasta ROTA_DIR com wp_001.png, wp_002.png... e rota.json.
"""
import glob
import json
import os

import cv2

from config import ROTA_DIR

PASTA = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(PASTA, ROTA_DIR)
ARQ_ROTA = os.path.join(DIR, "rota.json")


def carregar():
    """Retorna a lista de pontos [{"img", "lure", "pos"}], ou [] se não houver rota.
    "pos" = (x, y, z) da coordenada do ponto (rotas antigas não têm: None)."""
    if not os.path.exists(ARQ_ROTA):
        return []
    with open(ARQ_ROTA, encoding="utf-8") as f:
        dados = json.load(f)
    pontos = []
    for item in dados:
        img = cv2.imread(os.path.join(DIR, item["arquivo"]))
        if img is None:
            raise ValueError(f"Não consegui abrir a imagem {item['arquivo']} da rota.")
        pos = tuple(item["pos"]) if item.get("pos") else None
        pontos.append({"img": img, "lure": bool(item.get("lure")), "pos": pos})
    return pontos


def salvar(pontos):
    os.makedirs(DIR, exist_ok=True)
    for antigo in glob.glob(os.path.join(DIR, "wp_*.png")):
        os.remove(antigo)

    dados = []
    for i, p in enumerate(pontos, start=1):
        nome = f"wp_{i:03d}.png"
        cv2.imwrite(os.path.join(DIR, nome), p["img"])
        item = {"arquivo": nome, "lure": p["lure"]}
        if p.get("pos"):
            item["pos"] = list(p["pos"])
        dados.append(item)

    with open(ARQ_ROTA, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)
