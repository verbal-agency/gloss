"""The grounding check's classifier, answered by TypeSafe's Jev instead of an LLM.

Follows the pattern of TypeSafe's guardrails cookbook
(https://docs.typesafe.ai/cookbooks/llm_guardrails): one Jev request asks a
battery of questions about the user's message, and code turns the answers into
an action. The cookbook screens for jailbreaks; here the questions are the
grounding standard in GROUND_SYSTEM (app/pipeline/assumptions.py), worded as
closely to it as Jev's question format allows, so a difference in results is a
difference in the classifier, not in the standard.

Two ways to ask, both in one request:

  choice  the standard's two fields as two multiple-choice questions,
          `request` (fix / task / other) and `link` (stated / absent /
          contradicted). The action follows from the top choices exactly as for
          the LLM classifier (GroundResult.action).
  nouls   the standard decomposed into yes/no questions, each answered with a
          probability, and combined in code by thresholds (`route`), as the
          cookbook's `route` combines its hazards.

`evidence_beyond_plan` is asked too but is NOT part of the standard: it asks
whether anything besides the plan's own wording supports the cause, the gap
G37b found. Rules that use it are reported separately as a possible change to
the standard, never as the standard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings
from app.pipeline.assumptions import GroundResult

logger = logging.getLogger("gloss.jev_ground")

_CONVERSATION_NOTE = (
    " The text is a conversation: judge the LATEST REQUEST in the light of the user's "
    "turns taken together. Evidence stated in any earlier user turn counts. Assistant "
    "turns are context only: a cause the assistant suggested is not the user's evidence "
    "unless the user confirmed it. If the assistant asked how the user knows the plan "
    "addresses the cause and the user answered, that answer is the user's evidence."
)

_REQUEST = (
    "A user wrote this to an assistant. What kind of request is it?",
    {
        "fix": "The user describes a problem (something failing, slow, wrong, or missing a "
               "target) and asks for help building a plan meant to solve it.",
        "task": "The user asks for help with a piece of work that is a requirement in itself, "
                "not a response to a problem whose cause is in question (a migration, a "
                "backfill, enforcing a limit, adding a capability).",
        "other": "Anything else: a question, a discussion, no plan to build.",
    },
)

_LINK = (
    "Judged only from what the user's own text says, how is the user's plan linked to "
    "the cause of their problem? The user's own account of the cause counts as evidence: "
    "a measurement, an observation, \"we traced it\", or a plain statement of what causes "
    "the problem. Do not second-guess whether their diagnosis is right.",
    {
        "contradicted": "The facts or requirements the user states show the plan will not "
                        "achieve what they need: it acts on something other than the cause "
                        "they describe, or cannot meet a requirement they state. General "
                        "worries, best practice and missing safeguards are not contradictions.",
        "absent": "The request is a fix, and the text names a symptom and a plan but never "
                  "says what is causing the problem, so nothing connects the plan to the cause.",
        "stated": "Everything else: the text says what causes the problem and the plan acts "
                  "on it; or the request is a task the plan can meet; or there is no plan.",
    },
)

_NOULS = {
    "is_fix": (
        "Does the user describe a problem (something failing, slow, wrong, or missing a "
        "target) and ask for help building a plan meant to solve it?",
        "Yes: a problem plus a plan to fix it.",
        "No: a task that is a requirement in itself, a question, or a discussion.",
    ),
    "cause_stated": (
        "Does the user's text say WHY the problem happens? A measurement, an observation, "
        "\"we traced it\", or a plain statement of the cause all count. Could a reader point "
        "to a sentence that says why?",
        "Yes: a sentence in the user's text states the cause.",
        "No: the text names a symptom and a plan but never says what causes the problem.",
    ),
    "contradicted": (
        "Do the facts or requirements the user states show the plan will not achieve what "
        "they need, because it acts on something other than the cause they describe or "
        "cannot meet a requirement they state? General worries, best practice and missing "
        "safeguards do not count.",
        "Yes: the user's own statements conflict with the plan.",
        "No: nothing the user states conflicts with the plan.",
    ),
    "evidence_beyond_plan": (
        "Besides the wording of the plan itself, does the user give evidence (a "
        "measurement, an observation, a trace, a report) that the thing the plan acts on is "
        "what causes the problem? A plan that merely implies its own cause does not count.",
        "Yes: there is evidence other than the plan's wording.",
        "No: the only hint of the cause is the plan itself.",
    ),
}


def battery(conversation: bool) -> dict:
    """Every question, as raw question dicts, in one request. The Jev SDK
    accepts these dicts in place of its question objects."""
    note = _CONVERSATION_NOTE if conversation else ""
    qs: dict = {
        "request": {"type": "choice", "instructions": _REQUEST[0] + note, "criteria": _REQUEST[1]},
        "link": {"type": "choice", "instructions": _LINK[0] + note, "criteria": _LINK[1]},
    }
    for name, (question, yes, no) in _NOULS.items():
        qs[name] = {"type": "noul", "instructions": question + note,
                    "criteria": {"true": yes, "false": no}}
    return qs


@dataclass(frozen=True)
class Rule:
    """How yes/no probabilities become an action. `cause` names the noul that
    stands for "the cause is stated" (`cause_stated` is the standard)."""
    fix: float = 0.5
    cause: float = 0.5
    contra: float = 0.5
    cause_noul: str = "cause_stated"

    @property
    def name(self) -> str:
        tag = "" if self.cause_noul == "cause_stated" else f"[{self.cause_noul}]"
        return f"nouls{tag} fix>={self.fix} cause<{self.cause} contra>={self.contra}"


DEFAULT_RULE = Rule()


def choice_action(answers: dict) -> str:
    """The action from the two multiple-choice answers, as for the LLM classifier."""
    return GroundResult(request=answers["request"]["choice"],
                        link=answers["link"]["choice"]).action


def route(answers: dict, rule: Rule = DEFAULT_RULE) -> str:
    """The action from the yes/no probabilities. An objection outranks a
    question, as in GroundResult.action."""
    p = {k: answers[k]["noul"] for k in _NOULS}
    if p["contradicted"] >= rule.contra:
        return "objected"
    if p["is_fix"] >= rule.fix and p[rule.cause_noul] < rule.cause:
        return "asked"
    return "none"


def to_result(answers: dict, backend: str, rule: Rule = DEFAULT_RULE) -> GroundResult:
    """A GroundResult the middleware can use unchanged."""
    action = choice_action(answers) if backend == "jev_choice" else route(answers, rule)
    link = {"objected": "contradicted", "asked": "absent", "none": "stated"}[action]
    request = "fix" if action == "asked" else answers["request"]["choice"]
    probs = ", ".join(f"{k}={answers[k]['noul']:.2f}" for k in _NOULS)
    return GroundResult(request=request, link=link,
                        reasoning=f"jev {backend}: request={answers['request']['choice']}, "
                                  f"link={answers['link']['choice']}; {probs}")


async def ask_jev(state: str, conversation: bool) -> dict:
    """One Jev request; returns the answers as plain dicts keyed by question."""
    from typesafe_sdk import AsyncTypeSafeClient

    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=120.0) as client:
        resp = await client.system_one(state=state, questions=battery(conversation),
                                       model=settings.jev_model)
    return {k: v.model_dump(mode="json") for k, v in resp.answers.items()}


async def classify(query: str, context: str | None, backend: str) -> GroundResult:
    answers = await ask_jev(context or query, conversation=context is not None)
    return to_result(answers, backend)
