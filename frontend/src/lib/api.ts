export type Mode = "removebg" | "upscale";
export type Quality = "rapido" | "maximo";

export interface StandardizeOpts {
  width: number;
  height: number;
  fit: "encaixar" | "preencher";
  margin: number;
  align: "centro" | "base";
  uniform: boolean;
}

export interface JobInfo {
  entrada: string;
  saida: string;
  transparente: boolean;
  segundos: number;
}

export interface JobResult {
  id: string;
  url: string;
  downloadUrl: string;
  filename: string;
  info: JobInfo;
}

interface JobStatus {
  status: "enviado" | "na fila" | "processando" | "pronto" | "erro";
  progress?: number;
  error?: string;
  filename?: string;
  info?: JobInfo;
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function processImage(
  file: File,
  opts: { mode: Mode; scale: 2 | 4; quality: Quality; standardize?: StandardizeOpts | null },
  onProgress: (p: number, queued: boolean) => void,
  signal?: AbortSignal,
): Promise<JobResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", opts.standardize ? "standardize" : opts.mode);
  fd.append("scale", String(opts.scale));
  fd.append("quality", opts.quality);
  if (opts.standardize) {
    const s = opts.standardize;
    fd.append("width", String(s.width));
    fd.append("height", String(s.height));
    fd.append("fit", s.fit);
    fd.append("margin", String(s.margin));
    fd.append("align", s.align);
    fd.append("uniform", s.uniform ? "1" : "0");
  }

  const res = await fetch("/api/process", { method: "POST", body: fd, signal });
  if (!res.ok) throw new Error("Não foi possível enviar a imagem. Confira se o NoIMG está aberto e tente de novo.");
  const { id } = (await res.json()) as { id: string };

  for (;;) {
    const job = (await (await fetch(`/api/job/${id}`, { signal })).json()) as JobStatus;
    if (job.status === "erro") throw new Error(job.error || "O processamento falhou.");
    onProgress(job.progress ?? 0, job.status === "na fila");
    if (job.status === "pronto" && job.info && job.filename) {
      const url = `/api/job/${id}/result`;
      return { id, url, downloadUrl: `${url}?download=1`, filename: job.filename, info: job.info };
    }
    await wait(700);
  }
}

export async function fileFromUrl(url: string, name: string): Promise<File> {
  const blob = await (await fetch(url)).blob();
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}
