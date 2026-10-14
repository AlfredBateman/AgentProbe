import Link from "next/link";
import { Hero } from "@/components/landing/hero";
import { Reveal, Stagger } from "@/components/landing/motion";
import { Proof } from "@/components/landing/proof";
import { INSTALL, LICENSE, OWNER, REPO, TAG } from "@/components/landing/site";
import { StatusChip } from "@/components/landing/status-chip";
import { buttonClasses } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code";
import { MenuIcon } from "@/components/ui/icons";
import { Panel } from "@/components/ui/panel";

const NAV = [
  ["Docs", `${REPO}#documentation`],
  ["GitHub", REPO],
  ["Sign in", "/login"],
];

const CARDS = [
  { title: "Repeat every case", body: "Every case runs many times, not once.", href: "#proof" },
  { title: "Judge traces and tool calls", body: "Judges read tool calls, not just text.", href: `${REPO}#how-it-works` },
  { title: "Gate the pull request", body: "The check fails only on a real drop.", href: "#install" },
];

// A long title wraps inside its own width, so the corner arrow stays in the corner.
const CARD = "hover:bg-surface-1 [&>header]:flex-nowrap [&>header]:items-start";
const navLink = "inline-flex min-h-40 items-center text-ink-muted no-underline hover:text-ink pointer-coarse:min-h-44";

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-1440 flex-1 flex-col border-x border-hairline-strong">
      <header className="border-b border-hairline-strong">
        <div className="relative flex h-56 items-center gap-8 px-16 tablet:gap-24 tablet:px-32">
          <Link href="/" className="tap type-headline text-ink no-underline">
            AgentProbe
            <span aria-hidden className="text-accent">
              ®
            </span>
          </Link>
          <nav aria-label="Site" className="ml-auto hidden items-center gap-24 type-label tablet:flex">
            {NAV.map(([label, href]) => (
              <a key={label} href={href} className={navLink}>
                {label}
              </a>
            ))}
          </nav>
          {/* Below 810px the links are a native disclosure: no script, and the open list floats
              over the page, so it moves nothing. */}
          <details className="ml-auto tablet:hidden">
            <summary aria-label="Menu" className={buttonClasses("icon", "list-none [&::-webkit-details-marker]:hidden")}>
              <MenuIcon />
            </summary>
            <nav aria-label="Site menu" className="absolute inset-x-0 top-full z-(--z-nav) flex flex-col border-y border-hairline-strong bg-canvas px-16 py-8 type-label">
              {NAV.map(([label, href]) => (
                <a key={label} href={href} className={navLink}>
                  {label}
                </a>
              ))}
            </nav>
          </details>
          {/* Under 360px the bar has no room for it; the hero's own button is one scroll away. */}
          <Link href="/register" className={buttonClasses("primary", "max-[359px]:hidden")}>
            Get started
          </Link>
        </div>
        <div className="flex min-h-40 flex-wrap items-center justify-between gap-x-16 gap-y-4 border-t border-hairline px-16 py-8 type-micro text-ink-muted tablet:px-32">
          <p>
            REV <span className="normal-case">{TAG}</span> <span aria-hidden>{"///"}</span> Unit D-01
          </p>
          <StatusChip />
        </div>
      </header>

      <main className="flex flex-1 flex-col">
        <Hero />

        <Stagger as="section" aria-label="How it works" className="grid gap-16 border-b border-hairline-strong px-16 py-32 tablet:grid-cols-3 tablet:px-32">
          {CARDS.map((card, i) => (
            <Panel key={card.title} title={card.title} href={card.href} className={CARD}>
              {/* The numeral is the card's index, drawing only; the sentence beside it is the body. */}
              <div className="flex items-end justify-between gap-16">
                <p className="max-w-[20ch] type-body-sm text-ink-muted">{card.body}</p>
                <span aria-hidden className="type-display-lg leading-none tabular-nums">{`0${i + 1}`}</span>
              </div>
            </Panel>
          ))}
        </Stagger>

        <Proof />

        <section id="install" aria-labelledby="install-title" className="px-16 py-48 tablet:px-32 tablet:py-96">
          <h2 id="install-title" className="type-display-xl">
            Install
          </h2>
          <Reveal as="div" className="mt-32">
            <CodeBlock code={INSTALL} label="CLI /// Run /// GitHub Action" />
          </Reveal>
          <p className="mt-12 max-w-720 type-body-sm text-ink-muted">
            Install from the git URL: the PyPI name agentprobe belongs to an unrelated project.{" "}
            <a href={`${REPO}#quick-start`}>Quick start</a>
          </p>
        </section>
      </main>

      <footer className="grid-lines border-t border-hairline-strong tablet:grid-cols-2 desktop:grid-cols-[2fr_1fr_1fr]">
        <div className="relative overflow-hidden p-16 tablet:col-span-2 tablet:p-32 desktop:col-span-1">
          <p className="type-display-lg">
            AgentProbe
            <span aria-hidden className="text-accent">
              ®
            </span>
          </p>
          <p className="mt-12 type-body-sm text-ink-muted">Regression detection for LLM agents.</p>
          {/* The marks as drawing, not as legal text: the copyright line is in the last cell. */}
          <p aria-hidden className="mt-24 flex gap-16 type-display-xl text-outline text-hairline-strong select-none">
            <span>©</span>
            <span>®</span>
          </p>
        </div>
        <nav aria-label="Footer" className="flex flex-col p-16 type-label tablet:p-32">
          {[...NAV, ["Metrics", `${REPO}/blob/main/docs/metrics.md`], ["Get started", "/register"]].map(([label, href]) => (
            <a key={label} href={href} className={navLink}>
              {label}
            </a>
          ))}
        </nav>
        <dl className="flex flex-col gap-12 p-16 type-label tablet:p-32">
          {[
            ["Copyright", `© ${new Date().getFullYear()} ${OWNER}`],
            ["License", LICENSE],
            ["Rev", TAG],
          ].map(([name, value]) => (
            <div key={name} className="flex items-baseline justify-between gap-12">
              <dt className="text-ink-muted">{name}</dt>
              <dd className="normal-case">{value}</dd>
            </div>
          ))}
        </dl>
      </footer>
    </div>
  );
}
