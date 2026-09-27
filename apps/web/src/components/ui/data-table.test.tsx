import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { type Column, DataTable } from "./data-table";

type Row = { id: string; name: string; rate: number | null };
const rows: Row[] = [
  { id: "a", name: "case-10", rate: 0.8 },
  { id: "b", name: "case-2", rate: 1 },
  { id: "c", name: "case-1", rate: 0.8 },
  { id: "d", name: "case-3", rate: null },
];
const columns: Column<Row>[] = [
  { key: "name", header: "Case", value: (r) => r.name },
  { key: "rate", header: "Pass rate", value: (r) => r.rate, align: "right" },
  { key: "note", header: "Note", render: () => "-" },
];

const order = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent);

test("unsorted rows keep their order", () => {
  render(<DataTable caption="Cases" columns={columns} rows={rows} rowKey={(r) => r.id} />);
  expect(order()).toEqual(["case-10", "case-2", "case-1", "case-3"]);
});

test("strings sort naturally; a second click reverses; aria-sort follows", () => {
  render(<DataTable caption="Cases" columns={columns} rows={rows} rowKey={(r) => r.id} />);
  fireEvent.click(screen.getByRole("button", { name: "Case" }));
  expect(order()).toEqual(["case-1", "case-2", "case-3", "case-10"]);
  expect(screen.getByRole("columnheader", { name: "Case" }).getAttribute("aria-sort")).toBe("ascending");
  expect(screen.getByRole("columnheader", { name: "Pass rate" }).getAttribute("aria-sort")).toBe("none");
  fireEvent.click(screen.getByRole("button", { name: "Case" }));
  expect(order()).toEqual(["case-10", "case-3", "case-2", "case-1"]);
  expect(screen.getByRole("columnheader", { name: "Case" }).getAttribute("aria-sort")).toBe("descending");
});

test("numbers sort numerically, ties keep their order, nulls go last", () => {
  render(<DataTable caption="Cases" columns={columns} rows={rows} rowKey={(r) => r.id} />);
  fireEvent.click(screen.getByRole("button", { name: "Pass rate" }));
  expect(order()).toEqual(["case-10", "case-1", "case-2", "case-3"]);
});

test("unsortable columns have no button; the table is tabular and has a sticky header", () => {
  render(<DataTable caption="Cases" columns={columns} rows={rows} rowKey={(r) => r.id} />);
  expect(screen.queryByRole("button", { name: "Note" })).toBeNull();
  expect(screen.getByRole("table").className).toContain("tabular-nums");
  expect(screen.getByRole("columnheader", { name: "Note" }).className).toContain("sticky");
});

test("empty rows show the empty slot", () => {
  render(<DataTable caption="Cases" columns={columns} rows={[]} rowKey={(r) => r.id} empty={<p>No runs yet</p>} />);
  expect(screen.getByText("No runs yet")).toBeTruthy();
});
