import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { CodeBlock, CopyButton, PlainText, safeJson, visibleText } from "./code";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
}

const PAYLOAD = '<img src=x onerror="alert(1)"><script>alert(2)</script>';

test("untrusted output renders as literal text, never as HTML", () => {
  const { container } = render(<CodeBlock code={PAYLOAD} label="output" />);
  expect(container.querySelector("img, script")).toBeNull();
  expect(container.querySelector("code")!.textContent).toBe(PAYLOAD);
});

test("PlainText is literal text too, in a samp by default and a kbd for typed input", () => {
  const { container, rerender } = render(<PlainText text={PAYLOAD} />);
  expect(container.querySelector("img, script")).toBeNull();
  expect(container.querySelector("pre > samp")!.textContent).toBe(PAYLOAD);
  rerender(<PlainText text={PAYLOAD} as="kbd" />);
  expect(container.querySelector("pre > kbd")!.textContent).toBe(PAYLOAD);
  expect(container.querySelector("script")).toBeNull();
});

test("verbatim text is never case-changed by its type class", () => {
  const { container } = render(<PlainText text="Refund-Outside-Window" />);
  expect(container.querySelector("samp")!.className).toContain("type-code"); // type-code is text-transform: none
});

test("CodeBlock's scrolling code is reachable by keyboard", () => {
  const { container } = render(<CodeBlock code="a: 1" as="samp" />);
  const pre = container.querySelector("pre")!;
  expect(pre.tabIndex).toBe(0);
  expect(pre.querySelector("samp")!.textContent).toBe("a: 1");
});

test("PlainText cuts a long value and toggles the rest in with an aria-expanded button", () => {
  render(<PlainText text={"x".repeat(30)} limit={10} />);
  const toggle = screen.getByRole("button", { name: /Show full \(30 characters\)/ });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(screen.getByText(`${"x".repeat(10)}…`)).toBeTruthy();
  fireEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Show less" }).getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("x".repeat(30))).toBeTruthy();
});

test("copy succeeds, announces, and resets after 2 s", async () => {
  vi.useFakeTimers();
  const writeText = vi.fn(() => Promise.resolve());
  stubClipboard(writeText);
  render(<CopyButton text="ap_example" />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
  expect(writeText).toHaveBeenCalledWith("ap_example");
  expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  expect(screen.getByText("Copied", { selector: "[aria-live]" })).toBeTruthy();
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
});

test("a rejected or missing clipboard says so", async () => {
  stubClipboard(() => Promise.reject(new Error("denied")));
  render(<CopyButton text="x" />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
  expect(screen.getByRole("button", { name: "Copy failed" })).toBeTruthy();
});

test("a long line wraps in the block and the copy button still holds all of it", async () => {
  const long = `pip install "agentprobe-core @ git+https://github.com/example/repo@v0.1.0#subdirectory=packages/core" ${"x".repeat(300)}`;
  const writeText = vi.fn(() => Promise.resolve());
  stubClipboard(writeText);
  const { container } = render(<CodeBlock code={long} />);
  const pre = container.querySelector("pre")!;
  expect(pre.className).toContain("whitespace-pre-wrap");
  expect(pre.className).toContain("break-words");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
  expect(writeText).toHaveBeenCalledWith(long);
});

test("a body replaces the read-only text inside the same frame, and the footer sits under it", () => {
  const { container } = render(
    <CodeBlock code="suite: a" label="suite.yaml" body={<textarea aria-label="edit" defaultValue="suite: a" />} footer={<p>2 problems</p>} invalid />,
  );
  expect(container.querySelector("pre")).toBeNull();
  expect(screen.getByRole("textbox", { name: "edit" })).toBeTruthy();
  expect(container.querySelector("figure")!.className).toContain("border-fail");
  expect(container.querySelector("figure")!.lastElementChild!.textContent).toBe("2 problems");
  expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
});

describe("visibleText and safeJson", () => {
  test("controls and bidi overrides become visible stand-ins; tabs, newlines and emoji stay", () => {
    expect(visibleText("\u001b[31mred\u001b[0m")).toBe("␛[31mred␛[0m");
    expect(visibleText("a\u0000b\u0007c\u007fd\u009be")).toBe("a␀b␇c␡d⟨U+009B⟩e");
    expect(visibleText("pay‮txt.exe ⁦x⁩ ‏")).toBe("pay⟨U+202E⟩txt.exe ⟨U+2066⟩x⟨U+2069⟩ ⟨U+200F⟩");
    expect(visibleText("line 1\n\tline 2 👩‍💻 é")).toBe("line 1\n\tline 2 👩‍💻 é");
  });

  test("safeJson is the same value, with nothing raw left that could steer a terminal or a reader", () => {
    const value = { "a‮b": ["\u001b[2J", "\u009b31m", "ok\n"], n: 1, nil: null };
    const text = safeJson(value);
    expect(JSON.parse(text)).toEqual(value);
    expect(text).not.toMatch(/[\u0000-\u0009\u000B-\u001F\u0080-\u009F‪-‮]/);
    expect(safeJson(undefined)).toBe("null");
  });

  test("a code block shows the stand-ins and copies them", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    stubClipboard(writeText);
    const { container } = render(<CodeBlock code={"echo \u001b]0;pwned\u0007"} label="Shell" />);
    expect(container.querySelector("pre")?.textContent).toBe("echo ␛]0;pwned␇");
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("echo ␛]0;pwned␇"));
  });
});
