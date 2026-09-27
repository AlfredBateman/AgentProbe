import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { Dialog } from "./dialog";

function Harness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Revoke key</button>
      <Dialog
        open={open}
        title="Revoke API key?"
        onClose={() => {
          onClose();
          setOpen(false);
        }}
      >
        CI jobs using it will fail.
      </Dialog>
    </>
  );
}

const dialog = () => screen.getByRole("dialog", { hidden: true }) as HTMLDialogElement;

test("opens as a labelled modal and closes once from the close button", () => {
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  expect(dialog().open).toBe(false);
  fireEvent.click(screen.getByText("Revoke key"));
  expect(dialog().open).toBe(true);
  expect(dialog().getAttribute("aria-labelledby")).toBe(screen.getByText("Revoke API key?").id);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(dialog().open).toBe(false);
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("Escape (the native close event) calls onClose", () => {
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  fireEvent.click(screen.getByText("Revoke key"));
  dialog().close(); // what the browser does on Escape
  expect(onClose).toHaveBeenCalledTimes(1);
});
