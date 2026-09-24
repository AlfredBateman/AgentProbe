"""In-process agents for the CLI tests (`type: python` in agentprobe.yaml)."""


def good(input: str) -> str:
    return f"ok: {input}"


def bad(input: str) -> str:
    return "nope"


def hostile(input: str) -> str:
    # Rich markup and a terminal escape sequence in an error message the report prints: it
    # must show the markup literally and drop the escape.
    raise RuntimeError("[bold red]PWNED[/bold red]\x1b[2J")


def with_tools(input: str) -> dict[str, object]:
    return {
        "output": "ok: deleted",
        "steps": [{"type": "tool_call", "tool": "delete_order", "arguments": {"id": "1"}}],
    }
