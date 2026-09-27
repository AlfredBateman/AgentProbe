"use client";

import { type ReactNode, useState } from "react";
import { cx } from "@/lib/cx";
import { SortIcon } from "./icons";

export type Column<T> = {
  key: string;
  header: string;
  /** The sort key; columns without one aren't sortable. */
  value?: (row: T) => number | string | null;
  /** Cell content; defaults to `value`. */
  render?: (row: T) => ReactNode;
  align?: "left" | "right";
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
};

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function compare(a: number | string | null, b: number | string | null): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1; // nulls last
  return typeof a === "number" && typeof b === "number" ? a - b : collator.compare(String(a), String(b));
}

/** Sortable table: sticky header, tabular numerals, hairline row dividers. */
export function DataTable<T>({ columns, rows, rowKey, caption, initialSort, empty, className }: Props<T>) {
  const [sort, setSort] = useState<Sort | undefined>(initialSort);
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

  return (
    <div className={cx("min-w-0 overflow-auto", className)}>
      <table className="w-full border-collapse text-data tabular-nums">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const direction = sort?.key === c.key ? sort.direction : undefined;
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={direction ?? (c.value ? "none" : undefined)}
                  className={cx(
                    "sticky top-0 z-10 border-b border-hairline bg-canvas px-12 py-8 text-data-label whitespace-nowrap text-ink-muted",
                    c.align === "right" ? "text-right" : "text-left",
                  )}
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
          {sorted.map((row) => (
            <tr key={rowKey(row)} className="border-b border-hairline-soft last:border-0 hover:bg-surface-1">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cx("px-12 py-10 whitespace-nowrap", c.align === "right" ? "text-right" : "text-left")}
                >
                  {c.render ? c.render(row) : c.value?.(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && empty}
    </div>
  );
}
