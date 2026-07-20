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
that are questionable. A premise is questionable in two distinct ways:

1. DUBIOUS CLAIM — something asserted or assumed that is factually shaky, \
contested, or loaded ("coffee is bad for you", "Python is faster than C").

2. NARROW FRAME — the wording bakes in a conclusion even when no single claim is \
false. This is easy to miss because nothing stated is wrong; the frame itself is \
the problem. Watch for:
   - false dichotomy / collapsed options: two choices offered as if they were the \
only ones ("should I do A or B?") when others exist;
   - presupposed solution: asking HOW to do X when X may be the wrong approach \
("how do I add indexes to speed up my slow database" assumes indexing is the fix);
   - under-specified: the responsible answer depends on the user's situation that \
the query omits — flag what is needed ("answering 'pay off the mortgage or invest' \
well needs the user's interest rate, risk tolerance, and timeline").

Be faithful: a well-posed query has an EMPTY questionable list. Do NOT manufacture \
doubt to seem useful. Crucially, a query that ASKS for tradeoffs, factors, or \
considerations ("what are the tradeoffs between X and Y", "what should I weigh \
when deciding...") is OPENING the frame, not presupposing one — not questionable. \
A neutral how-to whose approach the user has legitimately chosen ("how do I write \
a Kubernetes manifest") is not questionable. Judge the premises, not the tone.

Return JSON:
{"premises": ["..."], "questionable": ["..."], "reasoning": "one sentence"}
- premises: every non-trivial thing the query takes as given
- questionable: the subset that are dubious claims OR narrow frames (may be empty)
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
