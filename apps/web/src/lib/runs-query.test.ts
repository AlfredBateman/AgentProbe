import { expect, test } from "vitest";
import { apiQuery, DEFAULT_QUERY, fromTableSort, parseRunsQuery, rangeText, runsSearch, tableSort } from "./runs-query";

test("the default view has a bare URL, and a URL round-trips", () => {
  expect(runsSearch(DEFAULT_QUERY)).toBe("");
  const q = { suite: "s1", status: "failed", branch: "feature/x", sort: "pass_rate", order: "asc", page: 3 } as const;
  const search = runsSearch(q);
  expect(search).toBe("?suite=s1&status=failed&branch=feature%2Fx&sort=pass_rate&order=asc&page=3");
  expect(parseRunsQuery(new URLSearchParams(search))).toEqual(q);
});

test("anything unknown in the URL falls back to the default instead of reaching the API", () => {
  expect(parseRunsQuery(new URLSearchParams("status=done&sort=secret&order=up&page=-2"))).toEqual(DEFAULT_QUERY);
  expect(parseRunsQuery(new URLSearchParams("page=2.5")).page).toBe(1);
});

test("the API query pages by 25 and leaves out empty filters", () => {
  expect(apiQuery({ ...DEFAULT_QUERY, page: 3 })).toEqual({ limit: 25, offset: 50, sort: "created_at", order: "desc" });
  expect(apiQuery({ ...DEFAULT_QUERY, suite: "s", status: "running", branch: "  main " })).toMatchObject({
    suite_id: "s",
    status: "running",
    branch: "main",
  });
});

test("the table's sort and the API's convert both ways", () => {
  const q = { ...DEFAULT_QUERY, sort: "cost", order: "asc" } as const;
  expect(tableSort(q)).toEqual({ key: "cost", direction: "ascending" });
  expect(fromTableSort({ key: "latency", direction: "descending" })).toEqual({ sort: "latency", order: "desc" });
});

test("the range line counts the page against the total", () => {
  expect(rangeText(1, 25, 312)).toBe("1–25 of 312");
  expect(rangeText(13, 12, 312)).toBe("301–312 of 312");
  expect(rangeText(1, 0, 0)).toBeNull();
});
