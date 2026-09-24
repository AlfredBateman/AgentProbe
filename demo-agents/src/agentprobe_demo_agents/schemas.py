"""Shared request/response models.

Support and vulnerable share one flat response shape (`ChatResponse`). RAG deliberately uses
a different, nested shape (`RagResponse`) so the future HTTP adapter's dotted-path response
mapping is genuinely exercised against more than one layout (PLAN.md ambiguity #12).
"""

from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    input: str
    context: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any]


class ChatResponse(BaseModel):
    output: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    steps: list[dict[str, str]] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=lambda: {"total_tokens": 0})


class RagResponse(BaseModel):
    result: dict[str, Any]
    meta: dict[str, Any]
