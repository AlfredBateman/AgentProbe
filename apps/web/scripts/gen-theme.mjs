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

const textVars = (name, t) => [
  `  --text-${name}: ${t.fontSize};`,
  `  --text-${name}--line-height: ${t.lineHeight};`,
  `  --text-${name}--letter-spacing: ${t.letterSpacing};`,
  `  --text-${name}--font-weight: ${t.fontWeight};`,
];

export function generate(tokens = readTokens()) {
  const { colors, typography, fonts } = tokens;
  const theme = [];
  for (const [name, value] of Object.entries(colors)) theme.push(`  --color-${name}: ${value};`);

  theme.push("");
  for (const [name, value] of Object.entries(tokens.rounded)) theme.push(`  --radius-${name}: ${value};`);

  // Spacing is a px scale (ADR 0042): p-15 is 15px. Tailwind resolves max-w-md from
  // --spacing-md before --container-md, so DESIGN.md's names can't be emitted as-is.
  for (const [name, value] of Object.entries(tokens.spacing)) {
    if (!/^\d+px$/.test(String(value))) throw new Error(`spacing.${name} = ${value} is not a whole px value`);
  }
  theme.push("", "  --spacing: 1px;");

  theme.push("");
  for (const [name, t] of Object.entries(typography)) theme.push(...textVars(name, t));

  theme.push("");
  for (const [name, value] of Object.entries(tokens.motion.easing)) theme.push(`  --ease-${name}: ${value};`);

  // DESIGN.md "Responsive Behavior": tablet at 810px, desktop at 1199px.
  theme.push("", "  --breakpoint-tablet: 810px;", "  --breakpoint-desktop: 1199px;");

  // Tailwind has no theme namespace for these, so they are plain custom properties.
  const root = [
    ...Object.entries(tokens.borders).map(([name, value]) => `  --border-${name}: ${value};`),
    ...Object.entries(tokens.zIndex).map(([name, value]) => `  --z-${name}: ${value};`),
    ...Object.entries(tokens.motion.duration).map(([name, value]) => `  --duration-${name}: ${value};`),
  ];

  // One class per type tier: a tier is a family, a case and a width as much as a size.
  const utilities = Object.entries(typography).map(([name, t]) => {
    const font = Object.keys(fonts).find((key) => fonts[key] === t.fontFamily);
    if (!font) throw new Error(`typography.${name}: DESIGN.md's fonts has no ${t.fontFamily}`);
    const rules = [
      `font-family: var(--font-${font})`,
      `font-size: ${t.fontSize}`,
      `font-weight: ${t.fontWeight}`,
      `line-height: ${t.lineHeight}`,
      `letter-spacing: ${t.letterSpacing}`,
      `text-transform: ${t.textTransform ?? "none"}`,
      ...(t.wordSpacing ? [`word-spacing: ${t.wordSpacing}`] : []),
      ...(t.fontStretch ? [`font-stretch: ${t.fontStretch}`] : []),
    ];
    return `@utility type-${name} {\n${rules.map((r) => `  ${r};`).join("\n")}\n}\n`;
  });

  return [
    "/* Generated from DESIGN.md by scripts/gen-theme.mjs. Do not edit. */",
    `@theme {\n${theme.join("\n")}\n}\n`,
    `:root {\n${root.join("\n")}\n}\n`,
    ...utilities,
  ].join("\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(OUTPUT, generate());
  console.log(`wrote ${OUTPUT}`);
}
