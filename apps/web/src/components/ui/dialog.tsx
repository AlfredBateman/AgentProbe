"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";
import { Button } from "./button";
import { CloseIcon } from "./icons";

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
};

/** A native modal <dialog>: focus trapping, Escape and the top layer come from the browser. */
export function Dialog({ open, onClose, title, children, actions }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[calc(100%-32px)] max-w-480 border border-hairline-strong bg-surface-2 p-0 text-ink backdrop:bg-canvas/80"
    >
      <header className="flex items-center justify-between gap-12 border-b border-hairline p-8 pl-16">
        <h2 id={titleId} className="type-headline">
          {title}
        </h2>
        <Button variant="icon" aria-label="Close" onClick={() => ref.current?.close()}>
          <CloseIcon />
        </Button>
      </header>
      <div className="p-16 type-body text-ink-muted">{children}</div>
      {actions && <div className="flex flex-wrap justify-end gap-8 border-t border-hairline p-16">{actions}</div>}
    </dialog>
  );
}
