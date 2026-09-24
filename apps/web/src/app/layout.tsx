import type { Metadata } from "next";
import { Geist, Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AgentProbe",
  description: "Testing, red-teaming and regression detection for LLM agents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
