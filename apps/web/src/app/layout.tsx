import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import { WakingNotice } from "@/components/shell/waking-notice";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

// next/font downloads both at build time and serves them from this origin (ADR 0042). The
// width axis is what condenses the largest display sizes.
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], axes: ["wdth"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

// Every page renders per request: the CSP nonce (src/proxy.ts) is new each time, and a page
// prerendered at build time would carry no nonce, so its scripts would be blocked.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "AgentProbe",
  description: "Statistically-corrected regression detection for LLM agents, gated in CI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ToastProvider>{children}</ToastProvider>
        <WakingNotice />
        {/* The one grain layer, for every page (DESIGN.md Details). */}
        <div aria-hidden className="noise" />
      </body>
    </html>
  );
}
