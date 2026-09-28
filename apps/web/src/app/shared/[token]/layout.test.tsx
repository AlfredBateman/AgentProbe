import { expect, test } from "vitest";
import { metadata } from "./layout";

test("a shared run link is never indexed", () => {
  expect(metadata.robots).toEqual({ index: false, follow: false });
});
