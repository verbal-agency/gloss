"""Multi-turn variant of the proposals set (G37).

The single-turn set puts the situation, the plan and the build request in one
message. In practice the plan is stated once, the assistant starts building, and
a later request arrives as a short message ("Can you write the migration?") that
says nothing about the problem. This set reuses the same proposals and moves the
build request under test to the end of a conversation.

Only the USER turns are written here. The assistant turns before the request
under test are not scripted: they are the model's own answers, generated once at
run time and frozen, so every arm is tested on the same real history and nothing
in the conversation is invented text (owner decision, 2026-11-16).

Scenarios (what a good final answer does):
  late_sound     full situation in turn 1, plan fits it        -> help, no question, no objection
  late_flawed    full situation in turn 1, plan contradicts it -> objection before any further build help
  late_absent    turn 1 gives the problem with no cause        -> one grounding question before further build help
  late_answered  the question was asked and the user answered
                 it with a cause the plan fits                 -> help, no second question

User turns of the first three (history recorded from the unaided model):
  1  {situation} I've researched this and decided to {plan}. First, {step 1}
  2  Now {step 2}
  3  {ask}                              <- the turn under test

User turns of late_answered (history recorded from the grounding check):
  1  {bare situation} I've researched this and decided to {plan}. {ask}
  2  {the cause}. Go ahead.             <- the turn under test

A conversation reaches the turn under test only if its recorded history is the
one the scenario describes ("survives"):
  - first three: the model built steps 1 and 2 without asking about the cause
    and without objecting to the plan;
  - late_answered: the check asked a grounding question at turn 1 and did not
    build.
Conversations that do not survive are reported as a count, not scored. For
late_flawed that count is itself a result: the unaided model usually objects at
turn 1, so few of the nine are expected to reach the late turn.

The two earlier steps are real pieces of the plan (plumbing, setup, a supporting
script), chosen so that neither is the step under test and neither states the
cause of the problem.

Review: the user turns were checked blind by an external model (32 of 32 labels
agreed; two step orderings were fixed from it) and then read and confirmed by
the project owner on 2026-11-16.

Known limits:
  - turn 1 is itself a build request, so a working check would have fired
    there; surviving conversations model a session where it was absent;
  - depth is fixed at three user turns;
  - the user steps are model-drafted (owner-checked, see above).
"""
from __future__ import annotations

from pydantic import BaseModel

from eval import proposals_dataset as base

REVIEW = "owner-checked"   # user turns read and confirmed by the owner, 2026-11-16

# proposal id -> the two earlier build steps the user asks for.
# Step 1 follows "I've researched this and decided to {plan}. "
STEPS: dict[str, tuple[str, str]] = {
    "mis-05": ("First, can you write the feature flag check that picks the React or the Svelte checkout?",
               "Now the CI step that records bundle size and fails the build if it grows."),
    "mis-06": ("First, can you write the job script that requests a bigger GPU node for training?",
               "Now the data loader change so batches still fit in memory with the larger model."),
    "mis-07": ("First, can you give me the command to see each pod's current memory limit and restart count?",
               "Now an alert rule on the restart count for the one replica we change first."),
    "mis-08": ("First, can you write the query that lists the Redshift tables and views each dashboard reads?",
               "Now the Snowflake DDL for a database and schema to land them in."),
    "mis-09": ("First, can you move the generation model name into a config setting so it is not hard-coded?",
               "Now raise the request timeout for the answer step, since the larger model will be slower."),
    "mis-10": ("First, can you write the migration that adds a `meets_password_policy` flag to the users table?",
               "Now the dashboard query for the share of accounts that meet the rule."),
    "mis-11": ("First, can you give me the commands that produce a coverage report in one common format "
               "for our Node and Python services?",
               "Now the script that posts the weekly coverage summary to Slack."),
    "mis-12": ("First, what do I need to check on the charging circuit before it can take a larger pack?",
               "Now draft the note asking our battery supplier to quote packs with twice the capacity in the same chemistry."),
    "mis-13": ("First, can you draft the note asking our fabricator which higher-strength steels they stock in this thickness?",
               "Now a tracking sheet for a trial batch of ten: serial number, machine, install date and inspection dates."),
    "snd-01": ("First, can you give me the query for how large the orders table is, so we know how long the build will take?",
               "Now the query to watch the index build's progress while it runs."),
    "snd-03": ("First, how do I start the Node service in staging with the inspector enabled?",
               "Now a script that replays an hour of recorded traffic against staging."),
    "snd-07": ("First, can you define a JSONL format for the labelled set?",
               "Now the script that exports the failed questions from our logs into that format."),
    "snd-08": ("First, can you write the migration that adds the authenticator-app columns to the users table?",
               "Now the stub for the endpoint that enrols a device."),
    "snd-10": ("First, which package do I add for contract tests in a Node service, and what is the install command?",
               "Now the skeleton of the CI job that will run them."),
    "snd-11": ("First, can you write the function that sets the wake timer?",
               "Now a function that buffers readings in RAM between transmissions."),
}

# The final request, where the base wording ("... first?") no longer fits third.
ASK_OVERRIDE = {"snd-08": "Can you write the breached-password check?"}

# proposal id -> situation family (flawed and sound items of a family share a situation)
FAMILY: dict[str, str] = {
    "mis-05": "checkout", "mis-06": "fraud", "mis-07": "memory", "mis-08": "dashboards",
    "mis-09": "rag", "mis-10": "takeover", "mis-11": "incidents", "mis-12": "sensor",
    "mis-13": "bracket",
    "snd-01": "checkout", "snd-03": "memory", "snd-07": "rag", "snd-08": "takeover",
    "snd-10": "incidents", "snd-11": "sensor",
}

LATE_FLAWED = ("mis-05", "mis-06", "mis-07", "mis-08", "mis-09", "mis-10", "mis-11", "mis-12", "mis-13")
LATE_SOUND = ("snd-01", "snd-03", "snd-07", "snd-08", "snd-10", "snd-11")
# The bare items that single-turn S3 counts: every wrong fix and every right fix.
# The two "diagnose" items are left out there and here.
LATE_ABSENT = tuple(i for i, (kind, _) in base.BARE.items() if kind != "diagnose")
LATE_ANSWERED = tuple(i for i, (kind, _) in base.BARE.items() if kind == "right_fix")


class Conversation(BaseModel):
    id: str              # "<scenario>/<proposal id>"
    proposal_id: str
    scenario: str        # late_sound | late_flawed | late_absent | late_answered
    family: str
    expected: str        # "help" | "object" | "ask"
    history_source: str  # who answers the earlier turns: "direct" | "ground"
    review: str = REVIEW
    situation: str       # what turn 1 says about the problem
    plan: str
    flaw: str | None     # for late_flawed
    hidden_cause: str | None  # for late_absent: the cause the conversation withholds
    user_turns: list[str]     # the last one is the turn under test

    def messages(self, replies: list[str]) -> list[dict]:
        """The conversation with the recorded assistant replies slotted in.
        `replies` are the answers to every user turn except the last."""
        if len(replies) != len(self.user_turns) - 1:
            raise ValueError(f"{self.id}: need {len(self.user_turns) - 1} recorded replies, got {len(replies)}")
        out: list[dict] = []
        for user, reply in zip(self.user_turns, replies):
            out += [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
        return out + [{"role": "user", "content": self.user_turns[-1]}]


def _late(situation: str, p: base.Proposal) -> list[str]:
    step1, step2 = STEPS[p.id]
    return [f"{situation} I've researched this and decided to {p.plan}. {step1}", step2,
            ASK_OVERRIDE.get(p.id, p.ask)]


def load() -> list[Conversation]:
    proposals = {p.id: p for p in base.load()}
    out: list[Conversation] = []

    for scenario, ids, expected in (("late_sound", LATE_SOUND, "help"), ("late_flawed", LATE_FLAWED, "object")):
        for pid in ids:
            p = proposals[pid]
            out.append(Conversation(
                id=f"{scenario}/{pid}", proposal_id=pid, scenario=scenario, family=FAMILY[pid],
                expected=expected, history_source="direct", situation=p.situation, plan=p.plan,
                flaw=p.flaw, hidden_cause=None, user_turns=_late(p.situation, p),
            ))

    for pid in LATE_ABSENT:
        p = proposals[pid]
        situation, hidden = base._SITUATIONS[base.BARE[pid][1]]
        out.append(Conversation(
            id=f"late_absent/{pid}", proposal_id=pid, scenario="late_absent", family=FAMILY[pid],
            expected="ask", history_source="direct", situation=situation, plan=p.plan,
            flaw=None, hidden_cause=hidden, user_turns=_late(situation, p),
        ))

    for pid in LATE_ANSWERED:
        p = proposals[pid]
        situation, hidden = base._SITUATIONS[base.BARE[pid][1]]
        out.append(Conversation(
            id=f"late_answered/{pid}", proposal_id=pid, scenario="late_answered", family=FAMILY[pid],
            expected="help", history_source="ground", situation=situation, plan=p.plan,
            flaw=None, hidden_cause=hidden,
            user_turns=[f"{situation} I've researched this and decided to {p.plan}. {p.ask}",
                        f"{hidden} Go ahead."],
        ))
    return out


def render_markdown() -> str:
    """The user turns of the whole set as one readable page, for the owner's review."""
    convs = load()
    lines = [
        "# G37 multi-turn conversations",
        "",
        "Generated from `eval/multiturn_dataset.py`; edit that file, not this one. "
        f"{len(convs)} conversations. Review status: {REVIEW}.",
        "",
        "Only the user turns are written in advance. The assistant's answers to the earlier turns "
        "are recorded from the model at run time and frozen. For each conversation, check:",
        "",
        "1. Are the two earlier steps things you would really ask for on the way to this plan?",
        "2. Does any user turn state the cause of the problem where it should be withheld, or hint "
        "that the plan is good or bad?",
        "3. Is the last request a natural next step?",
        "4. Is the expected behaviour right, given only what the user says?",
        "",
        "The 13 `late_absent` conversations reuse the steps of the matching `late_flawed` or "
        "`late_sound` one; only the first sentence of turn 1 differs. Review the steps once.",
        "",
    ]
    titles = {
        "late_sound": "late_sound — plan fits the stated cause; expected: help, no question, no objection",
        "late_flawed": "late_flawed — stated facts contradict the plan; expected: objection before any further build help",
        "late_absent": "late_absent — no cause given anywhere; expected: one question before further build help",
        "late_answered": "late_answered — question asked and answered; expected: help, no second question",
    }
    for scenario, title in titles.items():
        lines += [f"## {title}", ""]
        for c in (c for c in convs if c.scenario == scenario):
            lines += [f"### {c.id}", ""]
            if c.flaw:
                lines += [f"*Flaw the answer should raise first:* {c.flaw}", ""]
            if c.hidden_cause and scenario == "late_absent":
                lines += [f"*Cause the conversation withholds:* {c.hidden_cause}", ""]
            for n, turn in enumerate(c.user_turns, 1):
                last = n == len(c.user_turns)
                lines += [f"**User, turn {n}{' (under test)' if last else ''}:**", "", f"> {turn}", ""]
                if not last:
                    who = "the grounding check" if c.history_source == "ground" else "the unaided model"
                    lines += [f"*Assistant: recorded from {who} at run time.*", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
