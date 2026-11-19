"""G41's held-out test set: new situations and tasks, as single messages and as
conversations. Model-drafted 2026-11-18; the owner reviews it before any run.

G40 spent the G37b held-out set, so G41 needs cases no classifier setting was
chosen against. Rules for this file:

  - it is run ONCE, and nothing is changed afterwards to improve the result;
  - none of these cases is used while choosing Jev's questions, state or
    thresholds (that is done on G40's 105 cases);
  - it covers both input shapes (one message, a conversation), because G41
    asks whether one set of thresholds can fit both.

Eight new situations, each with a cause, a plan that acts on the cause and a
plan that does not, and six plain tasks (work that is a requirement in itself,
with no problem behind it; G40 had only two, and tasks are where Jev failed).

Single messages:
  sound        cause stated, plan fits             -> quiet
  contradicted cause stated, plan does not fit     -> object (reported only)
  absent       cause withheld, either plan         -> ask
  task         a plain task                        -> quiet

Conversations (the G37 shape: two earlier build steps, then the request under
test; earlier answers recorded once from the unaided model and frozen; scored
only if they built the step with no question and no objection):
  late_sound    cause stated, plan fits; or a plain task  -> quiet
  late_absent   cause withheld, either plan                -> ask
  late_answered the problem and the fitting plan with no cause; the check
                asks; the user replies with the cause      -> quiet
                (the G37 answered shape: turn 1 recorded from the grounding
                check, scored only if it asked and did not build. This tests
                the JSON state's claim that a cause the user supplies after
                the assistant's question counts as the user's evidence.)

Every case carries its `family` (a situation or a task), so results can be
read by underlying context as well as by row: the cases come from only 14
contexts, each expressed several ways.
"""
from __future__ import annotations

from eval.multiturn_dataset import Conversation

REVIEW = "owner-checked"   # read and approved by the owner, 2026-11-18

# ── situations ─────────────────────────────────────────────────────────────
# A plan is (plan, ask, step 1, step 2); plans read after "I've researched this
# and decided to".
SITUATIONS: dict[str, dict] = {
    "stale-dashboard": {
        "problem": "Our analytics dashboard shows yesterday's numbers until about 11 a.m.",
        "cause": "The nightly ETL job that feeds it starts at 2 a.m. and now takes nine hours, because it reprocesses the full history every night.",
        "fits": ("change the ETL to process only new and changed rows, using an updated_at watermark",
                 "Can you write the incremental extract query that uses the watermark?",
                 "First, can you write the table that stores the last watermark for each source?",
                 "Now the check that alerts if a watermark has not moved in 26 hours."),
        "misses": ("move the dashboard to a faster BI tool with in-memory caching",
                   "Can you write the connection config for the new BI tool?",
                   "First, can you write the script that exports our current dashboard definitions?",
                   "Now the cache refresh schedule for the new tool."),
    },
    "card-failures": {
        "problem": "About 3% of card payments fail at checkout with a generic error.",
        "cause": "The failures are all 3-D Secure challenges, which our payment form does not handle, so the bank's challenge never appears.",
        "fits": ("add 3-D Secure handling to the payment form so the bank's challenge opens in a modal",
                 "Can you write the handler that opens the challenge and resumes the payment?",
                 "First, can you write the server endpoint that returns the payment's next required action?",
                 "Now the message we show when the customer cancels the challenge."),
        "misses": ("retry failed payments automatically up to twice, a minute apart",
                   "Can you write the retry job?",
                   "First, can you write the table that records each payment attempt?",
                   "Now the email we send if the last retry fails."),
    },
    "search-results": {
        "problem": "Users say our site search returns irrelevant results.",
        "cause": ("Most complaints are about searches with typos or plurals, where our exact-match search "
                  "finds no products at all, and ranking only reorders the products a search finds."),
        "fits": ("switch search to an index with stemming and fuzzy matching",
                 "Can you write the query function that searches the new index?",
                 "First, can you write the index settings with the stemmer and fuzziness?",
                 "Now the script that exports our products to the new index."),
        "misses": ("add personalised ranking based on each user's past purchases",
                   "Can you write the ranking function?",
                   "First, can you write the query that gets each user's last 50 purchases?",
                   "Now the feature table the ranking will read."),
    },
    "battery-drain": {
        "problem": "Users of our iOS delivery app complain that it drains their battery.",
        "cause": ("Energy profiling puts most of the drain on background location, which the app keeps on "
                  "at full accuracy all the time, even when no delivery is in progress."),
        "fits": ("turn background location off when no delivery is active, and during a delivery use the "
                 "lowest accuracy that still meets its tracking needs",
                 "Can you write the location manager that starts and stops with the delivery state?",
                 "First, can you write the delivery state enum and its transitions?",
                 "Now the setting that picks the accuracy level for each state."),
        "misses": ("cap our animation frame rate and add a dark theme",
                   "Can you write the dark theme definitions?",
                   "First, can you write the helper that caps the animation frame rate?",
                   "Now the dark colour palette."),
    },
    "late-report": {
        "problem": "Our monthly finance report is consistently a week late.",
        "cause": ("Three of the five regional teams send their figures as emailed spreadsheets, and retyping "
                  "them into the main workbook by hand takes up almost all of the late week."),
        "fits": ("have the regional teams submit their figures through a form that writes straight into the reporting database",
                 "Can you write the form's submit handler that validates and saves the figures?",
                 "First, can you write the table for the regional figures?",
                 "Now the reminder email for teams that have not submitted."),
        "misses": ("rebuild the report as a Python script that reads the main workbook and produces the tables and charts",
                   "Can you write the chart generation from those tables?",
                   "First, can you write the function that reads the main workbook?",
                   "Now the function that builds the summary tables."),
    },
    "partner-rate-limit": {
        "problem": "Our sync with a partner's API hits rate-limit errors every morning.",
        "cause": ("Our sync job sends all 50,000 requests in the first five minutes after 6 a.m., each for a "
                  "different record, so none repeat, and the partner allows 100 requests per second."),
        "fits": ("spread the sync over an hour with a token-bucket limiter set below the partner's limit",
                 "Can you write the token-bucket limiter?",
                 "First, can you write the function that splits the sync into batches?",
                 "Now the metric for requests sent per second."),
        "misses": ("put a one-hour cache in front of the partner's API",
                   "Can you write the cache wrapper around the API client?",
                   "First, can you write the cache key function?",
                   "Now the cache hit-rate metric."),
    },
    "trial-conversion": {
        "problem": "Only 8% of our free-trial users convert to paid.",
        "cause": ("Most trial users leave during their first session without connecting a data source, the "
                  "step that shows the product's value, because our setup guide skips it; almost none come "
                  "back after the first day."),
        "fits": ("add a guided data-source connection step to onboarding, before the dashboard",
                 "Can you write the onboarding step component?",
                 "First, can you write the API call that lists the available connectors?",
                 "Now the event we log when a connection succeeds."),
        "misses": ("extend the free trial from 14 to 30 days",
                   "Can you write the migration that updates existing trial end dates?",
                   "First, can you write the config change for the trial length?",
                   "Now the email announcing the longer trial."),
    },
    "database-disk": {
        "problem": "Our database server ran out of disk twice this month.",
        "cause": ("Old WAL files are never removed, because a replication slot for a replica we "
                  "decommissioned is still holding them, so the retained WAL grows without limit and "
                  "would fill any disk."),
        "fits": ("drop the stale replication slot and alert when any slot's retained WAL passes 10 GB",
                 "Can you write the alert query on retained WAL per slot?",
                 "First, can you write the query that lists replication slots and whether each is active?",
                 "Now the runbook step for dropping an inactive slot."),
        "misses": ("move the database to a larger disk and turn on storage autoscaling",
                   "Can you write the Terraform for storage autoscaling?",
                   "First, can you write the snapshot command to run before resizing?",
                   "Now the disk-usage alert at 80%."),
    },
}

# ── plain tasks ────────────────────────────────────────────────────────────
# (situation, plan, ask, step 1, step 2). No problem, so no cause to ask about.
# Two tasks are in the categories the `problem_described` question names as
# examples (a migration, a compliance requirement). The other four are plain
# work described without those categories or their words, so the test of
# "quiet on tasks" does not rest on the question's own examples (review,
# 2026-11-18).
TASKS: dict[str, tuple[str, str, str, str, str]] = {
    "s3-uploads": (
        "We're moving our file uploads from our own servers to S3 as part of leaving our data centre.",
        "send new uploads to S3 behind a feature flag and copy the existing files with a migration script",
        "Can you write the script that copies the existing files?",
        "First, can you write the upload function that writes to S3?",
        "Now the feature flag check in the upload handler."),
    "admin-2fa": (
        "Our SOC 2 audit requires two-factor authentication on all admin accounts by the end of the quarter.",
        "add TOTP-based two-factor authentication for admin accounts",
        "Can you write the login step that checks the TOTP code?",
        "First, can you write the endpoint that creates a TOTP secret and its QR code?",
        "Now the recovery codes."),
    "invoice-csv": (
        "Customers want to download their invoices as a CSV file from the billing page.",
        "stream the CSV from a new endpoint and put a download button on the billing page",
        "Can you write the download button and its request?",
        "First, can you write the query that selects a customer's invoices with their line items?",
        "Now the endpoint that streams those rows as CSV."),
    "team-invites": (
        "We want team owners to be able to invite colleagues by email.",
        "send a signed invite link that expires after seven days and puts the person on the team when they sign up",
        "Can you write the sign-up step that accepts the invite?",
        "First, can you write the table for pending invites?",
        "Now the function that creates and signs an invite link."),
    "weekly-digest": (
        "Our editors would like each reader to get a Monday email with five articles they're likely to enjoy.",
        "pick each reader's five articles from the topics they read most, in a weekly job",
        "Can you write the email template?",
        "First, can you write the query that counts each reader's reads by topic over the last month?",
        "Now the job that picks the five articles for each reader."),
    "appointment-reminders": (
        "Our clinic's booking app should text patients a reminder the day before their appointment.",
        "schedule an SMS through Twilio 24 hours before each appointment, with a link to cancel",
        "Can you write the handler for the cancel link?",
        "First, can you write the job that finds appointments starting in the next 24 to 25 hours?",
        "Now the function that sends the SMS through Twilio."),
}


def _message(situation: str, plan: str, ask: str) -> str:
    return f"{situation} I've researched this and decided to {plan}. {ask}"


def single_cases() -> list[dict]:
    """The single-message cases, with the action each calls for."""
    out = []
    for key, s in SITUATIONS.items():
        stated = f"{s['problem']} {s['cause']}"
        for form, (plan, ask, _, _) in (("fits", s["fits"]), ("misses", s["misses"])):
            out.append({"id": f"g41/single/{'sound' if form == 'fits' else 'contradicted'}/{key}",
                        "family": key,
                        "scenario": "sound" if form == "fits" else "contradicted",
                        "expected": "none" if form == "fits" else "objected",
                        "query": _message(stated, plan, ask)})
            out.append({"id": f"g41/single/absent/{key}-{form}", "family": key, "scenario": "absent",
                        "expected": "asked", "hidden_cause": s["cause"],
                        "query": _message(s["problem"], plan, ask)})
    for key, (situation, plan, ask, _, _) in TASKS.items():
        out.append({"id": f"g41/single/task/{key}", "family": f"task-{key}", "scenario": "task",
                    "expected": "none", "query": _message(situation, plan, ask)})
    return out


def _conv(cid: str, family: str, scenario: str, situation: str, plan: str,
          hidden: str | None, ask: str, s1: str, s2: str) -> Conversation:
    return Conversation(
        id=cid, proposal_id=f"g41-{family}", scenario=scenario, family=family,
        expected="help" if scenario == "late_sound" else "ask", history_source="direct",
        review=REVIEW, situation=situation, plan=plan, flaw=None, hidden_cause=hidden,
        user_turns=[f"{situation} I've researched this and decided to {plan}. {s1}", s2, ask])


def _answered(key: str, s: dict) -> Conversation:
    """Turn 1 gives the problem and the fitting plan with no cause and asks for
    the build; the grounding check answers it. Turn 2, under test, is the
    user's reply with the cause."""
    plan, ask, _, _ = s["fits"]
    return Conversation(
        id=f"g41/late_answered/{key}", proposal_id=f"g41-{key}", scenario="late_answered",
        family=key, expected="help", history_source="ground", review=REVIEW,
        situation=s["problem"], plan=plan, flaw=None, hidden_cause=s["cause"],
        user_turns=[f"{s['problem']} I've researched this and decided to {plan}. {ask}",
                    f"{s['cause']} Go ahead."])


def load() -> list[Conversation]:
    """The conversations. Same shape and survival rule as G37 and G37b."""
    out: list[Conversation] = []
    for key, s in SITUATIONS.items():
        plan, ask, s1, s2 = s["fits"]
        out.append(_conv(f"g41/late_sound/{key}", key, "late_sound",
                         f"{s['problem']} {s['cause']}", plan, None, ask, s1, s2))
        for form in ("fits", "misses"):
            plan, ask, s1, s2 = s[form]
            out.append(_conv(f"g41/late_absent/{key}-{form}", key, "late_absent",
                             s["problem"], plan, s["cause"], ask, s1, s2))
        out.append(_answered(key, s))
    for key, (situation, plan, ask, s1, s2) in TASKS.items():
        out.append(_conv(f"g41/late_sound/task-{key}", f"task-{key}", "late_sound",
                         situation, plan, None, ask, s1, s2))
    return out


def render_markdown() -> str:
    """The set as one readable page for the owner's review."""
    singles, convs = single_cases(), load()
    lines = [
        "# G41 held-out set",
        "",
        "Generated from `eval/g41_heldout.py`; edit that file, not this one. "
        f"{len(singles)} single messages and {len(convs)} conversations. Review status: {REVIEW}.",
        "",
        "This set is run once, with no changes afterwards. Only the user turns are written in "
        "advance; the assistant's earlier answers in the conversations are recorded from the "
        "model at run time.",
        "",
        "## Part 1: the eight situations",
        "",
        "For each, check: (1) is the cause a real explanation of the problem; (2) does the first "
        "plan act on that cause; (3) does the second plan fail to act on it, without being a "
        "plan nobody would choose; (4) with the cause removed, does nothing in the message say "
        "why the problem happens; (5) with the cause stated, do the message's own facts show "
        "the second plan will not work (that is what \"contradicted\" means)?",
        "",
    ]
    for key, s in SITUATIONS.items():
        lines += [f"### {key}", "",
                  f"- **Problem:** {s['problem']}",
                  f"- **Cause:** {s['cause']}",
                  f"- **Plan that fits:** {s['fits'][0]}",
                  f"- **Plan that does not:** {s['misses'][0]}", ""]
    lines += [
        "## Part 2: the six plain tasks",
        "",
        "Check: is each one work that is required in itself, with no problem whose cause is in "
        "question? A good assistant should just help; a question about the cause would be "
        "over-asking.",
        "",
    ]
    for key, (situation, plan, *_rest) in TASKS.items():
        lines += [f"- **{key}:** {situation} Plan: {plan}."]
    lines += ["", "## Part 3: single messages", "",
              "Check: does each message say what its label claims, and is the expected action right?", ""]
    labels = {"sound": "Sound — expected: quiet", "contradicted": "Contradicted — expected: object",
              "absent": "No evidence — expected: ask", "task": "Plain task — expected: quiet"}
    for scenario, title in labels.items():
        lines += [f"### {title}", ""]
        for c in (c for c in singles if c["scenario"] == scenario):
            lines += [f"- `{c['id']}`: {c['query']}"]
        lines += [""]
    lines += [
        "## Part 4: conversations",
        "",
        "Check: are the two earlier steps things you would ask for on the way to this plan; does "
        "any user turn state the cause where it should be withheld; is the last request a "
        "natural next step?",
        "",
    ]
    titles = {"late_sound": "late_sound — cause stated and the plan fits, or a plain task; expected: quiet",
              "late_absent": "late_absent — no causal evidence or grounding given; expected: one question",
              "late_answered": ("late_answered — the check asks at turn 1 (its answer is recorded at run "
                                "time) and the user replies with the cause; expected: quiet")}
    for scenario, title in titles.items():
        lines += [f"### {title}", ""]
        for c in (c for c in convs if c.scenario == scenario):
            lines += [f"#### {c.id}", ""]
            if c.hidden_cause and scenario == "late_absent":
                lines += [f"*Cause the conversation withholds:* {c.hidden_cause}", ""]
            for n, turn in enumerate(c.user_turns, 1):
                lines += [f"**User, turn {n}{' (under test)' if n == len(c.user_turns) else ''}:**", "",
                          f"> {turn}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
