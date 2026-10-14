"use client";

import Link from "next/link";
import { ErrorScreen } from "@/components/shell/error-screen";
import { Button, buttonClasses } from "@/components/ui/button";

// The error's message is never shown: it can carry server detail. The digest is a hash that
// matches the server's log line for it.
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorScreen
      code="500"
      title="Something went wrong"
      reference={error.digest}
      actions={
        <>
          <Button onClick={reset}>Try again</Button>
          <Link href="/projects" className={buttonClasses("secondary")}>
            Projects
          </Link>
        </>
      }
    >
      This page failed to load. Try again, or go back to your projects.
    </ErrorScreen>
  );
}
