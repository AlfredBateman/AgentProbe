"use client";

import Link from "next/link";
import { type KeyboardEvent, type ReactNode, useEffect, useState } from "react";
import { TAG } from "@/components/landing/site";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { cx } from "@/lib/cx";
import { ServicesChip } from "./services-chip";

export type ShellProject = { id: string; name: string };

type Props = {
  projects: ShellProject[];
  /** Absent on the projects list, where no project is open yet. */
  projectId?: string;
  email: string;
  pathname: string;
  onProjectChange: (id: string) => void;
  onSignOut: () => void;
  children: ReactNode;
};

const SECTIONS = [
  ["Agents", "/agents"],
  ["Suites", "/suites"],
  ["Runs", "/runs"],
  ["Settings", "/settings"],
] as const;

// NODE_ENV is inlined at build time, so server and client agree and nothing mismatches.
const ENV = process.env.NODE_ENV === "development" ? "Dev" : "Prod";

const itemClasses = (current: boolean) =>
  cx(
    // The ring sits inside the item: the rail's scroll container would clip an outer one.
    "relative flex min-h-40 items-center px-16 no-underline focus-visible:-outline-offset-2 pointer-coarse:min-h-44",
    current
      ? "bg-surface-1 text-accent before:absolute before:inset-y-0 before:left-0 before:w-3 before:bg-accent"
      : "text-ink-muted hover:bg-surface-1 hover:text-ink",
  );

/**
 * ArrowUp/ArrowDown/Home/End move between a nav's links, on top of Tab. The links stay in the tab
 * order, so nothing depends on this.
 */
function arrowNav(e: KeyboardEvent<HTMLElement>) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const items = [...e.currentTarget.querySelectorAll<HTMLAnchorElement>("a[href]")];
  const at = items.indexOf(document.activeElement as HTMLAnchorElement);
  if (at < 0) return;
  e.preventDefault();
  const to = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
  items[to].focus();
}

/**
 * The app frame (ADR 0047): a 56px top strip (project switcher, environment and version, API
 * status, account) over a left rail of mono nav items; the active one has a lime edge bar.
 * Below 810px the rail collapses into a menu and the switcher stays in the strip.
 */
export function AppShell({ projects, projectId, email, pathname, onProjectChange, onSignOut, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const base = projectId ? `/projects/${projectId}` : null;
  const project = projects.find((p) => p.id === projectId);
  const overview = base && { label: project?.name ?? "Project overview", href: base, current: pathname === base };
  const links = [
    { label: "Projects", href: "/projects", current: pathname === "/projects" },
    ...(base
      ? SECTIONS.map(([label, path]) => ({
          label,
          href: base + path,
          current: pathname === base + path || pathname.startsWith(base + path + "/"),
        }))
      : []),
  ];

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const item = (l: { label: string; href: string; current: boolean }, bracket = true) => (
    <Link key={l.href} href={l.href} aria-current={l.current ? "page" : undefined} onClick={() => setMenuOpen(false)} className={cx(itemClasses(l.current), "type-label")}>
      <span className={cx(bracket && "bracketed", "truncate")}>{l.label}</span>
    </Link>
  );

  // The project's own name is the way to its overview. It is the one item that is not a section.
  const overviewItem = overview && (
    <div className="border-y border-hairline py-8">
      <p className="px-16 type-micro text-ink-muted">Project</p>
      <Link
        href={overview.href}
        aria-current={overview.current ? "page" : undefined}
        aria-label={`Project overview: ${overview.label}`}
        onClick={() => setMenuOpen(false)}
        className={cx(itemClasses(overview.current), "type-headline normal-case!")}
      >
        <span className="truncate">{overview.label}</span>
      </Link>
    </div>
  );

  const navContent = (
    <>
      {item(links[0])}
      {overviewItem}
      {links.slice(1).map((l) => item(l))}
      {!base && <p className="px-16 pt-16 type-body-sm text-ink-muted">Open a project to see its agents, suites and runs.</p>}
    </>
  );

  return (
    <div className="mx-auto flex min-h-full w-full max-w-1440 flex-1 flex-col border-x border-hairline-strong">
      <a
        href="#main-content"
        className="sr-only type-button focus:not-sr-only focus:fixed focus:top-8 focus:left-8 focus:z-(--z-toast) focus:bg-accent focus:px-16 focus:py-12 focus:text-on-accent"
      >
        Skip to content
      </a>
      {/* The bar's bottom edge is its own border, so it is exactly 56px with the line inside it. */}
      <header className="sticky top-0 z-(--z-nav) flex h-56 shrink-0 items-center gap-8 border-b border-hairline-strong bg-canvas px-16 tablet:gap-16 tablet:px-24">
        <Button
          variant="icon"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="shell-menu"
          onClick={() => setMenuOpen((o) => !o)}
          className="tablet:hidden"
        >
          {menuOpen ? <CloseIcon /> : <MenuIcon />}
        </Button>
        <Link href="/" className="tap shrink-0 type-headline text-ink no-underline">
          AgentProbe
          <span aria-hidden className="text-accent">
            ®
          </span>
        </Link>
        <Select
          aria-label="Project"
          value={projectId ?? ""}
          onChange={(e) => onProjectChange(e.target.value)}
          className="min-w-0 max-w-240 shrink tablet:ml-8"
        >
          {!projectId && (
            <option value="" disabled>
              Select a project
            </option>
          )}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <div className="ml-auto hidden items-center gap-16 tablet:flex">
          <p className="hidden type-micro text-ink-muted desktop:block">
            Env <span className="text-ink">{ENV}</span> <span aria-hidden>{"///"}</span> Rev <span className="text-ink normal-case">{TAG}</span>
          </p>
          <ServicesChip />
          <span className="hidden max-w-200 truncate type-label normal-case! text-ink-muted desktop:inline" title={email}>
            {email}
          </span>
          <Button variant="secondary" onClick={onSignOut} title={`Signed in as ${email}`}>
            Sign out
          </Button>
        </div>
      </header>

      {menuOpen && (
        <div id="shell-menu" className="border-b border-hairline-strong bg-canvas tablet:hidden">
          <nav aria-label="Project menu" onKeyDown={arrowNav} className="flex flex-col py-8">
            {navContent}
          </nav>
          <div className="flex flex-wrap items-center justify-between gap-12 border-t border-hairline p-16">
            <ServicesChip />
            <p className="min-w-0 max-w-full truncate type-label normal-case! text-ink-muted">{email}</p>
            <Button variant="secondary" onClick={onSignOut}>
              Sign out
            </Button>
          </div>
        </div>
      )}

      <div className="grid flex-1 grid-cols-1 tablet:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden border-r border-hairline-strong tablet:block">
          <nav
            aria-label="Project sections"
            onKeyDown={arrowNav}
            className="sticky top-56 flex max-h-[calc(100dvh-56px)] flex-col overflow-y-auto py-16"
          >
            {navContent}
          </nav>
        </aside>
        {/* tabIndex -1 so the skip link lands focus here; nothing in it is a control. */}
        <main id="main-content" tabIndex={-1} className="min-w-0 px-16 py-24 outline-none tablet:px-32 tablet:py-32">
          {children}
        </main>
      </div>
    </div>
  );
}
