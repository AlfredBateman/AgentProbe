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
      className="m-auto w-[calc(100%-32px)] max-w-480 rounded-xl bg-surface-1 p-24 text-ink shadow-float backdrop:bg-black/70"
    >
      <div className="mb-15 flex items-start justify-between gap-12">
        <h2 id={titleId} className="font-display text-dash-heading">
          {title}
        </h2>
        <Button variant="icon" aria-label="Close" className="-mt-8 -mr-8 bg-transparent" onClick={() => ref.current?.close()}>
          <CloseIcon />
        </Button>
      </div>
      <div className="text-body text-ink-muted">{children}</div>
      {actions && <div className="mt-24 flex flex-wrap justify-end gap-8">{actions}</div>}
    </dialog>
  );
}
