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
is answered. Surface the premises the query presupposes, then flag the ones a \
knowledgeable, careful advisor would genuinely pause over before answering.

Apply one judgment, not a checklist: would answering the query exactly as framed \
risk misleading the user, foreclosing a materially better option they haven't \
considered, or building on something dubious? A premise earns a flag when a \
thoughtful expert would want to challenge or qualify it first — whether it \
asserts something factually shaky or contested, or the framing itself quietly \
narrows the space (offering a few options as if they were the only ones, \
assuming a solution the user has not justified, or posing a consequential \
question whose honest answer depends on context the query leaves out).

Calibrate to stakes and consequence — this is the crux, and the same surface \
shape can be fine or not depending on what a wrong-framed answer would cost. Do \
NOT flag when a generic answer would serve the user perfectly well: when the \
missing context is cheap, when the framing is a reasonable everyday \
simplification, or when they are simply asking how to do something they have \
sensibly chosen to do. A query that openly asks for tradeoffs, factors, or \
considerations is already reasoning well — leave it alone.

Be faithful: a well-posed query has an EMPTY questionable list, and you must not \
manufacture doubt to seem useful. Judge the premises, not the tone.

Return JSON:
{"premises": ["..."], "questionable": ["..."], "reasoning": "one sentence", "reposed_query": "..." or null}
- premises: every non-trivial thing the query takes as given
- questionable: the premises a careful advisor would genuinely pause over (may be empty)
- reasoning: a one-sentence justification
- reposed_query: if questionable is non-empty, the query reframed toward the user's underlying
  goal — dropping the questionable premise and opening the option space — so the answer serves
  what they actually need. null if questionable is empty (clean query passes through unchanged).
"""


class AssumptionResult(BaseModel):
    premises: list[str]
    questionable: list[str]
    reasoning: str
    reposed_query: str | None = None


_DECOMPOSE_SYSTEM = """\
Given a user's query, identify their underlying goal and decompose it into 2-4 \
questions that together cover the full space of what they are trying to achieve. \
Each question should open a different dimension of the goal — without assuming \
any particular solution, option set, means, or causal claim. The questions \
collectively should surface what a comprehensive expert answer would need to cover.
Return JSON: {"questions": ["...", "...", "..."]}
"""

_MOVE_SYSTEM = """\
You are given an original question with its answer, and a set of decomposed \
questions with their answers that explore the same underlying goal more fully. \
Judge how much the decomposed answers collectively change the substance — \
surfacing better options, a different recommendation, or decisive considerations \
the original answer missed.
Rate magnitude 0-3: 0 = same substance (the framing cost nothing); 1 = minor extra \
color; 2 = materially fuller/different (the framing was costing the user something); \
3 = fundamentally different or better path (the original framing was misleading).
Return JSON: {"magnitude": 0-3, "differences": ["..."]}
"""


class _Decomposed(BaseModel):
    questions: list[str]


class _Movement(BaseModel):
    magnitude: int
    differences: list[str]


async def extract_frame_delta(
    query: str, model: str | None = None, threshold: int = 2
) -> AssumptionResult:
    """Frame-delta detector (G32 spike): a frame is unproductively constrained
    iff decomposing to the underlying goal materially moves the answer. Decompose
    → answer all in parallel → judge aggregate movement (0-3). Flag iff magnitude
    >= threshold; the magnitude is the rankable materiality scalar (in `reasoning`)."""
    import asyncio

    model = model or settings.effective_judge_model
    decomposed = await llm.chat_json(
        [{"role": "system", "content": _DECOMPOSE_SYSTEM}, {"role": "user", "content": query}],
        model=model, schema=_Decomposed,
    )
    questions = decomposed["questions"]
    answers = await asyncio.gather(
        *[llm.chat([{"role": "user", "content": q}], model=model) for q in [query] + questions]
    )
    ans_orig = answers[0]
    ans_decomposed = answers[1:]
    combined = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(questions, ans_decomposed))
    move = await llm.chat_json(
        [{"role": "system", "content": _MOVE_SYSTEM},
         {"role": "user", "content": f"ORIGINAL QUESTION: {query}\nORIGINAL ANSWER: {ans_orig}\n\n"
                                     f"DECOMPOSED QUESTIONS AND ANSWERS:\n{combined}"}],
        model=model, schema=_Movement,
    )
    mag = int(move["magnitude"])
    flagged = mag >= threshold
    return AssumptionResult(
        premises=[],
        questionable=move["differences"] if flagged else [],
        reasoning=f"magnitude={mag}",
    )


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
