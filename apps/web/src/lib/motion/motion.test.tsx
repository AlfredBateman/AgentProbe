import { act, render } from "@testing-library/react";
import gsap from "gsap";
import { useRef } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { REDUCE_ATTR } from "./core";
import { useCountUp, useReveal, useStagger } from "./hooks";
import { useSplitHeading } from "./split-heading";

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

/** Jumps every running or paused tween to its end, as the clock eventually would. */
const finishAll = () => act(() => gsap.globalTimeline.getChildren(true, true, true).forEach((t) => t.progress(1)));
const tweensOf = (el: Element | null) => (el ? gsap.getTweensOf(el).length : -1);

afterEach(() => {
  document.documentElement.removeAttribute(REDUCE_ATTR);
  gsap.globalTimeline.clear();
});

function Reveal() {
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref);
  return (
    <div ref={ref} data-motion="hidden" data-testid="reveal">
      Final
    </div>
  );
}

function Count({ value = 97 }: { value?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const text = useCountUp(ref, value, (n) => `${Math.round(n)}%`);
  return (
    <span ref={ref} data-testid="count">
      {text}
    </span>
  );
}

function Rows() {
  const ref = useRef<HTMLUListElement>(null);
  useStagger(ref);
  return (
    <ul ref={ref} data-testid="rows">
      <li>one</li>
      <li>two</li>
      <li>three</li>
    </ul>
  );
}

function Heading() {
  const ref = useRef<HTMLHeadingElement>(null);
  useSplitHeading(ref);
  return (
    <h1 ref={ref} data-testid="heading">
      Regressions, caught before merge
    </h1>
  );
}

describe("reduced motion", () => {
  test("every effect is in its final state at once, with nothing created", () => {
    setReducedMotion(true);
    const { getByTestId } = render(
      <>
        <Reveal />
        <Count />
        <Rows />
        <Heading />
      </>,
    );
    const reveal = getByTestId("reveal");
    expect(reveal.hasAttribute("data-motion")).toBe(false);
    expect(reveal.getAttribute("style")).toBeNull();
    expect(getByTestId("count").textContent).toBe("97%");
    for (const li of getByTestId("rows").children) expect(li.getAttribute("style")).toBeNull();
    const heading = getByTestId("heading");
    expect(heading.innerHTML).toBe("Regressions, caught before merge");
    expect(heading.hasAttribute("aria-label")).toBe(false);
    expect(gsap.globalTimeline.getChildren(true, true, true)).toHaveLength(0);
  });

  test("the dev switch forces it even when the OS allows motion", () => {
    setReducedMotion(false);
    document.documentElement.setAttribute(REDUCE_ATTR, "");
    const { getByTestId } = render(<Count />);
    expect(getByTestId("count").textContent).toBe("97%");
    expect(gsap.globalTimeline.getChildren(true, true, true)).toHaveLength(0);
  });
});

describe("motion allowed", () => {
  test("a reveal starts clipped and ends with no inline style left", () => {
    setReducedMotion(false);
    const { getByTestId } = render(<Reveal />);
    const el = getByTestId("reveal");
    expect(el.hasAttribute("data-motion")).toBe(false);
    expect(tweensOf(el)).toBe(1);
    finishAll();
    expect(el.style.clipPath).toBe("");
    expect(el.style.transform).toBe("");
    expect(el.style.willChange).toBe("");
    expect(el.textContent).toBe("Final");
  });

  test("a count starts at zero, ends on React's text, and only touches that text node", () => {
    setReducedMotion(false);
    const { getByTestId, rerender } = render(<Count value={97} />);
    const el = getByTestId("count");
    const node = el.firstChild;
    expect(el.textContent).toBe("0%");
    finishAll();
    expect(el.textContent).toBe("97%");
    rerender(<Count value={40} />);
    expect(el.textContent).toBe("40%"); // counted once; later values just show
    expect(el.firstChild).toBe(node);
  });

  test("rows stagger and are left clean", () => {
    setReducedMotion(false);
    const { getByTestId } = render(<Rows />);
    const rows = [...getByTestId("rows").children];
    expect(rows.map(tweensOf)).toEqual([1, 1, 1]);
    finishAll();
    for (const li of rows) expect(li.getAttribute("style") ?? "").not.toMatch(/clip-path|transform|will-change/);
  });

  test("unmounting kills the tweens and restores the text", () => {
    setReducedMotion(false);
    const { getByTestId, unmount } = render(
      <>
        <Count />
        <Rows />
      </>,
    );
    const count = getByTestId("count");
    const rows = [...getByTestId("rows").children];
    expect(tweensOf(count)).toBe(0); // the tween's target is the counter object, not the node
    expect(gsap.globalTimeline.getChildren(true, true, true).length).toBeGreaterThan(0);
    unmount();
    expect(rows.map(tweensOf)).toEqual([0, 0, 0]);
    expect(gsap.globalTimeline.getChildren(true, true, true)).toHaveLength(0);
    expect(count.textContent).toBe("97%");
  });
});

describe("a server-rendered heading behind the first-paint guard", () => {
  function GuardedHeading({ expired }: { expired: boolean }) {
    const ref = useRef<HTMLHeadingElement>(null);
    useSplitHeading(ref);
    // jsdom runs no CSS animations; an inline style stands in for the guard's computed clip.
    return (
      <h1 ref={ref} data-motion="hidden" data-testid="heading" style={{ clipPath: expired ? "none" : "inset(0 0 100% 0)" }}>
        Regressions
      </h1>
    );
  }

  test("still guarded: the guard comes off and the lines reveal", () => {
    setReducedMotion(false);
    const { getByTestId } = render(<GuardedHeading expired={false} />);
    expect(getByTestId("heading").hasAttribute("data-motion")).toBe(false);
    expect(gsap.globalTimeline.getChildren(true, true, true).length).toBeGreaterThan(0);
  });

  test("guard already run out on a slow load: the heading is on screen and is not revealed again", () => {
    setReducedMotion(false);
    const { getByTestId } = render(<GuardedHeading expired />);
    const heading = getByTestId("heading");
    expect(heading.hasAttribute("data-motion")).toBe(false);
    expect(heading.innerHTML).toBe("Regressions");
    expect(gsap.globalTimeline.getChildren(true, true, true)).toHaveLength(0);
  });
});

describe("page transition", () => {
  // A fresh module graph per test resets the first-mount flag; it brings its own gsap, so the
  // timeline is read from the same graph.
  async function load() {
    vi.resetModules();
    const { default: g } = await import("gsap");
    const { PageTransition } = await import("./page-transition");
    const children = () => g.globalTimeline.getChildren(true, true, true);
    return { PageTransition, children, finish: () => act(() => children().forEach((t) => t.progress(1))) };
  }

  test("skips the server-rendered first mount, then wipes in each navigation", async () => {
    setReducedMotion(false);
    const { PageTransition, children, finish } = await load();
    const first = render(<PageTransition>page one</PageTransition>);
    expect(children()).toHaveLength(0);
    await Promise.resolve(); // the first-mount flag clears in a microtask
    first.unmount();
    const second = render(<PageTransition>page two</PageTransition>);
    expect(children()).toHaveLength(1);
    finish();
    expect((second.container.firstChild as HTMLElement).style.clipPath).toBe("");
    expect(second.container.textContent).toBe("page two");
  });

  test("renders its children untouched under reduced motion", async () => {
    setReducedMotion(true);
    const { PageTransition, children } = await load();
    render(<PageTransition>first</PageTransition>).unmount();
    await Promise.resolve();
    const { container } = render(<PageTransition>second</PageTransition>);
    expect(container.innerHTML).toBe("<div>second</div>");
    expect(children()).toHaveLength(0);
  });
});
