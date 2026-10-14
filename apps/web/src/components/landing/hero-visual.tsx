"use client";

import { useEffect, useRef } from "react";
import { REDUCE_ATTR } from "@/lib/motion/core";

type Device<T> = {
  reducedMotion: boolean;
  /** The viewport width, in CSS px. */
  width: number;
  /** navigator.hardwareConcurrency; undefined where the browser does not say. */
  cores: number | undefined;
  /** Asked last, because it makes a WebGL context: the context, or null if there is none. */
  webgl: () => T | null;
};

/**
 * Whether the hero gets the 3D grid: the WebGL probe's result if so, else null. No on reduced
 * motion, on a small screen (under 600px), on a device with two cores or fewer, and without
 * WebGL2 (three needs it). On a no the static figure stays and three is never loaded.
 */
export function wants3D<T>({ reducedMotion, width, cores, webgl }: Device<T>): T | null {
  if (reducedMotion || width < 600) return null;
  if (cores !== undefined && cores <= 2) return null;
  return webgl();
}

/** A WebGL2 context on a new canvas, made the way the scene wants it, so three can reuse both. */
function probeWebGL() {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("webgl2", { alpha: false, antialias: true, powerPreference: "low-power" });
  return context && { canvas, context };
}

/**
 * The hero's illustrative figure: a square-dot SVG, which the 3D grid covers where the device
 * can take it. The box's size comes from its aspect ratio alone, so neither moves anything.
 */
export function HeroVisual({ className }: { className: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    const track = el?.closest("section");
    if (!el || !track) return;
    const probe = wants3D({
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.hasAttribute(REDUCE_ATTR),
      width: window.innerWidth,
      cores: navigator.hardwareConcurrency || undefined,
      webgl: probeWebGL,
    });
    if (!probe) return;
    let unmount: (() => void) | undefined;
    let gone = false;
    import("./hero-scene")
      .then(({ mountScene }) => {
        if (!gone) unmount = mountScene({ ...probe, host: el, track });
      })
      .catch(() => {}); // the static figure is still there
    return () => {
      gone = true;
      // Before the scene took it over, the probe's context is released here.
      if (unmount) unmount();
      else probe.context.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, []);

  return (
    <div aria-hidden className={className}>
      <svg viewBox="0 0 320 240" className="block size-full">
        <defs>
          <pattern id="hero-dots" width="16" height="16" patternUnits="userSpaceOnUse">
            <rect x="7" y="7" width="2" height="2" fill="currentColor" />
          </pattern>
        </defs>
        <rect width="320" height="240" fill="url(#hero-dots)" />
      </svg>
      <div ref={host} data-testid="hero-3d" className="absolute inset-0 empty:hidden" />
      {/* On the bottom edge. Below 810px the headline's last line reaches it, so there the label
          is the caption row under the figure (Fig. 01 /// Illustrative), which is always shown. */}
      <p className="absolute bottom-0 left-8 hidden translate-y-1/2 border border-hairline-strong bg-canvas px-4 py-2 type-micro text-ink-muted tablet:block">
        Illustrative
      </p>
    </div>
  );
}
