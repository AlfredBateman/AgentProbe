"""Loads support-bot prompt files and derives policy facts from their text, so the mock
engine has no hardcoded policy of its own — editing the prompt file genuinely changes
behavior in both AGENT_MODE=mock and AGENT_MODE=llm.
"""

import re
from pathlib import Path

_REFUND_WINDOW = re.compile(r"within (\d+) days", re.IGNORECASE)
DEFAULT_REFUND_WINDOW_DAYS = 30


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def refund_window_days(prompt_text: str) -> int:
    match = _REFUND_WINDOW.search(prompt_text)
    return int(match.group(1)) if match else DEFAULT_REFUND_WINDOW_DAYS
