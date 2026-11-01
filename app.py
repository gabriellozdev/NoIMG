"""NoIMG — servidor local. Rode `iniciar.bat` (ou `python app.py`) e abra http://127.0.0.1:7860"""
import threading
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from io import BytesIO

from noimg import core

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()  # um processamento por vez: a máquina tem pouca RAM
MAX_INPUT_PIXELS = {"upscale": {2: 4_000_000, 4: 1_000_000}, "removebg": 40_000_000, "standardize": 16_000_000}


def _run(job_id: str, data: bytes, mode: str, opts: dict, name: str):
    job = JOBS[job_id]
    try:
        img = core.load_image(data)
        h, w = img.shape[:2]
        limit = MAX_INPUT_PIXELS[mode][opts["scale"]] if mode == "upscale" else MAX_INPUT_PIXELS[mode]
        if h * w > limit:
            raise ValueError(f"Imagem grande demais para este modo ({w}x{h}). Limite: {limit / 1e6:.0f} MP")
        job["status"] = "na fila"
        with LOCK:
            job["status"] = "processando"
            t0 = time.time()
            report = lambda p: job.update(progress=p)  # noqa: E731
            if mode == "upscale":
                out = core.upscale(img, opts["scale"], opts["quality"], progress=report)
                suffix = f"_{opts['scale']}x"
            elif mode == "standardize":
                out = core.standardize(
                    img, opts["width"], opts["height"], opts["fit"], opts["margin"], opts["align"], opts["quality"], opts["uniform"], progress=report
                )
                suffix = f"_{opts['width']}x{opts['height']}"
            else:
                job["progress"] = 0.3
                out = core.remove_background(img, cfg=core.MATTING_PROFILES[opts["profile"]])
                suffix = "_sem_fundo"
        job.update(
            status="pronto",
            progress=1.0,
            png=core.encode_png(out),
            filename=Path(name).stem + suffix + ".png",
            info={
                "entrada": f"{w}x{h}",
                "saida": f"{out.shape[1]}x{out.shape[0]}",
                "transparente": core.has_transparency(out),
                "segundos": round(time.time() - t0, 1),
            },
        )
    except Exception as exc:  # noqa: BLE001 - mostra o erro na interface
        job.update(status="erro", error=str(exc))


DIST = ROOT / "web" / "dist"  # gerado por `npm run build` em frontend/


@app.get("/")
def index():
    return send_from_directory(DIST, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(DIST, path)


@app.post("/api/process")
def process():
    f = request.files.get("file")
    if not f:
        abort(400, "Envie um arquivo")
    form = request.form
    mode = form.get("mode", "upscale")
    if mode not in ("upscale", "removebg", "standardize"):
        abort(400, "Modo inválido")
    try:
        opts = {
            "scale": int(form.get("scale", 2)),
            "quality": form.get("quality", "rapido"),
            "width": int(form.get("width", 1024)),
            "height": int(form.get("height", 1024)),
            "fit": form.get("fit", "encaixar"),
            "margin": min(max(float(form.get("margin", 0.08)), 0.0), 0.4),
            "align": form.get("align", "centro"),
            "uniform": form.get("uniform", "1") == "1",
            "profile": form.get("profile", "objetos"),
        }
    except ValueError:
        abort(400, "Parâmetros inválidos")
    if opts["scale"] not in (2, 4):
        abort(400, "Escala inválida")
    if opts["profile"] not in core.MATTING_PROFILES:
        abort(400, "Perfil inválido")
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "enviado", "progress": 0.0}
    threading.Thread(target=_run, args=(job_id, f.read(), mode, opts, f.filename or "imagem"), daemon=True).start()
    return jsonify(id=job_id)


@app.get("/api/job/<job_id>")
def job_status(job_id):
    job = JOBS.get(job_id) or abort(404)
    return jsonify({k: v for k, v in job.items() if k != "png"})


@app.get("/api/job/<job_id>/result")
def job_result(job_id):
    job = JOBS.get(job_id) or abort(404)
    if job.get("status") != "pronto":
        abort(409)
    return send_file(
        BytesIO(job["png"]),
        mimetype="image/png",
        as_attachment=request.args.get("download") == "1",
        download_name=job["filename"],
    )


@app.get("/api/zip")
def zip_results():
    """Junta vários resultados prontos num ZIP (para baixar um lote padronizado)."""
    ids = [i for i in request.args.get("ids", "").split(",") if i]
    buf, used = BytesIO(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # PNG já é comprimido
        for job_id in ids:
            job = JOBS.get(job_id)
            if not job or job.get("status") != "pronto":
                continue
            name, n = job["filename"], 2
            while name in used:
                name = f"{Path(job['filename']).stem}_{n}.png"
                n += 1
            used.add(name)
            z.writestr(name, job["png"])
    if not used:
        abort(404, "Nenhum resultado pronto")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="noimg_padronizadas.zip")


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7860
    print(f"NoIMG rodando em http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
