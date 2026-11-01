import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ShieldCheck, Cpu, FileImage } from "lucide-react";
import { SpotlightNavbar } from "@/components/ui/spotlight-navbar";
import TextAnimation from "@/components/ui/stagger-text";
import StatsCounter from "@/components/ui/stats-counter";
import { FaqAccordion } from "@/components/ui/faq-accordion";
import { CompareSlider } from "@/components/CompareSlider";
import { Workspace, TOOLS } from "@/components/Workspace";
import { fileFromUrl, type Mode } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { label: "Ferramenta", href: "#topo" },
  { label: "Remover fundo", href: "#removedor" },
  { label: "Melhorar qualidade", href: "#melhorador" },
  { label: "Exemplos", href: "#exemplos" },
  { label: "Dúvidas", href: "#duvidas" },
];

/* recortes reais, feitos pelo próprio NoIMG, espalhados em volta do título */
const COLLAGE = [
  { src: "/demo/web/cachorro-sem-fundo.png", alt: "Filhote recortado", cls: "left-[2%] top-[16%] w-52 -rotate-6", tile: "checker" },
  { src: "/demo/web/caneca-sem-fundo.png", alt: "Caneca recortada", cls: "left-[6%] top-[58%] w-44 rotate-3", tile: "bg-primary-light" },
  { src: "/demo/web/pelicano-sem-fundo.png", alt: "Pelicano recortado", cls: "right-[3%] top-[12%] w-48 rotate-6", tile: "bg-surface" },
  { src: "/demo/web/camera-sem-fundo.png", alt: "Câmera recortada", cls: "right-[5%] top-[52%] w-56 -rotate-3", tile: "checker" },
];

const SUBJECTS = [
  { id: "cachorro", label: "Filhote" },
  { id: "caneca", label: "Caneca" },
  { id: "pelicano", label: "Pelicano" },
  { id: "camera", label: "Câmera" },
  { id: "mel", label: "Mel" },
];

const BACKDROPS = [
  { id: "transparente", label: "Transparente", cls: "checker" },
  { id: "branco", label: "Branco de loja", cls: "bg-white" },
  { id: "gelo", label: "Azul gelo", cls: "bg-primary-light" },
  { id: "lagoa", label: "Lagoa", img: "/img/lagoa.jpg" },
  { id: "neblina", label: "Neblina", img: "/img/neblina.jpg" },
  { id: "neve", label: "Picos nevados", img: "/img/picos-neve.jpg" },
];

const SAMPLES: { img: string; name: string; mode: Mode; tall?: boolean }[] = [
  { img: "cachorro", name: "Filhote no deck", mode: "removebg", tall: true },
  { img: "montanha", name: "Montanha", mode: "upscale" },
  { img: "caneca", name: "Caneca antiga", mode: "removebg" },
  { img: "retrato", name: "Retrato no campo", mode: "upscale", tall: true },
  { img: "pelicano", name: "Pelicano", mode: "removebg" },
  { img: "vaca", name: "Vaca das Highlands", mode: "removebg" },
  { img: "lago", name: "Lago entre pinheiros", mode: "upscale", tall: true },
  { img: "camera", name: "Câmera de filme", mode: "removebg" },
  { img: "leopardo", name: "Leopardo na trilha", mode: "removebg" },
  { img: "pinheiros-neve", name: "Pinheiros na neve", mode: "upscale" },
  { img: "dente-de-leao", name: "Dente-de-leão", mode: "removebg", tall: true },
  { img: "mel", name: "Mel escorrendo", mode: "removebg" },
];

const FAQ = [
  {
    question: "Minhas imagens são enviadas para algum servidor?",
    answer: "Não. O NoIMG roda inteiro no seu computador. As imagens não saem da sua máquina, nem para processar, nem para guardar.",
  },
  {
    question: "Remover o fundo diminui a qualidade?",
    answer: "Não. O recorte sai no mesmo tamanho da foto original, em PNG sem perdas. Os pixels do objeto continuam idênticos, só as bordas recebem correção de cor para não carregar o tom do fundo antigo.",
  },
  {
    question: "Se eu melhorar um PNG sem fundo, ele continua transparente?",
    answer: "Sim. A cor e a transparência são ampliadas separadamente, então o resultado continua sem fundo e sem aquele contorno escuro em volta do objeto.",
  },
  {
    question: "Qual a diferença entre Rápido e Máxima qualidade?",
    answer: "Os dois usam o Real-ESRGAN. O Rápido usa um modelo compacto e termina em segundos. O Máxima qualidade usa o modelo completo, recupera mais textura e leva bem mais tempo em computadores sem placa de vídeo.",
  },
  {
    question: "Quais formatos posso usar?",
    answer: "JPG, PNG e WEBP na entrada. O resultado sempre sai em PNG, para não perder qualidade.",
  },
];

interface Credit {
  file: string;
  author: string;
  source: string;
}

export default function App() {
  const [mode, setMode] = useState<Mode>("removebg");
  const [incoming, setIncoming] = useState<File | null>(null);
  const [subject, setSubject] = useState(SUBJECTS[0].id);
  const [backdrop, setBackdrop] = useState(BACKDROPS[3].id);
  const [credits, setCredits] = useState<Credit[]>([]);

  useEffect(() => {
    fetch("/img/creditos.json")
      .then((r) => r.json())
      .then(setCredits)
      .catch(() => setCredits([]));
  }, []);

  const go = (href: string) => document.querySelector(href)?.scrollIntoView({ behavior: "smooth", block: "start" });

  const trySample = async (s: (typeof SAMPLES)[number]) => {
    setMode(s.mode);
    setIncoming(await fileFromUrl(`/img/${s.img}.jpg`, `${s.img}.jpg`));
    go("#topo");
  };

  const bd = BACKDROPS.find((b) => b.id === backdrop)!;

  return (
    <div className="overflow-x-clip">
      {/* ---------- topo ---------- */}
      <header className="fixed inset-x-0 top-0 z-50 flex h-[var(--header-height)] items-center px-4 md:px-8">
        <a
          href="#topo"
          className="flex items-center gap-2 rounded-full border border-line bg-white/80 p-1.5 sm:pr-4 text-lg font-bold tracking-tight text-ink shadow-md backdrop-blur-md"
          aria-label="NoIMG, início"
        >
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <span className="hidden sm:inline">NoIMG</span>
        </a>
        <SpotlightNavbar items={NAV} className="mx-auto hidden pt-0 md:flex" onItemClick={(item) => go(item.href)} />
        <span className="ml-auto hidden w-[104px] md:block" aria-hidden />
        <button onClick={() => go("#topo")} className="ml-auto rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white md:hidden">
          Abrir ferramenta
        </button>
      </header>

      {/* ---------- hero + ferramenta ---------- */}
      <section id="topo" className="relative isolate flex min-h-[100svh] flex-col items-center px-4 pt-32 pb-20">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60%_50%_at_50%_0%,var(--primary-light),transparent_70%)]" />

        {COLLAGE.map((c, i) => (
          <motion.div
            key={c.src}
            aria-hidden
            initial={{ opacity: 0, y: 30, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.5 + i * 0.12, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className={cn("absolute hidden rounded-xl border border-line p-3 shadow-lg xl:block", c.tile, c.cls)}
          >
            <img src={c.src} alt={c.alt} className="h-auto w-full drop-shadow-[0_10px_18px_rgba(23,45,58,0.25)]" />
          </motion.div>
        ))}

        <h1 className="max-w-4xl text-center text-[clamp(2.6rem,7vw,5.6rem)] leading-[0.95] font-extrabold tracking-[-0.04em] text-ink [font-variation-settings:'opsz'_96]">
          <TextAnimation delay={0.1}>Fotos mais nítidas.</TextAnimation>
          <br />
          <span className="text-primary">
            <TextAnimation delay={0.35}>Fundos que somem.</TextAnimation>
          </span>
        </h1>
        <p className="mt-6 max-w-xl text-center text-lg text-ink-2">
          Duas ferramentas de imagem que rodam no seu computador. Nada é enviado para a internet e nada perde resolução.
        </p>

        <div className="mt-10 flex w-full justify-center">
          <Workspace mode={mode} onModeChange={setMode} incoming={incoming} />
        </div>

        {/* recortes em linha no celular */}
        <div className="mt-10 flex gap-3 xl:hidden" aria-hidden>
          {COLLAGE.map((c) => (
            <div key={c.src} className={cn("w-20 rounded-lg border border-line p-1.5 sm:w-28", c.tile)}>
              <img src={c.src} alt="" className="h-auto w-full" />
            </div>
          ))}
        </div>
      </section>

      {/* ---------- removedor de fundo ---------- */}
      <section id="removedor" className="scroll-mt-20 bg-surface px-4 py-24">
        <div className="mx-auto grid max-w-[var(--container-width)] items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div>
            <h2 className="text-4xl leading-tight font-bold tracking-tight md:text-5xl">{TOOLS.removebg.title}</h2>
            <p className="mt-5 max-w-md text-lg text-ink-2">{TOOLS.removebg.text}</p>

            <p className="mt-10 mb-3 text-sm font-medium text-ink-3">Objeto</p>
            <div className="flex flex-wrap gap-2">
              {SUBJECTS.map((s) => (
                <Chip key={s.id} active={s.id === subject} onClick={() => setSubject(s.id)}>
                  {s.label}
                </Chip>
              ))}
            </div>
            <p className="mt-6 mb-3 text-sm font-medium text-ink-3">Novo fundo</p>
            <div className="flex flex-wrap gap-2">
              {BACKDROPS.map((b) => (
                <button
                  key={b.id}
                  onClick={() => setBackdrop(b.id)}
                  aria-pressed={b.id === backdrop}
                  title={b.label}
                  className={cn(
                    "h-12 w-12 overflow-hidden rounded-md border-2 transition",
                    b.id === backdrop ? "border-primary ring-4 ring-primary-light" : "border-line hover:border-line-hover",
                    b.cls,
                  )}
                >
                  {b.img && <img src={b.img} alt="" className="h-full w-full object-cover" />}
                  <span className="sr-only">{b.label}</span>
                </button>
              ))}
            </div>

            <button
              onClick={() => {
                setMode("removebg");
                go("#topo");
              }}
              className="mt-10 rounded-full bg-primary px-6 py-3 font-semibold text-white shadow-md transition-colors hover:bg-primary-hover"
            >
              {TOOLS.removebg.cta}
            </button>
          </div>

          <div className={cn("relative aspect-[4/3] overflow-hidden rounded-xl border border-line shadow-lg", bd.cls)}>
            <AnimatePresence initial={false}>
              {bd.img && (
                <motion.img key={bd.id} src={bd.img} alt="" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.45 }} className="absolute inset-0 h-full w-full object-cover" />
              )}
            </AnimatePresence>
            <AnimatePresence mode="wait">
              <motion.img
                key={subject}
                src={`/demo/web/${subject}-sem-fundo.png`}
                alt={`${SUBJECTS.find((s) => s.id === subject)?.label} sem fundo`}
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                className="absolute inset-x-0 bottom-[6%] mx-auto max-h-[78%] max-w-[70%] object-contain drop-shadow-[0_24px_30px_rgba(23,45,58,0.35)]"
              />
            </AnimatePresence>
            <span className="absolute bottom-3 left-3 rounded-full bg-white/85 px-3 py-1 text-xs text-ink-2 backdrop-blur">
              Recorte feito pelo NoIMG neste computador
            </span>
          </div>
        </div>
      </section>

      {/* ---------- melhorador de qualidade ---------- */}
      <section id="melhorador" className="scroll-mt-20 px-4 py-24">
        <div className="mx-auto max-w-[var(--container-width)]">
          <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <h2 className="text-4xl leading-tight font-bold tracking-tight md:text-5xl">{TOOLS.upscale.title}</h2>
              <p className="mt-5 max-w-xl text-lg text-ink-2">{TOOLS.upscale.text}</p>
            </div>
            <button
              onClick={() => {
                setMode("upscale");
                go("#topo");
              }}
              className="shrink-0 self-start rounded-full bg-primary px-6 py-3 font-semibold text-white shadow-md transition-colors hover:bg-primary-hover md:self-auto"
            >
              {TOOLS.upscale.cta}
            </button>
          </div>

          <div className="mt-12 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <figure>
              <CompareSlider
                className="aspect-[3/2] rounded-xl border border-line shadow-lg"
                initial={45}
                before={<img src="/demo/web/montanha-pequena.png" alt="Montanha em 360 pixels" className="h-full w-full object-cover" style={{ imageRendering: "pixelated" }} />}
                after={<img src="/demo/web/montanha-4x.jpg" alt="Montanha ampliada 4 vezes" className="h-full w-full object-cover" />}
                beforeLabel="360 px"
                afterLabel="1440 px"
              />
              <figcaption className="mt-3 text-sm text-ink-3">Arraste para comparar. Foto de 360 px de largura ampliada 4x no modo Rápido.</figcaption>
            </figure>
            <figure>
              <CompareSlider
                className="aspect-[3/4] rounded-xl border border-line shadow-lg lg:aspect-auto lg:h-[calc(100%-2rem)]"
                before={<img src="/demo/web/retrato-pequena.png" alt="Retrato em 300 pixels" className="h-full w-full object-cover" style={{ imageRendering: "pixelated" }} />}
                after={<img src="/demo/web/retrato-4x.jpg" alt="Retrato ampliado 4 vezes" className="h-full w-full object-cover" />}
                beforeLabel="300 px"
                afterLabel="1200 px"
              />
              <figcaption className="mt-3 text-sm text-ink-3">Retrato de 300 px, também em 4x.</figcaption>
            </figure>
          </div>
        </div>
      </section>

      {/* ---------- privacidade, sobre foto ---------- */}
      <section className="relative isolate overflow-hidden px-4 py-28 text-white">
        <img src="/img/cordilheira.jpg" alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[#172D3A]/90 via-[#172D3A]/70 to-[#172D3A]/30" />
        <div className="mx-auto max-w-[var(--container-width)]">
          <h2 className="max-w-2xl text-4xl leading-tight font-bold tracking-tight md:text-5xl">Suas imagens não saem do seu computador.</h2>
          <p className="mt-5 max-w-xl text-lg text-white/80">
            Os modelos de IA ficam instalados na sua máquina. Funciona até sem internet, e nenhuma foto fica guardada em servidor de ninguém.
          </p>
          <dl className="mt-14 grid max-w-3xl gap-10 sm:grid-cols-3">
            <Stat icon={ShieldCheck} value={0} label="imagens enviadas para a internet" />
            <Stat icon={Cpu} value={4} suffix="x" label="de ampliação, com ou sem fundo" />
            <Stat icon={FileImage} value={100} suffix="%" label="da resolução mantida no recorte" />
          </dl>
        </div>
      </section>

      {/* ---------- como funciona ---------- */}
      <section className="bg-surface px-4 py-24">
        <div className="mx-auto max-w-[var(--container-width)]">
          <h2 className="text-4xl font-bold tracking-tight md:text-5xl">Três passos</h2>
          <ol className="mt-12 grid gap-8 md:grid-cols-3">
            {[
              ["Escolha a ferramenta", "Remover fundo ou melhorar a qualidade. Dá para usar uma depois da outra."],
              ["Solte a imagem", "Arraste o arquivo para a área de envio ou clique para escolher. Aceita JPG, PNG e WEBP."],
              ["Baixe o PNG", "Compare o antes e depois e baixe o resultado no tamanho final, sem compressão."],
            ].map(([t, d], i) => (
              <li key={t} className="border-t-2 border-primary pt-6">
                <span className="text-5xl font-extrabold text-secondary">{i + 1}</span>
                <h3 className="mt-3 text-xl font-semibold">{t}</h3>
                <p className="mt-2 text-ink-2">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---------- exemplos ---------- */}
      <section id="exemplos" className="scroll-mt-20 px-4 py-24">
        <div className="mx-auto max-w-[var(--container-width)]">
          <h2 className="text-4xl font-bold tracking-tight md:text-5xl">Experimente com uma foto nossa</h2>
          <p className="mt-4 max-w-xl text-lg text-ink-2">Clique numa foto para abrir na ferramenta certa. Todas têm licença livre do Unsplash.</p>
          <div className="mt-12 columns-2 gap-4 md:columns-3 lg:columns-4">
            {SAMPLES.map((s) => (
              <button
                key={s.img}
                onClick={() => trySample(s)}
                className="group relative mb-4 block w-full break-inside-avoid overflow-hidden rounded-lg border border-line text-left shadow-sm"
              >
                <img src={`/img/${s.img}.jpg`} alt={s.name} loading="lazy" className={cn("w-full object-cover transition duration-500 group-hover:scale-[1.04]", s.tall ? "aspect-[3/4]" : "aspect-[4/3]")} />
                <span className="absolute inset-x-2 bottom-2 flex items-center justify-between rounded-md bg-white/90 px-3 py-2 text-sm backdrop-blur">
                  <span className="font-medium text-ink">{s.name}</span>
                  <span className="text-ink-3">{s.mode === "removebg" ? "Remover fundo" : "Melhorar"}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- dúvidas ---------- */}
      <section id="duvidas" className="scroll-mt-20 bg-surface px-4 py-24">
        <div className="mx-auto max-w-3xl">
          <h2 className="mb-6 text-4xl font-bold tracking-tight md:text-5xl">Dúvidas comuns</h2>
          <FaqAccordion items={FAQ} title="" className="py-0" />
        </div>
      </section>

      {/* ---------- rodapé ---------- */}
      <footer className="relative isolate overflow-hidden px-4 pt-20 pb-10">
        <img src="/img/neblina.jpg" alt="" className="absolute inset-0 -z-20 h-full w-full object-cover opacity-40" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-t from-page via-page/90 to-page/60" />
        <div className="mx-auto max-w-[var(--container-width)]">
          <p className="text-[clamp(3rem,12vw,9rem)] leading-none font-extrabold tracking-[-0.05em] text-primary/90">NoIMG</p>
          <p className="mt-4 max-w-md text-ink-2">Remoção de fundo com ISNet e ampliação com Real-ESRGAN, rodando localmente.</p>
          {credits.length > 0 && (
            <details className="mt-10 text-sm text-ink-3">
              <summary className="cursor-pointer font-medium text-ink-2">Créditos das fotos</summary>
              <ul className="mt-3 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
                {credits.map((c) => (
                  <li key={c.file}>
                    <a href={c.source} target="_blank" rel="noreferrer" className="underline-offset-2 hover:text-primary hover:underline">
                      {c.author}
                    </a>{" "}
                    no Unsplash ({c.file.replace(".jpg", "")})
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </footer>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-4 py-2 text-sm font-medium transition-colors",
        active ? "border-primary bg-primary text-white" : "border-line bg-surface text-ink-2 hover:border-line-hover hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function Stat({ icon: Icon, value, suffix, label }: { icon: typeof ShieldCheck; value: number; suffix?: string; label: string }) {
  return (
    <div>
      <Icon className="h-6 w-6 text-secondary" aria-hidden />
      <dd className="mt-3 text-6xl font-extrabold tracking-tight">
        <StatsCounter value={value} suffix={suffix} />
      </dd>
      <dt className="mt-1 text-white/75">{label}</dt>
    </div>
  );
}
