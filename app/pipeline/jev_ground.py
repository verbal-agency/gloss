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


# ── G41: structured state, a plain problem question, probability rules ──────
# G40's setup lost on plain tasks (its `is_fix` question scored ~0.7 on
# everything) and its multiple-choice form never asked on a conversation. G41
# changes the setup, not the standard: a yes/no question on whether anything is
# going wrong, the state as a JSON object with the user's and the assistant's
# turns in separate named parts, and rules that read Jev's probabilities rather
# than only its top labels. G40's battery, `route` and `Rule` above are kept
# unchanged so its result can be reproduced.

_PROBLEM_DESCRIBED = (
    "Does the user describe something going wrong: something failing, slow, wrong, broken, "
    "or missing a target they care about? Work the user wants done for its own sake (a "
    "migration, a new feature, a compliance requirement, an upgrade) is not something "
    "going wrong.",
    "Yes: the user describes a problem.",
    "No: the user wants work done, and nothing is described as going wrong.",
)

_JSON_NOTE = (
    " The state holds the user's earlier turns (`earlier_user_turns`), the assistant's replies "
    "(`assistant_replies`), and the user's latest request (`latest_user_request`). Judge the "
    "latest request in the light of all the user's turns taken together. Only the user's own "
    "words count as evidence: a cause the assistant suggested counts only if the user "
    "confirmed it. If the assistant asked how the user knows the plan addresses the cause and "
    "the user answered, that answer is the user's evidence."
)

G41_NOULS = ("is_fix", "problem_described", "cause_stated", "contradicted")


def json_state(messages: list[dict]) -> dict:
    """The conversation as a JSON object with the user's and the assistant's turns
    apart. A single message has the same shape, with no earlier turns. Long
    assistant replies are cut as in `assumptions.conversation_view`."""
    from app.pipeline.assumptions import _ASSISTANT_TURN_LIMIT

    turns = [m for m in messages if m.get("role") in ("user", "assistant")]
    while turns and turns[-1]["role"] != "user":
        turns.pop()
    if not turns:
        raise ValueError("no user turn to judge")
    replies = []
    for m in turns[:-1]:
        if m["role"] == "assistant":
            text = m["content"]
            if len(text) > _ASSISTANT_TURN_LIMIT:
                half = _ASSISTANT_TURN_LIMIT // 2
                text = f"{text[:half]}\n[...]\n{text[-half:]}"
            replies.append(text)
    return {"earlier_user_turns": [m["content"] for m in turns[:-1] if m["role"] == "user"],
            "assistant_replies": replies,
            "latest_user_request": turns[-1]["content"]}


def g41_battery(form: str, conversation: bool) -> dict:
    """G41's questions. `form` is "text" (G40's state: the message, or the
    conversation as one text) or "json" (`json_state`)."""
    if form == "json":
        note = _JSON_NOTE
    elif form == "text":
        note = _CONVERSATION_NOTE if conversation else ""
    else:
        raise ValueError(form)
    qs: dict = {
        "request": {"type": "choice", "instructions": _REQUEST[0] + note, "criteria": _REQUEST[1]},
        "link": {"type": "choice", "instructions": _LINK[0] + note, "criteria": _LINK[1]},
    }
    texts = {**{k: _NOULS[k] for k in ("is_fix", "cause_stated", "contradicted")},
             "problem_described": _PROBLEM_DESCRIBED}
    for name in G41_NOULS:
        question, yes, no = texts[name]
        qs[name] = {"type": "noul", "instructions": question + note,
                    "criteria": {"true": yes, "false": no}}
    return qs


@dataclass(frozen=True)
class G41Rule:
    """How G41's answers become an action.

    family "choice": the top labels, as the LLM classifier's rule.
    family "route":  ask when the gate question is at least `gate_t` and
                     `cause_stated` is below `cause_t` (G40's form).
    family "link":   ask when the probability of "link absent" is at least
                     `cause_t`, and the gate (if any) is at least `gate_t`.
    In "route" and "link", objecting outranks asking: `contradicted` at least
    `contra_t` objects."""
    family: str = "route"
    gate: str | None = "problem_described"
    gate_t: float = 0.5
    cause_t: float = 0.5
    contra_t: float = 0.5

    @property
    def name(self) -> str:
        if self.family == "choice":
            return "choice"
        gate = f"{self.gate}>={self.gate_t} " if self.gate else ""
        test = "cause_stated<" if self.family == "route" else "p_absent>="
        return f"{self.family}: {gate}{test}{self.cause_t} contra>={self.contra_t}"


def g41_action(answers: dict, rule: G41Rule) -> str:
    if rule.family == "choice":
        return choice_action(answers)
    if answers["contradicted"]["noul"] >= rule.contra_t:
        return "objected"
    gated = rule.gate is None or answers[rule.gate]["noul"] >= rule.gate_t
    if rule.family == "route":
        missing = answers["cause_stated"]["noul"] < rule.cause_t
    elif rule.family == "link":
        missing = answers["link"]["probabilities"]["absent"] >= rule.cause_t
    else:
        raise ValueError(rule.family)
    return "asked" if gated and missing else "none"


async def ask_jev_g41(state: str | dict, form: str, conversation: bool) -> dict:
    """One Jev request with G41's questions; answers as plain dicts."""
    from typesafe_sdk import AsyncTypeSafeClient

    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=120.0) as client:
        resp = await client.system_one(state=state, questions=g41_battery(form, conversation),
                                       model=settings.jev_model)
    return {k: v.model_dump(mode="json") for k, v in resp.answers.items()}
