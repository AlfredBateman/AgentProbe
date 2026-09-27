// Generates src/app/theme.css from DESIGN.md's front matter. Run: pnpm --filter web gen:theme
// theme.test.ts fails when the committed file differs from a fresh generation.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const DESIGN = fileURLToPath(new URL("../../../DESIGN.md", import.meta.url));
export const OUTPUT = fileURLToPath(new URL("../src/app/theme.css", import.meta.url));

export function readTokens(path = DESIGN) {
  const match = readFileSync(path, "utf8").match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) throw new Error(`${path}: no YAML front matter`);
  return parse(match[1]);
}

export function generate(tokens = readTokens()) {
  const lines = [];
  for (const [name, value] of Object.entries(tokens.colors)) lines.push(`  --color-${name}: ${value};`);
  // Result aliases (ADR 0028): components say what a color means, not which hue it is.
  for (const [alias, token] of [
    ["pass", "semantic-success"],
    ["fail", "semantic-danger"],
    ["flaky", "semantic-warning"],
    ["neutral", "semantic-neutral"],
  ]) {
    if (!(token in tokens.colors)) throw new Error(`DESIGN.md has no colors.${token}`);
    lines.push(`  --color-${alias}: var(--color-${token});`);
  }

  lines.push("");
  for (const [name, value] of Object.entries(tokens.rounded)) lines.push(`  --radius-${name}: ${value};`);

  // Spacing is a px scale (ADR 0028): p-15 is 15px. Tailwind resolves max-w-md from
  // --spacing-md before --container-md, so DESIGN.md's names can't be emitted as-is.
  for (const [name, value] of Object.entries(tokens.spacing)) {
    if (!/^\d+px$/.test(String(value))) throw new Error(`spacing.${name} = ${value} is not a whole px value`);
  }
  lines.push("", "  --spacing: 1px;");

  lines.push("");
  for (const [name, t] of Object.entries(tokens.typography)) {
    lines.push(
      `  --text-${name}: ${t.fontSize};`,
      `  --text-${name}--line-height: ${t.lineHeight};`,
      `  --text-${name}--letter-spacing: ${t.letterSpacing};`,
      `  --text-${name}--font-weight: ${t.fontWeight};`,
    );
  }

  // DESIGN.md "Responsive Behavior": tablet at 810px, desktop at 1199px.
  lines.push("", "  --breakpoint-tablet: 810px;", "  --breakpoint-desktop: 1199px;");
  return `/* Generated from DESIGN.md by scripts/gen-theme.mjs. Do not edit. */\n@theme {\n${lines.join("\n")}\n}\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(OUTPUT, generate());
  console.log(`wrote ${OUTPUT}`);
}
