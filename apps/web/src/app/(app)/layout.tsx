import type { ReactNode } from "react";
import { AppFrame } from "@/components/shell/app-frame";
import { PageTransition } from "@/lib/motion/page-transition";

// Everything signed-in lives in this group: the shell, one session load, and the page wipe.
// The wipe is mounted here and nowhere else, so the landing page, the auth pages and the shared
// run view never run it. It sits inside the shell, so the rail and the strip stay put.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame>
      <PageTransition>{children}</PageTransition>
    </AppFrame>
  );
}
