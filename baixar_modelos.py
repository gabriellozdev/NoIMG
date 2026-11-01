"""Baixa os modelos de IA para a pasta models/ e confere o SHA-256 de cada um.

Eles ficam fora do git porque passam do limite de 100 MB por arquivo do GitHub.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parent / "models"
RESGAN = "https://github.com/xinntao/Real-ESRGAN/releases/download"
REMBG = "https://github.com/danielgatis/rembg/releases/download/v0.0.0"

# arquivo: (url, sha256, obrigatório?)
FILES = {
    "realesr-general-x4v3.pth": (f"{RESGAN}/v0.2.5.0/realesr-general-x4v3.pth", "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292", True),
    "RealESRGAN_x4plus.pth": (f"{RESGAN}/v0.1.0/RealESRGAN_x4plus.pth", "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1", True),
    "RealESRGAN_x2plus.pth": (f"{RESGAN}/v0.2.1/RealESRGAN_x2plus.pth", "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb", True),
    "isnet-general-use.onnx": (f"{REMBG}/isnet-general-use.onnx", "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a", True),
    # só é usado em PCs com 8 GB de RAM ou mais
    "birefnet-lite.onnx": (f"{REMBG}/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx", "5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333", False),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    MODELS.mkdir(exist_ok=True)
    skip_optional = "--sem-birefnet" in sys.argv
    for name, (url, digest, required) in FILES.items():
        dest = MODELS / name
        if not required and skip_optional:
            continue
        if dest.exists() and (digest is None or sha256(dest) == digest):
            print(f"ok      {name}")
            continue
        print(f"baixando {name}…", flush=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        if digest and sha256(tmp) != digest:
            tmp.unlink()
            print(f"ERRO: {name} veio corrompido (SHA-256 diferente). Rode de novo.")
            return 1
        tmp.replace(dest)
        print(f"ok      {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
