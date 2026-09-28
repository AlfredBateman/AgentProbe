import type { Metadata } from "next";
import type { ReactNode } from "react";

// A public link, never indexed: it's meant for whoever holds the token, not search engines.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function SharedLayout({ children }: { children: ReactNode }) {
  return children;
}
