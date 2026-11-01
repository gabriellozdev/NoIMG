import { useCallback, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { Plus } from "lucide-react";
import { CompareSlider } from "@/components/CompareSlider";
import { Workspace } from "@/components/Workspace";
import type { Mode } from "@/lib/api";
import { cn } from "@/lib/utils";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const NAV: [string, string][] = [
  ["Remover fundo", "#remover"],
  ["Melhorar", "#melhorar"],
  ["Padronizar", "#padronizar"],
];

/* a vitrine: produtos reais recortados pelo NoIMG, cada um sobre um bloco de cor */
const VITRINE = [
  { id: "bota", alt: "Bota de tecido escuro", block: "bg-pink", blockH: "h-[26%]", w: "w-[40%]", fig: "w-[94%]" },
  { id: "bolsa", alt: "Bolsa redonda vermelha", block: "bg-yellow", blockH: "h-[42%]", w: "w-[33%]", fig: "w-[84%]" },
  { id: "frasco-rosa", alt: "Frasco rosa com válvula", block: "checker ring-1 ring-inset ring-line", blockH: "h-[18%]", w: "w-[21%]", fig: "w-[52%]" },
];

/* lote padronizado pelo NoIMG: 640 × 640, alinhados pela base */
const LOTE = [
  { id: "salto-vermelho", nome: "Salto", orig: "1482 × 901", from: { x: -6, y: 14, scale: 1.2, rotate: -8 } },
  { id: "relogio", nome: "Relógio", orig: "524 × 712", from: { x: 8, y: -10, scale: 0.6, rotate: 6 } },
  { id: "oculos", nome: "Óculos", orig: "949 × 587", from: { x: -4, y: 18, scale: 1.15, rotate: -5 } },
  { id: "pote", nome: "Pote", orig: "504 × 1062", from: { x: 6, y: -14, scale: 0.62, rotate: 9 } },
  { id: "fone", nome: "Fone", orig: "1010 × 1727", from: { x: -8, y: 8, scale: 1.25, rotate: -10 } },
  { id: "oxford", nome: "Sapato", orig: "1077 × 953", from: { x: 4, y: -6, scale: 0.7, rotate: 5 } },
];

const DUVIDAS: [string, string][] = [
  ["Minhas imagens vão para algum servidor?", "Não. O NoIMG roda inteiro no seu computador. As imagens não saem da sua máquina, nem para processar, nem para guardar."],
  ["Remover o fundo diminui a qualidade?", "Não. O recorte sai no mesmo tamanho da foto original, em PNG. Só as bordas recebem correção de cor, para não carregar o tom do fundo antigo."],
  ["Se eu melhorar um PNG sem fundo, ele continua transparente?", "Continua. A cor e a transparência são ampliadas separadamente, sem contorno escuro em volta."],
  ["Como deixo vários produtos do mesmo tamanho?", "Em Melhorar, ligue Padronizar tamanho e solte até 30 imagens. Todas saem com o mesmo tamanho, a mesma margem e a mesma nitidez, e você baixa tudo num ZIP."],
];

const CREDITOS: [string, string][] = [
  ["orhakim", "orhakim"],
  ["Claire Abdo", "claireabdo"],
  ["Birgith Roosipuu", "msbirgith"],
  ["Engin Akyurt", "enginakyurt"],
  ["Tareq Hasan", "tareq_hasan"],
  ["Jesper Nice", "jespernice"],
  ["Musi Studio", "musi_studio"],
  ["Kiran CK", "kiranck123"],
  ["Collab Media", "collab_media"],
  ["K8", "_k8_"],
];

function Lines({ lines }: { lines: string[] }) {
  return (
    <>
      {lines.map((l) => (
        <span key={l} className="line">
          <span data-line>{l}</span>
        </span>
      ))}
    </>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>("removebg");
  const [wide, setWide] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const onWide = useCallback((w: boolean) => setWide(w), []);

  const openTool = (m: Mode) => {
    setMode(m);
    document.querySelector("#ferramenta")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        /* entrada: blocos sobem da base, produtos pousam com um quique pequeno, título sobe por linha */
        const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
        tl.from(".hero-title [data-line]", { yPercent: 105, duration: 0.7, stagger: 0.07 }, 0)
          .from(".vit-block", { scaleY: 0, transformOrigin: "50% 100%", duration: 0.55, stagger: 0.08 }, 0.25)
          .from(".vit-fig", { y: -60, opacity: 0, duration: 0.6, stagger: 0.08, ease: "back.out(2.2)" }, 0.5)
          .from(".hero-card", { y: 24, opacity: 0, duration: 0.6 }, 0.3);

        gsap.utils.toArray<HTMLElement>("[data-reveal-title]").forEach((el) => {
          gsap.from(el.querySelectorAll("[data-line]"), {
            yPercent: 105,
            duration: 0.7,
            stagger: 0.07,
            ease: "power3.out",
            scrollTrigger: { trigger: el, start: "top 85%", once: true },
          });
        });
        gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((el) => {
          gsap.from(el, { y: 40, opacity: 0, duration: 0.7, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 85%", once: true } });
        });

        /* padronizar: o lote bagunçado se alinha na base enquanto rola */
        const stage = document.querySelector<HTMLElement>(".lote-stage");
        if (stage) {
          const t = gsap.timeline({ scrollTrigger: { trigger: stage, start: "top top", end: "+=120%", scrub: 0.6, pin: true } });
          LOTE.forEach((l, i) => {
            t.from(`.lote-${l.id}`, { xPercent: l.from.x, yPercent: l.from.y, scale: l.from.scale, rotate: l.from.rotate, ease: "power2.inOut", duration: 1 }, i * 0.06);
          });
          t.from(".lote-tile", { opacity: 0, duration: 0.3 }, 0.6)
            .fromTo(".lote-orig", { opacity: 1 }, { opacity: 0, duration: 0.2 }, 0.75)
            .fromTo(".lote-final", { opacity: 0 }, { opacity: 1, duration: 0.2 }, 0.8);
        }
      });
    },
    { scope: root },
  );

  return (
    <div ref={root} className="overflow-x-clip">
      {/* ---------- barra ---------- */}
      <header className="fixed inset-x-0 top-0 z-50 border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-[1320px] items-center px-5 sm:px-8">
          <a href="#topo" className="flex items-center" aria-label="NoIMG, início">
            <img src="/brand/noimg-horizontal.svg" alt="" className="h-10 w-auto" />
          </a>
          <nav className="ml-auto hidden gap-7 sm:flex" aria-label="Seções">
            {NAV.map(([label, href]) => (
              <a key={href} href={href} className="text-[15px] font-medium text-ink-2 hover:text-ink">
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      {/* ---------- vitrine + ferramenta ---------- */}
      <div className="bg-page-alt">
        <section id="topo" className={cn("mx-auto max-w-[1320px] px-5 pt-24 pb-14 sm:px-8 lg:pt-28", wide ? "lg:pb-24" : "lg:pb-0")}>
          <div className={cn("grid gap-4 sm:gap-8 lg:items-start lg:gap-10", wide ? "lg:grid-cols-1" : "lg:grid-cols-12")}>
            {/* esquerda: título atrás dos produtos */}
            <div className={cn("relative", !wide && "lg:col-span-7 lg:h-[740px]")}>
              <h1 className={cn("hero-title display relative z-0 text-ink", wide ? "text-[clamp(2.4rem,5vw,4rem)]" : "text-[clamp(3.1rem,8.4vw,7.6rem)]")}>
                <Lines lines={["Recortados,", "nítidos,", "iguais."]} />
              </h1>
              {!wide && (
                <>
                  <div aria-label="Produtos recortados pelo NoIMG" className="relative z-10 hidden items-end gap-[3%] lg:absolute lg:inset-x-0 lg:bottom-0 lg:flex lg:h-[54%]">
                    {VITRINE.map((v) => (
                      <figure key={v.id} className={cn("relative flex h-full flex-col justify-end", v.w)}>
                        <img src={`/site/vitrine-${v.id}.webp`} alt={v.alt} className={cn("vit-fig relative z-10 mx-auto -mb-[3%] h-auto max-h-[82%] object-contain drop-shadow-[0_14px_18px_rgba(20,20,24,0.18)]", v.fig)} />
                        <div className={cn("vit-block w-full rounded-t-[6px]", v.block, v.blockH)} />
                      </figure>
                    ))}
                  </div>
                  {/* celular: faixa curta de produtos entre o título e o cartão */}
                  <div aria-hidden className="mt-4 flex h-[88px] items-end gap-[3%] sm:h-[200px] lg:hidden">
                    {VITRINE.map((v) => (
                      <div key={v.id} className={cn("flex h-full flex-col justify-end", v.w)}>
                        <img src={`/site/vitrine-${v.id}.webp`} alt="" className={cn("relative z-10 mx-auto -mb-[3%] max-h-[80%] object-contain", v.fig)} />
                        <div className={cn("w-full rounded-t-[4px]", v.block, v.blockH)} />
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* direita: frase de apoio e cartão de envio sobre uma folha rosa */}
            <div className={cn("hero-card lg:pt-4", !wide && "lg:col-span-5 lg:pb-24")}>
              <p className="max-w-[40ch] text-[15px] text-ink-2 sm:text-lg">Tire o fundo, aumente a nitidez e deixe todas do mesmo tamanho. Tudo no seu computador.</p>
              <div className="relative mt-4 mr-2 mb-2 sm:mt-6 sm:mr-3.5 sm:mb-3.5">
                <div aria-hidden className="absolute inset-0 translate-x-2 translate-y-2 rounded-[14px] bg-pink sm:translate-x-3.5 sm:translate-y-3.5" />
                <div className="relative">
                  <Workspace mode={mode} onModeChange={setMode} onWideChange={onWide} />
                </div>
              </div>
              <p className="mt-8 flex items-center gap-2 text-sm text-ink-2">
                <span className="h-2 w-2 rounded-full bg-[var(--success)]" aria-hidden />
                Nenhuma imagem sai do seu computador.
              </p>
            </div>
          </div>
        </section>
      </div>

      {/* ---------- remover fundo: recorte sobre bloco rosa que sangra até a borda ---------- */}
      <section id="remover" className="scroll-mt-16 overflow-hidden py-28 lg:py-36">
        <div className="mx-auto grid max-w-[1320px] items-center gap-12 px-5 sm:px-8 lg:grid-cols-12">
          <div className="relative z-10 lg:col-span-5">
            <h2 data-reveal-title className="display text-[clamp(2.6rem,5vw,4.6rem)]">
              <Lines lines={["Tire o fundo", "sem perder nada."]} />
            </h2>
            <p className="mt-6 max-w-[40ch] text-lg text-ink-2">
              O recorte sai em PNG transparente, no mesmo tamanho da foto. Pronto para loja virtual, anúncio, apresentação ou rede social.
            </p>
            <button onClick={() => openTool("removebg")} className="btn-primary mt-8">
              Remover fundo de uma imagem
            </button>
          </div>
          <figure data-reveal className="relative lg:col-span-6 lg:col-start-7">
            <div aria-hidden className="absolute -top-10 bottom-14 left-[22%] -right-[50vw] bg-pink" />
            <CompareSlider
              className="checker relative aspect-[3/2] w-[92%] overflow-hidden rounded-[10px]"
              initial={45}
              beforeLabel="Foto original"
              afterLabel="Sem fundo"
              before={<img src="/site/mochila-foto.webp" alt="Mochila clara sobre fundo cinza" className="h-full w-full object-cover" />}
              after={<img src="/site/mochila-recorte.webp" alt="A mesma mochila recortada, com fundo transparente" className="h-full w-full object-cover" />}
            />
            <figcaption className="relative mt-5 text-sm text-ink-2">Arraste para comparar: o fundo cinza saiu, até o vão entre as alças.</figcaption>
          </figure>
        </div>
      </section>

      {/* ---------- melhorar: bloco amarelo sangrando para a esquerda ---------- */}
      <section id="melhorar" className="scroll-mt-16 overflow-hidden py-28 lg:py-36">
        <div className="mx-auto grid max-w-[1320px] items-center gap-12 px-5 sm:px-8 lg:grid-cols-12">
          <figure data-reveal className="relative order-2 lg:order-1 lg:col-span-6">
            <div aria-hidden className="absolute -top-10 -bottom-10 -left-[50vw] right-[22%] bg-yellow" />
            <CompareSlider
              className="relative ml-auto aspect-square w-[86%] overflow-hidden rounded-[10px] bg-ink"
              initial={50}
              beforeLabel="240 px"
              afterLabel="960 px"
              before={<img src="/site/melhorar-antes.png" alt="Relógio em 240 pixels" className="h-full w-full object-cover" style={{ imageRendering: "pixelated" }} />}
              after={<img src="/site/melhorar-depois.webp" alt="O mesmo relógio ampliado 4 vezes" className="h-full w-full object-cover" />}
            />
          </figure>
          <div className="relative z-10 order-1 lg:order-2 lg:col-span-5 lg:col-start-8">
            <h2 data-reveal-title className="display text-[clamp(2.6rem,5vw,4.6rem)]">
              <Lines lines={["Aumente", "sem borrar."]} />
            </h2>
            <p className="mt-6 max-w-[40ch] text-lg text-ink-2">Amplie 2x ou 4x com IA. A nitidez volta, os serrilhados somem, e imagens sem fundo continuam sem fundo.</p>
            <p className="display mt-6 text-4xl">
              240 px <span className="text-ink-3">→</span> 960 px
            </p>
            <button onClick={() => openTool("upscale")} className="btn-primary mt-8">
              Melhorar uma imagem
            </button>
          </div>
        </div>
      </section>

      {/* ---------- padronizar: bloco escuro, o lote se alinha com a rolagem ---------- */}
      <section id="padronizar" className="lote-stage bg-ink py-28 text-white lg:py-32">
        <div className="mx-auto w-full max-w-[1320px] px-5 sm:px-8">
          <div className="grid gap-6 lg:grid-cols-12">
            <h2 data-reveal-title className="display text-[clamp(2.6rem,5vw,4.6rem)] lg:col-span-6">
              <Lines lines={["Todos do", "mesmo tamanho."]} />
            </h2>
            <div className="lg:col-span-5 lg:col-start-8">
              <p className="max-w-[42ch] text-lg text-white/75">
                Produtos e personagens recortados em tamanhos diferentes saem com o mesmo enquadramento, a mesma margem e a mesma nitidez. Até 30 de uma vez, num ZIP.
              </p>
              <button onClick={() => openTool("upscale")} className="btn-primary mt-6">
                Padronizar um lote
              </button>
            </div>
          </div>

          <div className="relative mt-14 grid grid-cols-3 gap-3 sm:gap-4 lg:grid-cols-6">
            {LOTE.map((l) => (
              <figure key={l.id}>
                <div className="relative aspect-square">
                  <div aria-hidden className="lote-tile checker absolute inset-0 rounded-[8px]" />
                  <img src={`/site/lote-${l.id}.webp`} alt={`${l.nome} padronizado em 640 × 640 px`} className={`lote-${l.id} relative h-full w-full`} />
                </div>
                <figcaption className="mt-2 text-sm leading-snug">
                  <span className="block font-semibold">{l.nome}</span>
                  <span className="relative block whitespace-nowrap text-white/70 tabular-nums">
                    <span className="lote-orig absolute left-0 opacity-0">{l.orig}</span>
                    <span className="lote-final">640 × 640</span>
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- privacidade ---------- */}
      <section className="py-28 lg:py-36">
        <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
          <div data-reveal className="grid items-end gap-8 rounded-[16px] bg-pink px-6 py-14 sm:px-12 lg:grid-cols-12 lg:py-20">
            <h2 className="display text-[clamp(2.6rem,5.2vw,4.8rem)] lg:col-span-7">Nada sai do seu computador.</h2>
            <p className="max-w-[40ch] text-lg text-ink lg:col-span-5">
              Os modelos de IA ficam instalados na sua máquina. Funciona sem internet, e nenhuma imagem é guardada em servidor de ninguém.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- dúvidas ---------- */}
      <section id="duvidas" className="scroll-mt-16 pb-28">
        <div className="mx-auto grid max-w-[1320px] gap-10 px-5 sm:px-8 lg:grid-cols-12">
          <h2 className="display text-[clamp(2rem,3.6vw,3.2rem)] lg:col-span-4">Dúvidas</h2>
          <div className="lg:col-span-8">
            {DUVIDAS.map(([q, a]) => (
              <details key={q} className="group border-t border-line last:border-b">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-lg font-semibold [&::-webkit-details-marker]:hidden">
                  {q}
                  <Plus className="h-5 w-5 shrink-0 text-ink-2 transition-transform duration-200 group-open:rotate-45" strokeWidth={1.75} aria-hidden />
                </summary>
                <p className="max-w-[60ch] pb-6 text-ink-2">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- rodapé ---------- */}
      <footer className="border-t border-line px-5 py-10 sm:px-8">
        <div className="mx-auto flex max-w-[1320px] flex-col justify-between gap-4 text-sm text-ink-2 lg:flex-row">
          <p>
            <span className="display text-base text-ink">NoIMG</span>: remoção de fundo com ISNet e ampliação com Real-ESRGAN, no seu computador.
          </p>
          <p>
            Fotos do Unsplash por{" "}
            {CREDITOS.map(([nome, user], i) => (
              <span key={user}>
                <a href={`https://unsplash.com/@${user}`} target="_blank" rel="noreferrer" className="underline decoration-ink/25 underline-offset-2 hover:text-primary">
                  {nome}
                </a>
                {i < CREDITOS.length - 2 ? ", " : i === CREDITOS.length - 2 ? " e " : "."}
              </span>
            ))}
          </p>
        </div>
      </footer>
    </div>
  );
}
