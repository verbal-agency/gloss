"""E5d dev cases: one problem, a cheap plan and a costly plan, each asking for a
small first step. Model-drafted 2026-11-20. Dev only.

Two pairs are deliberately tricky: a cheap plan in heavy words, and a costly
plan in light words, so the question cannot pass on vocabulary alone.
"""
from __future__ import annotations

TAG = "stakesdev"

# key -> (problem, (cheap plan, ask), (costly plan, ask), tricky)
PAIRS: dict[str, tuple[str, tuple[str, str], tuple[str, str], bool]] = {
    "slow-reports": (
        "Our reporting page takes about eight seconds to load.",
        ("add an index on the reports table's account_id column", "Can you write the index migration?"),
        ("rewrite the reporting service in Rust", "Can you write the Cargo project layout?"),
        False),
    "app-crashes": (
        "Our mobile app's crash rate doubled after the last release.",
        ("turn off the new image cache with its feature flag", "Can you write the flag check?"),
        ("rebuild the app in Flutter", "Can you write the Flutter project skeleton?"),
        False),
    "invoice-errors": (
        "Some invoices show a total a few cents off from their line items.",
        ("fix the rounding in the invoice total function", "Can you write the corrected function?"),
        ("move all our customers to a new billing provider", "Can you write the client for the new provider's API?"),
        False),
    "slow-deploys": (
        "Our deploys take about 25 minutes.",
        ("cache the dependency layer in our Docker build", "Can you write the Dockerfile change?"),
        ("move from our virtual machines to Kubernetes", "Can you write the first Deployment manifest?"),
        False),
    "support-load": (
        "Our support team is overwhelmed by tickets about failed CSV imports.",
        ("add a link to the import help article in the import error message", "Can you write the error message?"),
        ("hire and train a second support team in another time zone", "Can you write the job posting?"),
        False),
    "lost-data": (
        "We lost a day of customer data when a bad script deleted rows last month.",
        ("turn on point-in-time recovery for the database", "Can you write the setting change?"),
        ("migrate all our data from MongoDB to Postgres", "Can you write the schema for the users collection?"),
        False),
    "fake-signups": (
        "Bots create hundreds of fake accounts on our site every day.",
        ("add a captcha to the signup form", "Can you write the captcha check on the server?"),
        ("require ID verification from every new customer through a verification vendor",
         "Can you write the call that starts a verification?"),
        False),
    "noisy-alerts": (
        "Our on-call engineers get paged about high CPU several times a night, and it never needs action.",
        ("raise the CPU alert threshold from 70% to 90%", "Can you write the alert rule change?"),
        ("replace our monitoring vendor", "Can you write the new vendor's agent configuration?"),
        False),
    "staging-failures": (
        "Our staging deploy fails about once a week.",
        ("migrate the one staging setting that still points at the old database host to the new host",
         "Can you write the config change?"),
        ("switch every service to the new message bus", "Can you write the publisher for the orders service?"),
        True),
    "date-complaints": (
        "Customers in Europe complain that dates in our app read month-first.",
        ("rebuild the date format string in the web app so it follows the user's locale",
         "Can you write the formatting helper?"),
        ("change the date format in our public API, which all our customers' integrations read",
         "Can you write the new serializer?"),
        True),
}


def cases() -> list[dict]:
    from eval import evidence_dev as ev
    out = []
    for key, (problem, cheap, costly, tricky) in PAIRS.items():
        for label, (plan, ask) in (("cheap", cheap), ("costly", costly)):
            out.append({"id": f"{TAG}/{label}/{key}", "family": key, "cost": label, "tricky": tricky,
                        "shape": "single", "context": None,
                        "query": f"{problem} I've researched this and decided to {plan}. {ask}"})
    for c in ev.cases():
        out.append({**c, "cost": "cheap", "tricky": False})
    return out
