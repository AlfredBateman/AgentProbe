// The Runs page's state lives in its URL (filters, sort, page), so a filtered view can be shared,
// reloaded and returned to with Back. Defaults are left out: the plain /runs URL is the default view.
import type { Sort } from "@/components/ui/data-table";
import type { operations } from "./api/schema";

type Query = NonNullable<operations["list_project_runs_projects__project_id__runs_get"]["parameters"]["query"]>;
export type ApiSort = NonNullable<Query["sort"]>;
export type ApiStatus = NonNullable<Query["status"]>;

export const RUN_STATUSES: readonly ApiStatus[] = ["queued", "running", "completed", "failed", "cancelled"];
const SORTS: readonly ApiSort[] = ["created_at", "pass_rate", "cost", "latency", "suite", "status"];
export const PAGE_SIZE = 25;

export type RunsQuery = { suite: string; status: ApiStatus | ""; branch: string; sort: ApiSort; order: "asc" | "desc"; page: number };
export const DEFAULT_QUERY: RunsQuery = { suite: "", status: "", branch: "", sort: "created_at", order: "desc", page: 1 };

/** Anything unknown in the URL falls back to the default rather than reaching the API as a 422. */
export function parseRunsQuery(params: URLSearchParams): RunsQuery {
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? "";
  const page = Number(params.get("page"));
  return {
    suite: params.get("suite") ?? "",
    status: (RUN_STATUSES as readonly string[]).includes(status) ? (status as ApiStatus) : "",
    branch: params.get("branch") ?? "",
    sort: (SORTS as readonly string[]).includes(sort) ? (sort as ApiSort) : DEFAULT_QUERY.sort,
    order: params.get("order") === "asc" ? "asc" : "desc",
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

export function runsSearch(q: RunsQuery): string {
  const params = new URLSearchParams();
  for (const key of ["suite", "status", "branch", "sort", "order", "page"] as const) {
    if (q[key] !== DEFAULT_QUERY[key]) params.set(key, String(q[key]));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** The API call's query for one page. */
export function apiQuery(q: RunsQuery): Query {
  return {
    limit: PAGE_SIZE,
    offset: (q.page - 1) * PAGE_SIZE,
    sort: q.sort,
    order: q.order,
    ...(q.suite ? { suite_id: q.suite } : {}),
    ...(q.status ? { status: q.status } : {}),
    ...(q.branch.trim() ? { branch: q.branch.trim() } : {}),
  };
}

/** DataTable's column sort <-> the API's. Column keys equal the API's sort names (RunsTable's SERVER_SORT). */
export const tableSort = (q: RunsQuery): Sort => ({ key: q.sort, direction: q.order === "asc" ? "ascending" : "descending" });
export const fromTableSort = (s: Sort): Pick<RunsQuery, "sort" | "order"> => ({
  sort: s.key as ApiSort,
  order: s.direction === "ascending" ? "asc" : "desc",
});

/** "26–50 of 312", or null when there is nothing to count. */
export function rangeText(page: number, shown: number, total: number): string | null {
  if (total === 0 || shown === 0) return null;
  const first = (page - 1) * PAGE_SIZE + 1;
  return `${first.toLocaleString()}–${(first + shown - 1).toLocaleString()} of ${total.toLocaleString()}`;
}
