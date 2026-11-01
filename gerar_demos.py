"""Gera as imagens de demonstração da landing usando o próprio NoIMG."""
import sys, time
from pathlib import Path
import cv2
from noimg import core

IMG = Path("frontend/public/img")
OUT = Path("frontend/public/demo")
OUT.mkdir(parents=True, exist_ok=True)

for name in ["cachorro", "camera", "pelicano", "caneca", "sapatos", "mel"]:
    t = time.time()
    img = core.load_image(IMG / f"{name}.jpg")
    (OUT / f"{name}-sem-fundo.png").write_bytes(core.encode_png(core.remove_background(img)))
    print(name, "fundo", round(time.time() - t), "s", flush=True)

for name, size in [("montanha", 360), ("retrato", 300)]:
    t = time.time()
    img = core.load_image(IMG / f"{name}.jpg")
    h, w = img.shape[:2]
    small = cv2.resize(img, (size, round(h * size / w)), interpolation=cv2.INTER_AREA)
    (OUT / f"{name}-pequena.png").write_bytes(core.encode_png(small))
    (OUT / f"{name}-4x.png").write_bytes(core.encode_png(core.upscale(small, 4, "rapido")))
    print(name, "upscale", round(time.time() - t), "s", flush=True)
