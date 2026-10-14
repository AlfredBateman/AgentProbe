"use client";

import { type ReactNode, useRef } from "react";
import { Panel } from "@/components/ui/panel";
import { useReveal } from "@/lib/motion/hooks";
import { BareHeader } from "./bare-header";

type Props = {
  /** A short mono line over the headline, e.g. `[ Access ]`. */
  eyebrow: string;
  /** The headline; wrap one word in `<span className="text-outline">` for the outline word. */
  headline: ReactNode;
  lede: string;
  /** The panel's title strip. */
  panelTitle: string;
  children: ReactNode;
};

/**
 * Sign in and register: a big headline beside a bordered form panel (one column below 810px).
 * Both halves are server-rendered and start clipped (`data-motion`), then wipe in once the page
 * has hydrated.
 */
export function AuthFrame({ eyebrow, headline, lede, panelTitle, children }: Props) {
  const headlineRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useReveal(headlineRef);
  useReveal(panelRef, { delay: 0.12 });
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-1440 flex-1 flex-col border-x border-hairline-strong">
      <BareHeader />
      <main className="grid flex-1 tablet:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div
          ref={headlineRef}
          data-motion="hidden"
          className="flex flex-col justify-between gap-48 border-b border-hairline-strong p-16 tablet:border-r tablet:border-b-0 tablet:p-32"
        >
          <p aria-hidden className="type-micro text-ink-muted">
            {eyebrow}
          </p>
          <div>
            <h1 className="type-display-xl">{headline}</h1>
            <p className="mt-24 max-w-420 type-body-lg text-ink-muted">{lede}</p>
          </div>
        </div>
        <div className="flex items-start p-16 tablet:items-center tablet:p-32">
          <div ref={panelRef} data-motion="hidden" className="w-full max-w-440">
            <Panel lifted crosshair title={panelTitle} titleStyle="label">
              {children}
            </Panel>
          </div>
        </div>
      </main>
    </div>
  );
}
