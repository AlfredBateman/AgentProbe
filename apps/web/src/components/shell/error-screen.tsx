import type { ReactNode } from "react";
import { BareHeader } from "./bare-header";

type Props = {
  /** The big mark: "404", "500". Drawing only; the title says it in words. */
  code: string;
  title: string;
  children: ReactNode;
  actions: ReactNode;
  /** An error digest, shown so a report can be matched to a server log line. */
  reference?: string;
};

/** The 404 and 500 pages: an outlined code over a short plain sentence and the ways out. */
export function ErrorScreen({ code, title, children, actions, reference }: Props) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-1440 flex-1 flex-col border-x border-hairline-strong">
      <BareHeader />
      <main className="@container flex flex-1 flex-col justify-between gap-48 p-16 tablet:p-32">
        <p aria-hidden className="type-micro text-ink-muted">
          [ {code} ] <span>{"///"}</span> Unit D-01
        </p>
        <div>
          <p aria-hidden className="type-display-xxl text-outline select-none">
            {code}
          </p>
          <h1 className="mt-24 type-display-md">{title}</h1>
          <p className="mt-12 max-w-420 type-body-lg text-ink-muted">{children}</p>
          <div className="mt-24 flex flex-wrap gap-12">{actions}</div>
          {reference && <p className="mt-24 type-micro text-ink-muted">Ref {reference}</p>}
        </div>
      </main>
    </div>
  );
}
