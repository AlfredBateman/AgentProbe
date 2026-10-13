"use client";

import { useEffect, useRef } from "react";

/**
 * The hero's backdrop loop, self-hosted. It has no `autoplay` attribute: playback starts here,
 * and only when motion is allowed, so with reduced motion (or without JS) the poster stays.
 */
export function HeroVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = ref.current;
    if (!video || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    video.play().catch(() => {}); // refused (data saver, low power): the poster stays
  }, []);
  return (
    <video
      ref={ref}
      src="/hero.mp4"
      poster="/hero-poster.webp"
      width={1154}
      height={720}
      muted
      loop
      playsInline
      preload="metadata"
      disablePictureInPicture
      aria-hidden="true"
      tabIndex={-1}
    />
  );
}
