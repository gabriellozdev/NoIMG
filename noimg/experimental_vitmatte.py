"""EXPERIMENTAL: refino de alfa com ViTMatte (Yao et al., 2023) sobre a máscara do ISNet.

Não faz parte do pipeline padrão. Existe para comparar com o refino atual no benchmark
(tests/bench_remocao.py). Resultados e decisão em docs/benchmark-remocao.md.

- Modelo: hustvl/vitmatte-small-composition-1k (pesos Apache-2.0 no Hugging Face; treinado
  no Composition-1k da Adobe, cujo uso é restrito a pesquisa).
- Dependências extras: transformers (+ huggingface_hub, safetensors). Baixa ~100 MB na
  primeira execução para models/vitmatte.
- Entrada: imagem + trimap (0 = fundo, 128 = dúvida, 255 = objeto). O trimap vem da
  máscara do ISNet: miolo e fundo "certos" por erosão, o resto vira dúvida.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np
import torch

from .core import MODELS

REPO = "hustvl/vitmatte-small-composition-1k"


@lru_cache(maxsize=1)
def _load():
    from transformers import VitMatteForImageMatting, VitMatteImageProcessor

    cache = MODELS / "vitmatte"
    proc = VitMatteImageProcessor.from_pretrained(REPO, cache_dir=cache)
    model = VitMatteForImageMatting.from_pretrained(REPO, cache_dir=cache).eval()
    return proc, model


def make_trimap(alpha: np.ndarray, width: int) -> np.ndarray:
    """Faixa de dúvida com `width` px de cada lado da borda da máscara."""
    k = np.ones((2 * width + 1, 2 * width + 1), np.uint8)
    fg = cv2.erode((alpha > 0.95).astype(np.uint8), k)
    bg = cv2.erode((alpha < 0.05).astype(np.uint8), k)
    tri = np.full(alpha.shape, 128, np.uint8)
    tri[fg > 0] = 255
    tri[bg > 0] = 0
    return tri


@torch.inference_mode()
def refine(rgb: np.ndarray, alpha: np.ndarray, max_side: int = 1024, band: int = 10) -> np.ndarray:
    """Refina `alpha` (resolução original) com ViTMatte, rodando em no máximo `max_side` px.

    Só a região de dúvida do trimap recebe o alfa do ViTMatte; miolo e fundo continuam
    exatamente como estavam.
    """
    proc, model = _load()
    h, w = alpha.shape
    s = min(1.0, max_side / max(h, w))
    sw, sh = max(32, round(w * s)), max(32, round(h * s))
    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA)
    a_small = cv2.resize(alpha, (sw, sh), interpolation=cv2.INTER_AREA)
    tri = make_trimap(a_small, band)
    inputs = proc(images=(small * 255).astype(np.uint8), trimaps=tri, return_tensors="pt")
    out = model(**inputs).alphas[0, 0].numpy()[:sh, :sw]  # o processador completa até múltiplo de 32
    out = np.clip(cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC), 0, 1)
    tri_full = cv2.resize(tri, (w, h), interpolation=cv2.INTER_NEAREST)
    res = alpha.copy()
    unk = tri_full == 128
    res[unk] = out[unk]
    return res.astype(np.float32)
