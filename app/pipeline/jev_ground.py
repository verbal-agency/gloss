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


# ── G42: narrower cause questions, examples in criteria, objection needs a cause ─
# G41's Jev pick missed five of 16 single messages that withheld the cause. Each
# change below follows a documented Jev practice (docs.typesafe.ai) aimed at one
# kind of miss; the standard itself is unchanged: a plain statement of the cause
# counts, and the cause has to be stated, not implied by the plan.
#   - "Rate-limit errors" read as its own cause. Jev "answers the question you
#     wrote": name the narrowest fact that decides it (a fact about the user's
#     own system), and put examples that look like real inputs in the criteria.
#   - A plan that names the cause ("drop the stale replication slot") passed as
#     a stated cause. "Is the cause stated anywhere but the plan?" is its own
#     yes/no question rather than an exception buried in another.
#   - A message with no cause was objected to. A plan can only contradict a
#     cause the user has stated, so a rule may require evidence before objecting.
#   - Jev can be moved by text that argues for an answer, and every message says
#     "I've researched this and decided". One arm tells it to ignore that.
# The examples come from situations used nowhere in dev or test.

_IGNORE_CONFIDENCE = (
    " How sure the user sounds, and saying they researched or decided, is not evidence: judge "
    "only the facts they state."
)

_G42_NOULS: dict[str, tuple[str, dict, dict]] = {
    "mechanism_stated": (
        "Does the user state a fact about their own system, data or process that explains why "
        "the problem happens: for example how much or how often something runs, what a component "
        "does, or what a measurement, trace or log showed? The name or type of the error or "
        "symptom (such as \"rate-limit errors\", \"out-of-memory crashes\", \"timeouts\") only "
        "says what the problem is, not why it happens, and does not count. The plan the user has "
        "chosen does not count either.",
        {"meaning": "Yes: beyond the symptom and the plan, the user states a fact that explains "
                    "why the problem happens.",
         "examples": [
             "Our push notifications arrive hours late. Our sender batches them and only flushes "
             "the batch every three hours.",
             "Nightly backups fail with timeout errors. They copy 2 TB over a link capped at "
             "50 Mbit/s, which takes longer than the eight-hour window.",
         ]},
        {"meaning": "No: the user names the problem, perhaps by its error type, and a plan, but "
                    "states no fact that explains why it happens.",
         "examples": [
             "Our image-resizing service throws out-of-memory errors. I've decided to give it "
             "more memory.",
             "Our booking API returns connection-refused errors at peak. I've decided to raise "
             "the database connection pool limit.",
         ]},
    ),
    "cause_outside_plan": (
        "Leaving aside the plan the user has chosen, does the user say what causes the problem? "
        "A cause that appears only inside the plan does not count: \"clear the stuck cache\" "
        "implies a stuck cache, but does not say the user found one.",
        {"meaning": "Yes: a sentence other than the plan says what causes the problem.",
         "examples": [
             "Our nightly backups time out because they copy 2 TB over a 50 Mbit/s link. I've "
             "decided to send only changed blocks.",
         ]},
        {"meaning": "No: the only sign of a cause is in the plan itself, or there is none.",
         "examples": [
             "Our booking API returns errors at peak. I've decided to raise the database "
             "connection pool limit.",
             "Our push notifications arrive late. I've decided to flush the notification batch "
             "every minute instead of every three hours.",
         ]},
    ),
}

G42_NOULS = (*G41_NOULS, *_G42_NOULS)


def g42_battery(conversation: bool, ignore_confidence: bool) -> dict:
    """G41's questions on text state (G41's pick) plus the two G42 questions.
    `ignore_confidence` adds the note telling Jev to discount how sure the user
    sounds, to every question."""
    note = (_CONVERSATION_NOTE if conversation else "") + (_IGNORE_CONFIDENCE if ignore_confidence else "")
    qs = g41_battery("text", conversation)
    if ignore_confidence:
        for q in qs.values():
            q["instructions"] += _IGNORE_CONFIDENCE
    for name, (question, yes, no) in _G42_NOULS.items():
        qs[name] = {"type": "noul", "instructions": question + note, "criteria": {"true": yes, "false": no}}
    return qs


@dataclass(frozen=True)
class G42Rule:
    """How G42's answers become an action.

    `evidence` names what must be present for the link to count as stated:
    ("link",) reads G41's probability of "link absent" (missing when it is at
    least `ev_t`); otherwise every named yes/no question must be at least
    `ev_t`. The question is asked when evidence is missing and the gate (if
    any) is at least `gate_t`. `contradicted` at least `contra_t` objects; with
    `contra_needs_evidence`, only when the evidence is present (a plan can only
    contradict a cause the user stated), and otherwise the case is asked."""
    evidence: tuple[str, ...] = ("link",)
    ev_t: float = 0.2
    gate: str | None = "problem_described"
    gate_t: float = 0.3
    contra_t: float = 0.3
    contra_needs_evidence: bool = False

    @property
    def name(self) -> str:
        gate = f"{self.gate}>={self.gate_t} " if self.gate else ""
        ev = (f"p_absent>={self.ev_t}" if self.evidence == ("link",)
              else f"min({','.join(self.evidence)})<{self.ev_t}")
        needs = " if-evidence" if self.contra_needs_evidence else ""
        return f"{gate}{ev} contra>={self.contra_t}{needs}"


def g42_missing(answers: dict, rule: G42Rule) -> bool:
    if rule.evidence == ("link",):
        return answers["link"]["probabilities"]["absent"] >= rule.ev_t
    return any(answers[n]["noul"] < rule.ev_t for n in rule.evidence)


def g42_action(answers: dict, rule: G42Rule) -> str:
    missing = g42_missing(answers, rule)
    if answers["contradicted"]["noul"] >= rule.contra_t and not (rule.contra_needs_evidence and missing):
        return "objected"
    gated = rule.gate is None or answers[rule.gate]["noul"] >= rule.gate_t
    return "asked" if gated and missing else "none"


async def ask_jev_g42(state: str, conversation: bool, ignore_confidence: bool) -> dict:
    """One Jev request with G42's questions; answers as plain dicts."""
    from typesafe_sdk import AsyncTypeSafeClient

    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=120.0) as client:
        resp = await client.system_one(state=state, questions=g42_battery(conversation, ignore_confidence),
                                       model=settings.jev_model)
    return {k: v.model_dump(mode="json") for k, v in resp.answers.items()}


# ── G43 exploration: user turns only, and a graded cause question ───────────
# Spent data only (docs/v3_spike.md, G43 exploration). Two changes, each
# approved by the owner on 2026-11-19:
#   - Conversations are sent as the user's messages alone. G42's misses on
#     conversations came from assistant text: replies that restate the plan's
#     reasoning, and clarifying questions that name other causes.
#   - One multiple-choice question rates how strongly the user's own words
#     state why the problem happens, from no cause to an observed one. It does
#     not judge whether the diagnosis is right. Owner ruling (2026-11-18): a
#     clause inside the plan counts when it says what is happening now.

_USER_ONLY_NOTE = (
    " The text holds only the user's messages from a conversation with an assistant; the "
    "assistant's replies are left out. Judge the LATEST REQUEST in the light of all the user's "
    "messages taken together. Evidence stated in any earlier user message counts."
)


def user_turns_view(messages: list[dict]) -> str | None:
    """The user's messages alone, in order, the latest marked as the one to
    judge. None when the latest user message is the only turn (as for
    `assumptions.conversation_view`, so single messages are sent unchanged)."""
    from app.pipeline.assumptions import conversation_view

    if conversation_view(messages) is None:
        return None
    turns = [m for m in messages if m.get("role") in ("user", "assistant")]
    while turns and turns[-1]["role"] != "user":
        turns.pop()
    users = [m["content"] for m in turns if m["role"] == "user"]
    earlier = "\n\n".join(f"USER MESSAGE {i}: {t}" for i, t in enumerate(users[:-1], 1))
    return ("THE USER'S EARLIER MESSAGES (the assistant's replies are left out):\n" + earlier
            + "\n\nLATEST REQUEST (the user message to judge):\n" + users[-1])


def g43_battery(conversation: bool, user_only: bool) -> dict:
    """G42's battery without the confidence note; with `user_only`, the
    conversation note describes a text of user messages alone."""
    qs = g42_battery(conversation, False)
    if conversation and user_only:
        for q in qs.values():
            q["instructions"] = q["instructions"].replace(_CONVERSATION_NOTE, _USER_ONLY_NOTE)
    return qs


_CAUSE_LEVEL = (
    "How strongly does the user's own text state WHY the problem happens? Rate only what the "
    "user says, not whether their diagnosis is right. A statement of what is happening now that "
    "causes the problem counts wherever it appears, including inside the plan. The name or type "
    "of the error or symptom is not a cause, and saying they researched or decided is not "
    "evidence. If nothing is going wrong (the user just wants work done), answer none.",
    {
        "none": {
            "meaning": "No cause is stated: the text gives the problem, perhaps by its error name, "
                       "and a plan, but nothing about why it happens.",
            "examples": [
                "Our podcast feed shows 'feed fetch failed' errors in two directories. I've "
                "decided to move the feed behind a CDN. Can you write the CDN config?",
                "Warehouse labels sometimes print with the wrong address. I've decided to rewrite "
                "the label template. Can you write the new one?",
            ]},
        "implied": {
            "meaning": "Only the plan's wording hints at a cause, or the plan only says what it "
                       "will achieve; the user never says what is happening now.",
            "examples": [
                "Readings from our rooftop weather stations have gaps every few hours. I've decided to add a "
                "local buffer on each device so readings survive reconnects.",
                "Thumbnails appear minutes after upload. I've decided to generate them in their "
                "own worker pool so they appear faster.",
            ]},
        "asserted": {
            "meaning": "The user says what is happening now that causes the problem, as a plain "
                       "statement, in the plan or elsewhere, without a measurement behind it.",
            "examples": [
                "Chat messages arrive a minute late on Android, because the app only checks the "
                "server once a minute in the background. I've decided to switch to push.",
                "Thumbnails appear minutes after upload. I've decided to stop queuing them behind "
                "the video transcodes, which hold the only worker for minutes at a time.",
            ]},
        "observed": {
            "meaning": "The user states the cause and backs it with a measurement, log, trace, "
                       "count or test.",
            "examples": [
                "Readings from our rooftop weather stations have gaps every few hours. The device logs show "
                "the modem reconnecting each time, and the gaps match the reconnects to the minute.",
                "About 2% of warehouse labels print with the wrong address; every one we checked "
                "was an order edited after the label job had read it.",
            ]},
    },
)

CAUSE_LEVELS = tuple(_CAUSE_LEVEL[1])


def cause_level_question(conversation: bool, user_only: bool) -> dict:
    note = (_USER_ONLY_NOTE if user_only else _CONVERSATION_NOTE) if conversation else ""
    return {"cause_level": {"type": "choice", "instructions": _CAUSE_LEVEL[0] + note,
                            "criteria": _CAUSE_LEVEL[1]}}


def stated_probability(answers: dict) -> float:
    """E: the probability that the cause is at least asserted."""
    p = answers["cause_level"]["probabilities"]
    return p["asserted"] + p["observed"]


async def ask_jev_questions(state: str, questions: dict) -> dict:
    """One Jev request with the given questions; answers as plain dicts."""
    from typesafe_sdk import AsyncTypeSafeClient

    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=120.0) as client:
        resp = await client.system_one(state=state, questions=questions, model=settings.jev_model)
    return {k: v.model_dump(mode="json") for k, v in resp.answers.items()}


# ── G43 exploration 2: contradiction split in two, and risk questions ──────
# docs/v3_spike.md, "G43 exploration 2". The two contradiction questions
# separate the kinds of objection G40's proposals contain: a plan aimed at
# something other than the stated cause, and a plan a stated requirement rules
# out. The risk questions reframe asking as value of information; `stakes` and
# `bad_solution` are descriptive only (the standard does not judge the
# diagnosis, and the labels do not encode stakes).

_G43_RISK_NOULS: dict[str, tuple[str, dict | str, dict | str]] = {
    "plan_misses_cause": (
        "Does the user state what causes the problem, and does their plan change something other "
        "than that cause? Judge only against the cause the user states. If the user states no "
        "cause, the answer is no.",
        {"meaning": "Yes: the user states a cause, and the plan acts on something else.",
         "examples": [
             "Our report emails go out at 9am instead of 6am; the scheduler log shows the job waits "
             "two hours for a lock the backup holds. I've decided to move the report job to a "
             "bigger server.",
         ]},
        {"meaning": "No: the plan acts on the cause the user states, or the user states no cause.",
         "examples": [
             "Our report emails go out at 9am instead of 6am; the scheduler log shows the job waits "
             "two hours for a lock the backup holds. I've decided to move the backup to 2am.",
             "Our report emails go out late. I've decided to move the report job to a bigger server.",
         ]},
    ),
    "plan_breaks_requirement": (
        "Does the user state a requirement or constraint (a limit, budget, deadline, policy, or "
        "compatibility need) that their plan cannot meet as described?",
        {"meaning": "Yes: a requirement the user states rules the plan out.",
         "examples": [
             "Our customers' corporate networks block all third-party domains, and every page must "
             "load for them. I've decided to load our fonts and charts from a public CDN.",
         ]},
        {"meaning": "No: the plan can meet every requirement the user states, or none is stated.",
         "examples": [
             "Our customers' corporate networks block all third-party domains, and every page must "
             "load for them. I've decided to serve our fonts and charts from our own domain.",
         ]},
    ),
    "wasted_effort": (
        "If the assistant builds exactly what the user asks, without questioning it, how likely is "
        "it that the work is wasted because nothing the user says shows the plan will fix their "
        "problem? Judge from the user's words only.",
        "Yes: the user gives nothing that shows the plan will fix the problem, so the work could "
        "easily be wasted.",
        "No: what the user says shows the plan addresses the problem, or the user just wants work "
        "done and nothing is going wrong.",
    ),
    "stakes": (
        "If this plan turns out to be wrong, is it costly or hard to undo: weeks of work, a "
        "rewrite, new infrastructure, a data migration, hiring, or a change customers see?",
        "Yes: a wrong plan would cost a lot of work or be hard to reverse.",
        "No: the plan is small, quick, or easy to undo.",
    ),
    "bad_solution": (
        "Would an experienced engineer, reading only what the user says, doubt that this plan "
        "will solve the user's problem?",
        "Yes: an experienced engineer would doubt the plan solves the problem.",
        "No: the plan looks like a reasonable way to solve the problem, or there is no problem.",
    ),
}

G43_RISK_NOULS = tuple(_G43_RISK_NOULS)


def g43_risk_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    return {name: {"type": "noul", "instructions": q + note, "criteria": {"true": yes, "false": no}}
            for name, (q, yes, no) in _G43_RISK_NOULS.items()}


# ── G43 exploration 3: a decision tree and a value-of-information model ─────
# docs/v3_spike.md, "G43 exploration 3". Step 2 of the tree asks whether the
# plan is an investigation (asking how the user knows the cause cannot change
# what they do when finding the cause is the plan). `plan_scope` gives the cost
# of a wrong plan for the value-of-information model. The step-4 questions are
# worded on the premise that a cause is stated; they are only used for cases
# that reach step 4.

_G43_TREE_NOULS: dict[str, tuple[str, dict, dict]] = {
    "plan_is_investigation": (
        "Is the plan the user has chosen a way to find out what causes the problem (measuring, "
        "profiling, logging, reproducing it, or comparing cases), rather than a change meant to "
        "fix it?",
        {"meaning": "Yes: the plan is to find out what is going on before fixing anything.",
         "examples": ["Our nightly import has got slower over the last month. I've decided to log "
                      "how long each stage takes for a week before changing anything."]},
        {"meaning": "No: the plan is a change meant to fix the problem, or there is no problem.",
         "examples": ["Our nightly import has got slower over the last month. I've decided to "
                      "split the import across four parallel workers."]},
    ),
}

_PLAN_SCOPE = (
    "If the plan the user has chosen turned out to be the wrong one, how much work would be "
    "wasted or need undoing?",
    {
        "small": "A small change: one function, query, index, setting or rule; hours of work.",
        "component": "One component: a service's caching, a queue between two services, a new "
                     "page, a schema change; days of work.",
        "system": "A system change: a migration, a rewrite, new infrastructure, moving platforms "
                  "or regions; weeks of work or hard to reverse.",
        "organisation": "A change to people or process: hiring, reorganising a team, changing "
                        "vendors or on-call; costly and slow to reverse.",
    },
)

PLAN_SCOPE_COST = {"small": 1.0, "component": 3.0, "system": 10.0, "organisation": 10.0}

_G43_STEP4: dict[str, tuple[str, dict, dict]] = {
    "misses_stated_cause": (
        "The user states why their problem happens. Does the plan they chose change something "
        "other than that cause?",
        _G43_RISK_NOULS["plan_misses_cause"][1],
        {"meaning": "No: the plan acts on the cause the user states.",
         "examples": [_G43_RISK_NOULS["plan_misses_cause"][2]["examples"][0]]},
    ),
    "breaks_stated_requirement": (
        "The user states what they need. Does a requirement or constraint they state (a limit, "
        "budget, deadline, policy or compatibility need) rule out the plan as described?",
        _G43_RISK_NOULS["plan_breaks_requirement"][1],
        _G43_RISK_NOULS["plan_breaks_requirement"][2],
    ),
}


def g43_tree_battery(conversation: bool) -> dict:
    """Steps 2 and the plan's scope, in one request."""
    note = _CONVERSATION_NOTE if conversation else ""
    qs = {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
          for n, (q, y, f) in _G43_TREE_NOULS.items()}
    qs["plan_scope"] = {"type": "choice", "instructions": _PLAN_SCOPE[0] + note, "criteria": _PLAN_SCOPE[1]}
    return qs


def g43_step4_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    return {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
            for n, (q, y, f) in _G43_STEP4.items()}


# ── G43 exploration 4: what the plan can be checked against ─────────────────
# docs/v3_spike.md, "G43 exploration 4". `goal_stated` lets a request with no
# problem (a "task") still be checked against what the user says it must
# achieve. `plan_correct` and `user_assuming` are the owner's two direct
# questions; `plan_correct` judges the plan itself and is exploratory only.

_G43_CHECK_NOULS: dict[str, tuple[str, dict | str, dict | str]] = {
    "goal_stated": (
        "Does the user state a goal, requirement or constraint that the result must meet: what it "
        "has to achieve, a limit, a deadline, or a policy? Wanting a problem they describe to go "
        "away does not count on its own.",
        {"meaning": "Yes: the user says what the result has to achieve or must not break.",
         "examples": [
             "The nightly export has to finish before the 7am team standup. Can you write the export "
             "job so it streams rows instead of loading them all?",
             "The stock dashboard must show a sale within a minute of it happening. I've decided to "
             "refresh it from the sales table every ten minutes.",
         ]},
        {"meaning": "No: the user asks for work or describes a problem, but states no goal or "
                    "requirement the result must meet.",
         "examples": [
             "Can you add a dark mode toggle to the settings page?",
             "Our nightly import has got slower. I've decided to split it across four workers.",
         ]},
    ),
    "plan_correct": (
        "How likely is it that the user's plan will actually achieve what they need?",
        "Yes: the plan is likely to achieve what the user needs.",
        "No: the plan is unlikely to achieve what the user needs.",
    ),
    "user_assuming": (
        "Is the user taking for granted something they have not checked or stated: about what "
        "causes the problem, about what their plan will do, or about what they need?",
        "Yes: the plan rests on something the user assumes without having checked or stated it.",
        "No: what the plan rests on is stated or checked in the user's own words.",
    ),
}


def g43_check_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    return {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
            for n, (q, y, f) in _G43_CHECK_NOULS.items()}


# ── E5: one critical question per kind of doubt ─────────────────────────────
# docs/v3_spike.md, "A formal frame" and "E5 details". The frame: the user's
# stated facts D and plan S should deliver what they need R (D, S |= R).
# Undercutting doubt (no causal link stated) asks; rebutting doubt (the plan
# won't deliver R, or breaks a stated constraint) objects. Owner rulings 1-3.

_E5_GOAL = (
    "What does the user's plan have to deliver?",
    {
        "problem": "Something is going wrong (failing, slow, wrong, broken, missing a target) and must "
                   "stop.",
        "requirement": "Nothing is going wrong, but the user states a goal, requirement or constraint "
                       "the result must meet.",
        "both": "Something is going wrong, and the user also states a goal or constraint the result "
                "must meet.",
        "neither": "A plain request for work, with no problem and no stated goal or constraint to "
                   "check it against.",
    },
)

_E5_NOULS: dict[str, tuple[str, dict | str, dict | str]] = {
    "link_stated": (
        "Does the user state what is happening that causes the problem, so the plan can be checked "
        "against it? A cause stated inside the plan counts if it says what is happening now. The name "
        "or type of the error or symptom does not count, and neither does what the plan is meant to "
        "achieve.",
        _G42_NOULS["mechanism_stated"][1],
        _G42_NOULS["mechanism_stated"][2],
    ),
    "achieves_goal": (
        "Given everything the user states, how likely is it that their plan delivers what they need?",
        "Yes: the plan is likely to deliver what the user needs.",
        "No: the plan is unlikely to deliver what the user needs.",
    ),
    "conflicts_constraint": (
        "Does the plan break a goal, limit or constraint that the user states?",
        _G43_RISK_NOULS["plan_breaks_requirement"][1],
        _G43_RISK_NOULS["plan_breaks_requirement"][2],
    ),
    "investigation": _G43_TREE_NOULS["plan_is_investigation"],
}


def e5_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    qs = {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
          for n, (q, y, f) in _E5_NOULS.items()}
    qs["goal_type"] = {"type": "choice", "instructions": _E5_GOAL[0] + note, "criteria": _E5_GOAL[1]}
    return qs


def e5_action(a: dict, t: float = 0.5) -> str:
    """The E5 decision table, rows in order."""
    p = a["goal_type"]["probabilities"]
    if a["investigation"]["noul"] >= 0.5:
        return "none"
    if 1 - p["neither"] < 0.5:
        return "none"
    if a["conflicts_constraint"]["noul"] >= t:
        return "objected"
    if p["problem"] + p["both"] >= 0.5 and a["link_stated"]["noul"] < 0.7:
        return "asked"
    if 1 - a["achieves_goal"]["noul"] >= t:
        return "objected"
    return "none"


# ── E5b: E5 without the goal-type question, and the delivery question judged
# on the user's overall plan in conversations (docs/v3_spike.md, "E5b").

_E5B_OVERALL = (" Judge the user's overall plan as the conversation describes it, not only the step "
                "asked for in the latest turn.")


def e5b_battery(conversation: bool) -> dict:
    qs = e5_battery(conversation)
    del qs["goal_type"]
    note = _CONVERSATION_NOTE if conversation else ""
    question, yes, no = _PROBLEM_DESCRIBED
    qs["problem_described"] = {"type": "noul", "instructions": question + note,
                               "criteria": {"true": yes, "false": no}}
    if conversation:
        qs["achieves_goal"]["instructions"] += _E5B_OVERALL
    return qs


def e5b_action(a: dict) -> str:
    """The E5b decision table, rows in order."""
    if a["investigation"]["noul"] >= 0.5:
        return "none"
    if a["conflicts_constraint"]["noul"] >= 0.5:
        return "objected"
    if a["problem_described"]["noul"] >= 0.3 and a["link_stated"]["noul"] < 0.7:
        return "asked"
    if 1 - a["achieves_goal"]["noul"] >= 0.5:
        return "objected"
    return "none"


# ── E5c: a claimed cause versus evidence for it ─────────────────────────────
# docs/v3_spike.md, "E5c". Evidence is an observation that would have come out
# differently if the claimed cause were wrong. `evidence_for_cause` carries
# paired examples in one situation: a measured symptom (no), an asserted cause
# (no), a measured cause (yes). Situations used nowhere in dev or test.

_E5C_NOULS: dict[str, tuple[str, dict, dict]] = {
    "cause_claimed": (
        "Does the user say, or does their plan imply, what causes the problem? An implied cause counts: a plan "
        "to fix a specific thing implies that thing is the cause.",
        {"meaning": "Yes: a cause is stated or implied by the plan.",
         "examples": ["Our map is slow to show tiles at peak. It's because the tile server is overloaded.",
                      "Our map is slow to show tiles at peak. I've decided to cache rendered tiles."]},
        {"meaning": "No: nothing is going wrong, or the user names the problem and asks for help without "
                    "pointing at a cause.",
         "examples": ["Our map is slow to show tiles at peak. Can you help me find out why?"]},
    ),
    "evidence_for_cause": (
        "Does the user report an observation about the CAUSE, not the symptom, that points to that cause rather "
        "than to other possible causes: a measurement, log, trace, profile, count, test, or a before-and-after? "
        "A measurement of the symptom itself (how slow, how often, for whom) does not count. A plain statement "
        "of the cause with nothing behind it does not count. A fact about their system that accounts for the "
        "specific symptom does count.",
        {"meaning": "Yes: an observation points to the stated cause rather than to others.",
         "examples": [
             "Our map takes four seconds to show tiles at peak. The tile server's logs show every tile is rendered "
             "on request, while the few tiles already cached come back in 50 ms.",
             "Product returns rose to 12% this quarter. In 200 return notes we read, 140 say the size ran small.",
         ]},
        {"meaning": "No: only the symptom is measured, or the cause is asserted with nothing behind it.",
         "examples": [
             "Our map takes four seconds to show tiles at peak and half a second at night.",
             "Our map is slow to show tiles at peak because the tile server is overloaded.",
             "Product returns rose to 12% this quarter, mostly on clothing and mostly from new customers.",
         ]},
    ),
}


def e5c_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    qs = {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
          for n, (q, y, f) in _E5C_NOULS.items()}
    for name in ("mechanism_stated", "cause_outside_plan"):
        q, y, f = _G42_NOULS[name]
        qs[name] = {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
    return qs


# ── E5d: is the plan costly or hard to reverse? ─────────────────────────────
# docs/v3_spike.md, "E5d". Narrow questions about the WHOLE plan, not the step
# asked for now, with paired examples in one situation used nowhere else.

_E5D_NOULS: dict[str, tuple[str, dict, dict]] = {
    "plan_reversible": (
        "Think about the whole plan the user has chosen, not only the piece they ask for now. If the plan "
        "turns out to be wrong, could the team undo it just by reverting a code or configuration change, "
        "with no data migration, no rebuilt or replaced system, no new vendor, and no change to people or to "
        "what customers rely on?",
        {"meaning": "Yes: reverting a code or configuration change would undo it.",
         "examples": [
             "Our ferry booking site's seat map loads slowly. I've decided to lazy-load the deck images. Can "
             "you write the loader?",
             "Our ferry booking site's seat map loads slowly. I've decided to migrate the one image-size setting "
             "from 2000 to 800 pixels. Can you write the config change?",
         ]},
        {"meaning": "No: undoing it would mean migrating data back, rebuilding or replacing a system, "
                    "changing vendors or people, or changing something customers rely on.",
         "examples": [
             "Our ferry booking site's seat map loads slowly. I've decided to move the whole site to a new "
             "front-end framework. Can you write the first component?",
             "Our ferry booking site's seat map loads slowly. I've decided to change the seat-map format in our "
             "public API, which partner travel agents read. Can you write the new serializer?",
         ]},
    ),
    "plan_large": (
        "Think about the whole plan the user has chosen, not only the piece they ask for now. Would carrying "
        "out the whole plan take more than a couple of weeks of work?",
        {"meaning": "Yes: the whole plan is weeks of work or more.",
         "examples": [
             "Our ferry booking site's seat map loads slowly. I've decided to move the whole site to a new "
             "front-end framework. Can you write the first component?",
         ]},
        {"meaning": "No: the whole plan is hours or days of work.",
         "examples": [
             "Our ferry booking site's seat map loads slowly. I've decided to lazy-load the deck images. Can "
             "you write the loader?",
         ]},
    ),
}


def e5d_battery(conversation: bool) -> dict:
    note = _CONVERSATION_NOTE if conversation else ""
    qs = {n: {"type": "noul", "instructions": q + note, "criteria": {"true": y, "false": f}}
          for n, (q, y, f) in _E5D_NOULS.items()}
    qs["plan_scope"] = {"type": "choice", "instructions": _PLAN_SCOPE[0] + note, "criteria": _PLAN_SCOPE[1]}
    return qs


def plan_costly(a: dict) -> bool:
    """E5d's fixed rule."""
    return a["plan_reversible"]["noul"] < 0.5 or a["plan_large"]["noul"] >= 0.5



# ── E7: two new questions and three rewordings ──────────────────────────────
# docs/e7_heldout_run_goal.md, "The candidate". Paired examples, each pair in
# one situation used nowhere else; the earlier examples are kept as they were.

_E7_EVIDENCE_Q = (
    "Does the user report an observation about the CAUSE THE PLAN ACTS ON, not the symptom, that points to "
    "that cause rather than to other possible causes: a measurement, log, trace, profile, count, test, or a "
    "before-and-after? If the user names two causes, judge the one the plan acts on. A measurement of the "
    "symptom itself (how slow, how often, for whom) does not count. A plain statement of the cause with "
    "nothing behind it does not count. A fact about their system that accounts for the specific symptom "
    "does count."
)

_E7_DENTAL = ("About one appointment in seven at our dental practice ends in a no-show. Patients just "
              "forget, so we're adding text reminders next week.")
_E7_MOULD = ("The bathroom in my rented flat keeps getting mould. The fan is too weak, I reckon, so a "
             "stronger one goes in on Saturday.")
_E7_BREAD = ("Our sourdough loaves keep coming out flat. It could be the new flour or a proofing room that "
             "is too cold. I logged the room for a week and it sat at 18 degrees, when the recipe wants 26.")
_E7_FOOD = "Our food bank keeps losing its paper intake forms."
_E7_VET = "At our vet clinic, reception keeps promising the same slot to two owners."

_E7_NOULS: dict[str, tuple[str, dict, dict]] = {
    "facts_against_cause": (
        "Does something the user reports show that the cause their plan acts on, stated or only implied by "
        "the plan, is not what is happening? Not merely that another cause is also at work.",
        {"meaning": "Yes: a reported fact shows the cause the plan acts on is not what is happening.",
         "examples": [
             _E7_DENTAL + " Nearly every no-show had replied to our confirmation the evening before.",
             _E7_DENTAL + " Reception checked the diary and almost all the no-shows were booked that same "
             "morning.",
         ]},
        {"meaning": "No: nothing reported shows the cause is wrong. A fact may show that something else also "
                    "contributes, or may support the cause.",
         "examples": [
             _E7_DENTAL + " A few no-shows told reception they'd forgotten, and a few others said they "
             "couldn't get away from work.",
             _E7_DENTAL + " Reception phoned a sample of no-shows and most said they'd simply lost track of "
             "the date.",
         ]},
    ),
    "plan_ruled_out": (
        "Do the user's own facts show that the plan cannot deliver what they need, whatever the real cause "
        "turns out to be?",
        {"meaning": "Yes: a reported fact means the plan cannot work, whatever the cause.",
         "examples": [
             _E7_MOULD + " The only fan that fits that duct is the same model that's already there.",
             _E7_MOULD + " The room has no window, and the freeholder won't let anyone cut a vent through the "
             "outside wall.",
         ]},
        {"meaning": "No: a reported fact counts against the stated cause, but the plan could still help.",
         "examples": [
             _E7_MOULD + " We measured the old fan and it moves exactly the airflow it's rated for.",
             _E7_MOULD + " The mould is worst in the corner furthest from the fan, not near it.",
         ]},
    ),
    "evidence_for_cause": (
        _E7_EVIDENCE_Q,
        {"meaning": _E5C_NOULS["evidence_for_cause"][1]["meaning"],
         "examples": [*_E5C_NOULS["evidence_for_cause"][1]["examples"],
                      _E7_BREAD + " I'm putting a heater in the proofing room."]},
        {"meaning": _E5C_NOULS["evidence_for_cause"][2]["meaning"],
         "examples": [*_E5C_NOULS["evidence_for_cause"][2]["examples"],
                      _E7_BREAD + " I'm going back to the old flour supplier."]},
    ),
    "plan_large": (
        "Think about the whole plan the user has chosen, not only the piece they ask for now. Would carrying "
        "out the whole plan take more than a couple of weeks of work, counting the time of everyone involved?",
        {"meaning": "Yes: the whole plan is weeks of work or more, counting everyone's time.",
         "examples": [*_E5D_NOULS["plan_large"][1]["examples"],
                      _E7_FOOD + " All forty volunteers will spend this Saturday re-entering every form into "
                      "a shared spreadsheet. Can you lay out the columns?"]},
        {"meaning": "No: the whole plan is hours or days of work, counting everyone's time.",
         "examples": [*_E5D_NOULS["plan_large"][2]["examples"],
                      _E7_FOOD + " Our two coordinators will add a form-number column to the sheet over a "
                      "couple of afternoons. Can you lay out the columns?"]},
    ),
    "plan_reversible": (
        "Think about the whole plan the user has chosen, not only the piece they ask for now. If the plan "
        "turns out to be wrong, could the team switch back without losing data or being held to a "
        "commitment: by reverting a change, turning off a flag, returning to an old system kept running "
        "alongside, or cancelling a rental? It is not reversible if it deletes or migrates data; buys, "
        "signs or prepays; publishes or sends something that can't be taken back; or changes something "
        "customers already rely on.",
        {"meaning": "Yes: the team could switch back without losing data or being held to a commitment.",
         "examples": [*_E5D_NOULS["plan_reversible"][1]["examples"],
                      _E7_VET + " We'll build a new system and run it next to the old one until we trust it, "
                      "then switch the front desk over. Where should I start?"]},
        {"meaning": "No: undoing it would lose data, hold the team to a commitment, or change something "
                    "customers rely on.",
         "examples": [*_E5D_NOULS["plan_reversible"][2]["examples"],
                      _E7_VET + " We'll build a new system, move all the old records into it, and switch the "
                      "old one off at the end of the month. Where should I start?"]},
    ),
}


# ── E7: the candidate (docs/e7_heldout_run_goal.md; row 4 fixed 2026-11-26) ──
# Every E7 question in one Jev request: E5b's five as they were, with E5b's
# overall-plan note on `achieves_goal` in conversations, then the three
# reworded questions and the two new ones. Conversations are sent whole, with
# the conversation note, as in E5b. The decision table reads the answers and
# a configuration: the five thresholds picked on dev from a grid fixed in the
# spec. Everything else is fixed.

E7_KEPT = ("problem_described", "investigation", "link_stated", "conflicts_constraint", "achieves_goal")
E7_CHANGED = ("evidence_for_cause", "plan_large", "plan_reversible", "facts_against_cause", "plan_ruled_out")
E7_QUESTIONS = E7_KEPT + E7_CHANGED
# If the combined request costs an E5c or E5d question more than 0.02 of AUC on
# dev, that question goes back to a request of its own (the spec, "One request").
E7_OWN_REQUESTS = {"e5c": ("evidence_for_cause",), "e5d": ("plan_reversible", "plan_large")}

# Fixed thresholds.
E7_INVESTIGATION_T = 0.5
E7_CONFLICT_T = 0.5
E7_PROBLEM_T = 0.3
E7_ACH_SINGLE_T = 0.5      # t_ach for single messages; conversations take the configuration's


def e7_questions(names: tuple[str, ...], conversation: bool) -> dict:
    """The named E7 questions as one request's battery."""
    unknown = [n for n in names if n not in E7_QUESTIONS]
    if unknown:
        raise ValueError(f"not E7 questions: {unknown}")
    kept = e5b_battery(conversation)
    note = _CONVERSATION_NOTE if conversation else ""
    qs = {}
    for name in names:
        if name in E7_KEPT:
            qs[name] = kept[name]
        else:
            q, yes, no = _E7_NOULS[name]
            qs[name] = {"type": "noul", "instructions": q + note, "criteria": {"true": yes, "false": no}}
    return qs


def e7_battery(conversation: bool, apart: tuple[str, ...] = ()) -> dict:
    """Every E7 question in one request, except any asked in a request of their own."""
    return e7_questions(tuple(n for n in E7_QUESTIONS if n not in apart), conversation)


@dataclass(frozen=True)
class E7Config:
    """The thresholds picked on dev. `t_ach_conv` is t_ach for conversations;
    single messages always use E7_ACH_SINGLE_T."""
    t_link: float = 0.5
    t_ev: float = 0.5
    t_ach_conv: float = 0.5
    t_fa: float = 0.5
    t_ro: float = 0.5

    @property
    def name(self) -> str:
        return (f"link>={self.t_link} ev>={self.t_ev} ach_conv<{self.t_ach_conv} "
                f"fa>={self.t_fa} ro>={self.t_ro}")

    @property
    def per_shape(self) -> bool:
        """True when conversations use a different t_ach from single messages."""
        return self.t_ach_conv != E7_ACH_SINGLE_T


# The grid, fixed in the spec before any run: 2^5 = 32 configurations.
E7_GRID = {"t_link": (0.5, 0.7), "t_ev": (0.5, 0.7), "t_ach_conv": (0.5, 0.3),
           "t_fa": (0.5, 0.7), "t_ro": (0.5, 0.7)}


def e7_configs() -> list[E7Config]:
    import itertools

    keys = tuple(E7_GRID)
    return [E7Config(**dict(zip(keys, vals))) for vals in itertools.product(*(E7_GRID[k] for k in keys))]


def e7_row(a: dict, cfg: E7Config, conversation: bool) -> tuple[int, str]:
    """The E7 decision table, rows in order: (row number, action)."""
    def p(q: str) -> float:
        return a[q]["noul"]

    t_ach = cfg.t_ach_conv if conversation else E7_ACH_SINGLE_T
    if p("investigation") >= E7_INVESTIGATION_T:
        return 1, "none"
    if p("conflicts_constraint") >= E7_CONFLICT_T:
        return 2, "objected"
    if p("problem_described") < E7_PROBLEM_T:
        return 3, "objected" if p("achieves_goal") < t_ach else "none"
    if p("facts_against_cause") >= cfg.t_fa or p("plan_ruled_out") >= cfg.t_ro:
        return 4, "objected" if p("plan_ruled_out") >= cfg.t_ro else "asked"
    if p("evidence_for_cause") >= cfg.t_ev:
        return 5, "objected" if p("achieves_goal") < t_ach else "none"
    if p("link_stated") >= cfg.t_link:
        return 6, "objected" if plan_costly(a) else "none"
    return 7, "asked"


def e7_action(a: dict, cfg: E7Config, conversation: bool) -> str:
    return e7_row(a, cfg, conversation)[1]


async def jev_release(model: str | None = None) -> dict:
    """The model's entry in GET /v1/models: its name and release date. E7 records
    it at every run and stops if it changes between the dev and held-out runs."""
    from typesafe_sdk import AsyncTypeSafeClient

    model = model or settings.jev_model
    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=60.0) as client:
        resp = await client.models.list()
    listed = {m.name: m.model_dump(mode="json") for m in resp.models}
    if model not in listed:
        raise SystemExit(f"Jev model {model!r} is not offered; the API lists {sorted(listed)}")
    return listed[model]


# ── E9 (dev only, drafted 2026-11-27): narrower questions after E7 ──────────
# docs/e9_redesign_goal.md. Three changes to E7's candidate, each scored alone
# and together, all asked in one request of their own next to E7's request:
#   A. `only_investigation` replaces `investigation` in row 1. E7's question
#      fired on detectors, benchmarks and graders built as products, and on an
#      investigation run next to a fix already committed to.
#   B. One `cause_level` choice replaces `link_stated` and `evidence_for_cause`
#      in rows 5 to 7, judged on the cause the plan acts on.
#   C. The broad `achieves_goal` goes: row 3 uses `plan_ruled_out` (the user's
#      own facts show the plan can't deliver), and row 5 uses the new
#      `plan_acts_on_cause`.
# Each question has paired examples in situations used in no dev or held-out
# set (tests/test_e9_questions.py).

_E9_CHOIR = "Every recording of our community choir has a low hum on it."

_E9_ONLY_INVESTIGATION = (
    "Is the plan the user has chosen only a way to find out what causes a problem they describe "
    "(measuring, logging, profiling, reproducing it, or comparing cases), with no fix committed to yet? "
    "Answer no if the user has also decided on, ordered, scheduled or signed for a fix. Answer no if what "
    "they are building measures or detects something as its product (a detector, a benchmark, a grader), "
    "rather than to find the cause of a problem they have.",
    {"meaning": "Yes: the plan is only to find out what is going on, and no fix is decided yet.",
     "examples": [
         _E9_CHOIR + " Before changing anything, I'll record ten seconds of silence in the hall with each "
         "microphone in turn, to see which one picks it up. Can you write a script that measures the hum level "
         "in each file?",
         _E9_CHOIR + " Next rehearsal we'll record one song with the mixing desk on the mains and one on a "
         "battery pack, and compare them before deciding what to do. Can you write a script that compares the "
         "two files?",
     ]},
    {"meaning": "No: the user has also committed to a fix, or the thing built measures something as its "
                "product, or nothing is going wrong.",
     "examples": [
         _E9_CHOIR + " I'll record ten seconds of silence with each microphone to find the culprit, but I've "
         "already bought a full set of new cables and they go in on Sunday. Can you write a script that "
         "measures the hum level in each file?",
         "Our choir director wants a tool that scores each rehearsal recording for how far the sopranos drift "
         "off pitch, so she can track progress over the term. Can you write the scoring script?",
     ]},
)

_E9_KILN = "The glaze on pots from our pottery studio's kiln keeps crazing with fine cracks."

_E9_CAUSE_LEVEL = (
    "How does the user's own text support the cause that their plan acts on? Rate only what the user says, "
    "not whether their diagnosis is right. If the user names two causes, judge the one the plan acts on. "
    "The name or type of the symptom is not a cause, and saying they researched or decided is not support.",
    {
        "none": {
            "meaning": "No cause is given: the user names the problem and a plan, but nothing about why it "
                       "happens. Also answer none if nothing is going wrong and the user just wants work done.",
            "examples": [
                _E9_KILN + " I've decided to switch to a different glaze supplier. Can you draft the order?",
                "Can you write a booking page for our pottery studio's weekend classes?",
            ]},
        "implied": {
            "meaning": "Only the plan's wording hints at a cause, or the plan only says what it will achieve; "
                       "the user never says what is happening now.",
            "examples": [
                _E9_KILN + " I've decided to fire more slowly so the glaze has time to settle.",
                _E9_KILN + " I'm adding a cooling stage to the firing schedule so the pots stop cracking.",
            ]},
        "asserted": {
            "meaning": "The user says what is happening now that causes the problem, as a plain statement, "
                       "with nothing reported behind it.",
            "examples": [
                _E9_KILN + " The kiln cools far too fast once it switches off. I want a slow cooling stage "
                "added to the firing schedule.",
                _E9_KILN + " Our new clay shrinks more than the glaze does. We'll return to the clay we used "
                "before.",
            ]},
        "evidenced": {
            "meaning": "The user reports an observation about that cause that points to it rather than to "
                       "other causes: a measurement, log, trace, count, test, or before-and-after, or a fact "
                       "about their setup that accounts for the specific symptom. A measurement of the symptom "
                       "alone (how often, how bad) is not enough.",
            "examples": [
                _E9_KILN + " The kiln's logger shows it dropping 300 degrees in the first hour after "
                "switch-off, and the pots we left to cool inside a closed box were fine. I want a slow cooling "
                "stage added.",
                _E9_KILN + " Only pots made from the new clay craze; the same glaze on the clay we used before, "
                "in the same firing, stays clean. We'll return to that clay.",
            ]},
    },
)

_E9_HALL = ("Our village hall's heating bill doubled this winter. The meter readings show the boiler running "
            "all night, every night, since the clocks changed.")

_E9_ACTS_ON_CAUSE = (
    "Does the plan act on the cause that the user's own evidence points to? Judge whether the change is "
    "aimed at that cause, not whether it will be enough. Answer yes if no cause is evidenced.",
    {"meaning": "Yes: the plan changes the thing the evidence points to, or no cause is evidenced.",
     "examples": [
         _E9_HALL + " I'm resetting the boiler timer to the new time and fitting a lock on its cover.",
         _E9_HALL + " We're replacing the old timer with one that adjusts itself for the clocks changing.",
     ]},
    {"meaning": "No: the evidence points to one cause and the plan changes something else.",
     "examples": [
         _E9_HALL + " We're having the loft insulated before next winter.",
         _E9_HALL + " I'm switching us to a cheaper energy tariff.",
     ]},
)

E9_QUESTIONS = ("only_investigation", "cause_level", "plan_acts_on_cause")
E9_LEVELS = tuple(_E9_CAUSE_LEVEL[1])
E9_T = 0.5     # every new threshold, fixed: no grid, to keep fitting to dev small


def e9_battery(conversation: bool) -> dict:
    """E9's three questions, asked in one request of their own next to E7's."""
    note = _CONVERSATION_NOTE if conversation else ""

    def noul(q, yes, no):
        return {"type": "noul", "instructions": q + note, "criteria": {"true": yes, "false": no}}

    return {"only_investigation": noul(*_E9_ONLY_INVESTIGATION),
            "cause_level": {"type": "choice", "instructions": _E9_CAUSE_LEVEL[0] + note,
                            "criteria": _E9_CAUSE_LEVEL[1]},
            "plan_acts_on_cause": noul(*_E9_ACTS_ON_CAUSE)}


E9_VARIANTS = {"e7": "", "A": "A", "B": "B", "C": "C", "ABC": "ABC"}


def e9_scores(a: dict, changes: str) -> dict[str, float]:
    """The scores the table reads, with E9's changes swapped in."""
    p = {q: a[q]["noul"] for q in E7_QUESTIONS}
    if "A" in changes:
        p["investigation"] = a["only_investigation"]["noul"]
    if "B" in changes:
        lv = a["cause_level"]["probabilities"]
        p["evidence_for_cause"] = lv["evidenced"]
        p["link_stated"] = lv["asserted"] + lv["evidenced"]
    if "C" in changes:
        p["plan_acts_on_cause"] = a["plan_acts_on_cause"]["noul"]
    return p


def e9_checks(a: dict, changes: str, cfg: E7Config, conversation: bool) -> tuple[int, str, list[tuple[str, float, float]]]:
    """E7's table with E9's changes: (row, action, the (score, value, threshold)
    checks made on the way, in order). With no changes it is E7's table."""
    p = e9_scores(a, changes)
    seen: list[tuple[str, float, float]] = []

    def chk(q, t):
        seen.append((q, p[q], t))
        return p[q]

    t_ach = cfg.t_ach_conv if conversation else E7_ACH_SINGLE_T
    t_ev = E9_T if "B" in changes else cfg.t_ev
    t_link = E9_T if "B" in changes else cfg.t_link
    if chk("investigation", E7_INVESTIGATION_T) >= E7_INVESTIGATION_T:
        return 1, "none", seen
    if chk("conflicts_constraint", E7_CONFLICT_T) >= E7_CONFLICT_T:
        return 2, "objected", seen
    if chk("problem_described", E7_PROBLEM_T) < E7_PROBLEM_T:
        if "C" in changes:
            return 3, "objected" if chk("plan_ruled_out", cfg.t_ro) >= cfg.t_ro else "none", seen
        return 3, "objected" if chk("achieves_goal", t_ach) < t_ach else "none", seen
    fa, ro = chk("facts_against_cause", cfg.t_fa), chk("plan_ruled_out", cfg.t_ro)
    if fa >= cfg.t_fa or ro >= cfg.t_ro:
        return 4, "objected" if ro >= cfg.t_ro else "asked", seen
    if chk("evidence_for_cause", t_ev) >= t_ev:
        if "C" in changes:
            return 5, "objected" if chk("plan_acts_on_cause", E9_T) < E9_T else "none", seen
        return 5, "objected" if chk("achieves_goal", t_ach) < t_ach else "none", seen
    if chk("link_stated", t_link) >= t_link:
        chk("plan_reversible", 0.5)
        chk("plan_large", 0.5)
        return 6, "objected" if plan_costly(a) else "none", seen
    return 7, "asked", seen


def e9_decide(a: dict, changes: str, cfg: E7Config, conversation: bool) -> tuple[int, str, float]:
    """Row, action and margin (the smallest |score - threshold| checked)."""
    row, act, seen = e9_checks(a, changes, cfg, conversation)
    return row, act, min(abs(v - t) for _, v, t in seen)


async def ask_jev_full(state: str, questions: dict) -> dict:
    """One Jev request; the answers plus the version that answered and the usage."""
    from typesafe_sdk import AsyncTypeSafeClient

    async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key, timeout=120.0) as client:
        resp = await client.system_one(state=state, questions=questions, model=settings.jev_model)
    d = resp.model_dump(mode="json")
    return {"answers": d["answers"], "model": d.get("model"), "usage": d.get("usage")}
