import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has neither matchMedia nor media playback; browsers do. Motion is allowed by default.
if (typeof window !== "undefined") {
  window.matchMedia ??= (media: string) =>
    ({ matches: false, media, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList;
  HTMLMediaElement.prototype.play = async () => {};
}

// jsdom has <dialog> but not its modal API; browsers do.
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
