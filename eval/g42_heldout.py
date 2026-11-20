"""G42's held-out test set. Model-drafted 2026-11-18; the owner reviews it
before any run.

G41 spent its own held-out set, which is now dev for G42. G42 tests changes
aimed at the two patterns behind G41's misses, so this set has more of both,
in situations used nowhere before (not in dev, not in the criteria examples in
`app/pipeline/jev_ground.py`):

  error-type   the problem is named by an error or symptom type that can read
               as its own cause ("lock wait timeout exceeded", "quota exceeded")
  plan-names   the plan that fits names the cause in its own wording, so with
               the cause withheld the plan alone implies it

Four situations of each pattern; each has a cause, a plan that acts on it and a
plan the message's own facts rule out once the cause is stated. Six plain tasks:
four described without the categories the `problem_described` question uses as
examples, two inside them.

Same shapes, labels and survival rules as G41 (see `eval/g41_heldout.py`):
single messages sound / contradicted / absent / task; conversations
late_sound / late_absent / late_answered. It is run once, and nothing is
changed afterwards.
"""
from __future__ import annotations

from eval import g41_heldout as base
from eval.multiturn_dataset import Conversation

REVIEW = "owner-checked"   # read and approved by the owner, 2026-11-18
TAG = "g42"

# situation -> which G41 miss pattern it carries (reported only)
PATTERN = {"mail-connections": "error-type", "lock-timeouts": "error-type",
           "dns-failures": "error-type", "translation-quota": "error-type",
           "admin-page": "plan-names", "partner-outages": "plan-names",
           "cold-starts": "plan-names", "french-tickets": "plan-names"}

# A plan is (plan, ask, step 1, step 2); plans read after "I've researched this
# and decided to".
SITUATIONS: dict[str, dict] = {
    # ── error-type ─────────────────────────────────────────────────────────
    "mail-connections": {
        "problem": "Our mail provider rejects some of our transactional emails with 'too many connections' errors.",
        "cause": ("Each of our 40 app servers opens its own connections to the provider at peak, about 400 at "
                  "once, and the provider allows 50 per account."),
        "fits": ("send all mail through one relay that keeps a pool of at most 40 connections to the provider",
                 "Can you write the app-side client that hands mail to the relay?",
                 "First, can you write the relay's connection pool with the 40-connection cap?",
                 "Now the queue the relay reads outgoing mail from."),
        "misses": ("switch our email templates to a compiled template engine so each email renders faster",
                   "Can you write the welcome email in the new engine's syntax?",
                   "First, can you write the function that loads and compiles the templates at startup?",
                   "Now the helper that formats prices and dates inside templates."),
    },
    "lock-timeouts": {
        "problem": "Our order service logs 'lock wait timeout exceeded' errors every evening.",
        "cause": ("The evening reconciliation job updates every order from the day in one transaction, which "
                  "holds its row locks for about ten minutes; its lookups already use the primary key, and "
                  "almost all that time is the updates themselves."),
        "fits": ("commit the reconciliation job in batches of 500 orders",
                 "Can you write the loop that reconciles one batch and commits it?",
                 "First, can you write the query that pages through the day's orders by id?",
                 "Now the progress log so a failed run can resume from the last batch."),
        "misses": ("add an index on the orders table's created_at column",
                   "Can you write the migration that creates the index without locking the table?",
                   "First, can you write the query that shows the table's current indexes and sizes?",
                   "Now the query that checks the planner uses the new index."),
    },
    "dns-failures": {
        "problem": "Our worker pods log 'name resolution failed' errors several times an hour.",
        "cause": ("Each pod looks up the queue's hostname for every message, about 2,000 lookups a second "
                  "across the cluster, and the cluster's DNS server drops queries above 1,000 a second."),
        "fits": ("cache DNS lookups in each pod for 60 seconds",
                 "Can you write the resolver wrapper with the 60-second cache?",
                 "First, can you write the config for a local DNS cache sidecar?",
                 "Now the metric for cache hits and misses."),
        "misses": ("move the workers to nodes with twice the CPU and memory",
                   "Can you write the node pool definition for the larger nodes?",
                   "First, can you write the pod resource requests for the larger nodes?",
                   "Now the drain script that moves workers off the old nodes."),
    },
    "translation-quota": {
        "problem": "Our nightly translation job stops halfway with 'quota exceeded' errors from the translation API.",
        "cause": ("Since we started translating product reviews, the job sends every review in full each night, "
                  "about three times our daily character quota, although 95% of them were translated the "
                  "night before."),
        "fits": ("translate only new and changed reviews, keyed on a hash of each review's text",
                 "Can you write the step that skips reviews whose hash is already translated?",
                 "First, can you write the table that stores each review's text hash and translation?",
                 "Now the function that computes the hash."),
        "misses": ("retry failed translation requests with exponential backoff, up to an hour",
                   "Can you write the retry wrapper around the translation client?",
                   "First, can you write the function that decides which errors are retryable?",
                   "Now the log line we write for each retry."),
    },
    # ── plan-names ─────────────────────────────────────────────────────────
    "admin-page": {
        "problem": "Our admin page that lists customers takes about 20 seconds to load.",
        "cause": "Query logs show the page runs one database query per customer row, about 3,000 queries per load.",
        "fits": ("load each customer's orders in one batched query instead of one query per row",
                 "Can you write the view code that uses the batched query?",
                 "First, can you write the batched query for the orders of a list of customer ids?",
                 "Now the function that groups the results by customer."),
        "misses": ("move the admin pages to their own server",
                   "Can you write the routing rule that sends /admin to the new server?",
                   "First, can you write the deployment config for the admin server?",
                   "Now the health check for it."),
    },
    "partner-outages": {
        "problem": "Our integration with our largest partner went down twice this year, for several hours each time.",
        "cause": ("Both times the TLS certificate on our integration endpoint expired, because someone renews it "
                  "by hand each year."),
        "fits": ("renew the integration endpoint's certificate automatically with cert-manager",
                 "Can you write the Certificate resource for the integration endpoint?",
                 "First, can you write the cert-manager issuer for our certificate authority?",
                 "Now the alert if a certificate is within 14 days of expiring and has not renewed."),
        "misses": ("run a second copy of the integration endpoint in another region behind a failover DNS record",
                   "Can you write the failover DNS record?",
                   "First, can you write the deployment for the second region?",
                   "Now the health check the failover uses."),
    },
    "cold-starts": {
        "problem": "The first request to our serverless prediction API after a quiet period takes about eight seconds.",
        "cause": ("Traces show almost all of that time is the function's cold start loading a 400 MB model "
                  "file before it can answer."),
        "fits": ("keep warm instances with provisioned concurrency so the model is not loaded on each cold start",
                 "Can you write the provisioned concurrency setting for the function?",
                 "First, can you write the scheduled scaling that lowers it overnight?",
                 "Now the metric for how many requests hit a cold instance."),
        "misses": ("rewrite the request handler in Go",
                   "Can you write the Go handler that parses the request?",
                   "First, can you write the Go module layout for the function?",
                   "Now the build step that packages the Go binary."),
    },
    "french-tickets": {
        "problem": "Support tickets written in French wait about three days for a first reply; English ones wait a few hours.",
        "cause": ("Our routing rules send every ticket to the English queue, the English-speaking agents skip "
                  "the French ones, and the two agents who read French check that queue once a day."),
        "fits": ("route tickets detected as French to a French queue that the French-speaking agents watch",
                 "Can you write the routing rule that uses the detected language?",
                 "First, can you write the language detection step for incoming tickets?",
                 "Now the French queue's notification to its agents."),
        "misses": ("hire three more English-speaking support agents",
                   "Can you write the job posting?",
                   "First, can you write the interview scorecard?",
                   "Now the onboarding checklist for the new agents."),
    },
}

# (situation, plan, ask, step 1, step 2). No problem, so no cause to ask about.
TASKS: dict[str, tuple[str, str, str, str, str]] = {
    "pdf-receipts": (
        "Customers would like a PDF receipt attached to their order confirmation email.",
        "render the receipt from an HTML template with WeasyPrint and attach it to the email",
        "Can you write the code that attaches the PDF to the email?",
        "First, can you write the receipt's HTML template?",
        "Now the function that renders the template to PDF."),
    "calendar-feed": (
        "We want users to see their bookings in their own calendar app.",
        "publish each user's bookings as a private iCal feed at a secret URL",
        "Can you write the settings page section that shows the feed URL?",
        "First, can you write the function that turns a list of bookings into iCal events?",
        "Now the endpoint that serves the feed for a secret token."),
    "referral-codes": (
        "Marketing would like each customer to have a referral code that gives a friend 10% off.",
        "generate a short unique code per customer and apply the discount at checkout",
        "Can you write the checkout step that applies the referral discount?",
        "First, can you write the function that generates unique codes?",
        "Now the table that records which code each order used."),
    "lead-upload": (
        "Our sales team would like to load leads into the CRM from a spreadsheet.",
        "accept a CSV upload, let the user map its columns, and insert the rows in a background job",
        "Can you write the background job that inserts the rows?",
        "First, can you write the upload endpoint that stores the file?",
        "Now the column-mapping form."),
    "backup-encryption": (
        "Our insurer requires that our production database backups are encrypted at rest by next month.",
        "turn on KMS encryption for new backups and re-encrypt the last 30 days of backups",
        "Can you write the script that re-encrypts the existing backups?",
        "First, can you write the KMS key policy for the backup role?",
        "Now the backup job change that encrypts new backups."),
    "cron-move": (
        "We're moving our scheduled jobs from a single VM to Kubernetes CronJobs before the VM's lease ends.",
        "rewrite each crontab entry as a CronJob and run both side by side for a week",
        "Can you write the CronJob for the nightly invoice export?",
        "First, can you write the script that lists the VM's crontab entries with their schedules?",
        "Now the container image for the jobs."),
}


def single_cases() -> list[dict]:
    return [{**c, "pattern": PATTERN.get(c["family"])}
            for c in base.single_cases(SITUATIONS, TASKS, TAG)]


def load() -> list[Conversation]:
    return base.load(SITUATIONS, TASKS, TAG, REVIEW)


def render_markdown() -> str:
    preface = [
        "",
        "G42 aims at G41's two kinds of miss, so four situations name the problem by an error type "
        "that can read as its own cause (`error-type`: mail-connections, lock-timeouts, dns-failures, "
        "translation-quota), and four have a fitting plan that names the cause in its own wording "
        "(`plan-names`: admin-page, partner-outages, cold-starts, french-tickets). With the cause "
        "withheld, the expected action is still to ask: a symptom's name or a plan's wording is not "
        "the user stating the cause.",
    ]
    return base.render_markdown(SITUATIONS, TASKS, TAG, REVIEW, preface)


if __name__ == "__main__":
    print(render_markdown())
