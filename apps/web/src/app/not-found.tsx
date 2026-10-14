import Link from "next/link";
import { ErrorScreen } from "@/components/shell/error-screen";
import { buttonClasses } from "@/components/ui/button";

export default function NotFound() {
  return (
    <ErrorScreen
      code="404"
      title="Page not found"
      actions={
        <>
          <Link href="/projects" className={buttonClasses("primary")}>
            Projects
          </Link>
          <Link href="/" className={buttonClasses("secondary")}>
            Home
          </Link>
        </>
      }
    >
      There is nothing at this address. It may have moved, or the link may be wrong.
    </ErrorScreen>
  );
}
