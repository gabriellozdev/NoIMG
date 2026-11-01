"""NoIMG.exe — prepara tudo na primeira vez e abre o NoIMG no navegador.

Funciona de dois jeitos:
  - avulso (baixado de um release): o exe leva o app e o site já gerado dentro dele e
    instala tudo em %LOCALAPPDATA%\\NoIMG; uma versão nova troca só o código (o .venv e
    os modelos ficam);
  - dentro da pasta do projeto (ao lado do app.py): usa essa pasta, como o iniciar.bat.
Em cada abertura ele:
  1. acha um Python 3.10+ (se não houver, oferece instalar o 3.12 pelo winget);
  2. cria o .venv e instala o requirements.txt (de novo só se o arquivo mudar);
  3. baixa os modelos de IA (só na primeira vez);
  4. gera o site com o npm se web/dist faltar ou estiver mais velho que o código;
  5. sobe o app.py, espera responder e abre o navegador.
Fechar a janela encerra o servidor.

Gerado com `build_exe.bat` (PyInstaller). Só usa a biblioteca padrão.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

PORT = 7860
MIN_PY = (3, 10)
PY_WINGET = "Python.Python.3.12"
NODE_WINGET = "OpenJS.NodeJS.LTS"


# o proxy do Windows não pode interceptar o 127.0.0.1
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Falha(Exception):
    pass


INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NoIMG"


def root_dir() -> Path:
    base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    for d in (base, base.parent):
        if (d / "app.py").exists() and (d / "requirements.txt").exists():
            return d
    payload = Path(getattr(sys, "_MEIPASS", "")) / "payload"
    if getattr(sys, "frozen", False) and (payload / "app.py").exists():
        return install_payload(payload, INSTALL_DIR)
    raise Falha(f"Não achei o app.py. Deixe o NoIMG.exe dentro da pasta do NoIMG (estou em {base}).")


def install_payload(payload: Path, dest: Path) -> Path:
    """Copia o app embutido no exe para `dest` quando a versão muda. O .venv e os modelos
    ficam; só as pastas de código do NoIMG são trocadas, para não sobrar arquivo velho."""
    version = (payload / "VERSION").read_text().strip()
    stamp = dest / "VERSION"
    if stamp.exists() and stamp.read_text().strip() == version and (dest / "app.py").exists():
        return dest
    print(f"\n> Instalando o NoIMG em {dest}...")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("noimg", "web"):
        shutil.rmtree(dest / name, ignore_errors=True)
    shutil.copytree(payload, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("VERSION"))
    stamp.write_text(version)  # por último: cópia interrompida reinstala na próxima vez
    return dest


def clean_env() -> dict:
    """Ambiente para os processos filhos sem as variáveis do PyInstaller, para que
    o Python do .venv não carregue nada do executável empacotado."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI")) and k not in ("PYTHONHOME", "PYTHONPATH")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(cmd: list, cwd: Path, what: str):
    print(f"\n> {what}...")
    if subprocess.call(cmd, cwd=cwd, env=clean_env()) != 0:
        raise Falha(f"Falhou: {what}. Leia a mensagem acima.")


def ask(question: str) -> bool:
    try:
        return input(f"{question} [S/n] ").strip().lower() in ("", "s", "sim", "y", "yes")
    except EOFError:
        return False


def py_version(cmd: list) -> tuple | None:
    try:
        out = subprocess.run(
            cmd + ["-c", "import sys, struct; print(*sys.version_info[:2], struct.calcsize('P') * 8)"],
            capture_output=True, text=True, timeout=30, env=clean_env(),
        )
        major, minor, bits = map(int, out.stdout.split())
        return (major, minor) if bits == 64 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def find_python() -> list | None:
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    candidates = [["py", "-3"], ["python"]] + [[str(p)] for p in sorted(local.glob("Python3*/python.exe"), reverse=True)]
    for cmd in candidates:
        if shutil.which(cmd[0]) or Path(cmd[0]).exists():
            v = py_version(cmd)
            if v and v >= MIN_PY:
                return cmd
    return None


def winget_install(package: str, name: str, site: str) -> bool:
    if not shutil.which("winget"):
        print(f"\n{name} não está instalado e o winget não existe neste Windows.")
        print(f"Instale o {name} por {site} e abra o NoIMG.exe de novo.")
        webbrowser.open(site)
        return False
    if not ask(f"\n{name} não está instalado. Instalar agora pelo winget (baixa da internet)?"):
        return False
    cmd = ["winget", "install", "-e", "--id", package, "--accept-package-agreements", "--accept-source-agreements"]
    if package == PY_WINGET:
        cmd += ["--scope", "user"]
    return subprocess.call(cmd) == 0


def ensure_python() -> list:
    cmd = find_python()
    if cmd:
        return cmd
    if winget_install(PY_WINGET, "Python 3.12", "https://www.python.org/downloads/") and (cmd := find_python()):
        return cmd
    raise Falha(f"É preciso o Python {MIN_PY[0]}.{MIN_PY[1]} ou mais novo (64 bits).")


def file_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ensure_venv(root: Path) -> Path:
    vpy = root / ".venv" / "Scripts" / "python.exe"
    # sem pip = venv criado pela metade (janela fechada no meio, antivírus): recria
    try:
        ok = subprocess.call([str(vpy), "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env()) == 0
    except OSError:  # python.exe ausente ou corrompido
        ok = False
    if not ok:
        run(ensure_python() + ["-m", "venv", "--clear", str(root / ".venv")], root, "Criando o ambiente Python")
    stamp = root / ".venv" / "noimg-requirements.sha256"
    want = file_hash(root / "requirements.txt")
    if not stamp.exists() or stamp.read_text().strip() != want:
        run([str(vpy), "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"], root,
            "Instalando as dependências (a primeira vez demora: o PyTorch tem uns 200 MB)")
        stamp.write_text(want)
    return vpy


def total_ram_gb() -> float:
    class MemStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("total", "avail", "tpf", "apf", "tv", "av", "aev")
        ]

    st = MemStatus()
    st.dwLength = ctypes.sizeof(st)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return 0.0
    return st.total / 1024**3


def ensure_models(root: Path, vpy: Path):
    stamp = root / "models" / ".noimg-ok"
    want = file_hash(root / "baixar_modelos.py")  # lista nova de modelos → baixa de novo
    if stamp.exists() and stamp.read_text().strip() == want:
        return
    cmd = [str(vpy), "baixar_modelos.py"]
    if total_ram_gb() < 8:  # o BiRefNet só é usado com 8 GB ou mais
        cmd.append("--sem-birefnet")
    run(cmd, root, "Baixando os modelos de IA (cerca de 300 MB, só na primeira vez)")
    stamp.write_text(want)


def newest_mtime(paths) -> float:
    m = 0.0
    for p in paths:
        if p.is_dir():
            m = max([m] + [f.stat().st_mtime for f in p.rglob("*") if f.is_file()])
        elif p.exists():
            m = max(m, p.stat().st_mtime)
    return m


def ensure_site(root: Path):
    front = root / "frontend"
    index = root / "web" / "dist" / "index.html"
    sources = [front / "src", front / "public", front / "index.html", front / "package.json", front / "vite.config.ts"]
    if index.exists() and index.stat().st_mtime >= newest_mtime(sources):
        return
    npm = shutil.which("npm")
    if not npm and not index.exists():
        if winget_install(NODE_WINGET, "Node.js", "https://nodejs.org/"):
            npm = shutil.which("npm") or next((str(p) for p in [Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "npm.cmd"] if p.exists()), None)
    if not npm:
        if index.exists():
            print("\nAviso: o site pode estar desatualizado (o Node.js não está instalado para gerá-lo de novo).")
            return
        raise Falha("É preciso o Node.js para gerar o site na primeira vez: https://nodejs.org/")
    # os scripts do npm (tsc, vite) chamam "node" pelo PATH, que não muda sozinho depois do winget
    os.environ["PATH"] = str(Path(npm).parent) + os.pathsep + os.environ.get("PATH", "")
    try:
        stamp = front / "node_modules" / ".noimg-deps"
        want = hashlib.sha256(b"".join(file_hash(front / f).encode() for f in ("package.json", "package-lock.json") if (front / f).exists())).hexdigest()
        if not stamp.exists() or stamp.read_text().strip() != want:
            run([npm, "install", "--no-audit", "--no-fund"], front, "Instalando as dependências do site")
            stamp.write_text(want)
        run([npm, "run", "build"], front, "Gerando o site")
    except Falha:
        if not index.exists():
            raise
        print("\nAviso: não deu para gerar o site de novo. Abrindo a versão anterior.")


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_noimg(url: str) -> bool:
    try:
        with NO_PROXY.open(url, timeout=2) as r:
            return b"NoIMG" in r.read(4096)
    except OSError:
        return False


def serve(root: Path, vpy: Path):
    port = PORT
    while port_busy(port):
        if is_noimg(f"http://127.0.0.1:{port}/"):
            print(f"\nO NoIMG já está aberto em http://127.0.0.1:{port}")
            webbrowser.open(f"http://127.0.0.1:{port}")
            return
        port += 1
    url = f"http://127.0.0.1:{port}"
    print(f"\n> Abrindo o NoIMG em {url} ...")
    proc = subprocess.Popen([str(vpy), "app.py", str(port)], cwd=root, env=clean_env())
    try:
        deadline = time.time() + 180  # carregar o PyTorch num PC lento leva um tempo
        while not is_noimg(url):
            if proc.poll() is not None:
                raise Falha("O servidor fechou sozinho. Leia a mensagem acima.")
            if time.time() > deadline:
                raise Falha("O servidor não respondeu em 3 minutos.")
            time.sleep(1)
        webbrowser.open(url)
        print("\nPronto! O NoIMG está aberto no navegador.")
        print("Deixe esta janela aberta enquanto usa. Para sair, feche a janela ou aperte Ctrl+C.\n")
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()


def main() -> int:
    os.system("title NoIMG")
    sys.stdout.reconfigure(line_buffering=True)  # mensagens na ordem certa entre as do pip/npm
    if getattr(sys, "frozen", False) and os.name == "nt":
        # o PyInstaller muda a pasta de DLLs do processo e os filhos herdam isso
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    print("NoIMG — ferramenta local de imagens\n")
    try:
        root = root_dir()
        vpy = ensure_venv(root)
        ensure_models(root, vpy)
        ensure_site(root)
        serve(root, vpy)
        return 0
    except Falha as e:
        print(f"\nErro: {e}")
    except KeyboardInterrupt:
        return 0
    try:
        input("\nAperte Enter para fechar.")
    except EOFError:
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
