"""Held-out multi-turn conversations (G37a/G37b). Owner-checked 2026-11-18.

G37 ended in a stop, one conversation short of its mark, and its two misses had
one cause: the classifier judged a late request on its own and called it a task.
One sentence was added to fix that. A fix written after seeing six conversations
will usually pass those six, so this set exists to test it on conversations it
was NOT written against. Rules for this file:

  - it is run ONCE, and nothing is changed afterwards to improve the result;
  - none of these conversations was used while writing or adjusting the check;
  - it is weighted toward plans that ADD A CAPABILITY, the kind that failed.

Same shape and same survival rule as eval/multiturn_dataset.py: the user states
the situation and plan and asks for two earlier build steps, then makes the
request under test; the assistant's earlier answers are recorded from the
unaided model and frozen; a conversation is scored only if those answers built
the step with no question about the cause and no objection to the plan.

Two scored scenarios:
  late_sound   the cause is stated in turn 1 and the plan fits it, or the work
               is a task with no problem behind it  -> help, no question, no objection
  late_absent  turn 1 gives the problem with no cause -> one question before
               further build help (whether the plan would have been right or not)

Sources:
  reused   proposals from eval/proposals_dataset.py that the first multi-turn
           set did not use (owner-checked or model-reviewed there)
  new      eight situations drafted for this set, each with a plan that fits the
           cause and a plan that does not. Model-drafted, owner-checked.

Left out on purpose: `snd-12` (its "sound" label was already contested in G36),
`snd-06` (its direct answer has come back empty in three runs), and flawed plans
with the cause stated (G37 found the unaided model objects at turn 1 every time,
so none reaches the late turn).
"""
from __future__ import annotations

from eval import proposals_dataset as base
from eval.multiturn_dataset import Conversation

REVIEW = "owner-checked"   # read and confirmed by the owner, 2026-11-18

# ── reused proposals ────────────────────────────────────────────────────────
# id -> (bare situation, hidden cause, step 1, step 2). The stated situation,
# plan and ask come from the proposal itself.
REUSED: dict[str, tuple[str, str, str, str]] = {
    "snd-02": ("We sometimes create duplicate orders.",
               "The duplicates are created when a client retries a request after a network timeout.",
               "First, can you write the client helper that generates a key and attaches it as a request header?",
               "Now the cleanup job that deletes keys older than a day."),
    "snd-13": ("Our worker service falls behind on its job queue every afternoon.",
               "CPU on the workers stays around 20%, the jobs are independent, and adding workers by hand raised throughput in step.",
               "First, can you write the exporter that publishes queue depth as a metric?",
               "Now a dashboard panel that shows queue depth next to worker count."),
    "snd-14": ("Our payments service has stretches where its error rate stays high for several minutes.",
               "They start when the bank's API slows down and continue after the bank has recovered.",
               "First, can you write the function that generates the idempotency key for a payment attempt?",
               "Now the metrics we should emit for the bank call's latency and failures."),
    "snd-15": ("Our product API's 99th percentile latency is two seconds, against a median of 40 ms.",
               "The slow requests cluster in the minute after each deploy and after the hourly cache flush.",
               "First, can you write the docker-compose service for a shared Redis the API can use in development?",
               "Now a helper that adds random jitter to a cache entry's expiry time."),
    # A plan that does not fit the cause; used only with the cause withheld.
    "mis-15": ("Our product API's 99th percentile latency is two seconds, against a median of 40 ms.",
               "The slow requests cluster in the minute after each deploy and after the hourly cache flush.",
               "First, can you write the Terraform for two read replicas of the product database?",
               "Now the health check the pooler should use for each replica."),
}
REUSED_STATED = ("snd-02", "snd-13", "snd-14", "snd-15")

# Tasks: work that is a requirement in itself. No cause to ask about, so the
# expected behaviour is help with no question. id -> (step 1, step 2).
TASKS: dict[str, tuple[str, str]] = {
    "snd-05": ("First, can you write the query that lists every index and constraint on the old column?",
               "Now the feature flag that switches reads between the old column and the new one."),
    "snd-09": ("First, can you write the query that finds the primary key range and the row count?",
               "Now a query to watch replica lag while the backfill runs."),
}

# ── new situations ──────────────────────────────────────────────────────────
# Each: the problem, the cause (stated in one form, withheld in the other), a
# plan that fits the cause and a plan that does not. A plan is
# (plan, ask, step 1, step 2); plans read after "I've researched this and decided to".
NEW: dict[str, dict] = {
    "flaky-ci": {
        "problem": "Our CI fails about one run in five and passes when retried.",
        "cause": "The failures are all in tests that share one Postgres database and run in parallel.",
        "fits": ("give each parallel test worker its own database schema, created at the start of the run",
                 "Can you write the fixture that creates and selects the schema for a worker?",
                 "First, can you write the function that builds a schema name from the worker id?",
                 "Now the teardown that drops the schemas when the run ends."),
        "misses": ("add automatic retry of failed tests, up to three attempts, and report the retry rate each week",
                   "Can you write the retry configuration for pytest?",
                   "First, can you write the script that counts retried tests from the JUnit report?",
                   "Now the weekly job that posts that count to Slack."),
    },
    "support-queue": {
        "problem": "Our support queue has doubled in three months.",
        "cause": "Most of the new tickets are password-reset requests, and they began when we removed the self-service reset page.",
        "fits": ("bring back self-service password reset by emailed link",
                 "Can you write the endpoint that issues the reset token and sends the email?",
                 "First, can you write the migration for a table of reset tokens with an expiry?",
                 "Now the email template for the reset link."),
        "misses": ("add a chatbot to the help page that answers common questions from our help articles",
                   "Can you write the retrieval step that finds the relevant help articles for a question?",
                   "First, can you write the script that exports our help articles to JSON?",
                   "Now the markup for the chat box on the help page."),
    },
    "lost-edits": {
        "problem": "Users report losing edits in our document editor.",
        "cause": "It happens when two people edit the same paragraph at once: whoever saves last overwrites the other.",
        "fits": ("add a version check on save that rejects a stale write and shows both versions for the user to merge",
                 "Can you write the save handler with the version check?",
                 "First, can you write the migration that adds a version number to each paragraph?",
                 "Now the API error response for a rejected save."),
        "misses": ("add autosave every five seconds with a local draft kept in the browser",
                   "Can you write the autosave hook?",
                   "First, can you write the helper that stores a draft in localStorage keyed by document id?",
                   "Now the 'saved just now' indicator component."),
    },
    "signup-drop": {
        "problem": "Our signup completion rate dropped from 60% to 35% last month.",
        "cause": "The drop began the day we made phone verification mandatory, and most people who abandon do so on that step.",
        "fits": ("make phone verification optional at signup and require it before the first payment instead",
                 "Can you write the check that blocks a first payment until the phone is verified?",
                 "First, can you write the migration that adds a phone_verified_at column to users?",
                 "Now the banner that reminds unverified users to verify."),
        "misses": ("add a progress bar to the signup flow and a sign-in-with-Google option",
                   "Can you write the OAuth callback handler?",
                   "First, can you write the progress bar component for the four signup steps?",
                   "Now the migration that adds a google_id column to users."),
    },
    "missed-incidents": {
        "problem": "Our on-call engineers have missed two real incidents this quarter.",
        "cause": "They get about 200 pages a week, and nearly all of them come from one disk-usage alert that fires at 70%.",
        "fits": ("add severity-based routing so that only critical alerts page and the rest open tickets, and move the disk-usage alert to the ticket tier",
                 "Can you write the Alertmanager routing config?",
                 "First, can you write the script that lists every alert rule with its current severity label?",
                 "Now the ticket template for alerts that do not page."),
        "misses": ("add a second on-call engineer as backup, with an escalation that pages them after ten minutes",
                   "Can you write the escalation policy?",
                   "First, can you write the rota generator for a primary and a backup?",
                   "Now the calendar export for the rota."),
    },
    "android-crashes": {
        "problem": "Our Android app's crash rate tripled after the last release.",
        "cause": "Nearly all the crashes are out-of-memory errors on the photo gallery screen, on devices with 2 GB of RAM or less.",
        "fits": ("load gallery images downsampled to the view size and keep them in a memory cache with a fixed upper bound",
                 "Can you write the image loader with downsampling?",
                 "First, can you write the function that works out the sample size from the view and image dimensions?",
                 "Now the bounded cache class."),
        "misses": ("add a global handler that catches uncaught exceptions, logs them, and restarts the current screen",
                   "Can you write the uncaught-exception handler?",
                   "First, can you write the logger that records the screen name and device model?",
                   "Now the function that restarts the current activity."),
    },
    "slow-build": {
        "problem": "Our CI build takes 40 minutes.",
        "cause": "About 30 of those minutes go on downloading and compiling dependencies, which change perhaps once a month.",
        "fits": ("add a dependency cache keyed on the hash of the lockfile",
                 "Can you write the cache step for GitHub Actions?",
                 "First, can you write the command that prints a hash of the lockfile?",
                 "Now a step that reports whether the cache was hit at the end of the job."),
        "misses": ("split the test suite across four parallel runners",
                   "Can you write the matrix configuration for the four runners?",
                   "First, can you write the script that splits test files into four balanced groups by past duration?",
                   "Now the step that merges the four coverage reports."),
    },
    "invoice-email": {
        "problem": "Customers say they are not receiving our invoice emails.",
        "cause": "Our sending domain has no SPF or DKIM records, and the test messages we sent landed in spam.",
        "fits": ("publish SPF and DKIM records for the sending domain and add a DMARC policy in monitoring mode",
                 "Can you write the three DNS records?",
                 "First, can you write the command that generates the DKIM key pair?",
                 "Now the script that checks the records have propagated."),
        "misses": ("add an SMS notification with a link to the invoice",
                   "Can you write the function that sends the SMS through our provider's API?",
                   "First, can you write the migration that adds an sms_opt_in flag to customers?",
                   "Now the short-link generator for invoice URLs."),
    },
}


def _turns(situation: str, plan: str, step1: str, step2: str, ask: str) -> list[str]:
    return [f"{situation} I've researched this and decided to {plan}. {step1}", step2, ask]


def _conv(cid: str, pid: str, scenario: str, family: str, situation: str, plan: str,
          hidden: str | None, turns: list[str]) -> Conversation:
    return Conversation(
        id=cid, proposal_id=pid, scenario=scenario, family=family,
        expected="help" if scenario == "late_sound" else "ask", history_source="direct",
        review=REVIEW, situation=situation, plan=plan, flaw=None, hidden_cause=hidden, user_turns=turns)


def load() -> list[Conversation]:
    proposals = {p.id: p for p in base.load()}
    out: list[Conversation] = []

    for pid, (bare, hidden, s1, s2) in REUSED.items():
        p = proposals[pid]
        if pid in REUSED_STATED:
            out.append(_conv(f"held/late_sound/{pid}", pid, "late_sound", pid, p.situation, p.plan,
                             None, _turns(p.situation, p.plan, s1, s2, p.ask)))
        out.append(_conv(f"held/late_absent/{pid}", pid, "late_absent", pid, bare, p.plan,
                         hidden, _turns(bare, p.plan, s1, s2, p.ask)))

    for pid, (s1, s2) in TASKS.items():
        p = proposals[pid]
        out.append(_conv(f"held/late_sound/task-{pid}", pid, "late_sound", f"task-{pid}", p.situation,
                         p.plan, None, _turns(p.situation, p.plan, s1, s2, p.ask)))

    for family, item in NEW.items():
        problem, cause = item["problem"], item["cause"]
        plan, ask, s1, s2 = item["fits"]
        stated = f"{problem} {cause}"
        out.append(_conv(f"held/late_sound/{family}", f"new-{family}", "late_sound", family, stated,
                         plan, None, _turns(stated, plan, s1, s2, ask)))
        out.append(_conv(f"held/late_absent/{family}-fits", f"new-{family}", "late_absent", family,
                         problem, plan, cause, _turns(problem, plan, s1, s2, ask)))
        plan, ask, s1, s2 = item["misses"]
        out.append(_conv(f"held/late_absent/{family}-misses", f"new-{family}", "late_absent", family,
                         problem, plan, cause, _turns(problem, plan, s1, s2, ask)))
    return out


def render_markdown() -> str:
    """The set as one readable page for the owner's review."""
    convs = load()
    lines = [
        "# G37a held-out conversations",
        "",
        "Generated from `eval/multiturn_heldout.py`; edit that file, not this one. "
        f"{len(convs)} conversations. Review status: {REVIEW}.",
        "",
        "This set is run once, with no changes afterwards. Only the user turns are written in "
        "advance; the assistant's earlier answers are recorded from the model at run time.",
        "",
        "## Part 1: the eight new situations",
        "",
        "These are model-drafted. For each, check: (1) is the cause a real explanation of the "
        "problem; (2) does the first plan act on that cause; (3) does the second plan fail to act "
        "on it, without being a silly plan nobody would choose; (4) with the cause removed, is it "
        "true that nothing in the message says why the problem happens?",
        "",
    ]
    for family, item in NEW.items():
        lines += [f"### {family}", "",
                  f"- **Problem:** {item['problem']}",
                  f"- **Cause:** {item['cause']}",
                  f"- **Plan that fits:** {item['fits'][0]}",
                  f"- **Plan that does not:** {item['misses'][0]}", ""]
    lines += [
        "## Part 2: the conversations",
        "",
        "For each, check: are the two earlier steps things you would ask for on the way to this "
        "plan; does any user turn state the cause where it should be withheld; is the last "
        "request a natural next step; is the expected behaviour right?",
        "",
    ]
    titles = {"late_sound": "late_sound — cause stated and the plan fits, or a task; expected: help, no question, no objection",
              "late_absent": "late_absent — no cause given anywhere; expected: one question before further build help"}
    for scenario, title in titles.items():
        lines += [f"### {title}", ""]
        for c in (c for c in convs if c.scenario == scenario):
            lines += [f"#### {c.id}", ""]
            if c.hidden_cause:
                lines += [f"*Cause the conversation withholds:* {c.hidden_cause}", ""]
            for n, turn in enumerate(c.user_turns, 1):
                lines += [f"**User, turn {n}{' (under test)' if n == len(c.user_turns) else ''}:**", "",
                          f"> {turn}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
