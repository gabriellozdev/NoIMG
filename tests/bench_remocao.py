"""Benchmark reproduzível da remoção de fundo do NoIMG.

Compara configurações do pipeline (noimg.core.MattingConfig) com máscaras de referência
(ground truth) de dois conjuntos públicos de matting:

- AIM-500 (Li et al., 2021): 500 imagens naturais com alfa anotado à mão, 7 categorias
  (animal, retrato, planta, fruta, móvel, brinquedo, transparente) e 3 tipos (SO, STM, NS).
  Espelho em parquet: https://huggingface.co/datasets/nobg/AIM-500
- PPM-100 (Ke et al., 2020, MODNet): 100 retratos com cabelo e alfa anotado.
  https://huggingface.co/datasets/realdream-ai/ppm-matting

Os dados NÃO ficam no repositório (licenças de pesquisa); baixe-os em uma pasta e passe
com --data. Passos:

    python tests/bench_remocao.py prepare --data DADOS --set CONJUNTO
    python tests/bench_remocao.py raw     --set CONJUNTO          # roda o modelo (lento, com cache)
    python tests/bench_remocao.py eval    --set CONJUNTO --out resultados.json
    python tests/bench_remocao.py fg      --set CONJUNTO --out fg.json
    python tests/bench_remocao.py perf    --out perf.json
    python tests/bench_remocao.py sheet   --set CONJUNTO --out pasta_png

Métricas (alfa em 0–1, como no Composition-1k): SAD/1000, MSE×1000, Grad/1000, Conn/1000,
todas também restritas à região de transição (alfa de referência entre 0 e 1, dilatada).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from noimg import core  # noqa: E402

MAX_SIDE = 1600  # imagens maiores são reduzidas (mantém o teste viável num PC de 4 GB)

# configurações comparadas: (nome, config)
CONFIGS = {
    "legado": core.LEGACY_MATTING,
    "letterbox": replace(core.LEGACY_MATTING, letterbox="always"),
    "letterbox+mean": replace(core.LEGACY_MATTING, letterbox="always", pad="mean"),
    "lb+rgb": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb"),
    "lb+rgb+sem-contraste": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0),
    "lb+cinza+sem-contraste": replace(core.LEGACY_MATTING, letterbox="always", guide="gray", contrast=1.0),
    "lb+sem-refino": replace(core.LEGACY_MATTING, letterbox="always", guide="none", contrast=1.0),
    "lb+rgb+r4": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0, gf_radius=4.0),
    "lb+rgb+eps1e-3": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0, gf_eps=1e-3),
    "lb+rgb+norm-none": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0, norm="none"),
    "lb+rgb+norm-guarded": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0, norm="guarded"),
    "achatado+cinza+sem-contraste": replace(core.LEGACY_MATTING, contrast=1.0),
    "achatado+cinza+r4": replace(core.LEGACY_MATTING, contrast=1.0, gf_radius=4.0),
    "achatado+rgb+r4": replace(core.LEGACY_MATTING, contrast=1.0, guide="rgb", gf_radius=4.0),
    "achatado+rgb+r6": replace(core.LEGACY_MATTING, contrast=1.0, guide="rgb", gf_radius=6.0),
    "lb+rgb+r6": replace(core.LEGACY_MATTING, letterbox="always", guide="rgb", contrast=1.0, gf_radius=6.0),
    "lb+cinza+r4": replace(core.LEGACY_MATTING, letterbox="always", guide="gray", contrast=1.0, gf_radius=4.0),
    "achatado+cinza+r6": replace(core.LEGACY_MATTING, contrast=1.0, guide="gray", gf_radius=6.0),
    "achatado+rgb+r8": replace(core.LEGACY_MATTING, contrast=1.0, guide="rgb", gf_radius=8.0),
    "achatado+rgb+r6+guarded": replace(core.LEGACY_MATTING, contrast=1.0, guide="rgb", gf_radius=6.0, norm="guarded"),
    "achatado+rgb+r6+norm-none": replace(core.LEGACY_MATTING, contrast=1.0, guide="rgb", gf_radius=6.0, norm="none"),
    "novo+contraste1.15": replace(core.DEFAULT_MATTING, contrast=1.15),
    "novo+contraste1.3": replace(core.DEFAULT_MATTING, contrast=1.3),
    "novo+eps1e-3": replace(core.DEFAULT_MATTING, gf_eps=1e-3),
    "novo+r4": replace(core.DEFAULT_MATTING, gf_radius=4.0),
    "padrao-novo": core.DEFAULT_MATTING,
}


# ---------------------------------------------------------------- métricas


def sad(pred, gt):
    return float(np.abs(pred - gt).sum() / 1000)


def mse(pred, gt, mask=None):
    d = (pred - gt) ** 2
    return float((d[mask].mean() if mask is not None else d.mean()) * 1000) if (mask is None or mask.any()) else 0.0


def _gauss_grad(x, sigma=1.4):
    """Gradiente com derivada de gaussiana (σ = 1.4), como no benchmark de Rhemann et al."""
    k = int(np.ceil(3 * sigma)) * 2 + 1
    g = cv2.getGaussianKernel(k, sigma)
    xs = np.arange(k) - k // 2
    dg = (-xs / sigma**2 * g[:, 0]).reshape(-1, 1)
    dg /= np.abs(dg).sum() / 2
    gx = cv2.sepFilter2D(x, cv2.CV_32F, dg, g)
    gy = cv2.sepFilter2D(x, cv2.CV_32F, g, dg)
    return np.sqrt(gx**2 + gy**2)


def grad(pred, gt, mask=None):
    d = (_gauss_grad(pred) - _gauss_grad(gt)) ** 2
    return float((d[mask].sum() if mask is not None else d.sum()) / 1000)


def conn(pred, gt, step=0.1):
    """Conectividade (Rhemann et al., 2009): penaliza pedaços soltos da máscara."""
    thresh = np.arange(0, 1 + step, step)
    l_map = np.full(pred.shape, -1.0, np.float32)
    for i in range(1, len(thresh)):
        both = ((pred >= thresh[i]) & (gt >= thresh[i])).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(both, connectivity=4)
        if n <= 1:
            comp = np.zeros_like(both, bool)
        else:
            comp = lab == (1 + np.argmax(st[1:, cv2.CC_STAT_AREA]))
        l_map[(l_map == -1) & ~comp] = thresh[i - 1]
    l_map[l_map == -1] = 1
    d_pred, d_gt = pred - l_map, gt - l_map
    phi_pred = 1 - d_pred * (d_pred >= 0.15)
    phi_gt = 1 - d_gt * (d_gt >= 0.15)
    return float(np.abs(phi_pred - phi_gt).sum() / 1000)


def transition_mask(gt):
    t = ((gt > 0.01) & (gt < 0.99)).astype(np.uint8)
    edge = cv2.Canny((gt * 255).astype(np.uint8), 10, 40) > 0
    t = (t | edge).astype(np.uint8)
    return cv2.dilate(t, np.ones((7, 7), np.uint8)) > 0


# ---------------------------------------------------------------- dados


def _limit(img, alpha):
    h, w = alpha.shape
    s = MAX_SIDE / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        alpha = cv2.resize(alpha, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img, alpha


def prepare(data: Path, out: Path, per_category: int, n_portrait: int, seed: int):
    """Escolhe um subconjunto fixo e estratificado e grava image.jpg + alpha.png."""
    import pyarrow.parquet as pq

    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    meta = []
    table = pq.read_table(data / "aim500.parquet", columns=["image_name", "category", "type"])
    rows = table.to_pylist()
    cats = sorted({r["category"] for r in rows})
    chosen = []
    for c in cats:
        idx = [i for i, r in enumerate(rows) if r["category"] == c]
        chosen += list(rng.choice(idx, size=min(per_category, len(idx)), replace=False))
    wanted = {int(x) for x in chosen}
    pf = pq.ParquetFile(data / "aim500.parquet")
    picked, pos = [], 0
    for batch in pf.iter_batches(batch_size=4):  # em lotes pequenos: o arquivo inteiro não cabe em 4 GB
        for r in batch.to_pylist():
            if pos in wanted:
                picked.append(r)
            pos += 1
    for r in picked:
        img = cv2.imdecode(np.frombuffer(r["image"]["bytes"], np.uint8), cv2.IMREAD_COLOR)
        al = cv2.imdecode(np.frombuffer(r["mask"]["bytes"], np.uint8), cv2.IMREAD_UNCHANGED)
        if al.ndim == 3:
            al = al[..., 3] if al.shape[2] == 4 else al[..., 0]
        img, al = _limit(img, al)
        name = f"aim_{r['category']}_{r['image_name']}"
        _save(out, name, img, al)
        meta.append({"name": name, "source": "AIM-500", "category": r["category"], "type": r["type"], **_shape(al)})
    ppm = sorted((data / "PPM-100").glob("*/fg/*.jpg"))
    for p in [ppm[i] for i in sorted(rng.choice(len(ppm), size=min(n_portrait, len(ppm)), replace=False))]:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        al = cv2.imread(str(p.parent.parent / "alpha" / p.name), cv2.IMREAD_GRAYSCALE)  # o PPM-100 guarda o alfa em .jpg
        if img is None or al is None:
            continue
        img, al = _limit(img, al)
        name = f"ppm_{p.stem}"
        _save(out, name, img, al)
        meta.append({"name": name, "source": "PPM-100", "category": "portrait-hair", "type": "STM", **_shape(al)})
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(meta)} imagens em {out}")


def _save(out, name, img, al):
    cv2.imwrite(str(out / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(str(out / f"{name}.alpha.png"), al)


def _shape(al):
    h, w = al.shape
    o = "quadrada" if abs(w - h) / max(w, h) < 0.1 else ("horizontal" if w > h else "vertical")
    return {"w": w, "h": h, "orientacao": o}


def load_set(setdir: Path):
    meta = json.loads((setdir / "meta.json").read_text(encoding="utf-8"))
    for m in meta:
        rgb = core.load_image(setdir / f"{m['name']}.jpg")[..., :3]
        gt = cv2.imread(str(setdir / f"{m['name']}.alpha.png"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
        yield m, rgb, gt


# ---------------------------------------------------------------- etapas


def raw(setdir: Path, model: str):
    """Saída do modelo para cada modo de entrada (com cache em .npy)."""
    cache = setdir / "raw"
    cache.mkdir(exist_ok=True)
    modes = {"squash": (False, "replicate"), "lb-replicate": (True, "replicate"), "lb-mean": (True, "mean")}
    for m, rgb, _ in load_set(setdir):
        for mode, (lb, pad) in modes.items():
            f = cache / f"{m['name']}.{model}.{mode}.npy"
            if f.exists():
                continue
            t = time.perf_counter()
            r = core.raw_mask(rgb, model, lb, pad)
            np.save(f, r.astype(np.float32))
            print(m["name"], mode, f"{time.perf_counter() - t:.1f}s", flush=True)


def _raw_for(setdir, name, model, cfg, shape=None):
    if shape is None:
        shape = cv2.imread(str(setdir / f"{name}.alpha.png"), cv2.IMREAD_GRAYSCALE).shape
    lb = core.use_letterbox(cfg, *shape)
    mode = "squash" if not lb else ("lb-mean" if cfg.pad == "mean" else "lb-replicate")
    return np.load(setdir / "raw" / f"{name}.{model}.{mode}.npy")


def evaluate(setdir: Path, model: str, out: Path, names: list[str]):
    res = {"model": model, "configs": {n: asdict(CONFIGS[n]) for n in names}, "images": []}
    for m, rgb, gt in load_set(setdir):
        trans = transition_mask(gt)
        row = {**m, "results": {}}
        for n in names:
            cfg = CONFIGS[n]
            t = time.perf_counter()
            pred = core.alpha_from_raw(rgb, _raw_for(setdir, m["name"], model, cfg), cfg)
            dt = time.perf_counter() - t
            row["results"][n] = {
                "SAD": sad(pred, gt),
                "MSE": mse(pred, gt),
                "Grad": grad(pred, gt),
                "Conn": conn(pred, gt),
                "SAD_trans": sad(pred * trans, gt * trans),
                "MSE_trans": mse(pred, gt, trans),
                "Grad_trans": grad(pred, gt, trans),
                "t_refino_s": dt,
            }
        res["images"].append(row)
        print(m["name"], {n: round(v["MSE"], 2) for n, v in row["results"].items()}, flush=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


def fg_eval(setdir: Path, out: Path):
    """Cor do primeiro plano em composições sintéticas: a foto (cor conhecida = verdade)
    com o alfa de referência sobre outro fundo; o estimador recebe só a composição e o alfa."""
    items = list(load_set(setdir))
    res = []
    for i, (m, rgb, gt) in enumerate(items):
        h, w = gt.shape
        B = cv2.resize(items[(i + 7) % len(items)][1], (w, h), interpolation=cv2.INTER_AREA)  # fundo complexo
        a3 = gt[..., None]
        comp = rgb * a3 + B * (1 - a3)
        trans = (gt > 0.02) & (gt < 0.98)
        if trans.sum() < 50:
            continue
        row = {"name": m["name"], "category": m["category"], "results": {}}
        for method in ("nenhum", "blur", "ml"):
            t = time.perf_counter()
            F = comp if method == "nenhum" else core.estimate_foreground(comp, gt, method)
            dt = time.perf_counter() - t
            err = (np.abs(F - rgb) * a3)[trans].mean() * 1000  # erro de cor ponderado pelo alfa
            # (F·a + fundo·(1−a)) − (verdade·a + fundo·(1−a)) = (F − verdade)·a: o erro de
            # composição é o mesmo sobre qualquer fundo novo; os halos de MÁSCARA errada
            # aparecem nas métricas de alfa (etapa eval), não aqui.
            comp_mse = float((((F - rgb) * a3) ** 2)[trans].mean() * 1000)
            row["results"][method] = {"erro_cor": float(err), "composicao_mse": comp_mse, "t_s": dt}
        res.append(row)
        print(m["name"], {k: round(v["erro_cor"], 2) for k, v in row["results"].items()}, flush=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


_PERF_CHILD = r"""
import sys, time, json, ctypes, ctypes.wintypes as wt
sys.path.insert(0, sys.argv[1])
import numpy as np
from dataclasses import replace
from noimg import core
cfg = core.LEGACY_MATTING if sys.argv[2] == "legado" else core.DEFAULT_MATTING
w, h = int(sys.argv[3]), int(sys.argv[4])
rng = np.random.default_rng(0)
img = (rng.random((h, w, 3), dtype=np.float32) * 0.2 + 0.4)
img[h//4:3*h//4, w//4:3*w//4] = [0.8, 0.2, 0.1]
core.remove_background(img[:64, :64], cfg=cfg)  # carrega o modelo fora da medição
t = time.perf_counter(); core.remove_background(img, cfg=cfg); dt = time.perf_counter() - t
class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [(n, ctypes.c_size_t) for n in
        ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
         "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
k32, ps = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
k32.GetCurrentProcess.restype = wt.HANDLE
ps.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
# memória comprometida (privada) é a medida estável; o working set encolhe quando falta RAM
print(json.dumps({"t_s": dt, "pico_commit_mb": pmc.PeakPagefileUsage / 2**20, "pico_ws_mb": pmc.PeakWorkingSetSize / 2**20}))
"""


def perf(out: Path):
    """Tempo e pico de memória de remove_background ponta a ponta, um processo por medida."""
    res = []
    for w, h, o in ((1600, 1067, "horizontal"), (1067, 1600, "vertical"), (1400, 1400, "quadrada"), (2400, 1600, "grande")):
        for cfg in ("legado", "padrao-novo"):
            r = subprocess.run([sys.executable, "-c", _PERF_CHILD, str(ROOT), cfg, str(w), str(h)], capture_output=True, text=True)
            line = [x for x in r.stdout.splitlines() if x.startswith("{")]
            d = json.loads(line[-1]) if line else {"erro": r.stderr[-400:]}
            res.append({"config": cfg, "w": w, "h": h, "orientacao": o, **d})
            print(res[-1], flush=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


def sheet(setdir: Path, model: str, out: Path, names: list[str], a: str, b: str):
    """Pranchas visuais: referência × config A × config B, sobre xadrez, escuro e cor."""
    out.mkdir(parents=True, exist_ok=True)
    chosen = set(names)
    for m, rgb, gt in load_set(setdir):
        if chosen and m["name"] not in chosen:
            continue
        cols = []
        for label, alpha, fg in (
            ("referencia", gt, core.estimate_foreground(rgb, gt, "ml")),
            (a, *_full(setdir, m, rgb, model, CONFIGS[a])),
            (b, *_full(setdir, m, rgb, model, CONFIGS[b])),
        ):
            tiles = [_comp(fg, alpha, bg) for bg in ("checker", (0.06, 0.06, 0.08), (0.18, 0.29, 1.0))]
            tiles.append(np.repeat(alpha[..., None], 3, 2))
            col = np.vstack([cv2.resize(t, (360, round(360 * t.shape[0] / t.shape[1]))) for t in tiles])
            col = (col[..., ::-1] * 255).astype(np.uint8)
            cv2.putText(col, label, (6, 22), 0, 0.6, (0, 0, 255), 2)
            cols.append(col)
        cv2.imwrite(str(out / f"{m['name']}.png"), np.hstack(cols))


def _full(setdir, m, rgb, model, cfg):
    alpha = core.alpha_from_raw(rgb, _raw_for(setdir, m["name"], model, cfg), cfg)
    return alpha, core.estimate_foreground(rgb, alpha, cfg.fg)


def _comp(fg, a, bg):
    h, w = a.shape
    if bg == "checker":
        yy, xx = np.mgrid[:h, :w]
        B = (((yy // 16 + xx // 16) % 2) * 0.12 + 0.82)[..., None].repeat(3, 2).astype(np.float32)
    else:
        B = np.broadcast_to(np.array(bg, np.float32), (h, w, 3))
    return fg * a[..., None] + B * (1 - a[..., None])


def vitmatte_eval(setdir: Path, model: str, out: Path, base: str, limit: int, max_side: int):
    """Base (config `base`) × base + refino ViTMatte, nas imagens mais difíceis primeiro
    (cabelo, transparente, animal, planta, tipos STM/NS), até `limit` imagens."""
    from noimg import experimental_vitmatte as vm

    order = {"portrait-hair": 0, "transparent": 1, "animal": 2, "plant": 3, "portrait": 4}
    items = sorted(load_set(setdir), key=lambda x: (order.get(x[0]["category"], 9), x[0]["type"] == "SO"))[:limit]
    cfg = CONFIGS[base]
    res = []
    for m, rgb, gt in items:
        trans = transition_mask(gt)
        a0 = core.alpha_from_raw(rgb, _raw_for(setdir, m["name"], model, cfg), cfg)
        a1, used, dt, erro = None, None, None, None
        for side in (max_side, 768, 512):  # em 4 GB o ViTMatte pode faltar memória: tenta menor
            try:
                t = time.perf_counter()
                a1 = vm.refine(rgb, a0, max_side=side)
                dt, used = time.perf_counter() - t, side
                break
            except (RuntimeError, MemoryError) as e:
                erro = f"{side}px: {str(e)[:120]}"
                import gc

                gc.collect()
        row = {**m, "t_vitmatte_s": dt, "vitmatte_lado": used, "falha_memoria": erro, "results": {}}
        if a1 is None:
            res.append(row)
            print(m["name"], "SEM MEMÓRIA", erro, flush=True)
            continue
        for label, pred in ((base, a0), (base + "+vitmatte", a1)):
            row["results"][label] = {"SAD": sad(pred, gt), "MSE": mse(pred, gt), "Grad": grad(pred, gt), "MSE_trans": mse(pred, gt, trans), "Grad_trans": grad(pred, gt, trans)}
        res.append(row)
        print(m["name"], {k: round(v["MSE_trans"], 2) for k, v in row["results"].items()}, f"{dt:.0f}s @ {used}px", flush=True)
        out.write_text(json.dumps({"max_side": max_side, "images": res}, indent=1, ensure_ascii=False), encoding="utf-8")

    # memória: medida em processo separado (docs/benchmark-remocao.md)
    out.write_text(json.dumps({"max_side": max_side, "images": res}, indent=1, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("etapa", choices=["prepare", "raw", "eval", "fg", "perf", "sheet", "vitmatte"])
    ap.add_argument("--limit", type=int, default=16)
    ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--data", type=Path)
    ap.add_argument("--set", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--model", default="isnet")
    ap.add_argument("--per-category", type=int, default=6)
    ap.add_argument("--portraits", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--names", default="")
    ap.add_argument("--a", default="legado")
    ap.add_argument("--b", default="padrao-novo")
    a = ap.parse_args()
    if a.etapa == "prepare":
        prepare(a.data, a.set, a.per_category, a.portraits, a.seed)
    elif a.etapa == "raw":
        raw(a.set, a.model)
    elif a.etapa == "eval":
        evaluate(a.set, a.model, a.out, a.configs.split(","))
    elif a.etapa == "fg":
        fg_eval(a.set, a.out)
    elif a.etapa == "perf":
        perf(a.out)
    elif a.etapa == "vitmatte":
        vitmatte_eval(a.set, a.model, a.out, a.b, a.limit, a.max_side)
    else:
        sheet(a.set, a.model, a.out, [n for n in a.names.split(",") if n], a.a, a.b)


if __name__ == "__main__":
    main()
