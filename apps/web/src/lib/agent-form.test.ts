import { describe, expect, it } from "vitest";
import { configFrom, draftFrom, parseHeaders } from "./agent-form";

// An HTTP agent as the API stores it, with fields the form never shows (a custom template,
// plain headers, and a field from a newer adapter version).
const stored = {
  name: "support",
  adapter_type: "http",
  config: {
    url: "https://agent.example.com/chat",
    method: "PUT",
    headers: { "X-Team": "qa" },
    request_template: { messages: [{ role: "user", content: "{{input}}" }] },
    response: { output: "$.reply", tool_calls: "$.calls", tool_name: "$.n", tool_arguments: "$.a", total_tokens: null, future_path: "$.x" },
    timeout_ms: 5000,
    max_retries: 1,
    follow_redirects: true,
    allow_private: false,
    some_future_field: 7,
  },
};

describe("draftFrom / configFrom", () => {
  it("round-trips a stored HTTP agent without losing anything the form doesn't show", () => {
    const { config, errors } = configFrom(draftFrom(stored), stored);
    expect(errors).toEqual({});
    expect(config).toEqual({
      ...stored.config,
      adapter_type: "http",
      response: { ...stored.config.response, input_tokens: null, output_tokens: null },
    });
  });

  it("applies edits on top of the stored config", () => {
    const draft = { ...draftFrom(stored), url: "https://other.example.com/v2", headers: "X-Team: ops\nX-Env: staging" };
    const { config } = configFrom(draft, stored);
    expect(config).toMatchObject({ url: "https://other.example.com/v2", headers: { "X-Team": "ops", "X-Env": "staging" }, some_future_field: 7 });
  });

  it("builds an MCP config, dropping HTTP-only fields when the type changes", () => {
    const draft = { ...draftFrom(stored), adapterType: "mcp" as const, url: "https://mcp.example.com/mcp" };
    const { config } = configFrom(draft, stored);
    expect(config).toEqual({
      adapter_type: "mcp",
      transport: "http",
      url: "https://mcp.example.com/mcp",
      headers: { "X-Team": "qa" },
      timeout_ms: 5000,
      max_retries: 1,
      allow_private: false,
    });
  });

  it("a new agent defaults to the demo agents' shape", () => {
    const draft = { ...draftFrom(), name: "demo", url: "http://127.0.0.1:9000/support/v1/chat" };
    const { config } = configFrom(draft);
    expect(config).toMatchObject({
      adapter_type: "http",
      method: "POST",
      allow_private: true,
      request_template: { input: "{{input}}", documents: "{{documents}}" },
      response: { output: "$.output", tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" },
    });
  });

  it("reports every field it can't build", () => {
    const draft = { ...draftFrom(), template: "{not json", headers: "no colon here", timeoutMs: "0", maxRetries: "9" };
    expect(configFrom(draft).errors).toEqual({
      name: "Name is required.",
      url: "URL is required.",
      headers: "Line 1: write it as Name: value",
      template: "Not valid JSON.",
      timeoutMs: "A whole number of milliseconds, 1 to 120000.",
      maxRetries: "A whole number from 0 to 5.",
    });
    const noInput = { ...draftFrom(), name: "a", url: "https://a.example.com", template: '{"q": "hi"}' };
    expect(configFrom(noInput).errors).toEqual({ template: "The template must contain {{input}}." });
  });
});

describe("parseHeaders", () => {
  it("reads Name: value lines, skipping blanks and keeping colons in values", () => {
    expect(parseHeaders("A: 1\n\nB: http://x:8080 ")).toEqual({ A: "1", B: "http://x:8080" });
    expect(parseHeaders(": nameless")).toBe("Line 1: write it as Name: value");
  });
});
