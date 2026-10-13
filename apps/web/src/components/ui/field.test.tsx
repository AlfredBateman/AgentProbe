import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { expect, test } from "vitest";
import { Checkbox, FieldError, Input, Label, Select, Switch, Textarea } from "./field";

test("Input forwards props and ref, and styles the invalid state", () => {
  const ref = createRef<HTMLInputElement>();
  render(
    <label>
      Agent URL
      <Input ref={ref} aria-invalid defaultValue="http://" />
    </label>,
  );
  const input = screen.getByLabelText("Agent URL");
  expect(ref.current).toBe(input);
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(input.className).toContain("aria-invalid:border-fail");
  expect(input.className).toContain("border-hairline-strong"); // a control's edge is at least 3:1
  expect(input.className).toContain("type-code"); // typed text is data: never uppercased
});

test("Textarea and Select render native controls with their roles", () => {
  render(
    <>
      <Textarea aria-label="YAML" defaultValue="cases: []" />
      <Select aria-label="Agent" defaultValue="b">
        <option value="a">support-bot</option>
        <option value="b">rag-bot</option>
      </Select>
    </>,
  );
  expect((screen.getByRole("textbox", { name: "YAML" }) as HTMLTextAreaElement).value).toBe("cases: []");
  expect((screen.getByRole("combobox", { name: "Agent" }) as HTMLSelectElement).value).toBe("b");
});

test("every field is focusable, and a disabled one is not", () => {
  render(
    <>
      <Input aria-label="Name" />
      <Input aria-label="Locked" disabled />
    </>,
  );
  const name = screen.getByRole("textbox", { name: "Name" });
  name.focus();
  expect(document.activeElement).toBe(name);
  expect((screen.getByRole("textbox", { name: "Locked" }) as HTMLInputElement).disabled).toBe(true);
});

test("Checkbox is a native checkbox that toggles from its label", () => {
  render(
    <label>
      <Checkbox defaultChecked={false} />
      Include flaky cases
    </label>,
  );
  const box = screen.getByRole("checkbox", { name: "Include flaky cases" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  fireEvent.click(screen.getByText("Include flaky cases"));
  expect(box.checked).toBe(true);
  expect(box.className).toContain("checked:bg-ink"); // checked is ink, never a lime fill
  expect(box.className).not.toContain("bg-accent");
});

test("Switch has the switch role and flips with a click", () => {
  render(
    <label>
      <Switch />
      Mock LLM
    </label>,
  );
  const toggle = screen.getByRole("switch", { name: "Mock LLM" }) as HTMLInputElement;
  expect(toggle.checked).toBe(false);
  fireEvent.click(toggle);
  expect(toggle.checked).toBe(true);
  toggle.focus();
  expect(document.activeElement).toBe(toggle);
});

test("Label shows an optional mono caption", () => {
  render(
    <>
      <Label htmlFor="n">Runs per case</Label>
      <Label htmlFor="m" caption="optional">
        Notes
      </Label>
    </>,
  );
  expect(screen.getByText("Runs per case").tagName).toBe("LABEL");
  expect(screen.getByText("optional").className).toContain("type-micro");
});

test("FieldError renders the message linked to its id, or nothing at all", () => {
  const { rerender } = render(<FieldError id="email-error">Enter a valid email address.</FieldError>);
  expect(screen.getByText("Enter a valid email address.").id).toBe("email-error");
  rerender(<FieldError id="email-error">{null}</FieldError>);
  expect(screen.queryByText("Enter a valid email address.")).toBeNull();
});
