"""G43's held-out test set (E6). Model-drafted 2026-11-19; the owner reviews it,
and labels the four debatable cases, before any run.

Spec: docs/v3_spike.md, "E6". Every case is written in the formal frame: what the
plan must deliver (R), what the user states about their world (D), the plan (S),
the expected verdict, and the kind of doubt (none / undercutting / rebutting /
undermining). It adds what the spent pool lacks: objection in conversations,
requirement-bound tasks, debatable diagnoses, weak engineering, investigations.

Run once; nothing is changed afterwards.
"""
from __future__ import annotations

from eval import g41_heldout as base
from eval.multiturn_dataset import Conversation

REVIEW = "drafted"   # becomes "owner-checked" after the owner's review
TAG = "g43"

# A plan is (plan, ask, step 1, step 2); plans read after "I've researched this
# and decided to".

# ── situations: a problem, its cause, a plan that fits and one that misses ──
SITUATIONS: dict[str, dict] = {
    "video-uploads": {
        "problem": "Video uploads larger than about 1 GB fail with '413 Request Entity Too Large'.",
        "cause": "Our load balancer caps request bodies at 1 GB, and the app sends each video in a single request.",
        "fits": ("upload videos in 50 MB parts with a resumable multipart upload straight to object storage",
                 "Can you write the call that completes the upload once every part is in?",
                 "First, can you write the endpoint that starts a multipart upload and returns a signed URL for each part?",
                 "Now the client code that uploads the parts in parallel."),
        "misses": ("move the upload service to an instance with twice the memory",
                   "Can you write the deploy script that moves the service to the new instance?",
                   "First, can you write the Terraform for the larger instance?",
                   "Now the memory alert for it."),
    },
    "queue-backlog": {
        "problem": "Our order-confirmation queue builds a backlog of several thousand messages every weekday lunchtime.",
        "cause": ("Each confirmation calls the tax service, which takes about two seconds a call at lunchtime, and "
                  "our consumer handles one message at a time."),
        "fits": ("run the consumer with 20 concurrent workers, well inside the tax service's limit of 50 concurrent calls",
                 "Can you write the worker pool that processes messages concurrently?",
                 "First, can you write the config for the number of workers?",
                 "Now the metric for messages in flight."),
        "misses": ("move the queue from RabbitMQ to Kafka and keep a single consumer that handles one message at a time",
                   "Can you write the Kafka consumer for order confirmations?",
                   "First, can you write the topic configuration?",
                   "Now the producer change that publishes to Kafka."),
    },
    "session-logins": {
        "problem": "About one login in fifty fails with 'invalid session' right after the password is accepted.",
        "cause": ("Each app server keeps sessions in its own memory. The load balancer keeps a user on one server, "
                  "but autoscaling replaces servers through the day, and the failures are logins whose server was "
                  "removed within the next minute."),
        "fits": ("store sessions in Redis so every server reads the same ones",
                 "Can you write the session middleware that reads and writes Redis?",
                 "First, can you write the Redis connection settings?",
                 "Now the session expiry handling."),
        "misses": ("raise the session timeout from 30 minutes to 8 hours",
                   "Can you write the config change for the timeout?",
                   "First, can you write the setting that reads the timeout from the environment?",
                   "Now the note for the security review."),
    },
    "revenue-mismatch": {
        "problem": "Our monthly revenue report disagrees with the payment provider's totals by a few hundred dollars every month.",
        "cause": ("Refunds issued in the provider's dashboard are never sent to us, so our database still counts "
                  "those payments as revenue."),
        "fits": ("subscribe to the provider's refund webhook and record each refund against its payment",
                 "Can you write the webhook handler that records the refund?",
                 "First, can you write the refunds table?",
                 "Now the signature check for the webhook."),
        "misses": ("round every amount to two decimal places before summing",
                   "Can you write the summing function with the rounding?",
                   "First, can you write the helper that rounds amounts?",
                   "Now the unit tests for the rounding."),
    },
    "warehouse-sync": {
        "problem": "Our weekly sync to the data warehouse fails with 'No space left on device' on the sync worker.",
        "cause": ("The sync writes every table to the worker's local disk before uploading, and the largest table "
                  "alone is now bigger than the worker's 50 GB disk."),
        "fits": ("stream each table straight to object storage instead of writing it to local disk first",
                 "Can you write the streaming upload for one table?",
                 "First, can you write the query that reads a table in chunks?",
                 "Now the retry for a failed chunk."),
        "misses": ("compress each table file with zstd instead of gzip after it has been written to the worker's disk",
                   "Can you write the zstd compression step?",
                   "First, can you write the function that picks the compression level?",
                   "Now the check that the warehouse can read zstd files."),
    },
    "slow-quotes": {
        "problem": "Our insurance quote page takes about six seconds to load.",
        "cause": "The page asks each of our four insurers for a rate one after another, and each call takes about 1.4 seconds.",
        "fits": ("call the four insurers in parallel with a two-second timeout each",
                 "Can you write the function that gathers the four rates in parallel?",
                 "First, can you write the client for one insurer with the timeout?",
                 "Now the fallback message when an insurer times out."),
        "misses": ("serve the page's images and scripts from a CDN",
                   "Can you write the CDN configuration?",
                   "First, can you write the build step that uploads assets to the CDN?",
                   "Now the cache headers."),
    },
    "duplicate-emails": {
        "problem": "Some customers receive the same shipping email two or three times.",
        "cause": "Our email job runs on three servers on the same cron schedule, and each server sends every pending email.",
        "fits": ("run the email job as one scheduled job that takes a database lock, so only one instance sends at a time",
                 "Can you write the job's lock acquisition?",
                 "First, can you write the scheduled job definition?",
                 "Now the alert if the job has not run for an hour."),
        "misses": ("switch to an email provider with better deliverability",
                   "Can you write the client for the new provider?",
                   "First, can you write the DNS records the new provider needs?",
                   "Now the bounce handling."),
    },
    "stale-prices": {
        "problem": "Customers sometimes see an old price in the cart after we change it in the admin.",
        "cause": ("The product page and cart read prices from a cache that keeps entries for 24 hours, and changing "
                  "a price in the admin does not clear it."),
        "fits": ("clear a product's cached price whenever it is changed in the admin",
                 "Can you write the cache invalidation call in the admin save handler?",
                 "First, can you write the cache key function for a product's price?",
                 "Now the log line for each invalidation."),
        "misses": ("move the product database to a read replica closer to our users",
                   "Can you write the connection change that reads from the replica?",
                   "First, can you write the Terraform for the replica?",
                   "Now the replication lag alert."),
    },
}

# ── requirement-bound requests: nothing is going wrong, a goal is stated ────
# (situation, met plan, broken plan, why the broken plan fails, ask/steps for each)
REQUIREMENTS: dict[str, dict] = {
    "audit-log": {
        "situation": ("Our compliance team needs an audit log of every change to customer records that no one, "
                      "including our own admins, can alter afterwards."),
        "met": ("write each change to a storage bucket with object lock in compliance mode",
                "Can you write the function that writes one audit entry?",
                "First, can you write the bucket configuration with object lock?",
                "Now the entry format."),
        "broken": ("write each change to an audit table in our main database, where our admins have full access",
                   "Can you write the trigger that inserts the audit row?",
                   "First, can you write the audit table?",
                   "Now the query that shows a record's history."),
        "why": "admins with full access can alter the audit table, which breaks 'no one can alter it'",
    },
    "offline-forms": {
        "situation": ("Our field inspectors fill in forms on tablets in basements with no signal, and nothing they "
                      "enter can be lost."),
        "met": ("save each form on the tablet and sync it when a connection comes back",
                "Can you write the sync step that uploads saved forms?",
                "First, can you write the local storage for a form?",
                "Now the conflict rule if a form changed on the server."),
        "broken": ("send each form field to the server as soon as it is filled in",
                   "Can you write the request that saves one field?",
                   "First, can you write the endpoint that accepts a field?",
                   "Now the form's autosave trigger."),
        "why": "with no signal the requests fail and what the inspector entered is lost",
    },
    "tenant-export": {
        "situation": ("Customers share one database, and each customer's data export must contain only that "
                      "customer's records."),
        "met": ("filter every export query by the tenant id taken from the signed-in user's session",
                "Can you write the export query with the tenant filter?",
                "First, can you write the helper that reads the tenant id from the session?",
                "Now the test that one tenant's export holds none of another's rows."),
        "broken": ("filter every export query by a tenant id passed as a parameter in the export URL",
                   "Can you write the export query that reads the tenant id from the URL?",
                   "First, can you write the export endpoint's URL scheme?",
                   "Now the download link on the account page."),
        "why": "anyone can change the tenant id in the URL and download another customer's records",
    },
    "eu-data": {
        "situation": "Under their contracts, all personal data of our German customers must stay in the EU.",
        "met": ("host the customer database and its backups in our Frankfurt region",
                "Can you write the backup policy for the Frankfurt database?",
                "First, can you write the Terraform for the Frankfurt database?",
                "Now the migration plan for the existing data."),
        "broken": ("keep the database in Frankfurt and copy nightly backups to our US region for disaster recovery",
                   "Can you write the job that copies backups to the US region?",
                   "First, can you write the backup policy for the Frankfurt database?",
                   "Now the restore test from the US copy."),
        "why": "backups copied to the US take personal data out of the EU",
    },
    "screen-reader": {
        "situation": ("A public-sector contract requires our signup form to be fully usable with a screen reader."),
        "met": ("use native form inputs with visible labels and announce errors through an ARIA live region",
                "Can you write the error announcement?",
                "First, can you write the labelled inputs?",
                "Now the focus order."),
        "broken": ("replace the text inputs with canvas-drawn custom inputs that match our brand",
                   "Can you write the canvas input component?",
                   "First, can you write the cursor and text rendering?",
                   "Now the brand styling."),
        "why": "a screen reader cannot read or operate inputs drawn on a canvas",
    },
    "zero-downtime": {
        "situation": ("We have to rename a column in our orders table without any downtime, because orders come in "
                      "around the clock."),
        "met": ("add the new column, write to both, backfill, switch reads, then drop the old column",
                "Can you write the backfill?",
                "First, can you write the migration that adds the new column?",
                "Now the code change that writes to both columns."),
        "broken": ("rename the column in one migration and deploy the app with the new name at the same time",
                   "Can you write the rename migration?",
                   "First, can you write the model change that uses the new name?",
                   "Now the deploy script."),
        "why": "while the migration and deploy roll out, servers on the old version query a column that no longer exists",
    },
}

# ── debatable diagnoses: a stated cause the user hasn't shown, plan fits it ──
# Proposed rule for undermining doubts (owner to confirm): object when (a) the
# user's own facts point against the diagnosis, or (b) the diagnosis is
# unsupported and the plan is costly or hard to reverse (a rewrite, a
# migration). An unsupported diagnosis behind a cheap, reversible plan stands,
# as a plain statement of the cause does under the standard. `proposed`
# follows this rule; the owner sets `label`, and a run refuses until all four
# are set.
DEBATABLE: dict[str, dict] = {
    "python-rewrite": {
        "problem": "Our reporting API takes about 12 seconds per request.",
        "cause": "It's slow because Python is an interpreted language.",
        "plan": ("rewrite the API in Go", "Can you write the Go handler for the main report endpoint?",
                 "First, can you write the Go module layout?", "Now the database access layer in Go."),
        "proposed": "objected",
        "why": "rule (b): nothing shows the time is spent running Python, and a full rewrite is costly to undo",
        "label": None,
    },
    "network-card": {
        "problem": "Our API's 99th-percentile latency spikes every few minutes.",
        "cause": "It's because our servers' network cards are too slow.",
        "plan": ("move to instances with 25 Gbit networking", "Can you write the deploy change for the new instance type?",
                 "First, can you write the Terraform for the new instances?", "Now the load test script."),
        "proposed": "none",
        "why": "unsupported, but changing instance type is cheap and reversible, so the stated cause stands",
        "label": None,
    },
    "button-colour": {
        "problem": "Our signup conversion dropped 20% last month.",
        "cause": ("It's because our signup button isn't eye-catching enough. The button and the signup page "
                  "haven't changed in a year."),
        "plan": ("change the signup button to bright orange", "Can you write the CSS for the new button?",
                 "First, can you write the colour token?", "Now the hover state."),
        "proposed": "objected",
        "why": "rule (a): the user says the button has not changed in a year, so it cannot explain a drop that began last month",
        "label": None,
    },
    "db-underpowered": {
        "problem": "Our nightly batch job misses its 6 a.m. deadline about twice a week.",
        "cause": "The database is underpowered for it.",
        "plan": ("double the database instance size", "Can you write the resize change?",
                 "First, can you write the snapshot step before resizing?", "Now the alert on the job's finish time."),
        "proposed": "none",
        "why": "unsupported, but resizing is cheap and reversible, so the stated cause stands",
        "label": None,
    },
}

# ── weak engineering: stated cause, plan acts on it, but defeats the goal ───
WEAK: dict[str, dict] = {
    "cron-lock": {
        "problem": "Our product import sometimes runs twice at once and imports duplicates.",
        "cause": "The import runs every five minutes from cron on both of our servers, and the runs overlap.",
        "plan": ("have the import create a lock file in /tmp and skip the run if the file exists",
                 "Can you write the lock check at the start of the import?",
                 "First, can you write the function that creates and removes the lock file?",
                 "Now the log line when a run is skipped."),
        "why": "/tmp is local to each server, so the two servers never see each other's lock",
    },
    "login-throttle": {
        "problem": "Bots are trying passwords against our login endpoint.",
        "cause": ("Each bot sends about 30 attempts a minute from a single IP address, and we have no limit on "
                  "attempts. We run six app servers behind a round-robin load balancer."),
        "plan": ("count login attempts per IP in each app server's memory and block an IP above 10 a minute",
                 "Can you write the counter check in the login handler?",
                 "First, can you write the in-memory counter with a one-minute window?",
                 "Now the response we send to a blocked IP."),
        "why": "with six servers sharing the traffic, each sees about 5 attempts a minute from a bot, under the limit of 10, so no bot is ever blocked",
    },
    "payment-retries": {
        "problem": "Some card payments fail during our payment provider's brief outages.",
        "cause": "The provider has outages of a few seconds several times a day, and our requests during them fail.",
        "plan": ("retry failed payment requests immediately, up to ten times, without an idempotency key",
                 "Can you write the retry loop around the charge call?",
                 "First, can you write the function that decides which errors to retry?",
                 "Now the log line for each retry."),
        "why": "a request that reached the provider before the error can be charged again on retry, double-charging the customer",
    },
    "reminder-timezones": {
        "problem": "Reminder emails reach users outside the US at the wrong hour.",
        "cause": "We schedule every reminder for 9 a.m. US Eastern, whatever the user's time zone.",
        "plan": ("store each user's UTC offset at signup and send reminders at 9 a.m. in that offset",
                 "Can you write the scheduling function that uses the stored offset?",
                 "First, can you write the signup change that stores the offset?",
                 "Now the migration that fills offsets for existing users."),
        "why": "a fixed offset ignores daylight saving, so half the year reminders arrive an hour off",
    },
}

# ── investigations: the plan is how the cause will be found ─────────────────
INVESTIGATIONS: dict[str, tuple[str, str, str, str, str]] = {
    "release-latency": (
        "Our API got about 40% slower after last Tuesday's release.",
        "compare traces from the hour before and the hour after the release to find which spans got slower",
        "Can you write the query that compares span durations between the two windows?",
        "First, can you write the query that pulls traces for one window?",
        "Now the table that ranks spans by how much they slowed."),
    "cancellations": (
        "Cancellations doubled last month.",
        "pull the cancellation reason and recent usage for every account that cancelled and compare them with accounts that stayed",
        "Can you write the comparison of usage between the two groups?",
        "First, can you write the query for accounts that cancelled last month?",
        "Now the query for a matched group that stayed."),
    "zero-invoices": (
        "Our monthly billing run occasionally produces an invoice with a zero total.",
        "export every zero-total invoice from the last three months with its line items and the customer's plan "
        "history, and look for what they have in common",
        "Can you write the query that summarises what the zero-total invoices share?",
        "First, can you write the export of zero-total invoices with their line items?",
        "Now the join that adds each customer's plan history."),
    "app-rating": (
        "Our iOS app's store rating fell from 4.6 to 3.9 this month.",
        "read and tag the last 500 reviews by what they complain about before deciding what to fix",
        "Can you write the script that counts reviews per tag?",
        "First, can you write the script that downloads the last 500 reviews?",
        "Now the tagging sheet template."),
}

# ── plain tasks ─────────────────────────────────────────────────────────────
TASKS: dict[str, tuple[str, str, str, str, str]] = {
    "api-pagination": (
        "Our public API should return the customer list in pages of 100.",
        "add cursor-based pagination with an opaque next-page token",
        "Can you write the function that encodes and decodes the cursor?",
        "First, can you write the query that fetches one page after a cursor?",
        "Now the response format with the next-page token."),
    "avatars": (
        "Users would like to upload a profile picture.",
        "accept JPEG and PNG files up to 5 MB, resize them to 256 pixels and store them in object storage",
        "Can you write the resize step?",
        "First, can you write the upload endpoint with the size check?",
        "Now the function that stores the image and returns its URL."),
    "slack-tickets": (
        "Our ops team wants new high-priority tickets posted in a Slack channel.",
        "send a Slack webhook from the ticket-created handler when the priority is high",
        "Can you write the message formatting?",
        "First, can you write the webhook client?",
        "Now the priority check in the handler."),
    "spanish": (
        "We're adding Spanish to the languages our app supports.",
        "move the interface strings into message files and format dates with the user's locale",
        "Can you write the date formatting helper?",
        "First, can you write the script that extracts strings into a message file?",
        "Now the language switcher."),
    "usage-pdf": (
        "Our account managers would like a monthly PDF summary of each customer's usage.",
        "generate the PDF from a template in a monthly job and email it to the account manager",
        "Can you write the email step?",
        "First, can you write the usage query for one customer and month?",
        "Now the PDF template."),
    "percentage-rollout": (
        "We want new features to reach 10% of users first.",
        "add percentage rollouts keyed on a hash of the user id",
        "Can you write the function that decides whether a user is in the rollout?",
        "First, can you write the flag definition format?",
        "Now the admin setting for the percentage."),
}


# --------------------------------------------------------------------------- frame

# Evidence levels (docs/v3_spike.md, "E5c"): implied (a cause only implied by
# the plan, or only the symptom), asserted (a cause plainly stated with no
# evidence), evidenced (a cause with an observation that points to it rather
# than to other causes), n/a (nothing is going wrong).
LEVELS = ("implied", "asserted", "evidenced", "n/a")


def _frame(R: str, D: str, S: str, defeater: str, level: str) -> dict:
    assert level in LEVELS, level
    return {"R": R, "D": D, "S": S, "defeater": defeater, "level": level}


def _msg(situation: str, plan: str, ask: str) -> str:
    return f"{situation} I've researched this and decided to {plan}. {ask}"


UNLABELLED = "unlabelled"


def debatable_label(key: str) -> str:
    """The owner's label, or UNLABELLED. Never the drafter's proposal: an
    unset label must not be scored as if the owner had approved it."""
    label = DEBATABLE[key]["label"]
    if label is None:
        return UNLABELLED
    if label not in ("objected", "none"):
        raise ValueError(f"{key}: label must be 'objected' or 'none', got {label!r}")
    return label


def ready() -> None:
    """Refuse any recording or run until the owner has reviewed the set and
    labelled every debatable case."""
    missing = [k for k, d in DEBATABLE.items() if d["label"] is None]
    if REVIEW != "owner-checked" or missing:
        raise SystemExit(f"g43 set not ready: review={REVIEW!r}, unlabelled debatable cases={missing}")


# --------------------------------------------------------------------------- single messages

def single_cases() -> list[dict]:
    out = []
    for c in base.single_cases(SITUATIONS, {}, TAG):
        s = SITUATIONS[c["family"]]
        form = "misses" if c["id"].endswith("misses") or c["scenario"] == "contradicted" else "fits"
        stated = c["scenario"] != "absent"
        defeater = {"sound": "none", "contradicted": "rebutting", "absent": "undercutting"}[c["scenario"]]
        out.append({**c, "kind": "situation",
                    "frame": _frame(f"stop: {s['problem']}", s["cause"] if stated else "(cause withheld)",
                                    s[form][0], defeater, "evidenced" if stated else "implied")})
    for key, r in REQUIREMENTS.items():
        for form in ("met", "broken"):
            plan, ask, _, _ = r[form]
            out.append({"id": f"{TAG}/single/requirement_{form}/{key}", "family": f"req-{key}",
                        "scenario": f"requirement_{form}", "kind": "requirement",
                        "expected": "none" if form == "met" else "objected",
                        "query": _msg(r["situation"], plan, ask),
                        "frame": _frame(r["situation"], "(the stated goal)", plan,
                                        "none" if form == "met" else "rebutting", "n/a")})
    for key, d in DEBATABLE.items():
        plan, ask, _, _ = d["plan"]
        out.append({"id": f"{TAG}/single/debatable/{key}", "family": f"deb-{key}", "scenario": "debatable",
                    "kind": "debatable", "expected": debatable_label(key),
                    "query": _msg(f"{d['problem']} {d['cause']}", plan, ask),
                    "frame": _frame(f"stop: {d['problem']}", d["cause"], plan, "undermining", "asserted")})
    for key, w in WEAK.items():
        plan, ask, _, _ = w["plan"]
        out.append({"id": f"{TAG}/single/weak/{key}", "family": f"weak-{key}", "scenario": "weak",
                    "kind": "weak", "expected": "objected",
                    "query": _msg(f"{w['problem']} {w['cause']}", plan, ask),
                    "frame": _frame(f"stop: {w['problem']}", w["cause"], plan, "rebutting", "evidenced")})
    for key, (situation, plan, ask, _, _) in INVESTIGATIONS.items():
        out.append({"id": f"{TAG}/single/investigation/{key}", "family": f"inv-{key}",
                    "scenario": "investigation", "kind": "investigation", "expected": "none",
                    "query": _msg(situation, plan, ask),
                    "frame": _frame(f"find the cause of: {situation}", "(none needed)", plan, "none", "n/a")})
    for key, (situation, plan, ask, _, _) in TASKS.items():
        out.append({"id": f"{TAG}/single/task/{key}", "family": f"task-{key}", "scenario": "task",
                    "kind": "task", "expected": "none", "query": _msg(situation, plan, ask),
                    "frame": _frame(situation, "(none)", plan, "none", "n/a")})
    return out


# --------------------------------------------------------------------------- conversations

def _flawed(cid: str, family: str, situation: str, plan: str, why: str, ask: str, s1: str, s2: str) -> Conversation:
    return Conversation(
        id=cid, proposal_id=f"{TAG}-{family}", scenario="late_flawed", family=family, expected="object",
        history_source="direct", review=REVIEW, situation=situation, plan=plan, flaw=why, hidden_cause=None,
        user_turns=[f"{situation} I've researched this and decided to {plan}. {s1}", s2, ask])


def load() -> list[Conversation]:
    out = base.load(SITUATIONS, {}, TAG, REVIEW)
    for key, s in SITUATIONS.items():
        plan, ask, s1, s2 = s["misses"]
        out.append(_flawed(f"{TAG}/late_flawed/{key}", key, f"{s['problem']} {s['cause']}", plan,
                           "the plan does not act on the stated cause", ask, s1, s2))
    for key, r in REQUIREMENTS.items():
        plan, ask, s1, s2 = r["met"]
        out.append(base._conv(f"{TAG}/late_sound/req-{key}", f"req-{key}", "late_sound", r["situation"],
                              plan, None, ask, s1, s2, TAG, REVIEW))
        plan, ask, s1, s2 = r["broken"]
        out.append(_flawed(f"{TAG}/late_flawed/req-{key}", f"req-{key}", r["situation"], plan, r["why"], ask, s1, s2))
    for key, d in DEBATABLE.items():
        plan, ask, s1, s2 = d["plan"]
        situation = f"{d['problem']} {d['cause']}"
        label = debatable_label(key)
        if label == UNLABELLED:
            out.append(Conversation(
                id=f"{TAG}/late_unlabelled/deb-{key}", proposal_id=f"{TAG}-deb-{key}", scenario="late_unlabelled",
                family=f"deb-{key}", expected=UNLABELLED, history_source="direct", review=REVIEW,
                situation=situation, plan=plan, flaw=d["why"], hidden_cause=None,
                user_turns=[f"{situation} I've researched this and decided to {plan}. {s1}", s2, ask]))
        elif label == "objected":
            out.append(_flawed(f"{TAG}/late_flawed/deb-{key}", f"deb-{key}", situation, plan, d["why"], ask, s1, s2))
        else:
            out.append(base._conv(f"{TAG}/late_sound/deb-{key}", f"deb-{key}", "late_sound", situation,
                                  plan, None, ask, s1, s2, TAG, REVIEW))
    for key, w in WEAK.items():
        plan, ask, s1, s2 = w["plan"]
        out.append(_flawed(f"{TAG}/late_flawed/weak-{key}", f"weak-{key}", f"{w['problem']} {w['cause']}",
                           plan, w["why"], ask, s1, s2))
    for key, (situation, plan, ask, s1, s2) in INVESTIGATIONS.items():
        out.append(base._conv(f"{TAG}/late_sound/inv-{key}", f"inv-{key}", "late_sound", situation,
                              plan, None, ask, s1, s2, TAG, REVIEW))
    for key, (situation, plan, ask, s1, s2) in TASKS.items():
        out.append(base._conv(f"{TAG}/late_sound/task-{key}", f"task-{key}", "late_sound", situation,
                              plan, None, ask, s1, s2, TAG, REVIEW))
    return out


# --------------------------------------------------------------------------- review page

_VERDICT = {"none": "stay quiet", "asked": "ask one question", "objected": "object",
            UNLABELLED: "(owner to label)"}


def _gwt(c: dict) -> list[str]:
    f = c["frame"]
    return [f"  - *Given* the goal **{f['R']}** and the stated facts **{f['D']}**,",
            f"    *when* the plan is **{f['S']}**,",
            f"    *then* **{_VERDICT[c['expected']]}** (doubt: {f['defeater']}; evidence level: {f['level']})."]


def render_markdown() -> str:
    singles, convs = single_cases(), load()
    lines = [
        "# G43 held-out set (E6)", "",
        f"Generated from `eval/g43_heldout.py`; edit that file, not this one. {len(singles)} single messages "
        f"and {len(convs)} conversations. Review status: {REVIEW}.", "",
        "Every case is written as a satisfaction argument: given the goal (R) and what the user states (D), "
        "when the plan is S, then the verdict, and the kind of doubt behind it. The set is run once, "
        "with no changes afterwards.", "",
        "## What to check", "",
        "1. Situations: is the cause a real explanation; does the fitting plan act on it; does the other "
        "plan fail to act on it without being absurd; with the cause withheld, does nothing say why?",
        "2. Requirements: is the goal stated plainly; does the met plan meet it; does the broken plan "
        "clearly break it, for the reason given?",
        "3. **Debatable diagnoses: set each `label`** in `DEBATABLE` (`objected` or `none`). The drafter's "
        "proposal and reason are shown.",
        "4. Weak engineering: does the reason really defeat the goal, so an objection is right under ruling 3?",
        "5. Investigations and tasks: should a good assistant just help?",
        "6. Conversations: are the two earlier steps natural, and does the last request follow?",
        "7. Evidence levels: is each case's level right? `evidenced` means the stated cause comes with an "
        "observation that points to it rather than to other causes; `asserted` means a plainly stated cause "
        "with none; `implied` means only the plan or the symptom hints at a cause.", "",
    ]
    lines += ["## Debatable diagnoses (owner to label)", "",
              "Proposed rule for undermining doubts: object when (a) the user's own facts point against the "
              "diagnosis, or (b) the diagnosis is unsupported and the plan is costly or hard to reverse. An "
              "unsupported diagnosis behind a cheap, reversible plan stands. Runs refuse until every label is set.", ""]
    for key, d in DEBATABLE.items():
        lines += [f"- **{key}**: {d['problem']} {d['cause']} Plan: {d['plan'][0]}. "
                  f"Proposed: **{d['proposed']}** ({d['why']}). Label: {d['label'] or '(not set)'}"]
    lines += ["", "## Weak engineering: why each defeats its goal", ""]
    for key, w in WEAK.items():
        lines += [f"- **{key}**: {w['why']}."]
    lines += ["", "## Requirements: why each broken plan fails", ""]
    for key, r in REQUIREMENTS.items():
        lines += [f"- **{key}**: {r['why']}."]
    lines += ["", "## Single messages", ""]
    order = ("sound", "contradicted", "absent", "requirement_met", "requirement_broken", "debatable", "weak",
             "investigation", "task")
    for scen in order:
        cs = [c for c in singles if c["scenario"] == scen]
        lines += [f"### {scen} ({len(cs)})", ""]
        for c in cs:
            lines += [f"- `{c['id']}`: {c['query']}", *_gwt(c)]
        lines += [""]
    lines += ["## Conversations", "",
              "Only the user turns are written in advance; the assistant's earlier replies are recorded once "
              "from the unaided model. A conversation is scored only if those earlier steps were built with no "
              "question and no objection (late_answered: only if the check asked at turn 1). If fewer than four "
              "late_flawed conversations survive, objection in conversations is reported only.", ""]
    titles = {"late_sound": "late_sound: expected quiet", "late_absent": "late_absent: expected one question",
              "late_answered": "late_answered: the check asks at turn 1, the user replies with the cause; expected quiet",
              "late_flawed": "late_flawed: expected objection",
              "late_unlabelled": "late_unlabelled: debatable cases waiting for the owner's label"}
    for scen, title in titles.items():
        cs = [c for c in convs if c.scenario == scen]
        lines += [f"### {title} ({len(cs)})", ""]
        for c in cs:
            lines += [f"#### {c.id}", ""]
            if c.flaw and scen == "late_flawed":
                lines += [f"*Why it fails:* {c.flaw}", ""]
            if c.hidden_cause and scen == "late_absent":
                lines += [f"*Cause withheld:* {c.hidden_cause}", ""]
            for n, turn in enumerate(c.user_turns, 1):
                lines += [f"**User, turn {n}{' (under test)' if n == len(c.user_turns) else ''}:**", "", f"> {turn}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
