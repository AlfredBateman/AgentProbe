"use client";

import { Fragment, type ReactNode, useId, useState } from "react";
import { cx } from "@/lib/cx";
import { ChevronDownIcon, SortIcon } from "./icons";

export type Column<T> = {
  key: string;
  header: string;
  /** The sort key; columns without one aren't sortable. */
  value?: (row: T) => number | string | null;
  /** Cell content; defaults to `value`. */
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Extra classes on the column's cells, e.g. `hidden desktop:table-cell` to drop it on narrow screens. */
  className?: string;
};

type Sort = { key: string; direction: "ascending" | "descending" };

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
  initialSort?: Sort;
  empty?: ReactNode;
  /** Set a max height here to get a vertically scrolling body with a sticky header. */
  className?: string;
  /** Detail shown under a row when its toggle is open; `expandLabel` names the row for the toggle. */
  expand?: (row: T) => ReactNode;
  expandLabel?: (row: T) => string;
};

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function compare(a: number | string | null, b: number | string | null): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1; // nulls last
  return typeof a === "number" && typeof b === "number" ? a - b : collator.compare(String(a), String(b));
}

/** Sortable table: sticky header, tabular numerals, hairline row dividers. */
export function DataTable<T>({ columns, rows, rowKey, caption, initialSort, empty, className, expand, expandLabel }: Props<T>) {
  const [sort, setSort] = useState<Sort | undefined>(initialSort);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const baseId = useId();
  const column = columns.find((c) => c.key === sort?.key);
  const sorted =
    column?.value && sort
      ? rows.toSorted((a, b) => {
          // Array.prototype.sort is stable, so ties keep their incoming order.
          const order = compare(column.value!(a), column.value!(b));
          return sort.direction === "ascending" ? order : -order;
        })
      : rows;

  function toggle(key: string) {
    setSort((s) =>
      s?.key === key && s.direction === "ascending" ? { key, direction: "descending" } : { key, direction: "ascending" },
    );
  }

  function toggleRow(key: string) {
    setOpen((o) => {
      const next = new Set(o);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }

  const th = "sticky top-0 z-10 border-b border-hairline bg-canvas px-10 py-8 text-data-label whitespace-nowrap text-ink-muted";
  return (
    // A size container, so an expanded row's detail can be exactly as wide as what's visible.
    <div className={cx("@container min-w-0 overflow-auto", className)}>
      <table className="w-full border-collapse text-data tabular-nums">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {expand && (
              <th scope="col" className={cx(th, "w-0 pr-0")}>
                <span className="sr-only">Details</span>
              </th>
            )}
            {columns.map((c) => {
              const direction = sort?.key === c.key ? sort.direction : undefined;
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={direction ?? (c.value ? "none" : undefined)}
                  className={cx(th, c.align === "right" ? "text-right" : "text-left", c.className)}
                >
                  {c.value ? (
                    <button
                      type="button"
                      onClick={() => toggle(c.key)}
                      className={cx(
                        "inline-flex cursor-pointer items-center gap-4 rounded-xs outline-none hover:text-ink focus-visible:shadow-focus",
                        direction && "text-ink",
                        c.align === "right" && "flex-row-reverse",
                      )}
                    >
                      {c.header}
                      <SortIcon direction={direction} className="size-12" />
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => {
            const key = rowKey(row);
            const isOpen = !!expand && open.has(key);
            const detailId = `${baseId}-detail-${i}`;
            return (
              <Fragment key={key}>
                <tr className={cx("border-b border-hairline-soft last:border-0 hover:bg-surface-1", isOpen && "border-0 bg-surface-1")}>
                  {expand && (
                    <td className="py-4 pr-0 pl-8">
                      <button
                        type="button"
                        aria-expanded={isOpen}
                        aria-controls={isOpen ? detailId : undefined}
                        aria-label={`${isOpen ? "Hide" : "Show"} ${expandLabel?.(row) ?? "details"}`}
                        onClick={() => toggleRow(key)}
                        className="inline-flex size-32 cursor-pointer items-center justify-center rounded-full text-ink-muted outline-none hover:text-ink focus-visible:shadow-focus pointer-coarse:size-44"
                      >
                        <ChevronDownIcon className={cx("transition-transform motion-reduce:transition-none", isOpen ? "rotate-0" : "-rotate-90")} />
                      </button>
                    </td>
                  )}
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cx("px-10 py-10 whitespace-nowrap", c.align === "right" ? "text-right" : "text-left", c.className)}
                    >
                      {c.render ? c.render(row) : c.value?.(row)}
                    </td>
                  ))}
                </tr>
                {isOpen && (
                  <tr id={detailId} className="border-b border-hairline-soft bg-surface-1 last:border-0">
                    <td colSpan={columns.length + 1} className="p-0">
                      <div className="sticky left-0 w-[100cqw] px-12 pt-4 pb-15">{expand(row)}</div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && empty}
    </div>
  );
}
