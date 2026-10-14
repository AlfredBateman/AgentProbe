import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import ErrorPage from "@/app/error";
import NotFound from "@/app/not-found";

test("404 names the problem and offers the way out", () => {
  render(<NotFound />);
  expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Projects" }).getAttribute("href")).toBe("/projects");
  expect(screen.getByRole("link", { name: "Home" }).getAttribute("href")).toBe("/");
});

test("500 retries on request and shows only the digest, never the error's message", () => {
  const reset = vi.fn();
  const error = Object.assign(new Error("connection to db-internal.example refused"), { digest: "abc123" });
  render(<ErrorPage error={error} reset={reset} />);
  expect(screen.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeTruthy();
  expect(screen.getByText("Ref abc123")).toBeTruthy();
  expect(document.body.textContent).not.toContain("db-internal");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledOnce();
});

test("500 without a digest shows no reference line", () => {
  render(<ErrorPage error={new Error("boom")} reset={() => {}} />);
  expect(screen.queryByText(/^Ref /)).toBeNull();
});
