import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted: Google's Inter drops the cv01/05/09/11 and ss03/07 features DESIGN.md depends on
// (ADR 0004). This is rsms' own variable build, Latin subset.
const inter = localFont({
  src: "../../node_modules/inter-ui/variable-latin/InterVariable-subset.woff2",
  variable: "--font-inter",
  weight: "100 900",
});
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AgentProbe",
  description: "Statistically-corrected regression detection for LLM agents, gated in CI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geist.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
