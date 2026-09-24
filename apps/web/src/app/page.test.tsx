import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import Home from "./page";

test("home page names the product", () => {
  expect(renderToStaticMarkup(<Home />)).toContain("AgentProbe");
});
