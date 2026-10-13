import { render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { HEADLINE, Hero } from "./hero";

afterEach(() => vi.restoreAllMocks());

const reducedMotion = (reduce: boolean) =>
  vi.spyOn(window, "matchMedia").mockImplementation(
    (media) => ({ matches: reduce && media === "(prefers-reduced-motion: reduce)", media }) as MediaQueryList,
  );

test("the headline is one real h1, named in words and drawn as the three lines", () => {
  render(<Hero />);
  expect(HEADLINE).toEqual(["MEASURE", "REGRESSION", "PROVEN"]);
  const h1 = screen.getByRole("heading", { level: 1, name: "Measure, regression, proven" });
  expect(screen.getAllByRole("heading")).toEqual([h1]);
  // The drawn lines are hidden from assistive tech, so the words are announced once.
  const lines = [...h1.children];
  expect(lines.map((line) => line.textContent)).toEqual(HEADLINE);
  expect(lines.every((line) => line.getAttribute("aria-hidden") === "true")).toBe(true);
});

test("the copy: tagline and the three services", () => {
  render(<Hero />);
  expect(screen.getByText(/Regression detection for LLM agents\./).parentElement).toHaveProperty(
    "textContent",
    "Regression detection for LLM agents. Statistically corrected, flakiness-aware. ",
  );
  const services = within(screen.getByRole("list", { name: "What AgentProbe does" })).getAllByRole("listitem");
  expect(services.map((li) => li.textContent)).toEqual([
    "Repeat every case",
    "Judge traces and tool calls",
    "Gate the pull request",
  ]);
});

test("every control is a real link to the right place", () => {
  render(<Hero />);
  const href = (name: string) => screen.getByRole("link", { name }).getAttribute("href");
  expect(href("Sign in")).toBe("/login");
  expect(href("Get started")).toBe("/register");
  expect(href("AgentProbe, home")).toBe("/");
  expect(href("GitHub")).toBe("https://github.com/AlfredBateman/AgentProbe");
  expect(href("v0.1.0")).toBe("https://github.com/AlfredBateman/AgentProbe/releases/tag/v0.1.0");
  expect(screen.queryAllByRole("button")).toEqual([]);
});

test("the video is self-hosted, silent and never autoplays by attribute", () => {
  const { container } = render(<Hero />);
  const video = container.querySelector("video")!;
  expect(video.getAttribute("src")).toBe("/hero.mp4");
  expect(video.getAttribute("poster")).toBe("/hero-poster.webp");
  expect(video.muted).toBe(true);
  expect(video.loop).toBe(true);
  expect(video.playsInline).toBe(true);
  expect(video.preload).toBe("metadata");
  expect(video.autoplay).toBe(false);
  expect(video.controls).toBe(false);
  // The box is reserved before anything loads.
  expect([video.getAttribute("width"), video.getAttribute("height")]).toEqual(["1154", "720"]);
  expect(container.innerHTML).not.toMatch(/https?:\/\/[^"]*\.(mp4|webm|webp)/); // nothing hotlinked
});

test("with motion allowed the video starts playing, muted", () => {
  reducedMotion(false);
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const { container } = render(<Hero />);
  expect(play).toHaveBeenCalledTimes(1);
  expect(container.querySelector("video")!.muted).toBe(true);
});

test("with reduced motion the video never plays: the poster stays", () => {
  reducedMotion(true);
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const { container } = render(<Hero />);
  expect(play).not.toHaveBeenCalled();
  expect(container.querySelector("video")!.getAttribute("poster")).toBe("/hero-poster.webp");
});

test("a refused autoplay is not an error", async () => {
  reducedMotion(false);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(new DOMException("blocked", "NotAllowedError"));
  render(<Hero />);
  await Promise.resolve(); // an unhandled rejection would fail the run
});
