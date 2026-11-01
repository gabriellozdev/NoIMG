import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Check, ChevronDown, Download, ImagePlus, Loader2, PackageOpen, RotateCcw } from "lucide-react";
import { CompareSlider } from "@/components/CompareSlider";
import { processImage, type JobResult, type Mode, type Profile, type Quality, type StandardizeOpts } from "@/lib/api";
import { cn } from "@/lib/utils";

export const TOOLS: Record<Mode, { title: string; cta: string }> = {
  removebg: { title: "Remover fundo", cta: "Remover fundo" },
  upscale: { title: "Melhorar", cta: "Melhorar imagem" },
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
  | { kind: "working"; progress: number }
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
  /** avisa quando o cartão precisa de mais espaço (lote ou resultado) */
  onWideChange?: (wide: boolean) => void;
}

const isImage = (f: File) => /^image\/(png|jpe?g|webp)$/.test(f.type);

export function Workspace({ mode, onModeChange, onWideChange }: WorkspaceProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [scale, setScale] = useState<2 | 4>(2);
  const [quality, setQuality] = useState<Quality>("rapido");
  const [profile, setProfile] = useState<Profile>("objetos");
  const [standardizeOn, setStandardizeOn] = useState(false);
  const [std, setStd] = useState<StandardizeOpts>({ width: 1024, height: 1024, fit: "encaixar", margin: 0.08, align: "base", uniform: true });
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(0);
  const input = useRef<HTMLInputElement>(null);

  const standardize = mode === "upscale" && standardizeOn;
  const finished = items.length > 0 && items.every((i) => i.state.kind === "done" || i.state.kind === "error");
  const showResults = finished && !running;
  const wide = items.length > 1 || showResults;

  useEffect(() => onWideChange?.(wide), [wide, onWideChange]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started.current) / 1000)), 500);
    return () => clearInterval(t);
  }, [running]);

  const addFiles = (list: FileList | File[] | null | undefined) => {
    const all = Array.from(list ?? []);
    const valid = all.filter(isImage);
    if (!valid.length) {
      if (all.length) setNotice("Esse arquivo não é JPG, PNG ou WEBP. Escolha outra imagem.");
      return;
    }
    setNotice(all.length > valid.length ? "Alguns arquivos não eram JPG, PNG ou WEBP e ficaram de fora." : null);
    const make = (f: File): Item => ({ key: `${f.name}-${f.size}-${Math.random()}`, file: f, preview: URL.createObjectURL(f), state: { kind: "waiting" } });
    setItems((prev) => {
      const keep = finished ? [] : prev;
      if (finished) prev.forEach((i) => URL.revokeObjectURL(i.preview));
      const next = [...keep, ...valid.map(make)];
      if (next.length > MAX_FILES) setNotice(`O lote aceita até ${MAX_FILES} imagens. Ficaram as ${MAX_FILES} primeiras.`);
      return next.slice(0, MAX_FILES);
    });
    setSelected(null);
  };

  const update = (key: string, state: ItemState) => setItems((prev) => prev.map((i) => (i.key === key ? { ...i, state } : i)));

  const run = async (only?: Item[]) => {
    const queue = only ?? items;
    if (!queue.length || running) return;
    started.current = Date.now();
    setElapsed(0);
    setRunning(true);
    setNotice(null);
    // uma de cada vez: o servidor trabalha em fila e o computador tem pouca memória
    for (const it of queue) {
      update(it.key, { kind: "working", progress: 0 });
      try {
        const result = await processImage(it.file, { mode, scale, quality, profile, standardize: standardize ? std : null }, (progress) =>
          update(it.key, { kind: "working", progress }),
        );
        update(it.key, { kind: "done", result });
      } catch (e) {
        update(it.key, { kind: "error", message: (e as Error).message || "Não deu para processar. Tente de novo." });
      }
    }
    setRunning(false);
  };

  const reset = () => {
    items.forEach((i) => URL.revokeObjectURL(i.preview));
    setItems([]);
    setNotice(null);
    setSelected(null);
  };

  const done = items.filter((i) => i.state.kind === "done") as (Item & { state: { kind: "done"; result: JobResult } })[];
  const failed = items.filter((i) => i.state.kind === "error");
  const overall = useMemo(() => {
    if (!items.length) return 0;
    const sum = items.reduce((a, i) => a + (i.state.kind === "done" || i.state.kind === "error" ? 1 : i.state.kind === "working" ? i.state.progress : 0), 0);
    return sum / items.length;
  }, [items]);
  const focus = done.find((i) => i.key === selected) ?? done[0];
  const zipUrl = `/api/zip?ids=${done.map((i) => i.state.result.id).join(",")}`;
  const ctaLabel = standardize
    ? `Padronizar ${items.length > 1 ? `${items.length} imagens` : "imagem"}`
    : items.length > 1
      ? `${TOOLS[mode].cta} (${items.length})`
      : TOOLS[mode].cta;

  return (
    <div id="ferramenta" className="scroll-mt-24 rounded-[14px] bg-white p-5 sm:p-7">
      {/* ferramenta: o indicador desliza entre as opções */}
      <div role="tablist" aria-label="Ferramenta" className="flex w-full gap-1 rounded-[10px] bg-[var(--muted)] p-1 sm:w-fit">
        {(Object.keys(TOOLS) as Mode[]).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={m === mode}
            disabled={running}
            onClick={() => {
              onModeChange(m);
              if (finished) reset();
            }}
            className={cn("relative flex-1 whitespace-nowrap rounded-[8px] px-4 py-2.5 text-[15px] font-semibold transition-colors sm:flex-none sm:px-5", m === mode ? "text-white" : "text-ink hover:text-primary")}
          >
            {m === mode && <motion.span layoutId="tool-pill" className="absolute inset-0 rounded-[8px] bg-ink" transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
            <span className="relative">{TOOLS[m].title}</span>
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {showResults ? (
          <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-5">
            {focus && (
              <CompareSlider
                className="checker aspect-[4/5] w-full overflow-hidden rounded-[10px] sm:aspect-[4/3]"
                before={<img src={focus.preview} alt="Imagem original" className="h-full w-full object-contain" style={{ imageRendering: mode === "upscale" && !standardize ? "pixelated" : undefined }} />}
                after={<img src={focus.state.result.url} alt="Resultado" className="h-full w-full object-contain" />}
                beforeLabel="Original"
                afterLabel={mode === "removebg" ? "Sem fundo" : standardize ? "Padronizada" : "Melhorada"}
              />
            )}
            {items.length > 1 && <Grid items={items} selected={focus?.key} onSelect={setSelected} />}
            {items.length === 1 && items[0].state.kind === "error" && <ErrorLine message={items[0].state.message} onRetry={() => run(items)} />}

            <div className="mt-5 flex flex-wrap items-center gap-3">
              {done.length > 1 && (
                <a href={zipUrl} className="btn-primary">
                  <PackageOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden /> Baixar todas (ZIP)
                </a>
              )}
              {focus && (
                <a href={focus.state.result.downloadUrl} download={focus.state.result.filename} className={done.length > 1 ? "btn-quiet" : "btn-primary"}>
                  <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden /> {done.length > 1 ? "Baixar esta" : "Baixar PNG"}
                </a>
              )}
              {failed.length > 0 && items.length > 1 && (
                <button className="btn-quiet" onClick={() => run(failed)}>
                  Tentar de novo as {failed.length} com erro
                </button>
              )}
              <button onClick={reset} className="btn-quiet">
                <RotateCcw className="h-4 w-4" strokeWidth={1.75} aria-hidden /> {items.length > 1 ? "Novo lote" : "Outra imagem"}
              </button>
              <p className="w-full text-sm text-ink-2 sm:ml-auto sm:w-auto">
                {items.length === 1 && focus
                  ? `${focus.state.result.info.entrada} → ${focus.state.result.info.saida} px, em ${focus.state.result.info.segundos}s`
                  : `${done.length} de ${items.length} prontas em ${elapsed}s`}
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div key="input" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-5">
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
                "relative flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-[10px] px-5 py-4 text-center sm:min-h-52 sm:gap-3 sm:py-7 transition-[background-color,box-shadow] sm:min-h-52",
                over ? "bg-primary-light ring-2 ring-primary" : "bg-[var(--muted)] hover:bg-[#ECECEF]",
                running && "pointer-events-none",
              )}
            >
              <input
                ref={input}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                className="sr-only"
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              {items.length > 1 ? (
                <>
                  <Grid items={items} compact />
                  <span className="text-sm text-ink-2">{running ? "Processando uma de cada vez…" : `${items.length} imagens. Clique ou solte mais para adicionar.`}</span>
                </>
              ) : items[0] ? (
                <>
                  <img src={items[0].preview} alt="" className={cn("max-h-48 rounded-[6px] object-contain transition", running && "opacity-60")} />
                  <span className="text-sm text-ink-2">{items[0].file.name}. Clique ou solte para adicionar mais.</span>
                </>
              ) : (
                <>
                  <span className="grid h-12 w-12 place-items-center rounded-full bg-primary text-white">
                    <ImagePlus className="h-5 w-5" strokeWidth={1.75} aria-hidden />
                  </span>
                  <span className="text-lg font-semibold text-ink">Solte suas imagens aqui</span>
                  <span className="text-sm text-ink-2">ou clique para escolher. JPG, PNG ou WEBP, até {MAX_FILES} de uma vez.</span>
                </>
              )}
            </label>

            {mode === "upscale" && (
              <div className="mt-4">
                <button type="button" onClick={() => setOptionsOpen((o) => !o)} aria-expanded={optionsOpen} className="flex items-center gap-1.5 text-sm font-semibold text-ink sm:hidden">
                  Opções
                  <ChevronDown className={cn("h-4 w-4 transition-transform", optionsOpen && "rotate-180")} aria-hidden />
                </button>
                <div className={cn("space-y-4", optionsOpen ? "mt-3 block" : "hidden", "sm:mt-0 sm:block")}>
                  <div className="flex flex-wrap gap-x-6 gap-y-3">
                    {!standardize && <Segmented label="Ampliar" value={scale} onChange={setScale} options={[[2, "2x"], [4, "4x"]]} disabled={running} />}
                    <Segmented label="Modelo" value={quality} onChange={setQuality} options={[["rapido", "Rápido"], ["maximo", "Máxima qualidade"]]} disabled={running} />
                  </div>
                  <Toggle checked={standardizeOn} onChange={setStandardizeOn} disabled={running} label="Padronizar tamanho" hint="Deixa todas com o mesmo tamanho, a mesma margem e a mesma nitidez." />
                  <AnimatePresence initial={false}>
                    {standardize && (
                      <motion.fieldset disabled={running} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                        <StandardizeControls value={std} onChange={setStd} />
                      </motion.fieldset>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            )}

            {mode === "removebg" && (
              <div className="mt-4">
                <Segmented
                  label="Tipo"
                  value={profile}
                  onChange={setProfile}
                  options={[["objetos", "Objeto"], ["detalhado", "Pessoa ou animal"]]}
                  disabled={running}
                />
                <p className="mt-2 text-sm text-ink-2">
                  {profile === "objetos" ? "Mais rápido. Bordas firmes, sem partes apagadas." : "Mais lento. Preserva cabelo, pelo e bordas finas."}
                </p>
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3">
              {items.length ? (
                <button onClick={() => run()} disabled={running} className="btn-primary">
                  {running && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                  {running ? "Processando…" : ctaLabel}
                </button>
              ) : (
                <button onClick={() => input.current?.click()} className="btn-primary">
                  Escolher imagens
                </button>
              )}
              <p className="text-sm text-ink-2" aria-live="polite">
                {running
                  ? `${Math.round(overall * 100)}%, ${elapsed}s`
                  : !items.length && (mode === "removebg" ? "Sai em PNG transparente, no tamanho original." : "Se a imagem não tiver fundo, continua sem fundo.")}
              </p>
            </div>

            {running && (
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[var(--muted)]">
                <motion.div className="h-full rounded-full bg-primary" animate={{ width: `${Math.max(4, overall * 100)}%` }} transition={{ ease: "easeOut" }} />
              </div>
            )}
            {notice && <ErrorLine message={notice} />}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ErrorLine({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <p role="alert" className="mt-4 flex items-center gap-2 rounded-[8px] bg-[#FDECEC] px-4 py-3 text-sm text-[#B42525]">
      <AlertCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="ml-auto font-semibold underline underline-offset-2">
          Tentar de novo
        </button>
      )}
    </p>
  );
}

/* grade do lote: estado de cada imagem; clicar numa pronta abre a comparação */
function Grid({ items, compact, selected, onSelect }: { items: Item[]; compact?: boolean; selected?: string; onSelect?: (k: string) => void }) {
  return (
    <ul className={cn("grid w-full gap-2", compact ? "grid-cols-5 sm:grid-cols-6" : "mt-3 grid-cols-4 sm:grid-cols-6")}>
      {items.map((i) => {
        const s = i.state;
        const src = s.kind === "done" ? s.result.url : i.preview;
        const pick = !compact && s.kind === "done" && onSelect;
        return (
          <li key={i.key}>
            <button
              type="button"
              disabled={!pick}
              onClick={(e) => {
                e.preventDefault();
                if (pick) onSelect(i.key);
              }}
              className={cn("checker relative block aspect-square w-full overflow-hidden rounded-[6px]", selected === i.key && "ring-2 ring-primary ring-offset-2", s.kind === "working" && "opacity-70")}
              aria-label={s.kind === "error" ? `${i.file.name}: ${s.message}` : i.file.name}
            >
              <img src={src} alt="" className="h-full w-full object-contain" />
              <span className="absolute top-1 right-1 grid h-5 w-5 place-items-center rounded-full bg-white">
                {s.kind === "done" && <Check className="h-3 w-3 text-[var(--success)]" strokeWidth={2.5} />}
                {s.kind === "working" && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
                {s.kind === "error" && <AlertCircle className="h-3 w-3 text-[#B42525]" />}
                {s.kind === "waiting" && <span className="h-1.5 w-1.5 rounded-full bg-ink-3" />}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function StandardizeControls({ value, onChange }: { value: StandardizeOpts; onChange: (v: StandardizeOpts) => void }) {
  const set = <K extends keyof StandardizeOpts>(k: K, v: StandardizeOpts[K]) => onChange({ ...value, [k]: v });
  const [custom, setCustom] = useState(!SIZE_PRESETS.some(([, w, h]) => w === value.width && h === value.height));
  return (
    <div className="space-y-4 rounded-[10px] bg-[var(--muted)] p-4">
      <div>
        <p className="mb-2 text-sm font-semibold text-ink">Tamanho final</p>
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
          <div className="mt-3 flex items-center gap-2 text-sm">
            <NumberField label="Largura" value={value.width} onChange={(v) => set("width", v)} />
            <span aria-hidden>×</span>
            <NumberField label="Altura" value={value.height} onChange={(v) => set("height", v)} />
            <span className="text-ink-2">px</span>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <Segmented label="Encaixe" value={value.fit} onChange={(v) => set("fit", v)} options={[["encaixar", "Inteira"], ["preencher", "Preencher"]]} />
        {value.fit === "encaixar" && <Segmented label="Alinhar" value={value.align} onChange={(v) => set("align", v)} options={[["base", "Pela base"], ["centro", "No centro"]]} />}
      </div>
      {value.fit === "encaixar" && (
        <label className="flex items-center gap-3 text-sm font-semibold text-ink">
          Margem
          <input type="range" min={0} max={0.3} step={0.01} value={value.margin} onChange={(e) => set("margin", Number(e.target.value))} className="w-36 accent-[var(--primary)]" />
          <span className="w-10 font-normal text-ink-2 tabular-nums">{Math.round(value.margin * 100)}%</span>
        </label>
      )}
      <Toggle checked={value.uniform} onChange={(v) => set("uniform", v)} label="Nitidez igual em todas" hint="Passa todas pelo mesmo processo de IA. Desligue para manter o detalhe das que já são grandes." />
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
      className="w-24 rounded-[8px] bg-white px-3 py-2 text-ink tabular-nums ring-1 ring-[var(--line)] focus:ring-2 focus:ring-primary focus:outline-none"
    />
  );
}

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn("rounded-[8px] px-3 py-1.5 text-sm font-medium transition-colors", active ? "bg-ink text-white" : "bg-white text-ink hover:text-primary")}
    >
      {children}
    </button>
  );
}

function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint: string; disabled?: boolean }) {
  return (
    <div className={cn("flex items-start gap-3", disabled && "opacity-60")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn("relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-[#CFCFD6]")}
      >
        <span className={cn("absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform", checked && "translate-x-5")} />
      </button>
      <span>
        <span className="block font-semibold text-ink">{label}</span>
        <span className="block text-sm text-ink-2">{hint}</span>
      </span>
    </div>
  );
}

function Segmented<T extends string | number>({ label, value, onChange, options, disabled }: { label: string; value: T; onChange: (v: T) => void; options: [T, string][]; disabled?: boolean }) {
  return (
    <fieldset disabled={disabled} className="flex items-center gap-3">
      <legend className="sr-only">{label}</legend>
      <span className="text-sm font-semibold text-ink" aria-hidden>
        {label}
      </span>
      <div className="flex rounded-[8px] bg-[var(--muted)] p-0.5">
        {options.map(([v, text]) => (
          <button
            key={String(v)}
            type="button"
            aria-pressed={v === value}
            onClick={() => onChange(v)}
            className={cn("rounded-[6px] px-3 py-1.5 text-sm transition-colors", v === value ? "bg-white font-semibold text-ink shadow-[0_1px_2px_rgba(20,20,24,0.12)]" : "text-ink-2 hover:text-ink")}
          >
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
