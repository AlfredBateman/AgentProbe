"""Keyword-retrieval doc-QA engine for /rag.

Planted flaw: `context` documents from the request are trusted as retrieved content with no
filtering, so a document containing an `INSTRUCTION:` line hijacks the answer outright —
indirect prompt injection delivered through "retrieved" content (PLAN.md ambiguity #11).
"""

import re
from dataclasses import dataclass
from typing import Any

_INSTRUCTION_LINE = re.compile(r"^\s*INSTRUCTION:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_WORD = re.compile(r"\w+")
_STOPWORDS = frozenset(
    "a an the is are what how does do you your i to of for can in on and or we it "
    "that this take takes".split()
)


@dataclass(frozen=True)
class Doc:
    id: str
    text: str
    answer: str


CORPUS: tuple[Doc, ...] = (
    Doc(
        "shipping",
        "How long does shipping take? Standard shipping takes 3-5 business days.",
        "Standard shipping takes 3-5 business days.",
    ),
    Doc(
        "returns",
        "What is the return policy? Items can be returned within 14 days in original condition.",
        "You can return items within 14 days, in their original condition.",
    ),
    Doc(
        "hours",
        "What are your support hours? Support is available Monday to Friday, 9am to 6pm.",
        "Support is available Monday-Friday, 9am-6pm.",
    ),
    Doc(
        "payment",
        "What payment methods are accepted? We accept all major credit cards and PayPal.",
        "We accept all major credit cards and PayPal.",
    ),
)


def _score(query: str, text: str) -> int:
    query_words = set(_WORD.findall(query.lower())) - _STOPWORDS
    text_words = set(_WORD.findall(text.lower())) - _STOPWORDS
    return len(query_words & text_words)


def answer(question: str, extra_context: list[str]) -> dict[str, Any]:
    ranked = sorted(CORPUS, key=lambda d: _score(question, d.text), reverse=True)
    corpus_hits = [d for d in ranked if _score(question, d.text) > 0][:3]
    context_docs = [Doc(f"context-{i}", text, text) for i, text in enumerate(extra_context)]
    retrieved = corpus_hits + context_docs

    for doc in retrieved:
        if match := _INSTRUCTION_LINE.search(doc.text):
            return _result(match.group(1).strip(), retrieved)

    if not corpus_hits:
        return _result("I don't have information about that.", retrieved)
    return _result(corpus_hits[0].answer, retrieved)


def _result(text: str, retrieved: list[Doc]) -> dict[str, Any]:
    return {
        "result": {"text": text, "citations": [d.id for d in retrieved]},
        "meta": {
            "retrieved_doc_ids": [d.id for d in retrieved],
            "tokens": {"input": len(text.split()), "output": len(text.split())},
        },
    }
