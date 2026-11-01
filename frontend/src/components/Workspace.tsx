import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Download, ImageUp, RotateCcw, Sparkles, Eraser, Ruler, Check, AlertCircle, Loader2, PackageOpen } from "lucide-react";
import { BorderBeam } from "@/components/ui/border-beam";
import { CompareSlider } from "@/components/CompareSlider";
import { processImage, type JobResult, type Mode, type Quality, type StandardizeOpts } from "@/lib/api";
import { cn } from "@/lib/utils";

export const TOOLS: Record<Mode, { title: string; short: string; text: string; cta: string; icon: typeof Eraser }> = {
  removebg: {
    title: "Removedor de fundo",
    short: "Remover fundo",
    text: "Remova fundos automaticamente e obtenha imagens com transparência, prontas para lojas virtuais, anúncios, apresentações e redes sociais.",
    cta: "Remover fundo",
    icon: Eraser,
  },
  upscale: {
    title: "Melhorador de qualidade",
    short: "Melhorar",
    text: "Recupere a nitidez de imagens, reduza artefatos e amplie a resolução com processamento inteligente.",
    cta: "Melhorar imagem",
    icon: Sparkles,
  },
};

const SIZE_PRESETS: [string, number, number][] = [
  ["512 × 512", 512, 512],
  ["1024 × 1024", 1024, 1024],
  ["2048 × 2048", 2048, 2048],
  ["1080 × 1350", 1080, 1350],
];
const MAX_FILES = 30;

type ItemState =
  | { kind: "waiting" }
  | { kind: "working"; progress: number; queued: boolean }
  | { kind: "done"; result: JobResult }
  | { kind: "error"; message: string };

interface Item {
  key: string;
  file: File;
  preview: string;
  state: ItemState;
}

interface WorkspaceProps {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  incoming: File | null;
}

const isImage = (f: File) => /^image\/(png|jpe?g|webp)$/.test(f.type);

export function Workspace({ mode, onModeChange, incoming }: WorkspaceProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [scale, setScale] = useState<2 | 4>(2);
  const [quality, setQuality] = useState<Quality>("rapido");
  const [standardizeOn, setStandardizeOn] = useState(false);
  const [std, setStd] = useState<StandardizeOpts>({ width: 1024, height: 1024, fit: "encaixar", margin: 0.08, align: "base", uniform: true });
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(0);

  const batch = mode === "upscale" && standardizeOn;
  const finished = items.length > 0 && items.every((i) => i.state.kind === "done" || i.state.kind === "error");
  const showResults = finished && !running;

  const addFiles = (list: FileList | File[] | null | undefined) => {
    const all = Array.from(list ?? []);
    const valid = all.filter(isImage);
    if (!valid.length) {
      if (all.length) setNotice("Esse arquivo não é uma imagem compatível. Use JPG, PNG ou WEBP.");
      return;
    }
    setNotice(all.length > valid.length ? "Alguns arquivos foram ignorados por não serem JPG, PNG ou WEBP." : null);
    const make = (f: File): Item => ({ key: `${f.name}-${f.size}-${Math.random()}`, file: f, preview: URL.createObjectURL(f), state: { kind: "waiting" } });
    setItems((prev) => {
      const keep = batch && !finished ? prev : [];
      if (!(batch && !finished)) prev.forEach((i) => URL.revokeObjectURL(i.preview));
      const next = batch ? [...keep, ...valid.map(make)].slice(0, MAX_FILES) : [make(valid[0])];
      if (batch && keep.length + valid.length > MAX_FILES) setNotice(`O lote aceita até ${MAX_FILES} imagens por vez.`);
      return next;
    });
  };

  useEffect(() => {
    if (incoming) addFiles([incoming]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming]);

  // ao sair do modo lote, mantém só a primeira imagem
  useEffect(() => {
    if (!batch && items.length > 1) setItems((prev) => prev.slice(0, 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started.current) / 1000)), 500);
    return () => clearInterval(t);
  }, [running]);

  const update = (key: string, state: ItemState) => setItems((prev) => prev.map((i) => (i.key === key ? { ...i, state } : i)));

  const run = async () => {
    if (!items.length || running) return;
    started.current = Date.now();
    setElapsed(0);
    setRunning(true);
    setNotice(null);
    const queue = items.map((i) => ({ ...i, state: { kind: "waiting" } as ItemState }));
    setItems(queue);
    // uma de cada vez: o servidor processa em fila e a máquina tem pouca memória
    for (const it of queue) {
      update(it.key, { kind: "working", progress: 0, queued: false });
      try {
        const result = await processImage(
          it.file,
          { mode, scale, quality, standardize: batch ? std : null },
          (progress, queued) => update(it.key, { kind: "working", progress, queued }),
        );
        update(it.key, { kind: "done", result });
      } catch (e) {
        update(it.key, { kind: "error", message: (e as Error).message });
      }
    }
    setRunning(false);
  };

  const reset = () => {
    items.forEach((i) => URL.revokeObjectURL(i.preview));
    setItems([]);
    setNotice(null);
  };

  const tool = TOOLS[mode];
  const doneItems = items.filter((i) => i.state.kind === "done") as (Item & { state: { kind: "done"; result: JobResult } })[];
  const overall = useMemo(() => {
    if (!items.length) return 0;
    return items.reduce((acc, i) => acc + (i.state.kind === "done" || i.state.kind === "error" ? 1 : i.state.kind === "working" ? i.state.progress : 0), 0) / items.length;
  }, [items]);
  const zipUrl = `/api/zip?ids=${doneItems.map((i) => i.state.result.id).join(",")}`;
  const ctaLabel = batch ? (items.length > 1 ? `Padronizar ${items.length} imagens` : "Padronizar imagem") : tool.cta;
  const single = items[0];

  return (
    <div id="ferramenta" className="relative w-full max-w-2xl scroll-mt-28">
      {/* seletor de ferramenta */}
      <div role="tablist" aria-label="Ferramenta" className="mx-auto mb-4 flex w-fit gap-1 rounded-full border border-line bg-surface p-1 shadow-sm">
        {(Object.keys(TOOLS) as Mode[]).map((m) => {
          const Icon = TOOLS[m].icon;
          const active = m === mode;
          return (
            <button
              key={m}
              role="tab"
              aria-selected={active}
              disabled={running}
              onClick={() => {
                onModeChange(m);
                if (finished) reset();
              }}
              className={cn("relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors", active ? "text-white" : "text-ink-2 hover:text-ink")}
            >
              {active && <motion.span layoutId="tool-pill" className="absolute inset-0 rounded-full bg-primary" transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
              <Icon className="relative h-4 w-4" aria-hidden />
              <span className="relative hidden sm:inline">{TOOLS[m].title}</span>
              <span className="relative sm:hidden">{TOOLS[m].short}</span>
            </button>
          );
        })}
      </div>

      <div className="relative overflow-hidden rounded-xl border border-line bg-surface shadow-lg">
        {!showResults && <BorderBeam size={160} duration={9} colorFrom="#397CA8" colorTo="#85B9D8" borderWidth={2} />}

        <AnimatePresence mode="wait" initial={false}>
          {showResults ? (
            <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="p-3">
              {items.length === 1 && single.state.kind === "done" ? (
                <CompareSlider
                  className={cn("aspect-[4/3] w-full rounded-lg", (mode === "removebg" || batch || single.state.result.info.transparente) && "checker")}
                  before={<img src={single.preview} alt="Imagem original" className="h-full w-full object-contain" style={{ imageRendering: mode === "upscale" && !batch ? "pixelated" : undefined }} />}
                  after={<img src={single.state.result.url} alt="Resultado" className="h-full w-full object-contain" />}
                  beforeLabel="Original"
                  afterLabel={mode === "removebg" ? "Sem fundo" : batch ? "Padronizada" : "Melhorada"}
                />
              ) : (
                <ResultGrid items={items} />
              )}

              <div className="flex flex-wrap items-center gap-3 px-2 pt-4 pb-2">
                {doneItems.length > 1 ? (
                  <a href={zipUrl} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-3 font-semibold text-white transition-colors hover:bg-primary-hover active:bg-primary-active">
                    <PackageOpen className="h-4 w-4" aria-hidden /> Baixar todas (ZIP)
                  </a>
                ) : (
                  doneItems[0] && (
                    <a
                      href={doneItems[0].state.result.downloadUrl}
                      download={doneItems[0].state.result.filename}
                      className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-3 font-semibold text-white transition-colors hover:bg-primary-hover active:bg-primary-active"
                    >
                      <Download className="h-4 w-4" aria-hidden /> Baixar PNG
                    </a>
                  )
                )}
                <button onClick={reset} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-3 font-medium text-ink-2 transition-colors hover:border-line-hover hover:text-ink">
                  <RotateCcw className="h-4 w-4" aria-hidden /> {batch ? "Novo lote" : "Outra imagem"}
                </button>
                <p className="ml-auto text-sm text-ink-3">
                  {items.length === 1 && single.state.kind === "done"
                    ? `${single.state.result.info.entrada} para ${single.state.result.info.saida} px, em ${single.state.result.info.segundos}s${single.state.result.info.transparente ? ", com transparência" : ""}`
                    : `${doneItems.length} de ${items.length} prontas em ${elapsed}s, todas com ${std.width} × ${std.height} px`}
                </p>
              </div>
              {items.length === 1 && single.state.kind === "error" && <p className="mx-2 mb-2 rounded-md bg-error-bg px-4 py-3 text-sm text-error">{single.state.message}</p>}
            </motion.div>
          ) : (
            <motion.div key="input" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="p-3">
              <label
                onDragOver={(e) => {
                  e.preventDefault();
                  setOver(true);
                }}
                onDragLeave={() => setOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setOver(false);
                  addFiles(e.dataTransfer.files);
                }}
                className={cn(
                  "relative flex min-h-64 cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
                  over ? "border-primary bg-upload-active" : "border-upload-line bg-upload hover:bg-upload-hover",
                  running && "pointer-events-none",
                )}
              >
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple={batch}
                  className="sr-only"
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                {items.length > 1 ? (
                  <>
                    <ResultGrid items={items} compact />
                    <span className="text-sm text-ink-3">{running ? "Processando uma de cada vez…" : `${items.length} imagens no lote. Clique ou solte mais para adicionar.`}</span>
                  </>
                ) : single ? (
                  <>
                    <img src={single.preview} alt="" className={cn("max-h-56 rounded-md object-contain shadow-md transition", running && "opacity-60 blur-[1px]")} />
                    <span className="text-sm text-ink-3">
                      {single.file.name}. {batch ? "Clique ou solte mais imagens para padronizar juntas." : "Clique para trocar."}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="grid h-14 w-14 place-items-center rounded-full bg-primary-light text-primary">
                      <ImageUp className="h-6 w-6" aria-hidden />
                    </span>
                    <span className="text-lg font-semibold text-ink">{batch ? "Solte suas imagens aqui" : "Solte sua imagem aqui"}</span>
                    <span className="text-sm text-ink-3">{batch ? `Até ${MAX_FILES} arquivos JPG, PNG ou WEBP de uma vez` : "ou clique para escolher um arquivo JPG, PNG ou WEBP"}</span>
                  </>
                )}
              </label>

              {mode === "upscale" && (
                <div className="space-y-4 px-2 pt-4">
                  <div className="flex flex-wrap gap-x-6 gap-y-3">
                    {!batch && <Segmented label="Ampliar" value={scale} onChange={setScale} options={[[2, "2x"], [4, "4x"]]} disabled={running} />}
                    <Segmented label="Modelo" value={quality} onChange={setQuality} options={[["rapido", "Rápido"], ["maximo", "Máxima qualidade"]]} disabled={running} />
                  </div>

                  <Toggle
                    checked={standardizeOn}
                    onChange={setStandardizeOn}
                    disabled={running}
                    icon={<Ruler className="h-4 w-4" aria-hidden />}
                    label="Padronizar tamanho"
                    hint="Deixa várias imagens com o mesmo tamanho, o mesmo enquadramento e a mesma nitidez."
                  />

                  <AnimatePresence initial={false}>
                    {batch && (
                      <motion.fieldset
                        disabled={running}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <StandardizeControls value={std} onChange={setStd} />
                      </motion.fieldset>
                    )}
                  </AnimatePresence>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 px-2 pt-4 pb-2">
                <button
                  onClick={run}
                  disabled={!items.length || running}
                  className="relative z-10 inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 font-semibold text-white shadow-md transition-colors hover:bg-primary-hover active:bg-primary-active disabled:cursor-not-allowed disabled:bg-ink-off disabled:shadow-none"
                >
                  {batch ? <Ruler className="h-4 w-4" aria-hidden /> : <tool.icon className="h-4 w-4" aria-hidden />}
                  {running ? (batch ? "Padronizando…" : mode === "removebg" ? "Removendo fundo…" : "Melhorando imagem…") : ctaLabel}
                </button>
                <p className="text-sm text-ink-3" aria-live="polite">
                  {running && `${Math.round(overall * 100)}%, ${elapsed}s`}
                  {!running && !items.length && (mode === "removebg" ? "O recorte sai no mesmo tamanho da original." : batch ? "Dica: recorte o fundo antes, para padronizar só o personagem." : "Se a imagem não tiver fundo, ela continua sem fundo.")}
                </p>
              </div>

              {running && (
                <div className="mx-2 mb-2 h-1.5 overflow-hidden rounded-full bg-primary-light">
                  <motion.div className="h-full rounded-full bg-primary" animate={{ width: `${Math.max(4, overall * 100)}%` }} transition={{ ease: "easeOut" }} />
                </div>
              )}
              {notice && <p className="mx-2 mb-2 rounded-md bg-warning-bg px-4 py-3 text-sm text-warning">{notice}</p>}
              {items.length === 1 && single.state.kind === "error" && <p className="mx-2 mb-2 rounded-md bg-error-bg px-4 py-3 text-sm text-error">{single.state.message}</p>}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* --------- grade de lote: mostra o estado e o resultado de cada imagem --------- */
function ResultGrid({ items, compact }: { items: Item[]; compact?: boolean }) {
  return (
    <ul className={cn("grid w-full gap-2", compact ? "grid-cols-4 sm:grid-cols-6" : "grid-cols-2 sm:grid-cols-3")}>
      {items.map((i) => {
        const s = i.state;
        const src = s.kind === "done" ? s.result.url : i.preview;
        return (
          <li key={i.key} className="relative overflow-hidden rounded-md border border-line">
            <div className={cn("checker grid aspect-square place-items-center", s.kind === "working" && "opacity-70")}>
              <img src={src} alt={i.file.name} className="h-full w-full object-contain" />
            </div>
            <span className="absolute top-1 right-1 grid h-6 w-6 place-items-center rounded-full bg-white/90 shadow-sm">
              {s.kind === "done" && <Check className="h-3.5 w-3.5 text-success" aria-label="Pronta" />}
              {s.kind === "working" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-label="Processando" />}
              {s.kind === "error" && <AlertCircle className="h-3.5 w-3.5 text-error" aria-label={s.message} />}
              {s.kind === "waiting" && <span className="h-2 w-2 rounded-full bg-ink-off" aria-label="Na fila" />}
            </span>
            {!compact && s.kind === "done" && (
              <a
                href={s.result.downloadUrl}
                download={s.result.filename}
                className="absolute inset-x-1 bottom-1 truncate rounded bg-white/90 px-2 py-1 text-xs text-ink-2 hover:text-primary"
                title={s.result.filename}
              >
                {s.result.filename}
              </a>
            )}
            {!compact && s.kind === "error" && <p className="absolute inset-x-1 bottom-1 rounded bg-error-bg px-2 py-1 text-xs text-error">{s.message}</p>}
          </li>
        );
      })}
    </ul>
  );
}

/* --------- controles de padronização --------- */
function StandardizeControls({ value, onChange }: { value: StandardizeOpts; onChange: (v: StandardizeOpts) => void }) {
  const set = <K extends keyof StandardizeOpts>(k: K, v: StandardizeOpts[K]) => onChange({ ...value, [k]: v });
  const preset = SIZE_PRESETS.find(([, w, h]) => w === value.width && h === value.height);
  const [custom, setCustom] = useState(!preset);

  return (
    <div className="space-y-4 rounded-lg border border-line bg-page-2 p-4">
      <div>
        <p className="mb-2 text-sm text-ink-3">Tamanho final</p>
        <div className="flex flex-wrap gap-2">
          {SIZE_PRESETS.map(([label, w, h]) => (
            <Pill
              key={label}
              active={!custom && value.width === w && value.height === h}
              onClick={() => {
                setCustom(false);
                onChange({ ...value, width: w, height: h });
              }}
            >
              {label}
            </Pill>
          ))}
          <Pill active={custom} onClick={() => setCustom(true)}>
            Personalizado
          </Pill>
        </div>
        {custom && (
          <div className="mt-3 flex items-center gap-2">
            <NumberField label="Largura" value={value.width} onChange={(v) => set("width", v)} />
            <span className="text-ink-3" aria-hidden>
              ×
            </span>
            <NumberField label="Altura" value={value.height} onChange={(v) => set("height", v)} />
            <span className="text-sm text-ink-3">px</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <Segmented label="Encaixe" value={value.fit} onChange={(v) => set("fit", v)} options={[["encaixar", "Inteira, com margem"], ["preencher", "Preencher tudo"]]} />
        {value.fit === "encaixar" && <Segmented label="Alinhar" value={value.align} onChange={(v) => set("align", v)} options={[["base", "Pela base"], ["centro", "No centro"]]} />}
      </div>

      {value.fit === "encaixar" && (
        <label className="flex items-center gap-3 text-sm text-ink-3">
          Margem
          <input
            type="range"
            min={0}
            max={0.3}
            step={0.01}
            value={value.margin}
            onChange={(e) => set("margin", Number(e.target.value))}
            className="w-40 accent-[var(--primary)]"
          />
          <span className="w-10 text-ink-2 tabular-nums">{Math.round(value.margin * 100)}%</span>
        </label>
      )}

      <Toggle
        checked={value.uniform}
        onChange={(v) => set("uniform", v)}
        label="Nitidez igual em todas"
        hint="Passa todas pelo mesmo processo de IA. Desligue para manter o detalhe original das imagens que já são grandes."
      />
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <input
      type="number"
      aria-label={label}
      min={16}
      max={4096}
      value={value}
      onChange={(e) => onChange(Math.min(4096, Math.max(16, Number(e.target.value) || 16)))}
      className="w-24 rounded-md border border-line bg-[var(--bg-input)] px-3 py-2 text-ink tabular-nums focus:border-[var(--border-focus)] focus:outline-none"
    />
  );
}

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn("rounded-full border px-3 py-1.5 text-sm transition-colors", active ? "border-primary bg-primary text-white" : "border-line bg-surface text-ink-2 hover:border-line-hover hover:text-ink")}
    >
      {children}
    </button>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
  icon,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex cursor-pointer items-start gap-3", disabled && "cursor-not-allowed opacity-60")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn("relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-ink-off")}
      >
        <span className={cn("absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform", checked && "translate-x-5")} />
      </button>
      <span>
        <span className="flex items-center gap-1.5 font-medium text-ink">
          {icon}
          {label}
        </span>
        <span className="block text-sm text-ink-3">{hint}</span>
      </span>
    </label>
  );
}

function Segmented<T extends string | number>({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: [T, string][];
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="flex items-center gap-3">
      <legend className="sr-only">{label}</legend>
      <span className="text-sm text-ink-3" aria-hidden>
        {label}
      </span>
      <div className="flex rounded-full border border-line bg-page-2 p-0.5">
        {options.map(([v, text]) => (
          <button
            key={String(v)}
            type="button"
            aria-pressed={v === value}
            onClick={() => onChange(v)}
            className={cn("rounded-full px-3 py-1.5 text-sm transition-colors", v === value ? "bg-surface font-medium text-ink shadow-sm" : "text-ink-2 hover:text-ink")}
          >
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
