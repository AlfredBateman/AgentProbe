# 0005: Trace timeline is plain HTML/CSS, not React Flow

Status: accepted (2026-09-25)

## Context
SPEC.md §6 lists React Flow for the trace-viewer timeline (§4.9). A trace, as stored (`traces.steps` JSONB), is an ordered sequence of messages, tool calls and tool results — a straight line, not a graph. React Flow is a node-and-edge graph library: it earns its weight when nodes branch, merge, or need free-form positioning, none of which a single agent's linear trace does.

## Decision
Build the trace viewer (E5) as a plain semantic HTML/CSS vertical timeline: an ordered list of step elements, each showing its role, content, tool call/result and any judge verdict inline. No graph library dependency.

## Consequences
- One fewer runtime dependency in `apps/web`; simpler accessibility story (a real `<ol>` of steps reads correctly to assistive tech, where a canvas-based graph would need bespoke ARIA work).
- If a future feature introduces genuinely branching traces (e.g., a multi-agent handoff or parallel tool-call fan-out that needs to show simultaneous branches), revisit this decision then — React Flow or a comparable graph library becomes the right tool at that point, not before.
