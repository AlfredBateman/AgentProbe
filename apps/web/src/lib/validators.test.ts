import { expect, test } from "vitest";
import { emailError, loginPasswordError, newPasswordError, requiredError } from "./validators";

test.each(["", "  ", "not-an-email", "missing-at.com", "no-domain@x", "spaces in@it.com"])(
  "%s is an invalid email",
  (value) => {
    expect(emailError(value)).not.toBeNull();
  },
);

test("a plausible email passes", () => {
  expect(emailError("alice@example.com")).toBeNull();
});

test("login requires only a non-empty password", () => {
  expect(loginPasswordError("")).not.toBeNull();
  expect(loginPasswordError("x")).toBeNull();
});

test("registration requires 12-128 characters", () => {
  expect(newPasswordError("short")).toContain("at least 12");
  expect(newPasswordError("x".repeat(129))).toContain("at most 128");
  expect(newPasswordError("x".repeat(12))).toBeNull();
  expect(newPasswordError("x".repeat(128))).toBeNull();
});

test("requiredError trims whitespace-only input", () => {
  expect(requiredError("   ", "Name")).toBe("Name is required.");
  expect(requiredError("demo", "Name")).toBeNull();
});
