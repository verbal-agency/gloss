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

import logging

from typing import Literal

from pydantic import BaseModel

from app import llm
from app.config import settings

logger = logging.getLogger("gloss.assumptions")

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


async def run(query: str, model: str | None = None) -> AssumptionResult | None:
    """Pipeline entry point: `extract`, but never raises on a malformed judge
    response. Returns None on failure or when nothing is questionable, so the
    caller has one check. A `reposed_query` without a questionable premise is
    ignored — the premise is the only licence to act."""
    try:
        result = await extract(query, model=model)
    except (llm.JsonParseError, llm.JsonSchemaError):
        # Safe degrade (same direction as the normalizer): the user's request
        # proceeds untouched and nothing is fabricated.
        logger.warning("assumption extraction JSON failed; passing query through")
        return None
    if not result.questionable:
        return None
    return result


def annotation(result: AssumptionResult) -> str:
    """The note given to the answering model in "annotate" mode. The user's
    question is left exactly as asked; this asks the model to name the premise
    in its answer so the user sees it and can disagree."""
    premises = "\n".join(f"- {q}" for q in result.questionable)
    goal = (f"\nA fuller statement of what they may be trying to achieve: {result.reposed_query}"
            if result.reposed_query else "")
    return (
        "A reviewer read the user's latest question before you and noted that it takes "
        f"the following for granted:\n{premises}\n"
        f"Why this may matter: {result.reasoning}{goal}\n\n"
        "In your answer, say briefly and plainly that the question assumes this and why "
        "it may not hold, then help with what the user is trying to achieve, including "
        "what they asked. Do not lecture. If the assumption is reasonable in their "
        "situation, say so in a sentence and answer the question as asked."
    )


# ── Grounding check (ASSUMPTION_ACTION=ground) ──────────────────────────────
# The questionable-premise check above fires on almost everything: nearly any
# plan has a premise a careful advisor could doubt. A one-line instruction to
# "check the plan against the cause" over-fires too (G35: it asked on 8 of 15
# sound plans), because it re-examines a diagnosis the user already stated and
# invents a cause for work that has none. This check asks a narrower question:
# does the MESSAGE ITSELF connect the plan to the cause?

GROUND_SYSTEM = """\
You read a user's message to an assistant BEFORE it is answered. The user may be \
asking for help building something they have already decided on. Classify the \
message; do not answer it.

request:
  "fix"   the user describes a problem (something failing, slow, wrong, or \
missing a target) and asks for help building a plan meant to solve it.
  "task"  the user asks for help with a piece of work that is a requirement in \
itself, not a response to a problem whose cause is in question (a migration, a \
backfill, enforcing a limit, adding a capability).
  "other" anything else: a question, a discussion, no plan to build.

link — judged ONLY from what the message itself says:
  "contradicted" the facts or requirements stated in the message show the plan \
will not achieve what the user needs: it acts on something other than the cause \
the message describes, or it cannot meet a requirement the message states. Use \
this only when the conflict is with the message's own statements. General \
worries, best practice, and missing safeguards are not contradictions.
  "absent"  the request is a fix, and the message names a symptom and a plan but \
never says what is causing the problem, so nothing in it connects the plan to \
the cause.
  "stated"  everything else: the message says what is causing the problem and \
the plan acts on that; or the request is a task the plan can meet; or it is "other".

The user's own account of the cause counts as evidence. A measurement, an \
observation, "we traced it", or a plain statement of what causes the problem \
all make the link stated. Do not second-guess whether their diagnosis is right \
or well enough supported. Test for "absent": could a reader point to a sentence \
in the message that says WHY the problem happens? If yes, it is not absent.

Return JSON: {"request": "fix"|"task"|"other", "link": "stated"|"absent"|"contradicted", \
"evidence": "<the sentence that states the cause, or empty>", \
"contradiction": "<for contradicted: one sentence on what the plan misses; else empty>", \
"reasoning": "<one sentence>"}
"""

# What the answering model is told when the link is absent. The ask-and-wait
# behaviour is the part of the G35 instruction that worked (13 of 13).
ASK_NOTE = (
    "The user has asked for help building a plan, and their message does not say how they "
    "know the plan addresses the cause of their problem. Do not build anything yet. Ask one "
    "short question about that, and wait for their answer."
)


class GroundResult(BaseModel):
    request: Literal["fix", "task", "other"]
    link: Literal["stated", "absent", "contradicted"]
    evidence: str = ""
    contradiction: str = ""
    reasoning: str = ""

    @property
    def action(self) -> str:
        """none | asked | objected. Asking only makes sense for a fix: a task
        has no cause to ask about."""
        if self.link == "contradicted":
            return "objected"
        if self.link == "absent" and self.request == "fix":
            return "asked"
        return "none"


async def classify_grounding(query: str, model: str | None = None) -> GroundResult:
    data = await llm.chat_json(
        [{"role": "system", "content": GROUND_SYSTEM}, {"role": "user", "content": query}],
        model=model or settings.ground_model or settings.effective_judge_model,
        schema=GroundResult,
    )
    return GroundResult(**data)


async def run_ground(query: str, model: str | None = None) -> GroundResult | None:
    """Pipeline entry point for the grounding check. Never raises on a malformed
    classifier response: returns None and the request proceeds untouched."""
    try:
        return await classify_grounding(query, model=model)
    except (llm.JsonParseError, llm.JsonSchemaError):
        logger.warning("grounding classifier JSON failed; passing query through")
        return None


def objection_note(result: GroundResult) -> str:
    """The note for a plan the message's own facts contradict: say so first."""
    return annotation(AssumptionResult(
        premises=[],
        questionable=[result.contradiction or "the plan does not act on the cause the message describes"],
        reasoning=result.reasoning,
    ))
