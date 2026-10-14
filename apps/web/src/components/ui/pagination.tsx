import { cx } from "@/lib/cx";

type Props = {
  /** 1-based. */
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  /** Names the landmark when a page has more than one. */
  label?: string;
  className?: string;
};

/** The pages to show: the first, the last, and one either side of the current one; `"gap"` stands for a run of skipped pages. */
export function pageWindow(page: number, pageCount: number): (number | "gap")[] {
  const wanted = new Set([1, pageCount, page - 1, page, page + 1].filter((p) => p >= 1 && p <= pageCount));
  const pages = [...wanted].sort((a, b) => a - b);
  return pages.flatMap((p, i) => (i > 0 && p - pages[i - 1] > 1 ? ["gap" as const, p] : [p]));
}

const item =
  "inline-flex h-40 min-w-40 cursor-pointer items-center justify-center border px-8 type-data transition-[background-color,border-color,color] duration-120 ease-linear " +
  "motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-50 pointer-coarse:h-44 pointer-coarse:min-w-44";

export function Pagination({ page, pageCount, onPageChange, label = "Pagination", className }: Props) {
  const current = Math.min(Math.max(page, 1), Math.max(pageCount, 1));
  return (
    <nav aria-label={label} className={className}>
      <ul className="flex flex-wrap items-center gap-4">
        <li>
          <button
            type="button"
            aria-label="Previous page"
            disabled={current <= 1}
            onClick={() => onPageChange(current - 1)}
            className={cx(item, "border-hairline-strong text-ink hover:border-ink")}
          >
            <span aria-hidden>{"<"}</span>
          </button>
        </li>
        {pageWindow(current, pageCount).map((p, i) =>
          p === "gap" ? (
            <li key={`gap-${i}`} aria-hidden className="px-4 type-data text-ink-muted">
              …
            </li>
          ) : (
            <li key={p}>
              <button
                type="button"
                aria-label={`Page ${p}`}
                aria-current={p === current ? "page" : undefined}
                onClick={() => onPageChange(p)}
                className={cx(item, p === current ? "border-accent text-accent" : "border-hairline text-ink-muted hover:border-ink hover:text-ink")}
              >
                {p}
              </button>
            </li>
          ),
        )}
        <li>
          <button
            type="button"
            aria-label="Next page"
            disabled={current >= pageCount}
            onClick={() => onPageChange(current + 1)}
            className={cx(item, "border-hairline-strong text-ink hover:border-ink")}
          >
            <span aria-hidden>{">"}</span>
          </button>
        </li>
      </ul>
    </nav>
  );
}
