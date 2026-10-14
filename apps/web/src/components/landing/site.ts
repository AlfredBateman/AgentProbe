import pkg from "../../../package.json";

// The release the page advertises is the app's own package version, never a typed one.
export const VERSION: string = pkg.version;
export const TAG = `v${VERSION}`;
/** The SPDX id in package.json, which is where the LICENSE file at the repo root is named. */
export const LICENSE: string = pkg.license;

export const REPO = "https://github.com/AlfredBateman/AgentProbe";
/** `owner/name`, as a workflow's `uses:` spells it. */
export const REPO_SLUG = new URL(REPO).pathname.slice(1);
export const OWNER = REPO_SLUG.split("/")[0];

// The CLI, a run, and the Action, all at the current release tag. The same lines are in README.md.
const pip = (name: string, dir: string) => `"${name} @ git+${REPO}@${TAG}#subdirectory=packages/${dir}"`;
export const INSTALL = [
  `pip install ${pip("agentprobe-core", "core")} ${pip("agentprobe", "cli")}`,
  "agentprobe run suites/regression.yaml",
  `- uses: ${REPO_SLUG}/action@${TAG}`,
].join("\n");

/**
 * Where "Try the demo" goes: NEXT_PUBLIC_DEMO_URL, a share link to a seeded run. A same-origin
 * path or an https URL; anything else (unset, a typo, another scheme) means no demo link.
 */
export function demoUrl(raw = process.env.NEXT_PUBLIC_DEMO_URL): string | undefined {
  const url = raw?.trim();
  return url && /^(\/(?!\/)|https:\/\/)/.test(url) ? url : undefined;
}
