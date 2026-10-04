"""The attack ids a suite may name in `Case.attack`, with their category.

An attack id classifies an author-written case (its literal `input` or `call`); nothing generates
payloads from it (ADR 0027). The schema validates `Case.attack` against these keys, and the suite
editor can offer them for autocomplete.
"""

ATTACKS: dict[str, str] = {
    "prompt_injection.direct": "prompt_injection",
    "prompt_injection.indirect": "prompt_injection",
    "jailbreak.roleplay": "jailbreak",
    "jailbreak.hypothetical": "jailbreak",
    "jailbreak.developer_mode": "jailbreak",
    "extraction.repeat": "extraction",
    "extraction.translate": "extraction",
    "extraction.summarize": "extraction",
    "leakage.secrets": "leakage",
    "leakage.pii": "leakage",
    "tool_misuse": "tool_misuse",
    "tool_misuse.unauthorized_call": "tool_misuse",
    "tool_misuse.argument_tampering": "tool_misuse",
    "tool_misuse.excessive_agency": "tool_misuse",
    "scope_drift.off_topic": "scope_drift",
}
