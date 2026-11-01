"""Núcleo do NoIMG: melhoria de qualidade (upscale) e remoção de fundo.

Ambas as funções trabalham com arrays float32 RGB/RGBA em [0, 1] e devolvem a imagem
na resolução final sem passar por compressão com perdas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
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


def estimate_foreground(img: np.ndarray, alpha: np.ndarray, method: str = "ml") -> np.ndarray:
    """Cor do primeiro plano nas bordas semitransparentes (cabelo, pelos, vidro).

    Remove o "vazamento" da cor do fundo antigo. É o mesmo papel do color.jpg que o
    remove.bg entrega separado do alpha.png. Pixels com alfa confiável (>= 0.999) saem
    idênticos ao original.

    - "ml": estimativa multinível (Germer et al., 2020), padrão; menos halo.
    - "blur": "blur fusion" (Forte & Pitié, 2021), a versão anterior.
    """
    if method == "ml":
        return _estimate_foreground_ml(img, alpha)
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


def _estimate_foreground_ml(img: np.ndarray, alpha: np.ndarray, reg: float = 1e-5, grad_w: float = 1.0) -> np.ndarray:
    """Estimativa multinível de primeiro plano e fundo (Germer et al., 2020).

    Resolve, de uma resolução minúscula até a original, o sistema
    I = a·F + (1 − a)·B por pixel, com F e B suaves entre vizinhos (peso maior onde o
    alfa muda pouco). Iterações de Jacobi vetorizadas; o resultado de cada nível
    inicializa o próximo. Só a cor de F nas bordas importa: onde o alfa é confiável o
    original volta intacto.
    """
    h0, w0 = alpha.shape
    n_levels = int(np.ceil(np.log2(max(h0, w0))))
    mean = img.reshape(-1, 3).mean(0)
    F = np.broadcast_to(mean, (1, 1, 3)).astype(np.float32).copy()
    B = F.copy()
    for lvl in range(n_levels + 1):
        w = max(1, round(w0 ** (lvl / n_levels)))
        h = max(1, round(h0 ** (lvl / n_levels)))
        I = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA) if (w, h) != (w0, h0) else img
        a = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_AREA) if (w, h) != (w0, h0) else alpha
        I = I.reshape(h, w, 3)  # o cv2 pode descartar eixos de tamanho 1
        a = a.reshape(h, w)
        F = cv2.resize(F, (w, h), interpolation=cv2.INTER_LINEAR).reshape(h, w, 3)
        B = cv2.resize(B, (w, h), interpolation=cv2.INTER_LINEAR).reshape(h, w, 3)
        iters = 10 if min(w, h) <= 32 else 2
        ap = np.pad(a, 1, mode="edge")
        # pesos dos 4 vizinhos: regularização + gradiente do alfa
        wts = [reg + grad_w * np.abs(a - ap[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]) for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))]
        W = sum(wts)
        a3 = a[..., None]
        a00 = (W + a * a)[..., None]
        a01 = (a * (1 - a))[..., None]
        a11 = (W + (1 - a) ** 2)[..., None]
        det = a00 * a11 - a01 * a01
        for _ in range(iters):
            Fp, Bp = np.pad(F, ((1, 1), (1, 1), (0, 0)), mode="edge"), np.pad(B, ((1, 1), (1, 1), (0, 0)), mode="edge")
            sF = np.zeros_like(F)
            sB = np.zeros_like(B)
            for wt, (dy, dx) in zip(wts, ((-1, 0), (1, 0), (0, -1), (0, 1))):
                sF += wt[..., None] * Fp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                sB += wt[..., None] * Bp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            b0 = a3 * I + sF
            b1 = (1 - a3) * I + sB
            F = np.clip((a11 * b0 - a01 * b1) / det, 0, 1).astype(np.float32)
            B = np.clip((a00 * b1 - a01 * b0) / det, 0, 1).astype(np.float32)
    solid = alpha >= 0.999
    F[solid] = img[solid]
    return F.astype(np.float32)


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
    out = estimate_foreground(rgb, alpha, method="blur")  # upscale: comportamento mantido
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
    # todos os núcleos lógicos: o padrão do ORT usa só os físicos (ISNet num i3 de 2 núcleos: 8,7 s → 7,0 s)
    opts.intra_op_num_threads = os.cpu_count() or 0
    return ort.InferenceSession(str(MODELS / SEG_MODELS[name][0]), opts, providers=["CPUExecutionProvider"])


@dataclass(frozen=True)
class MattingConfig:
    """Opções do pipeline de máscara. Os padrões vêm do benchmark (docs/benchmark-remocao.md)."""

    # Proporção na entrada do modelo (1024×1024):
    #   "never"  achata a imagem, como no treino do ISNet/BiRefNet (melhor até ~2:1);
    #   "always" mantém a proporção e completa com padding;
    #   "auto"   achata até `aspect_limit` e usa padding a partir daí (panorâmicas, banners).
    letterbox: str = "auto"
    aspect_limit: float = 2.0
    pad: str = "mean"  # padding: "mean" (média do modelo = 0 normalizado) ou "replicate" (repete a borda)
    norm: str = "guarded"  # "guarded", "minmax" (anterior) ou "none"
    guide: str = "rgb"  # guia do guided filter: "rgb", "gray" ou "none"
    gf_radius: float = 6.0  # raio do guided filter em pixels de modelo (escala com a imagem)
    gf_eps: float = 1e-4
    contrast: float = 1.0  # >1 encurta a transição da borda (a versão antiga usava 1.6)
    fg: str = "ml"  # estimativa de cor do primeiro plano: "ml" ou "blur"
    # Objetos de borda firme (produtos, móveis, frutas). Desligado (0) para cabelo e pelos.
    hard_edges: float = 0.0  # inclinação da curva do alfa em torno de 0,5 (ex.: 4 → borda de ~25% da largura)
    min_island: float = 0.0  # remove manchas soltas menores que esta fração do maior objeto
    fill_holes: float = 0.0  # fecha furos fechados menores que esta fração da área do objeto


DEFAULT_MATTING = MattingConfig()
# reproduz exatamente o pipeline anterior, para comparação
LEGACY_MATTING = MattingConfig(letterbox="never", pad="replicate", norm="minmax", guide="gray", gf_radius=2.0, contrast=1.6, fg="blur")
# Produtos e objetos de borda firme: borda curta, sem manchas soltas e cor rápida (blur).
# Nos 19 objetos opacos do benchmark: pixels apagados 20,8% → 10,4%, fundo vazando 2,1% → 0,14%.
OBJECTS_MATTING = MattingConfig(hard_edges=3.0, min_island=0.02, fill_holes=0.002, fg="blur")
# Perfis expostos no app: "objetos" (rápido) e "detalhado" (cabelo, pelos, pessoas, animais).
MATTING_PROFILES = {"objetos": OBJECTS_MATTING, "detalhado": DEFAULT_MATTING}


def _model_input(rgb: np.ndarray, letterbox: bool, pad: str, mean) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Leva a imagem a 1024×1024. Com letterbox, o lado maior vira 1024 e o resto é
    padding; devolve também a janela (topo, esquerda, altura, largura) da imagem útil."""
    h, w = rgb.shape[:2]
    if not letterbox:
        return cv2.resize(rgb, (SEG_SIZE, SEG_SIZE), interpolation=cv2.INTER_AREA), (0, 0, SEG_SIZE, SEG_SIZE)
    s = SEG_SIZE / max(h, w)
    nh, nw = max(1, round(h * s)), max(1, round(w * s))
    small = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    top, left = (SEG_SIZE - nh) // 2, (SEG_SIZE - nw) // 2
    border = (top, SEG_SIZE - nh - top, left, SEG_SIZE - nw - left)
    if pad == "mean":
        canvas = cv2.copyMakeBorder(small, *border, cv2.BORDER_CONSTANT, value=tuple(float(m) for m in mean))
    else:
        canvas = cv2.copyMakeBorder(small, *border, cv2.BORDER_REPLICATE)
    return canvas, (top, left, nh, nw)


def _segment(small: np.ndarray, name: str) -> np.ndarray:
    """Roda o modelo com o pré-processamento dele (média/desvio do treino) e devolve
    a probabilidade de primeiro plano em [0, 1], 1024×1024."""
    _, mean, std, is_prob = SEG_MODELS[name]
    x = ((small - np.array(mean, np.float32)) / np.array(std, np.float32)).transpose(2, 0, 1)[None]
    out = _seg_session(name).run(None, {"input_image": np.ascontiguousarray(x, np.float32)})[0][0, 0]
    return out if is_prob else 1.0 / (1.0 + np.exp(-out))


def _normalize(m: np.ndarray, how: str) -> np.ndarray:
    if how == "minmax":  # anterior: estica sempre para 0–1, mesmo previsões fracas
        return (m - m.min()) / max(float(m.max() - m.min()), 1e-6)
    if how == "guarded":  # estica no máximo até 0.8 → 1: previsões fracas não viram opacas
        lo, hi = float(m.min()), max(float(m.max()), 0.8)
        return np.clip((m - lo) / max(hi - lo, 1e-6), 0, 1)
    return np.clip(m, 0, 1)


def _guided_filter(guide: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Guided filter (He et al.) com guia de 1 canal."""
    mean_i, mean_p = _box(guide, r), _box(p, r)
    var_i = _box(guide * guide, r) - mean_i * mean_i
    cov_ip = _box(guide * p, r) - mean_i * mean_p
    a = cov_ip / (var_i + eps)
    b = mean_p - a * mean_i
    return _box(a, r) * guide + _box(b, r)


def _guided_filter_rgb(I: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Guided filter com guia colorido (He et al., eq. 19): usa a covariância 3×3 da cor,
    então separa bordas que têm o mesmo cinza mas cores diferentes (ex.: vermelho sobre verde)."""
    b = _box
    mI = b(I, r)
    mp = b(p, r)
    Ip = b(I * p[..., None], r)
    cov_ip = Ip - mI * mp[..., None]
    # covariância 3×3 simétrica da guia + eps·Id
    v = {}
    for i in range(3):
        for j in range(i, 3):
            v[i, j] = b(I[..., i] * I[..., j], r) - mI[..., i] * mI[..., j] + (eps if i == j else 0.0)
    rr, rg, rb, gg, gb, bb = v[0, 0], v[0, 1], v[0, 2], v[1, 1], v[1, 2], v[2, 2]
    # inversa por cofatores
    i_rr = gg * bb - gb * gb
    i_rg = gb * rb - rg * bb
    i_rb = rg * gb - gg * rb
    i_gg = rr * bb - rb * rb
    i_gb = rb * rg - rr * gb
    i_bb = rr * gg - rg * rg
    det = rr * i_rr + rg * i_rg + rb * i_rb
    c0, c1, c2 = cov_ip[..., 0], cov_ip[..., 1], cov_ip[..., 2]
    a0 = (i_rr * c0 + i_rg * c1 + i_rb * c2) / det
    a1 = (i_rg * c0 + i_gg * c1 + i_gb * c2) / det
    a2 = (i_rb * c0 + i_gb * c1 + i_bb * c2) / det
    bias = mp - a0 * mI[..., 0] - a1 * mI[..., 1] - a2 * mI[..., 2]
    return b(a0, r) * I[..., 0] + b(a1, r) * I[..., 1] + b(a2, r) * I[..., 2] + b(bias, r)


def _refine_band(rgb: np.ndarray, coarse: np.ndarray, band: np.ndarray, cfg: MattingConfig, r: int) -> np.ndarray:
    """Aplica o guided filter só na caixa que contém a faixa de borda, em tiras
    horizontais (com margem 2r) para limitar a memória em imagens grandes."""
    out = coarse.copy()
    ys, xs = np.nonzero(band)
    if len(ys) == 0:
        return out
    h, w = coarse.shape
    m = 3 * r
    y0, y1 = max(0, ys.min() - m), min(h, ys.max() + 1 + m)
    x0, x1 = max(0, xs.min() - m), min(w, xs.max() + 1 + m)
    strip = 384
    for sy in range(y0, y1, strip):
        ey = min(y1, sy + strip)
        py0, py1 = max(y0, sy - m), min(y1, ey + m)
        p = coarse[py0:py1, x0:x1]
        if cfg.guide == "rgb":
            q = _guided_filter_rgb(rgb[py0:py1, x0:x1], p, r, cfg.gf_eps)
        else:
            q = _guided_filter(cv2.cvtColor(rgb[py0:py1, x0:x1], cv2.COLOR_RGB2GRAY), p, r, cfg.gf_eps)
        if cfg.contrast != 1.0:
            q = (q - 0.5) * cfg.contrast + 0.5
        q = q[sy - py0:ey - py0]
        sel = band[sy:ey, x0:x1]
        out[sy:ey, x0:x1][sel] = q[sel]
    return out


def _run_model(small: np.ndarray, model: str) -> np.ndarray:
    global _birefnet_failed
    if model == "auto" and not _birefnet_failed:
        try:
            return _segment(small, "birefnet")
        except Exception:  # falta de RAM: cai para o modelo leve e lembra disso
            _birefnet_failed = True
            _seg_session.cache_clear()
            return _segment(small, "isnet")
    return _segment(small, "isnet" if model == "auto" else model)


def use_letterbox(cfg: MattingConfig, h: int, w: int) -> bool:
    if cfg.letterbox == "auto":
        return max(h, w) / min(h, w) >= cfg.aspect_limit
    return cfg.letterbox == "always"


def raw_mask(rgb: np.ndarray, model: str = "auto", letterbox: bool = False, pad: str = "mean") -> np.ndarray:
    """Saída do modelo na janela útil (sem padding), ainda em resolução de modelo."""
    name = "isnet" if (model == "auto" and _birefnet_failed) else ("birefnet" if model == "auto" else model)
    small, (top, left, nh, nw) = _model_input(rgb, letterbox, pad, SEG_MODELS[name][1])
    m = _run_model(small, model)
    return m[top:top + nh, left:left + nw]


def alpha_from_raw(rgb: np.ndarray, m: np.ndarray, cfg: MattingConfig = DEFAULT_MATTING) -> np.ndarray:
    """Da saída do modelo à máscara final na resolução ORIGINAL da imagem."""
    h, w = rgb.shape[:2]
    m = _normalize(m, cfg.norm)
    coarse = np.clip(cv2.resize(m, (w, h), interpolation=cv2.INTER_CUBIC), 0, 1).astype(np.float32)
    if cfg.guide != "none":
        # Só a faixa incerta da borda é refinada; o miolo e o fundo ficam como o modelo disse.
        s = max(h, w) / SEG_SIZE
        k = int(round(6 * s)) * 2 + 1
        kernel = np.ones((k, k), np.uint8)
        band = (cv2.dilate(coarse, kernel) - cv2.erode(coarse, kernel)) > 0.05
        coarse = _refine_band(rgb, coarse, band, cfg, r=max(2, int(round(cfg.gf_radius * s))))
    alpha = np.clip(coarse, 0, 1).astype(np.float32)
    if cfg.hard_edges or cfg.min_island or cfg.fill_holes:
        alpha = _solidify(alpha, cfg)
    alpha[alpha < 0.02] = 0.0
    alpha[alpha > 0.98] = 1.0
    return alpha


def _solidify(alpha: np.ndarray, cfg: MattingConfig) -> np.ndarray:
    """Para objetos de borda firme: o ISNet deixa partes do objeto semitransparentes
    ("apagadas") e manchas fracas no fundo. Aqui a transição fica curta, manchas soltas
    saem e furinhos fechados dentro do objeto são preenchidos."""
    a = alpha
    if cfg.hard_edges:
        a = np.clip((a - 0.5) * cfg.hard_edges + 0.5, 0, 1)
    solid = (a > 0.5).astype(np.uint8)
    if cfg.min_island and solid.any():
        n, lab, st, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
        areas = st[1:, cv2.CC_STAT_AREA]
        small = [i + 1 for i, ar in enumerate(areas) if ar < cfg.min_island * areas.max()]
        if small:
            drop = np.isin(lab, small).astype(np.uint8)
            # leva junto a borda suave em volta da mancha removida
            drop = cv2.dilate(drop, np.ones((5, 5), np.uint8)) & (1 - np.isin(lab, [i for i in range(1, n) if i not in small]).astype(np.uint8))
            a = np.where(drop > 0, 0.0, a)
            solid = (a > 0.5).astype(np.uint8)
    if cfg.fill_holes and solid.any():
        holes = (1 - solid).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
        h, w = a.shape
        x, y, bw, bh, ar = (st[:, i] for i in range(5))
        inside = (x > 0) & (y > 0) & (x + bw < w) & (y + bh < h)
        fill = inside & (ar < cfg.fill_holes * int(solid.sum()))
        fill[0] = False  # rótulo 0 é o próprio objeto
        a = np.where(fill[lab], 1.0, a)
    return a.astype(np.float32)


def predict_alpha(rgb: np.ndarray, model: str = "auto", cfg: MattingConfig = DEFAULT_MATTING) -> np.ndarray:
    """Máscara alfa suave na resolução ORIGINAL da imagem."""
    h, w = rgb.shape[:2]
    return alpha_from_raw(rgb, raw_mask(rgb, model, use_letterbox(cfg, h, w), cfg.pad), cfg)


def remove_background(img: np.ndarray, decontaminate: bool = True, model: str = "auto", cfg: MattingConfig = DEFAULT_MATTING) -> np.ndarray:
    """Remove o fundo mantendo a resolução e os pixels originais do objeto."""
    rgb = img[..., :3]
    alpha = predict_alpha(rgb, model, cfg)
    if img.shape[2] == 4:  # já tinha transparência: não "ressuscita" o que era invisível
        alpha = np.minimum(alpha, img[..., 3])
    fg = estimate_foreground(rgb, alpha, cfg.fg) if decontaminate else rgb
    return np.dstack([fg, alpha])
