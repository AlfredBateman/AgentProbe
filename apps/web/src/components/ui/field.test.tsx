import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { expect, test } from "vitest";
import { Input, Select, Textarea } from "./field";

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
  expect(input.className).toContain("bg-surface-1");
});

test("Textarea and Select render native controls", () => {
  render(
    <>
      <Textarea aria-label="YAML" defaultValue="cases: []" />
      <Select aria-label="Agent" defaultValue="b">
        <option value="a">support-bot</option>
        <option value="b">rag-bot</option>
      </Select>
    </>,
  );
  expect((screen.getByLabelText("YAML") as HTMLTextAreaElement).value).toBe("cases: []");
  expect((screen.getByLabelText("Agent") as HTMLSelectElement).value).toBe("b");
});
