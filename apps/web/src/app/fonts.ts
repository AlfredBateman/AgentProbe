import { Archivo, JetBrains_Mono } from "next/font/google";

// next/font downloads both at build time and serves them from this origin (ADR 0042). The
// width axis is what condenses the largest display sizes. Shared by the root layout and
// global-error, which replaces it and so has to load them itself.
export const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], axes: ["wdth"] });
export const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });
