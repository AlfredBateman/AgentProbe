import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { REDUCE_ATTR } from "@/lib/motion/core";
import { HeroVisual, wants3D } from "./hero-visual";

const mountScene = vi.fn<(options: unknown) => () => void>(() => teardown);
const teardown = vi.fn();
vi.mock("./hero-scene", () => ({ mountScene }));

const desktop = { reducedMotion: false, width: 1440, cores: 8 };

describe("wants3D", () => {
  test("a capable desktop gets the scene, with the probe's context", () => {
    expect(wants3D({ ...desktop, webgl: () => "ctx" })).toBe("ctx");
    expect(wants3D({ ...desktop, width: 600, webgl: () => "ctx" })).toBe("ctx");
    expect(wants3D({ ...desktop, cores: 3, webgl: () => "ctx" })).toBe("ctx");
    expect(wants3D({ ...desktop, cores: undefined, webgl: () => "ctx" })).toBe("ctx"); // the browser does not say
  });

  test.each([
    ["reduced motion", { reducedMotion: true }],
    ["a screen under 600px", { width: 599 }],
    ["two cores", { cores: 2 }],
    ["one core", { cores: 1 }],
  ])("%s keeps the static figure without making a WebGL context", (_, override) => {
    const webgl = vi.fn(() => "ctx");
    expect(wants3D({ ...desktop, ...override, webgl })).toBeNull();
    expect(webgl).not.toHaveBeenCalled();
  });

  test("no WebGL2 keeps the static figure", () => {
    expect(wants3D({ ...desktop, webgl: () => null })).toBeNull();
  });
});

describe("HeroVisual", () => {
  const fakeContext = { getExtension: () => null };
  function setup({ reduce = false, webgl = true } = {}) {
    window.matchMedia = ((query: string) => ({ matches: reduce && query.includes("reduce") })) as unknown as typeof window.matchMedia;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue((webgl ? fakeContext : null) as never);
    return render(
      <section>
        <HeroVisual className="box" />
      </section>,
    );
  }

  afterEach(() => {
    vi.restoreAllMocks();
    mountScene.mockClear();
    teardown.mockClear();
    document.documentElement.removeAttribute(REDUCE_ATTR);
  });

  test("mounts the scene into its box, tracking the hero section, and tears it down on unmount", async () => {
    const { container, unmount } = setup();
    await waitFor(() => expect(mountScene).toHaveBeenCalledOnce());
    const options = mountScene.mock.calls[0][0] as { context: unknown; host: Element; track: Element };
    expect(options.context).toBe(fakeContext);
    expect(options.host).toBe(container.querySelector('[data-testid="hero-3d"]'));
    expect(options.track).toBe(container.querySelector("section"));
    unmount();
    expect(teardown).toHaveBeenCalledOnce();
  });

  test.each([
    ["the OS asks for reduced motion", { reduce: true }],
    ["there is no WebGL2", { webgl: false }],
  ])("when %s, the static figure stays and three is never loaded", async (_, options) => {
    const { container } = setup(options);
    await new Promise((resolve) => setTimeout(resolve, 20)); // long enough for a dynamic import to land
    expect(mountScene).not.toHaveBeenCalled();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.textContent).toBe("Illustrative");
  });

  test("the reduced-motion dev switch counts as reduced motion", async () => {
    document.documentElement.setAttribute(REDUCE_ATTR, "");
    setup();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mountScene).not.toHaveBeenCalled();
  });
});
