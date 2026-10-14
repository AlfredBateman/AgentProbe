import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { YamlEditor } from "./yaml-editor";

const YAML = "suite: demo\nagent: a\nruns_per_case: 99\n";

test("the text is a textarea's value, so markup in it is never parsed", () => {
  const payload = '<img src=x onerror="alert(1)">\nsuite: demo';
  const { container } = render(<YamlEditor value={payload} onChange={() => {}} />);
  expect(container.querySelector("img")).toBeNull();
  expect((screen.getByRole("textbox", { name: "YAML" }) as HTMLTextAreaElement).value).toBe(payload);
});

test("typing reports the new text", () => {
  const onChange = vi.fn();
  render(<YamlEditor value={YAML} onChange={onChange} />);
  fireEvent.change(screen.getByRole("textbox", { name: "YAML" }), { target: { value: "suite: other" } });
  expect(onChange).toHaveBeenCalledWith("suite: other");
});

test("the gutter numbers every line and is hidden from assistive technology", () => {
  render(<YamlEditor value={YAML} onChange={() => {}} />);
  const gutter = screen.getByRole("textbox", { name: "YAML" }).previousElementSibling!;
  expect(gutter.getAttribute("aria-hidden")).toBe("true");
  // Three lines and the empty one after the final newline.
  expect([...gutter.firstElementChild!.children].map((n) => n.textContent)).toEqual(["1", "2", "3", "4"]);
});

test("an issue marks its line, is listed inside the frame, and jumps to the line", () => {
  const issues = [
    { line: 3, path: null, message: "runs_per_case: Input should be less than or equal to 20" },
    { line: null, path: "cases", message: "List should have at least 1 item" },
  ];
  const { container } = render(<YamlEditor value={YAML} onChange={() => {}} issues={issues} invalid />);

  const area = screen.getByRole("textbox", { name: "YAML" }) as HTMLTextAreaElement;
  expect(area.getAttribute("aria-invalid")).toBe("true");
  const list = screen.getByTestId("suite-issues");
  expect(area.getAttribute("aria-describedby")).toBe(list.id);
  expect(container.querySelector("figure")!.contains(list)).toBe(true);
  expect(container.querySelector("figure")!.className).toContain("border-fail");

  const marked = [...container.querySelectorAll("[aria-hidden] .text-fail")];
  expect(marked.map((n) => n.textContent)).toEqual(["3"]);

  expect(list.textContent).toContain("cases: List should have at least 1 item");
  fireEvent.click(screen.getByRole("button", { name: /^Line 3: runs_per_case/ }));
  expect(document.activeElement).toBe(area);
  expect(YAML.slice(area.selectionStart, area.selectionEnd)).toBe("runs_per_case: 99");
});

test("a valid document has no issue list and no red", () => {
  const { container } = render(<YamlEditor value={YAML} onChange={() => {}} />);
  expect(screen.queryByTestId("suite-issues")).toBeNull();
  expect(container.querySelector("figure")!.className).not.toContain("border-fail");
  expect(screen.getByRole("textbox", { name: "YAML" }).getAttribute("aria-invalid")).toBe("false");
});
