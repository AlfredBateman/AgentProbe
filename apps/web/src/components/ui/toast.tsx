"use client";

import { createContext, type ReactNode, useCallback, useContext, useState } from "react";
import { Button } from "./button";
import { CloseIcon } from "./icons";
import { type Status, StatusDot } from "./status";

type Toast = { id: number; title: string; tone?: Exclude<Status, "stable"> };
type Push = (toast: Omit<Toast, "id">) => void;

const ToastContext = createContext<Push | null>(null);
const DISMISS_MS = 5000;
let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const push = useCallback<Push>(
    (toast) => {
      const id = ++nextId;
      setToasts((ts) => [...ts, { ...toast, id }]);
      setTimeout(() => dismiss(id), DISMISS_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      {/* Always mounted, so screen readers announce what gets added. */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-16 bottom-16 left-16 z-50 flex flex-col items-end gap-8 tablet:left-auto"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex w-full max-w-360 items-center gap-10 rounded-lg bg-surface-2 py-6 pr-6 pl-15 text-body-sm shadow-float"
          >
            {t.tone && <StatusDot status={t.tone} decorative />}
            <span className="flex-1">{t.title}</span>
            <Button variant="icon" aria-label="Dismiss" className="bg-transparent" onClick={() => dismiss(t.id)}>
              <CloseIcon />
            </Button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Push {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast needs a <ToastProvider> above it");
  return push;
}
