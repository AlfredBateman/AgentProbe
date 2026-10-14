import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { differingSteps, type Trace, Timeline, VerdictPanel } from "./timeline";

const XSS = `<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">x</a>**bold** [link](javascript:alert(4))`;

function trace(over: Partial<Trace> = {}): Trace {
  return {
    run_id: "11111111-2222-3333-4444-555555555555",
    case: "api-key-leak",
    attempt: 0,
    status: "failed",
    input: XSS,
    output: `Sure, our internal API key is AP-CANARY-APIKEY51D8F0A3C2. ${XSS}`,
    error: null,
    latency_ms: 12,
    tokens: null,
    cost_usd: null,
    judge_cost_usd: 0,
    retries: 0,
    steps: [
      { type: "message", role: "user", content: XSS, timestamp: "2026-09-28T10:00:00Z", duration_ms: null },
      { type: "tool_call", tool: "lookup<b>", arguments: { q: XSS }, timestamp: "2026-09-28T10:00:00.010Z", duration_ms: 3 },
      { type: "tool_result", tool: "lookup<b>", result: { rows: [XSS] }, timestamp: "2026-09-28T10:00:00.013Z" },
      {
        type: "message",
        role: "assistant",
        content: `Sure, our internal API key is AP-CANARY-APIKEY51D8F0A3C2. ${XSS}`,
        timestamp: "2026-09-28T10:00:00.020Z",
        duration_ms: 8,
      },
    ],
    judgments: [
      { judge: "not_contains", status: "fail", score: 0, reason: `output contains 'AP-CANARY' ${XSS}`, step: 3 },
      { judge: "llm_rubric", status: "pass", score: 1, reason: "refused", step: 3 },
      { judge: "latency_under", status: "pass", score: 1, reason: "12 ms", step: null },
    ],
    ...over,
  };
}

test("untrusted content renders as literal text: no HTML, no links, no markdown", () => {
  const { container } = render(<Timeline trace={trace()} compact={false} />);
  expect(container.querySelector("img, script, a, b, strong, iframe")).toBeNull();
  expect(container.innerHTML).not.toContain("<img");
  expect(container.innerHTML).not.toContain("<script");
  // The payload is all there, character for character: raw in the user message, the reply and
  // the judge's reason, and as a JSON string in the tool arguments and result.
  const texts = [...container.querySelectorAll("pre")].map((pre) => pre.textContent ?? "");
  expect(texts.filter((t) => t.includes(XSS))).toHaveLength(3);
  expect(texts.filter((t) => t.includes(JSON.stringify(XSS)))).toHaveLength(2);
  // A tool name is data: shown verbatim, in code type, never parsed.
  expect(screen.getAllByText("lookup<b>")[0].className).toContain("type-code");
});

// Every way agent output could try to be more than text: markup, event handlers, markdown,
// entities, terminal escapes (CSI, OSC 8 hyperlinks, an 8-bit CSI) and a bidi override.
const PAYLOADS = {
  script: "<script>window.__pwned = 1</script>",
  img: `<img src=x onerror="window.__pwned = 2">`,
  svg: "<svg onload=window.__pwned=3><circle r=9 /></svg>",
  link: `<a href="javascript:window.__pwned=4">click</a>`,
  markdown: "**bold** _em_ [link](javascript:alert(4)) ![x](https://evil.example/x.png)\n# Heading\n```js\nalert(1)\n```",
  entity: "&lt;b&gt;not bold&lt;/b&gt; &amp;",
  ansi: "\u001b[31mRED\u001b[0m \u001b]8;;https://evil.example\u0007click\u001b]8;;\u0007 \u009b2J\u0000",
  bidi: "invoice‮fdp.exe ⁦isolate⁩",
};
const ALL = Object.values(PAYLOADS).join("\n");
const RAW_CONTROL = /[\u0000-\u0008\u000B-\u001F\u007F-\u009F‪-‮⁦-⁩]/;

function hostile(): Trace {
  return trace({
    case: PAYLOADS.img,
    input: ALL,
    output: ALL,
    error: PAYLOADS.ansi,
    steps: [
      { type: "message", role: "user", content: ALL },
      { type: "tool_call", tool: PAYLOADS.svg, arguments: { q: ALL, [PAYLOADS.link]: PAYLOADS.bidi } },
      { type: "tool_result", tool: PAYLOADS.bidi, result: [ALL, { nested: PAYLOADS.ansi }] },
      { type: "error", message: ALL },
    ],
    judgments: [
      { judge: "not_contains", status: "fail", score: 0, reason: ALL, step: 0 },
      { judge: "llm_rubric", status: "pass", score: 1, reason: PAYLOADS.markdown, step: null },
    ],
  });
}

describe("hostile trace text", () => {
  beforeEach(() => {
    delete (window as { __pwned?: number }).__pwned;
  });

  function renderBoth() {
    const t = hostile();
    return render(
      <>
        <Timeline trace={t} compact={false} layout="narrow" />
        <VerdictPanel trace={t} />
      </>,
    );
  }

  test("creates no element, attribute or link from the text", () => {
    const { container } = renderBoth();
    expect(container.querySelector("script, img, iframe, object, embed, b, strong, em, h1, code[class*=language]")).toBeNull();
    // The only svgs are the copy buttons' own icons, with no handler on anything.
    for (const el of container.querySelectorAll("*")) {
      expect([...el.attributes].filter((a) => a.name.startsWith("on"))).toEqual([]);
    }
    for (const a of container.querySelectorAll("a")) expect(a.getAttribute("href")).toMatch(/^#step-\d+$/);
    expect((window as { __pwned?: number }).__pwned).toBeUndefined();
  });

  test("shows markup, markdown and entities exactly as written", () => {
    const { container } = renderBoth();
    const text = container.textContent ?? "";
    for (const p of [PAYLOADS.script, PAYLOADS.img, PAYLOADS.svg, PAYLOADS.link, PAYLOADS.entity, "**bold**", "# Heading", "```js"]) {
      expect(text).toContain(p);
    }
    expect(text).not.toContain("<b>not bold</b>"); // the entity is not decoded either
  });

  test("terminal escapes and bidi overrides become visible, inert stand-ins", () => {
    const { container } = renderBoth();
    const text = container.textContent ?? "";
    expect(text).not.toMatch(RAW_CONTROL);
    expect(text).toContain("␛[31mRED␛[0m");
    expect(text).toContain("␛]8;;https://evil.example␇click");
    expect(text).toContain("⟨U+009B⟩2J␀");
    expect(text).toContain("invoice⟨U+202E⟩fdp.exe ⟨U+2066⟩isolate⟨U+2069⟩");
  });

  test("copy puts the inert text on the clipboard, never the raw escapes", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderBoth();
    for (const button of screen.getAllByRole("button", { name: /^Copy step/ })) fireEvent.click(button);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(4));
    const copied = writeText.mock.calls.map((call) => (call as unknown as [string])[0]);
    for (const text of copied) expect(text).not.toMatch(RAW_CONTROL);
    expect(copied[0]).toContain("␛[31mRED");
    expect(copied[0]).toContain(PAYLOADS.script);
  });
});

test("the verdict panel lists every verdict with its step, score and kind", () => {
  render(<VerdictPanel trace={trace()} />);
  expect(screen.getByText("2 of 3 passed")).toBeTruthy();
  const items = within(screen.getByRole("list", { name: "Judge verdicts" })).getAllByRole("listitem");
  expect(items).toHaveLength(3);
  expect(within(items[0]).getByRole("link", { name: "Step 4" }).getAttribute("href")).toBe("#step-3");
  expect(within(items[0]).getByText("Rule")).toBeTruthy();
  expect(within(items[1]).getByText("LLM judge")).toBeTruthy();
  expect(within(items[2]).getByText("Whole attempt")).toBeTruthy();
});

test("a verdict sits with the step it concerns; rule and LLM verdicts say which they are", () => {
  render(<Timeline trace={trace()} compact={false} />);
  const steps = within(screen.getByRole("list", { name: "Trace steps" })).getAllByRole("listitem");
  const leak = steps.filter((li) => li.parentElement?.getAttribute("aria-label") === "Trace steps")[3];
  expect(within(leak).getByText(/AP-CANARY-APIKEY51D8F0A3C2/, { selector: "pre > samp" })).toBeTruthy();

  const verdicts = within(leak).getByRole("list", { name: "Verdicts on step 4" });
  const [rule, llm] = within(verdicts).getAllByRole("listitem");
  expect(within(rule).getByText("not_contains")).toBeTruthy();
  expect(within(rule).getByText("Fail")).toBeTruthy();
  expect(within(rule).getByText("Rule")).toBeTruthy();
  expect(within(llm).getByText("LLM judge")).toBeTruthy();
  expect(llm.className).toContain("border-dashed");
  expect(rule.className).not.toContain("border-dashed");

  const whole = screen.getByRole("list", { name: "Verdicts on the whole attempt" });
  expect(within(whole).getByText("latency_under")).toBeTruthy();
  expect(screen.queryByRole("list", { name: "Verdicts on step 1" })).toBeNull();
});

test("steps show their timing, and compact mode closes every step but keeps each openable", () => {
  const { container } = render(<Timeline trace={trace()} compact />);
  const details = [...container.querySelectorAll("details")];
  expect(details.every((d) => !d.open)).toBe(true);
  expect(screen.getByText(/\+10 ms · 3 ms/)).toBeTruthy();
  expect(screen.getAllByText(/no timing/)).toHaveLength(2);
  fireEvent.click(details[3].querySelector("summary")!);
  expect(details[3].open).toBe(true);
});

test("huge values are cut, with a control to show them in full", () => {
  const huge = "A".repeat(5000);
  const { container } = render(
    <Timeline trace={trace({ steps: [{ type: "message", role: "assistant", content: huge }], judgments: [] })} compact={false} />,
  );
  const pre = container.querySelector("pre")!;
  expect(pre.textContent).toHaveLength(2001); // 2000 characters and an ellipsis
  const toggle = screen.getByRole("button", { name: "Show full (5,000 characters)" });
  fireEvent.click(toggle);
  expect(pre.textContent).toBe(huge);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
});

test("steps differ on content, never on timing, and a missing step differs", () => {
  const a = trace().steps;
  const b = a.map((s) => ({ ...s, timestamp: "2030-01-01T00:00:00Z", duration_ms: 999 }));
  expect(differingSteps(a, b)).toEqual(new Set());
  b[3] = { ...b[3], type: "message", role: "assistant", content: "I can't share that." };
  expect(differingSteps(a, b.slice(0, 4))).toEqual(new Set([3]));
  expect(differingSteps(a, b.slice(0, 2))).toEqual(new Set([2, 3]));

  const { container } = render(<Timeline trace={trace()} compact={false} layout="narrow" differs={new Set([3])} />);
  expect(screen.getAllByText("Differs")).toHaveLength(1);
  expect(container.querySelectorAll("details")[3].className).toContain("bg-surface-2");
});

test("an attempt the agent never answered says so", () => {
  render(<Timeline trace={trace({ steps: [], judgments: [] })} compact={false} />);
  expect(screen.getByText("No trace: the agent never answered.")).toBeTruthy();
});
