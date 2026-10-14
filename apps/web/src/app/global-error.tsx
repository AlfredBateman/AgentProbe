"use client";

import { ErrorScreen } from "@/components/shell/error-screen";
import { Button } from "@/components/ui/button";
import { archivo, jetbrainsMono } from "./fonts";
import "./globals.css";

// Replaces the root layout when the layout itself fails, so it brings its own <html>, fonts and
// styles. A plain anchor, not next/link: the router may be what broke.
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en" className={`${archivo.variable} ${jetbrainsMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <ErrorScreen
          code="500"
          title="Something went wrong"
          reference={error.digest}
          actions={
            <>
              <Button onClick={reset}>Try again</Button>
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a full load: the router may be what failed */}
              <a href="/" className="inline-flex min-h-40 items-center border border-hairline-strong px-16 type-button text-ink no-underline hover:border-ink">
                Home
              </a>
            </>
          }
        >
          The app failed to load. Try again, or reload the page.
        </ErrorScreen>
      </body>
    </html>
  );
}
