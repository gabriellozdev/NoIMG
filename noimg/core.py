"""Núcleo do NoIMG: melhoria de qualidade (upscale) e remoção de fundo.

Ambas as funções trabalham com arrays float32 RGB/RGBA em [0, 1] e devolvem a imagem
na resolução final sem passar por compressão com perdas.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch

from .arch import RRDBNet, SRVGGNetCompact

MODELS = Path(__file__).resolve().parent.parent / "models"
torch.set_num_threads(os.cpu_count() or 4)

# ---------------------------------------------------------------- utilidades


def load_image(path_or_bytes) -> np.ndarray:
    """Lê PNG/JPG/WEBP preservando o canal alfa. Retorna float32 RGB ou RGBA em [0,1]."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        buf = np.frombuffer(path_or_bytes, np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    else:
        img = cv2.imdecode(np.fromfile(str(path_or_bytes), np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Formato de imagem não suportado")
    peak = 65535.0 if img.dtype == np.uint16 else 255.0
    img = img.astype(np.float32) / peak
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def encode_png(img: np.ndarray) -> bytes:
    """PNG sem perdas (8 bits). RGBA quando houver alfa."""
    u8 = (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    code = cv2.COLOR_RGBA2BGRA if u8.shape[2] == 4 else cv2.COLOR_RGB2BGR
    ok, buf = cv2.imencode(".png", cv2.cvtColor(u8, code), [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("Falha ao codificar PNG")
    return buf.tobytes()


def has_transparency(img: np.ndarray) -> bool:
    return img.shape[2] == 4 and float(img[..., 3].min()) < 0.999


def _box(x: np.ndarray, r: int) -> np.ndarray:
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def estimate_foreground(img: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Estimativa de cor do primeiro plano por "blur fusion" (Forte & Pitié, 2021).

    Remove o "vazamento" da cor do fundo nas bordas semitransparentes (cabelo, pelos,
    vidro). É o mesmo papel do color.jpg que o remove.bg entrega separado do alpha.png.
    Pixels totalmente opacos saem idênticos ao original.
    """
    a = alpha[..., None]
    fg = img.copy()
    bg = img.copy()
    scale = max(img.shape[:2]) / 1024.0
    for r in (max(int(90 * scale), 8), max(int(6 * scale), 3)):
        blur_a = _box(alpha, r)[..., None]
        blur_f = _box(fg * a, r) / (blur_a + 1e-5)
        blur_b = _box(bg * (1 - a), r) / ((1 - blur_a) + 1e-5)
        fg = np.clip(blur_f + a * (img - a * blur_f - (1 - a) * blur_b), 0, 1)
        bg = blur_b
    solid = alpha >= 0.999
    fg[solid] = img[solid]
    return fg.astype(np.float32)


# ---------------------------------------------------------------- upscale

UPSCALE_MODELS = {
    # nome: (arquivo, fator nativo, construtor)
    "rapido": ("realesr-general-x4v3.pth", 4, lambda: SRVGGNetCompact()),
    "maximo4": ("RealESRGAN_x4plus.pth", 4, lambda: RRDBNet(scale=4)),
    "maximo2": ("RealESRGAN_x2plus.pth", 2, lambda: RRDBNet(scale=2)),
}


@lru_cache(maxsize=3)
def _sr_model(name: str):
    fname, native, build = UPSCALE_MODELS[name]
    net = build()
    state = torch.load(MODELS / fname, map_location="cpu", weights_only=True)
    state = state.get("params_ema") or state.get("params") or state
    net.load_state_dict(state, strict=True)
    return net.eval(), native


@torch.inference_mode()
def _sr_rgb(rgb: np.ndarray, net, native: int, tile: int = 192, pad: int = 12, progress=None) -> np.ndarray:
    """Super-resolução em blocos (tiles) com sobreposição, para caber em pouca RAM."""
    h, w = rgb.shape[:2]
    out = np.zeros((h * native, w * native, 3), np.float32)
    src = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))[None]
    ys, xs = range(0, h, tile), range(0, w, tile)
    total, done = len(ys) * len(xs), 0
    for y in ys:
        for x in xs:
            y0, x0 = max(y - pad, 0), max(x - pad, 0)
            y1, x1 = min(y + tile + pad, h), min(x + tile + pad, w)
            patch = src[:, :, y0:y1, x0:x1]
            # o x2plus usa pixel_unshuffle e exige lados pares
            ph, pw = (patch.shape[2] % 2, patch.shape[3] % 2) if native == 2 else (0, 0)
            if ph or pw:
                patch = torch.nn.functional.pad(patch, (0, pw, 0, ph), mode="reflect")
            res = net(patch)[0].clamp_(0, 1).numpy().transpose(1, 2, 0)
            oy, ox = (y - y0) * native, (x - x0) * native
            th, tw = (min(y + tile, h) - y) * native, (min(x + tile, w) - x) * native
            out[y * native:y * native + th, x * native:x * native + tw] = res[oy:oy + th, ox:ox + tw]
            done += 1
            if progress:
                progress(done / total)
    return out


def _bleed_colors(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Preenche a cor das áreas transparentes com a cor da borda mais próxima.

    Sem isso, o modelo "vê" o RGB escondido (geralmente preto/branco) e cria halos
    escuros ao redor do objeto depois do upscale.
    """
    out = estimate_foreground(rgb, alpha)
    known = (alpha > 0.02).astype(np.float32)
    filled = known > 0
    src = out * known[..., None]
    for r in (2, 4, 8, 16, 32, 64, 128, 256):
        den = _box(known, r)
        new = (~filled) & (den > 1e-4)
        if new.any():
            out[new] = (_box(src, r) / (den[..., None] + 1e-8))[new]
            filled |= new
        if filled.all():
            break
    return out


def upscale(img: np.ndarray, scale: int = 2, quality: str = "rapido", progress=None) -> np.ndarray:
    """Melhora a qualidade aumentando a resolução 2x ou 4x.

    Se a imagem tem transparência, o resultado continua transparente: o RGB e o alfa
    são ampliados separadamente pelo mesmo modelo (como o Real-ESRGAN oficial faz).
    """
    if scale not in (2, 4):
        raise ValueError("Escala deve ser 2 ou 4")
    name = "maximo2" if quality == "maximo" and scale == 2 else "maximo4" if quality == "maximo" else "rapido"
    net, native = _sr_model(name)

    transparent = has_transparency(img)
    rgb = img[..., :3]
    alpha = img[..., 3] if img.shape[2] == 4 else None
    if transparent:
        rgb = _bleed_colors(rgb, alpha)

    steps = 2 if transparent else 1
    rep = (lambda base: (lambda p: progress((base + p) / steps))) if progress else (lambda base: None)

    out = _sr_rgb(rgb, net, native, progress=rep(0))
    if transparent:
        a_up = _sr_rgb(np.repeat(alpha[..., None], 3, 2), net, native, progress=rep(1)).mean(2)
        out = np.dstack([out, a_up])
    elif alpha is not None:
        out = np.dstack([out, np.ones(out.shape[:2], np.float32)])

    h, w = img.shape[:2]
    if native != scale:
        out = cv2.resize(out, (w * scale, h * scale), interpolation=cv2.INTER_AREA)
    if transparent:
        a = np.clip(out[..., 3], 0, 1)
        a[a < 0.004] = 0.0
        a[a > 0.996] = 1.0
        out[..., 3] = a
    return np.clip(out, 0, 1)


# ---------------------------------------------------------------- padronizar tamanho


def _resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Redimensiona em alfa pré-multiplicado, para as bordas não escurecerem."""
    interp = cv2.INTER_AREA if w < img.shape[1] else cv2.INTER_LANCZOS4
    if img.shape[2] != 4:
        return np.clip(cv2.resize(img, (w, h), interpolation=interp), 0, 1)
    a = img[..., 3:]
    pre = np.dstack([img[..., :3] * a, a])
    out = np.clip(cv2.resize(pre, (w, h), interpolation=interp), 0, 1)
    a = out[..., 3:]
    rgb = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0)
    return np.dstack([np.clip(rgb, 0, 1), a]).astype(np.float32)


def trim_transparent(img: np.ndarray, threshold: float = 0.02) -> np.ndarray:
    """Corta as margens totalmente transparentes ao redor do objeto."""
    if img.shape[2] != 4:
        return img
    ys, xs = np.where(img[..., 3] > threshold)
    if len(ys) == 0:
        return img
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def standardize(
    img: np.ndarray,
    width: int,
    height: int,
    fit: str = "encaixar",
    margin: float = 0.08,
    align: str = "centro",
    quality: str = "rapido",
    uniform: bool = True,
    progress=None,
) -> np.ndarray:
    """Deixa várias imagens com o mesmo tamanho final e a mesma nitidez.

    - Corta as margens transparentes, para que todos os objetos ocupem a tela por igual.
    - Se o objeto for menor que o espaço disponível, amplia com IA (2x ou 4x) antes de
      ajustar ao tamanho exato. Com `uniform`, até as maiores passam pela IA, para todas
      terminarem com a mesma nitidez.
    - "encaixar" mostra o objeto inteiro com margem; "preencher" cobre a tela toda (corta sobras).
    - "base" alinha todos pela parte de baixo, útil para personagens ficarem no mesmo "chão".
    """
    if not (16 <= width <= 4096 and 16 <= height <= 4096):
        raise ValueError("Tamanho final deve ficar entre 16 e 4096 px")
    if fit not in ("encaixar", "preencher") or align not in ("centro", "base"):
        raise ValueError("Opção de encaixe ou alinhamento inválida")

    transparent = has_transparency(img)
    if transparent:
        img = trim_transparent(img)
    h, w = img.shape[:2]

    if fit == "encaixar":
        box_w, box_h = width * (1 - 2 * margin), height * (1 - 2 * margin)
        s = min(box_w / w, box_h / h)
    else:
        s = max(width / w, height / h)

    new_w, new_h = max(1, round(w * s)), max(1, round(h * s))
    if uniform or s > 1.05:
        # Todas passam pela mesma etapa de IA na mesma escala: a imagem é levada a
        # 1/2 (ou 1/4) do tamanho final e ampliada pelo modelo. Assim uma imagem
        # borrada e uma nítida terminam com a mesma textura.
        factor = 4 if s > 2 else 2
        img = _resize(img, max(1, -(-new_w // factor)), max(1, -(-new_h // factor)))
        img = upscale(img, factor, quality, progress=progress)
    img = _resize(img, new_w, new_h)

    channels = 4 if (transparent or img.shape[2] == 4 or fit == "encaixar") else 3
    canvas = np.zeros((height, width, channels), np.float32)
    if channels == 4 and img.shape[2] == 3:
        img = np.dstack([img, np.ones(img.shape[:2], np.float32)])

    x = (width - new_w) // 2
    if align == "base" and fit == "encaixar":
        y = height - round(height * margin) - new_h
    else:
        y = (height - new_h) // 2
    # recorta o que passar da tela (modo preencher) e cola
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    cw, ch = min(new_w - sx, width - dx), min(new_h - sy, height - dy)
    canvas[dy:dy + ch, dx:dx + cw] = img[sy:sy + ch, sx:sx + cw, :channels]
    if progress:
        progress(1.0)
    return canvas


# ---------------------------------------------------------------- remover fundo

SEG_SIZE = 1024
SEG_MODELS = {
    # nome: (arquivo, média, desvio, saída já é probabilidade?)
    "birefnet": ("birefnet-lite.onnx", (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), False),
    "isnet": ("isnet-general-use.onnx", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), True),
}


def _total_ram_gb() -> float:
    try:
        import ctypes

        class MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong)
                for n in ("total", "avail", "totalPage", "availPage", "totalVirt", "availVirt", "availExt")
            ]

        st = MemStatus()
        st.dwLength = ctypes.sizeof(st)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.total / 1024**3
    except Exception:
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / 1024**3


# o BiRefNet precisa de ~3 GB livres a 1024 px; em máquinas menores vai direto ao ISNet
_birefnet_failed = _total_ram_gb() < 8


@lru_cache(maxsize=1)
def _seg_session(name: str):
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # sem arena/padrões de memória: o pico de RAM cai bastante em máquinas de 4 GB
    opts.enable_cpu_mem_arena = False
    opts.enable_mem_pattern = False
    return ort.InferenceSession(str(MODELS / SEG_MODELS[name][0]), opts, providers=["CPUExecutionProvider"])


def _segment(small: np.ndarray, name: str) -> np.ndarray:
    _, mean, std, is_prob = SEG_MODELS[name]
    x = ((small - np.array(mean, np.float32)) / np.array(std, np.float32)).transpose(2, 0, 1)[None]
    out = _seg_session(name).run(None, {"input_image": np.ascontiguousarray(x, np.float32)})[0][0, 0]
    return out if is_prob else 1.0 / (1.0 + np.exp(-out))


def _fast_guided_upsample(guide_hr: np.ndarray, guide_lr: np.ndarray, p_lr: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Guided filter rápido (He & Sun): calcula os coeficientes na resolução da máscara
    e aplica sobre a imagem original em resolução total -> bordas nítidas do original."""
    mean_i, mean_p = _box(guide_lr, r), _box(p_lr, r)
    var_i = _box(guide_lr * guide_lr, r) - mean_i * mean_i
    cov_ip = _box(guide_lr * p_lr, r) - mean_i * mean_p
    a = cov_ip / (var_i + eps)
    b = mean_p - a * mean_i
    a, b = _box(a, r), _box(b, r)
    h, w = guide_hr.shape[:2]
    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    b = cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)
    return a * guide_hr + b


def predict_alpha(rgb: np.ndarray, model: str = "auto") -> np.ndarray:
    """Máscara alfa suave na resolução ORIGINAL da imagem."""
    h, w = rgb.shape[:2]
    small = cv2.resize(rgb, (SEG_SIZE, SEG_SIZE), interpolation=cv2.INTER_AREA)
    global _birefnet_failed
    if model == "auto" and not _birefnet_failed:
        try:
            m = _segment(small, "birefnet")
        except Exception:  # falta de RAM: cai para o modelo leve e lembra disso
            _birefnet_failed = True
            _seg_session.cache_clear()
            m = _segment(small, "isnet")
    elif model == "auto":
        m = _segment(small, "isnet")
    else:
        m = _segment(small, model)
    m = (m - m.min()) / max(float(m.max() - m.min()), 1e-6)

    coarse = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    if max(h, w) <= SEG_SIZE:
        alpha = coarse
    else:
        # refina só a faixa incerta da borda usando a imagem original como guia
        gray_hr = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray_lr = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        refined = _fast_guided_upsample(gray_hr, gray_lr, m, r=4, eps=1e-3)
        k = max(3, int(round(max(h, w) / SEG_SIZE)) * 4 + 1)
        band = (cv2.dilate(coarse, np.ones((k, k), np.uint8)) - cv2.erode(coarse, np.ones((k, k), np.uint8))) > 0.1
        alpha = np.where(band, refined, coarse)
    alpha = np.clip(alpha, 0, 1).astype(np.float32)
    alpha[alpha < 0.01] = 0.0
    alpha[alpha > 0.99] = 1.0
    return alpha


def remove_background(img: np.ndarray, decontaminate: bool = True, model: str = "auto") -> np.ndarray:
    """Remove o fundo mantendo a resolução e os pixels originais do objeto."""
    rgb = img[..., :3]
    alpha = predict_alpha(rgb, model)
    if img.shape[2] == 4:  # já tinha transparência: não "ressuscita" o que era invisível
        alpha = np.minimum(alpha, img[..., 3])
    fg = estimate_foreground(rgb, alpha) if decontaminate else rgb
    return np.dstack([fg, alpha])
