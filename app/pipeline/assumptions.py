"""G27 (v2) — de-risk spike: faithful assumption extraction.

The v2 thesis moves the center of gravity to the input layer: before answering,
deconstruct the assumptions a query presupposes. This module is the isolated
*detection* half — surface a query's premises and flag the questionable ones —
so its faithfulness (recall on loaded queries, false-positive rate on clean ones)
can be measured on its own, before any re-posing is built on top (see THESIS.md,
"the three input-layer jobs"; measurement rationale in REMEDIATION.md G27).

Not wired into `middleware.process`. In production the fields below become the
LEADING fields of a single combined call that also re-poses (G29) — never a
separate detection round-trip.
"""
from __future__ import annotations

from pydantic import BaseModel

from app import llm
from app.config import settings

EXTRACT_SYSTEM = """\
You inspect a user's query for the assumptions it takes for granted, BEFORE it \
is answered. Surface the premises the query presupposes, then flag only those \
that are questionable — factually dubious, contested, or a framing that bakes in \
an unproven conclusion.

Be faithful: a well-posed query that presupposes nothing dubious has an EMPTY \
questionable list. Do not manufacture doubt to seem useful. A neutral how-to or \
a genuine open comparison ("tradeoffs between X and Y") is not questionable. \
Judge the premises, not the tone.

Return JSON:
{"premises": ["..."], "questionable": ["..."], "reasoning": "one sentence"}
- premises: every non-trivial thing the query takes as given
- questionable: the subset of premises that are dubious/contested/loaded (may be empty)
- reasoning: a one-sentence justification
"""


class AssumptionResult(BaseModel):
    premises: list[str]
    questionable: list[str]
    reasoning: str


async def extract(query: str, model: str | None = None) -> AssumptionResult:
    """Detect the premises a query presupposes and flag the questionable ones.

    `model` defaults to the judge model (a cheap dedicated model when configured,
    per G11) — this is inspection work, not the user-facing answer.
    """
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": query},
    ]
    data = await llm.chat_json(
        messages,
        model=model or settings.effective_judge_model,
        schema=AssumptionResult,
    )
    return AssumptionResult(**data)
