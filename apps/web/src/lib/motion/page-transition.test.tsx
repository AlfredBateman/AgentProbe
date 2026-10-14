import { act, render, waitFor } from "@testing-library/react";
import gsap from "gsap";
import { Suspense, use } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { contentSecurityPolicy } from "@/proxy";
import { PageTransition } from "./page-transition";

const nav = vi.hoisted(() => ({ pathname: "/projects" as string | null }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

/** Makes `(prefers-reduced-motion: reduce)` true or false, as the OS setting would. */
function setReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("no-preference") ? !reduce : reduce,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

const tweens = () => gsap.globalTimeline.getChildren(true, true, true);
const finish = () => act(() => tweens().forEach((t) => t.progress(1)));

beforeEach(() => {
  nav.pathname = "/projects";
  setReducedMotion(false);
  // The clock stays still: a 400 ms wipe on a loaded machine would otherwise finish, and leave
  // the timeline, before the test looked. `finish()` moves it by hand.
  gsap.globalTimeline.pause();
});
afterEach(() => {
  gsap.globalTimeline.clear();
  gsap.globalTimeline.resume();
});

describe("PageTransition in a layout, which never remounts", () => {
  test("skips the page already on screen, then wipes each pathname change without remounting", () => {
    const { container, rerender } = render(
      <PageTransition>
        <p>page one</p>
      </PageTransition>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    const child = wrapper.firstElementChild;
    expect(tweens()).toHaveLength(0);

    nav.pathname = "/projects/p1";
    rerender(
      <PageTransition>
        <p>page one</p>
      </PageTransition>,
    );
    expect(tweens()).toHaveLength(1);
    expect(wrapper.style.clipPath).not.toBe(""); // starts clipped, before paint
    finish();
    expect(wrapper.style.clipPath).toBe("");
    expect(container.firstElementChild).toBe(wrapper); // the same node: state and focus survive
    expect(wrapper.firstElementChild).toBe(child);
  });

  test("a render that keeps the pathname, such as a search-param change, does not wipe", () => {
    const { rerender } = render(<PageTransition>a</PageTransition>);
    rerender(<PageTransition>b</PageTransition>);
    expect(tweens()).toHaveLength(0);
  });

  test("a leaving wipe is reverted when the next navigation starts, never left clipped", () => {
    const { container, rerender } = render(<PageTransition>a</PageTransition>);
    const wrapper = container.firstElementChild as HTMLElement;
    for (const path of ["/projects/p1", "/projects/p1/runs"]) {
      nav.pathname = path;
      rerender(<PageTransition>a</PageTransition>);
    }
    expect(tweens()).toHaveLength(1); // the first was reverted, not stacked
    finish();
    expect(wrapper.getAttribute("style") ?? "").not.toMatch(/clip-path|transform|will-change/);
  });

  test("is plain markup under reduced motion", () => {
    setReducedMotion(true);
    const { container, rerender } = render(<PageTransition>a</PageTransition>);
    nav.pathname = "/projects/p1";
    rerender(<PageTransition>a</PageTransition>);
    expect(container.innerHTML).toBe("<div>a</div>");
    expect(tweens()).toHaveLength(0);
  });

  test("does not animate without a pathname", () => {
    nav.pathname = null;
    const { rerender } = render(<PageTransition>a</PageTransition>);
    nav.pathname = "/projects";
    rerender(<PageTransition>a</PageTransition>);
    expect(tweens()).toHaveLength(0);
  });
});

describe("streaming and the CSP", () => {
  function Late({ promise }: { promise: Promise<string> }) {
    return <p>{use(promise)}</p>;
  }

  test("a Suspense boundary inside keeps streaming through a wipe in progress", async () => {
    let resolve!: (text: string) => void;
    const promise = new Promise<string>((r) => (resolve = r));
    const tree = (
      <PageTransition>
        <Suspense fallback={<i>loading</i>}>
          <Late promise={promise} />
        </Suspense>
      </PageTransition>
    );
    const { container, rerender } = render(<PageTransition>previous page</PageTransition>);
    const wrapper = container.firstElementChild as HTMLElement;
    nav.pathname = "/projects/p1/runs";
    await act(async () => rerender(tree)); // suspends: React wants the act awaited
    expect(wrapper.textContent).toBe("loading");
    expect(tweens()).toHaveLength(1);

    await act(async () => resolve("streamed rows")); // arrives while the wipe is still running
    await waitFor(() => expect(wrapper.textContent).toBe("streamed rows"));
    finish();
    expect(container.firstElementChild).toBe(wrapper);
    expect(wrapper.style.clipPath).toBe(""); // nothing stays hidden
  });

  test("it injects no script or style element, and the policy allows what it does write", () => {
    const { container, rerender } = render(<PageTransition>a</PageTransition>);
    nav.pathname = "/projects/p1";
    rerender(<PageTransition>a</PageTransition>);
    finish();
    expect(container.querySelector("script, style, link")).toBeNull();
    expect(document.head.querySelector("script[data-gsap], style[data-gsap]")).toBeNull();

    const policy = contentSecurityPolicy("abc", false);
    const directive = (name: string) => policy.split("; ").find((d) => d.startsWith(`${name} `)) ?? "";
    // The wipe is an inline style set through the CSSOM: style-src covers it, script-src is untouched.
    expect(directive("style-src")).toContain("'unsafe-inline'");
    expect(directive("script-src")).not.toContain("'unsafe-inline'");
    expect(directive("script-src")).not.toContain("'unsafe-eval'");
  });
});
