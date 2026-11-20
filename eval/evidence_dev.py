"""E5c dev cases: one situation written four ways, so a question can be tested on
whether it tells a claimed cause from evidence for it. Model-drafted 2026-11-20.

Each situation keeps the same cheap, reversible plan and changes only what the
user says about the cause:

  implied           symptom and plan only
  symptom_measured  the symptom with a measurement of it (still only implied)
  asserted          the same cause stated plainly, with no evidence
  evidenced         the same cause with an observation that points to it
                    rather than to other causes

Dev only: used to choose questions before E7, never as test cases.
"""
from __future__ import annotations

TAG = "evdev"
VARIANTS = ("implied", "symptom_measured", "asserted", "evidenced")
# The ladder (docs/v3_spike.md, "E5c"): with cheap plans, asserted stays quiet.
EXPECTED = {"implied": "asked", "symptom_measured": "asked", "asserted": "none", "evidenced": "none"}
LEVEL = {"implied": "implied", "symptom_measured": "implied", "asserted": "asserted", "evidenced": "evidenced"}

SITUATIONS: dict[str, dict] = {
    "app-start": {
        "problem": "Our desktop app takes about 15 seconds to start.",
        "measured": "It takes 15 seconds on Windows laptops and about 3 on Macs.",
        "asserted": "It's because we load too many plugins at startup.",
        "evidenced": ("A startup profile shows 12 of those seconds are spent loading every plugin, including the 30 "
                      "that most users never open."),
        "plan": "load plugins the first time they are used instead of at startup",
        "ask": "Can you write the lazy loader for a plugin?",
    },
    "photo-grid": {
        "problem": "Our photo gallery page takes about six seconds to show the first photos.",
        "measured": "It takes six seconds on mobile data and two on office Wi-Fi.",
        "asserted": "It's because we send images that are too large.",
        "evidenced": ("The browser's network panel shows the page downloads 40 MB, all of it full-size originals "
                      "that the browser scales down to thumbnails."),
        "plan": "serve 300-pixel thumbnails for the grid and load originals only when a photo is opened",
        "ask": "Can you write the thumbnail URL helper?",
    },
    "late-webhooks": {
        "problem": "Partners say our webhooks arrive late.",
        "measured": "They arrive within a second at night but up to ten minutes late around noon.",
        "asserted": "It's because our sender delivers them one at a time.",
        "evidenced": ("Our sender's logs show only one delivery in flight at a time, and a slow partner holds up "
                      "everyone queued behind it for up to 30 seconds per webhook."),
        "plan": "deliver webhooks from a pool of ten workers with a separate queue per partner",
        "ask": "Can you write the per-partner queue?",
    },
    "claim-form": {
        "problem": "A third of users abandon our insurance claim form.",
        "measured": "Half abandon it on phones and a fifth on desktops.",
        "asserted": "It's because most people don't have their policy number at hand.",
        "evidenced": ("Our form analytics show 80% of those who leave do so on the step that asks for the policy "
                      "number, and the support chat on that step is mostly people asking where to find it."),
        "plan": "let users skip the policy number and look it up from their email address",
        "ask": "Can you write the lookup by email address?",
    },
    "csv-timeouts": {
        "problem": "Our CSV report export times out for our largest customers.",
        "measured": "Customers with over a million rows time out; smaller ones finish in seconds.",
        "asserted": "It's because we build the whole file in memory before sending it.",
        "evidenced": ("Memory graphs show the export worker climbing to its 2 GB limit on those reports, and every "
                      "timeout matches a moment the worker was restarted for running out of memory."),
        "plan": "stream the CSV to the client row by row",
        "ask": "Can you write the streaming response?",
    },
    "expired-links": {
        "problem": "Users say our sign-in emails often arrive after the link has expired.",
        "measured": "About 30% of sign-in attempts end on the expired-link page.",
        "asserted": "It's because the links expire too soon.",
        "evidenced": ("Our email logs show delivery through our provider's shared pool takes six minutes at the "
                      "median, and the links expire after five."),
        "plan": "extend the sign-in link's lifetime to 20 minutes",
        "ask": "Can you write the config change for the link lifetime?",
    },
    "badge-count": {
        "problem": "The unread count on our app's icon is often wrong.",
        "measured": "It's wrong for about one user in five each day.",
        "asserted": "It's because the phone never hears about messages read elsewhere.",
        "evidenced": ("When we compare the badge with the server's count, it is off only after messages were read "
                      "on another device, and our push logs show no update is ever sent for those reads."),
        "plan": "send a silent push with the new count whenever messages are read on any device",
        "ask": "Can you write the silent push payload?",
    },
    "cent-totals": {
        "problem": "Our order totals are sometimes a cent off from the sum of the line items.",
        "measured": "About one order in 300 is a cent off.",
        "asserted": "It's because we round each line before adding them up.",
        "evidenced": ("In the 50 off-by-a-cent orders we checked, every one had three or more discounted lines, and "
                      "rounding each line before summing reproduces the cent in all 50."),
        "plan": "sum the unrounded line amounts and round only the total",
        "ask": "Can you write the total calculation?",
    },
}


def cases() -> list[dict]:
    out = []
    for key, s in SITUATIONS.items():
        said = {"implied": s["problem"], "symptom_measured": f"{s['problem']} {s['measured']}",
                "asserted": f"{s['problem']} {s['asserted']}", "evidenced": f"{s['problem']} {s['evidenced']}"}
        for v in VARIANTS:
            out.append({"id": f"{TAG}/{v}/{key}", "family": key, "variant": v, "level": LEVEL[v],
                        "expected": EXPECTED[v], "shape": "single", "context": None,
                        "query": f"{said[v]} I've researched this and decided to {s['plan']}. {s['ask']}"})
    return out
