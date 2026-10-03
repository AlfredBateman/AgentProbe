// The agent form's model (E3): a flat draft of every field the form edits, built from a stored
// config and turned back into one. `configFrom` spreads the stored config first, so a field the
// form doesn't know about survives an edit instead of being reset to a default.

export type AdapterType = "http" | "mcp";
type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
type StoredConfig = Record<string, unknown>;

export type Draft = {
  name: string;
  adapterType: AdapterType;
  url: string;
  allowPrivate: boolean;
  /** One `Name: value` per line; plain headers only (secrets go in the auth header). */
  headers: string;
  timeoutMs: string;
  maxRetries: string;
  // HTTP only
  method: "POST" | "PUT" | "PATCH";
  template: string;
  followRedirects: boolean;
  output: string;
  toolCalls: string;
  toolName: string;
  toolArguments: string;
  inputTokens: string;
  outputTokens: string;
  totalTokens: string;
};

const DEFAULT_TEMPLATE = { input: "{{input}}", documents: "{{documents}}" };

// Defaults match the bundled demo agents, so pointing a new agent at one just works.
const NEW: Draft = {
  name: "",
  adapterType: "http",
  url: "",
  allowPrivate: true,
  headers: "",
  timeoutMs: "30000",
  maxRetries: "2",
  method: "POST",
  template: JSON.stringify(DEFAULT_TEMPLATE, null, 2),
  followRedirects: false,
  output: "$.output",
  toolCalls: "$.tool_calls",
  toolName: "$.tool",
  toolArguments: "$.arguments",
  inputTokens: "",
  outputTokens: "",
  totalTokens: "$.usage.total_tokens",
};

const str = (v: unknown, fallback = "") => (typeof v === "string" ? v : fallback);

export function draftFrom(agent?: { name: string; adapter_type: string; config: StoredConfig }): Draft {
  if (!agent) return { ...NEW };
  const c = agent.config;
  const response = (c.response ?? {}) as Record<string, unknown>;
  const headers = (c.headers ?? {}) as Record<string, string>;
  return {
    name: agent.name,
    adapterType: agent.adapter_type === "mcp" ? "mcp" : "http",
    url: str(c.url),
    allowPrivate: c.allow_private === true,
    headers: Object.entries(headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n"),
    timeoutMs: String(c.timeout_ms ?? 30000),
    maxRetries: String(c.max_retries ?? 2),
    method: (["POST", "PUT", "PATCH"] as const).find((m) => m === c.method) ?? "POST",
    template: JSON.stringify(c.request_template ?? DEFAULT_TEMPLATE, null, 2),
    followRedirects: c.follow_redirects === true,
    output: str(response.output, "$.output"),
    toolCalls: str(response.tool_calls),
    toolName: str(response.tool_name, "$.tool"),
    toolArguments: str(response.tool_arguments, "$.arguments"),
    inputTokens: str(response.input_tokens),
    outputTokens: str(response.output_tokens),
    totalTokens: str(response.total_tokens),
  };
}

export type FieldErrors = Partial<Record<"name" | "url" | "headers" | "template" | "timeoutMs" | "maxRetries", string>>;

export function parseHeaders(text: string): Record<string, string> | string {
  const headers: Record<string, string> = {};
  for (const [i, line] of text.split("\n").entries()) {
    if (!line.trim()) continue;
    const colon = line.indexOf(":");
    if (colon < 1) return `Line ${i + 1}: write it as Name: value`;
    headers[line.slice(0, colon).trim()] = line.slice(colon + 1).trim();
  }
  return headers;
}

function wholeNumber(text: string, min: number, max: number): number | null {
  const n = Number(text);
  return text.trim() !== "" && Number.isInteger(n) && n >= min && n <= max ? n : null;
}

/** The config the API stores, or the errors that stop it being built. The server validates
 * again (header rules, URL schemes, the template's `{{input}}`); these are the quick ones. */
export function configFrom(draft: Draft, stored?: { adapter_type: string; config: StoredConfig }): { config?: Record<string, Json>; errors: FieldErrors } {
  const errors: FieldErrors = {};
  if (!draft.name.trim()) errors.name = "Name is required.";
  if (!draft.url.trim()) errors.url = "URL is required.";
  const headers = parseHeaders(draft.headers);
  if (typeof headers === "string") errors.headers = headers;
  const timeout = wholeNumber(draft.timeoutMs, 1, 120_000);
  if (timeout === null) errors.timeoutMs = "A whole number of milliseconds, 1 to 120000.";
  const retries = wholeNumber(draft.maxRetries, 0, 5);
  if (retries === null) errors.maxRetries = "A whole number from 0 to 5.";

  let template: Json = null;
  if (draft.adapterType === "http") {
    try {
      template = JSON.parse(draft.template) as Json;
      if (!JSON.stringify(template).includes("{{input}}")) errors.template = "The template must contain {{input}}.";
    } catch {
      errors.template = "Not valid JSON.";
    }
  }
  if (Object.keys(errors).length) return { errors };

  // Same adapter type: keep every stored field the form doesn't show. Switching type: start clean.
  const base = (stored?.adapter_type === draft.adapterType ? stored.config : {}) as Record<string, Json>;
  const common = {
    url: draft.url.trim(),
    headers: headers as Record<string, string>,
    timeout_ms: timeout!,
    max_retries: retries!,
    allow_private: draft.allowPrivate,
  };
  if (draft.adapterType === "mcp") {
    return { config: { ...base, adapter_type: "mcp", transport: "http", ...common }, errors };
  }
  const orNull = (s: string) => s.trim() || null;
  return {
    config: {
      ...base,
      adapter_type: "http",
      ...common,
      method: draft.method,
      request_template: template,
      follow_redirects: draft.followRedirects,
      response: {
        ...((base.response ?? {}) as Record<string, Json>),
        output: draft.output.trim() || "$.output",
        tool_calls: orNull(draft.toolCalls),
        tool_name: draft.toolName.trim() || "$.tool",
        tool_arguments: draft.toolArguments.trim() || "$.arguments",
        input_tokens: orNull(draft.inputTokens),
        output_tokens: orNull(draft.outputTokens),
        total_tokens: orNull(draft.totalTokens),
      },
    },
    errors,
  };
}
