"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { cx } from "@/lib/cx";

export type ShellProject = { id: string; name: string };

type Props = {
  projects: ShellProject[];
  projectId: string;
  email: string;
  pathname: string;
  onProjectChange: (id: string) => void;
  onSignOut: () => void;
  children: ReactNode;
};

const SECTIONS = [
  ["Overview", ""],
  ["Agents", "/agents"],
  ["Suites", "/suites"],
  ["Runs", "/runs"],
  ["Settings", "/settings"],
] as const;

/** DESIGN.md top-nav: 56px on canvas. Below 810px the links collapse into a menu; the project switcher stays. */
export function AppShell({ projects, projectId, email, pathname, onProjectChange, onSignOut, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const base = `/projects/${projectId}`;
  const links = SECTIONS.map(([label, path]) => {
    const href = base + path;
    const current = path === "" ? pathname === href : pathname === href || pathname.startsWith(href + "/");
    return { label, href, current };
  });

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const navLink = (l: (typeof links)[number], className: string) => (
    <Link
      key={l.href}
      href={l.href}
      aria-current={l.current ? "page" : undefined}
      onClick={() => setMenuOpen(false)}
      className={cx(
        "rounded-pill outline-none focus-visible:shadow-focus",
        l.current ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink",
        className,
      )}
    >
      {l.label}
    </Link>
  );

  return (
    <div className="flex min-h-full flex-1 flex-col">
      {/* An inset shadow, not a border, keeps the bar at exactly 56px. */}
      <header className="sticky top-0 z-40 bg-canvas text-body-sm shadow-[inset_0_-1px_0_var(--color-hairline-soft)]">
        <div className="mx-auto flex h-56 max-w-1440 items-center gap-12 px-16 tablet:px-30">
          <Link href="/" className="font-display text-[20px] font-medium tracking-[-0.6px] text-ink outline-none focus-visible:shadow-focus">
            AgentProbe
          </Link>
          <Select
            aria-label="Project"
            value={projectId}
            onChange={(e) => onProjectChange(e.target.value)}
            className="min-w-0 max-w-160 shrink [&_select]:rounded-pill [&_select]:py-6 [&_select]:text-body-sm"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <nav aria-label="Project sections" className="hidden min-w-0 flex-1 justify-center-safe gap-2 tablet:flex">
            {links.map((l) => navLink(l, "shrink-0 px-12 py-8"))}
          </nav>
          <div className="ml-auto hidden items-center gap-12 tablet:flex">
            {/* 810px is too narrow for the email as well; it is still in the sign-out title. */}
            <span className="hidden max-w-200 truncate text-ink-muted desktop:inline" title={email}>
              {email}
            </span>
            <Button variant="secondary" onClick={onSignOut} title={`Signed in as ${email}`}>
              Sign out
            </Button>
          </div>
          <Button
            variant="icon"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="shell-menu"
            onClick={() => setMenuOpen((o) => !o)}
            className="ml-auto tablet:hidden"
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </Button>
        </div>
        {menuOpen && (
          <div id="shell-menu" className="border-t border-hairline-soft bg-canvas px-16 pt-12 pb-20 tablet:hidden">
            <nav aria-label="Project menu" className="flex flex-col gap-4">
              {links.map((l) => navLink(l, "px-15 py-12 text-body"))}
            </nav>
            <div className="mt-12 flex items-center justify-between gap-12 border-t border-hairline-soft pt-12">
              <span className="min-w-0 truncate text-ink-muted">{email}</span>
              <Button variant="secondary" onClick={onSignOut}>
                Sign out
              </Button>
            </div>
          </div>
        )}
      </header>
      <main className="mx-auto w-full max-w-1440 flex-1 px-16 py-30 tablet:px-30">{children}</main>
    </div>
  );
}
