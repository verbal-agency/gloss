from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
import uuid


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


# ---------------------------------------------------------------------------
# Individual stage request models
# ---------------------------------------------------------------------------

class NormalizeRequest(BaseModel):
    query: str


class CounterfactualRequest(BaseModel):
    query: str
    messages: list[Message] = Field(default_factory=list)


class PrecommitRequest(BaseModel):
    query: str
    messages: list[Message] = Field(default_factory=list)
    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")


class PressureTestRequest(BaseModel):
    response: str
    messages: list[Message] = Field(default_factory=list)


class InterrogateRequest(BaseModel):
    query: str
    response: str
    domain: Literal["auto", "code", "medical", "financial", "legal", "general"] = "auto"


class CheckDriftRequest(BaseModel):
    session_id: str
    turn: int


class MessagesRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int = 1024
    system: str | None = None
    temperature: float | None = None
    stream: bool = False


class SycophancyFlag(BaseModel):
    type: Literal[
        "counterfactual_divergence",
        "precommitment_inconsistency",
        "disagreement_collapse",
        "temporal_drift",
    ]
    flagged: bool
    score: float
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ResponseMeta(BaseModel):
    session_id: str
    sycophancy_flags: list[SycophancyFlag] = Field(default_factory=list)
    normalized_query: str | None = None
    signals_removed: list[str] = Field(default_factory=list)


class MessagesResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    type: str = "message"
    role: Literal["assistant"] = "assistant"
    content: str
    model: str
    meta: ResponseMeta
