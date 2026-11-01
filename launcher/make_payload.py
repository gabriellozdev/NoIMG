"""Junta em build/payload o que o NoIMG.exe leva dentro dele para funcionar sozinho
(baixado de um release, sem a pasta do projeto): o app, o pacote noimg e o site já gerado.

Grava também build/payload/VERSION, um hash do conteúdo: o iniciador só reinstala
quando ele muda. Rode pelo build_exe.bat, depois de `npm run build`.
"""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "payload"
FILES = ["app.py", "baixar_modelos.py", "requirements.txt"]


def main() -> int:
    if not (ROOT / "web" / "dist" / "index.html").exists():
        print("Falta o site gerado (web/dist). Rode `npm run build` em frontend/.")
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for f in FILES:
        shutil.copy2(ROOT / f, OUT / f)
    (OUT / "noimg").mkdir()
    for f in (ROOT / "noimg").glob("*.py"):
        shutil.copy2(f, OUT / "noimg" / f.name)
    shutil.copytree(ROOT / "web" / "dist", OUT / "web" / "dist")

    h = hashlib.sha256()
    for f in sorted(p for p in OUT.rglob("*") if p.is_file()):
        h.update(f.relative_to(OUT).as_posix().encode())
        h.update(f.read_bytes())
    (OUT / "VERSION").write_text(h.hexdigest()[:16])
    print(f"payload pronto: {OUT} (versão {h.hexdigest()[:16]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
