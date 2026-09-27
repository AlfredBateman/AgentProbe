# 0026: No MCP tool-description injection scan

Status: accepted (2026-09-27, user decision). Amends PLAN.md §2 #13.

## Context
PLAN.md §2 #13 resolved "an MCP server has no chat input" with two parts:
1. `call: {tool, arguments}` cases whose tool result is judged;
2. "an automatic scan of tool descriptions for injected instructions".

C3 built only the first part (ADR 0023). The scan stayed in PROGRESS.md's Next section as a
follow-up.

[POSITIONING.md](../POSITIONING.md) §4 has since fixed what the MCP adapter is: one adapter type,
so AgentProbe can point at more kinds of targets. It is explicitly not an MCP-security scanner.
Auditing `list_tools()` output for embedded instructions is a static security scan of the server
itself. It has nothing to do with regression-testing the server's behavior:
- it makes no calls;
- it doesn't vary from run to run, so the statistics have nothing to do;
- it has no baseline to regress against.

That is the product POSITIONING.md §4 says AgentProbe isn't. Dedicated MCP scanners already
cover it, and competing there means competing on scanner rule coverage, which is breadth again.

## Decision
The tool-description injection scan is out of scope. PLAN.md §2 #13's resolution is only the
`call:` case shape and judging the tool result. MCP stays one adapter type among HTTP and Python.

A suite can still test what an injected description would cause. The attack surface an MCP
server exposes shows up in what its tools *do* when called, and `call:` cases with rule or
`llm_rubric` judges regression-test that like any other case.

## Consequences
- PLAN.md §2 #13 and the C3 row are amended to point here. The item is removed from
  PROGRESS.md's Next section.
- The MCP adapter still calls `list_tools()`, as `test_connection`'s reachability probe. Nothing
  inspects the descriptions it returns.
- If AgentProbe's positioning ever widens to MCP security, this is where to revisit. The scan
  would be a new, separate feature, not a missing piece of C3.
