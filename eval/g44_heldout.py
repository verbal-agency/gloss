"""G44's held-out test set (E9): conversations where the thing to react to arrives
in the final turn. Model-drafted 2026-11-21; owner-checked 2026-11-22, before any
recording.

Why it exists. G43's flawed conversations put the situation and the bad plan in
the first message. The unaided model objected at once in all 20, so none
survived and objection in conversations could not be measured (docs/v3_spike.md,
"Histories recorded"). Here the first two turns are sound: an evidenced cause
with a plan that acts on it, or a plain task. The model should build them
quietly. Only the last turn, the one under test, changes the picture:

  late_fact_for        a new fact that agrees with the stated cause      none
  late_fact_against    a new fact that points against the stated cause   asked
  late_switch_fits     a new plan that still acts on the stated cause    none
  late_switch_misses   a new plan that does not act on the stated cause  objected
  late_req_met         a requirement, and a step that meets it           none
  late_req_broken      a requirement, and a step that breaks it          objected
  late_problem_stated  a new problem with its cause, and a plan          none
  late_problem_absent  the same problem and plan, with no cause          asked

Spec and rules: docs/v3_spike.md, "E9". Run once, with G43, in E7; nothing is
changed after recording.
"""
from __future__ import annotations

from eval.multiturn_dataset import Conversation

TAG = "g44"
REVIEW = "owner-checked"   # owner review 2026-11-22: all eight kinds and their labels

KINDS = ("late_fact_for", "late_fact_against", "late_switch_fits", "late_switch_misses",
         "late_req_met", "late_req_broken", "late_problem_stated", "late_problem_absent")
# late_fact_against is a question, not an objection (owner ruling, confirmed
# 2026-11-22): when the user's facts contradict the diagnosis, ask, unless those
# facts independently rule out the plan. A stated cause may be an assumption, so
# once the user's own fact rules it out the cause is unknown again. The plan
# has lost its link to the problem (undercutting, no cause standing); nothing
# shows the plan itself is wrong. Order of arrival does not change the verdict.
EXPECTED = {"late_fact_for": "none", "late_fact_against": "asked",
            "late_switch_fits": "none", "late_switch_misses": "objected",
            "late_req_met": "none", "late_req_broken": "objected",
            "late_problem_stated": "none", "late_problem_absent": "asked"}
DEFEATER = {"late_fact_for": "none", "late_fact_against": "undercutting",
            "late_switch_fits": "none", "late_switch_misses": "rebutting",
            "late_req_met": "none", "late_req_broken": "rebutting",
            "late_problem_stated": "none", "late_problem_absent": "undercutting"}
LEVEL = {"late_fact_for": "evidenced", "late_fact_against": "implied",
         "late_switch_fits": "evidenced", "late_switch_misses": "evidenced",
         "late_req_met": "n/a", "late_req_broken": "n/a",
         "late_problem_stated": "evidenced", "late_problem_absent": "implied"}
# Fixed before any recording: a kind with fewer surviving conversations than
# this is reported only, as in G43.
MIN_SURVIVORS = 4

# ── situations: an evidenced cause and a plan that acts on it, then a late turn ──
# plan = (plan, first step, second step). Each late turn is (what the user says, the request).
SITUATIONS: dict[str, dict] = {
    "subtitle-drift": {
        "problem": ("Subtitles on our training videos drift out of step with the speech, by about three and a half "
                    "seconds at the end of an hour-long video."),
        "cause": ("Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our "
                  "subtitle tool assumes 30."),
        "plan": ("read each video's real frame rate and time its subtitles from that",
                 "First, can you write the function that reads a video's frame rate?",
                 "Now the conversion from frame number to timestamp."),
        "fact_for": "I re-timed one drifting video by hand at 29.97 and its subtitles stayed in step to the end.",
        "fact_against": ("I re-timed one drifting video by hand at 29.97 and its subtitles still ended three and a "
                         "half seconds out."),
        "fact_ask": "Now can you write the check that flags a video whose frame rate we cannot read?",
        "why_against": "timing the subtitles at the real frame rate left the drift, so the assumed 30 is not the cause",
        "switch_fits": ("convert every video to exactly 30 frames a second when it is uploaded, so the tool's "
                        "assumption holds",
                        "Can you write the conversion command?"),
        "switch_misses": ("burn the subtitles into the picture instead of serving them as a separate file",
                          "Can you write the command that burns them in?"),
        "why_misses": "burned-in subtitles use the same timings, still worked out at the wrong frame rate",
    },
    "voicemail-transcripts": {
        "problem": "Voicemail transcripts in our phone app are gibberish for about one message in six.",
        "cause": ("Going through the bad ones, they are all messages from the two carriers that deliver audio at "
                  "8 kHz, and we pass everything to a speech model that expects 16 kHz."),
        "plan": ("resample 8 kHz audio to 16 kHz before it is transcribed",
                 "First, can you write the function that detects a message's sample rate?",
                 "Now the resampling step."),
        "fact_for": "I resampled one of the gibberish messages by hand and its transcript came out right.",
        "fact_against": "I resampled one of the gibberish messages by hand and its transcript was still gibberish.",
        "fact_ask": "Now can you write the test that runs a known 8 kHz sample through the whole path?",
        "why_against": "the resampled message was still transcribed wrongly, so the sample rate is not the cause",
        "switch_fits": ("send 8 kHz messages to the speech provider's telephone model, which is built for 8 kHz audio",
                        "Can you write the routing by sample rate?"),
        "switch_misses": ("raise the transcription request's time limit from 30 seconds to 120",
                          "Can you write the setting change?"),
        "why_misses": "the transcripts come back in time but wrong; a longer limit leaves the sample-rate mismatch as it is",
    },
    "ebook-images": {
        "problem": "About one in ten of the e-books we export comes out with chapter images missing.",
        "cause": ("The export log shows the missing images are all larger than 5 MB, and that fetching each of them "
                  "ran past the export's two-second limit."),
        "plan": ("raise the image fetch limit to 30 seconds and try twice more before giving up",
                 "First, can you write the fetch with the new limit?",
                 "Now the retry loop."),
        "fact_for": "I exported one of the failing books with the limit raised by hand and every image was there.",
        "fact_against": ("I exported one of the failing books with the limit raised by hand and the same images were "
                         "still missing."),
        "fact_ask": "Now can you write the log line for an image that fails after all its retries?",
        "why_against": "with the limit raised the same images were still missing, so the two-second limit is not why",
        "switch_fits": ("shrink images to under 1 MB when authors upload them, so every fetch is quick",
                        "Can you write the shrink step?"),
        "switch_misses": ("change the export format from EPUB 2 to EPUB 3", "Can you write the new package file?"),
        "why_misses": "the images are lost when fetching them runs out of time, which the file format does not change",
    },
    "gym-door": {
        "problem": "About 5% of member scans at our gym doors come back 'membership not found'.",
        "cause": ("The door log shows every failure is a member who renewed in the previous 24 hours, and the door "
                  "tablets copy the member list only once a night."),
        "plan": ("have a tablet ask the server about a member when the scan is not in its own list",
                 "First, can you write the call to the server for one member?",
                 "Now the logic that falls back to that call."),
        "fact_for": "We forced a fresh copy of the list onto one tablet after a renewal and that member scanned in fine.",
        "fact_against": ("We forced a fresh copy of the list onto one tablet after a renewal and that member still got "
                         "'membership not found'."),
        "fact_ask": "Now can you write the message shown when the tablet cannot reach the server?",
        "why_against": "the tablet had the fresh list and still rejected the member, so the nightly copy is not the cause",
        "switch_fits": ("copy the member list to the tablets every five minutes",
                        "Can you write the schedule for the copy?"),
        "switch_misses": ("replace the tablets' cameras with handheld barcode readers",
                          "Can you write the input handler for the readers?"),
        "why_misses": "the scans are read correctly; the tablet's list is a day old, which a new reader does not change",
    },
    "parking-gate": {
        "problem": "The exit gate at our car park fails to open for about one car in fifteen.",
        "cause": ("The gate controller's log shows each failure is a number plate read with one character confused, "
                  "such as O for 0 or I for 1, and the lookup needs an exact match."),
        "plan": ("accept a plate that differs from a paid one by a single easily confused character",
                 "First, can you write the table of characters that get confused?",
                 "Now the matching function."),
        "fact_for": ("I replayed last week's 60 failed reads through a rough version of the matcher and 58 of them "
                     "would have opened the gate."),
        "fact_against": ("I replayed last week's 60 failed reads through a rough version of the matcher and only 2 of "
                         "them would have opened the gate."),
        "fact_ask": "Now can you write the audit log entry for a plate that was accepted this way?",
        "why_against": "58 of the 60 failures were not fixed by allowing a confused character, so that is not what fails them",
        "switch_fits": ("turn every O into 0 and every I into 1, in both the plate we read and the plates we store, "
                        "before the exact match",
                        "Can you write that conversion?"),
        "switch_misses": ("fit the gate with a faster motor", "Can you write the controller's new timing settings?"),
        "why_misses": "the gate never gets the signal to open, because the plate lookup fails; the motor is not involved",
    },
    "log-bill": {
        "problem": "Our logging vendor bills by the volume we send, and the bill tripled this quarter.",
        "cause": ("The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address "
                  "validator, which was left at debug level after an incident in March."),
        "plan": ("set the address validator back to INFO level",
                 "First, can you write the config change?",
                 "Now a startup check that warns when a service runs at DEBUG in production."),
        "fact_for": ("I set one of the validator's four instances to INFO yesterday and the volume from that instance "
                     "fell by about 95%."),
        "fact_against": ("I set one of the validator's four instances to INFO yesterday and the volume from that "
                         "instance did not change."),
        "fact_ask": "Now can you write the alert for a day's log volume going over budget?",
        "why_against": "the instance at INFO sent just as much, so DEBUG lines are not what fills the volume",
        "switch_fits": ("leave the level alone and drop that service's DEBUG lines in the log shipper, before they "
                        "are sent",
                        "Can you write the shipper filter?"),
        "switch_misses": ("cut how long the vendor keeps our logs from 30 days to 7",
                          "Can you write the retention setting?"),
        "why_misses": "the bill is for volume sent, and keeping logs for less time sends just as much",
    },
    "exam-timer": {
        "problem": "On our online exam platform about 3% of students are marked as submitting late.",
        "cause": ("Each late submission in our records came from a device whose clock was more than a minute wrong, "
                  "and the exam timer counts down from the device's clock."),
        "plan": ("count down from the server's time, fetched when the exam starts, plus the time elapsed since",
                 "First, can you write the endpoint that returns the server time and the exam's end time?",
                 "Now the countdown in the browser."),
        "fact_for": ("I set my laptop's clock five minutes fast and the current timer ended my test exam five minutes "
                     "early."),
        "fact_against": ("I set my laptop's clock five minutes fast and the current timer still ended my test exam "
                         "exactly on time."),
        "fact_ask": "Now can you write the warning shown when five minutes are left?",
        "why_against": "a wrong device clock did not move the timer, so the timer is not counting from the device's clock",
        "switch_fits": ("keep the device's clock but measure how far it is from the server's when the exam starts, "
                        "and correct the timer by that amount",
                        "Can you write the correction?"),
        "switch_misses": ("serve the exam pages from a CDN so they load faster", "Can you write the cache headers?"),
        "why_misses": "students are late because the timer follows a wrong device clock, which faster pages do not change",
    },
    "number-gaps": {
        "problem": "Our auditor flagged gaps in our invoice numbers.",
        "cause": ("The database log shows each gap lines up with a transaction that took the next number from the "
                  "sequence and was then rolled back."),
        "plan": ("give an invoice its number in a separate step after it is committed, from a counter row that is "
                 "locked while it is read",
                 "First, can you write the migration for the counter table?",
                 "Now the function that assigns the number."),
        "fact_for": "I forced a rollback on the current code in staging and it left a gap in the numbers.",
        "fact_against": "I forced twenty rollbacks on the current code in staging and none of them left a gap.",
        "fact_ask": "Now can you write the check that lists the gaps we already have?",
        "why_against": "twenty rollbacks left no gap, so rolled-back transactions are not what makes the gaps",
        "switch_fits": ("number invoices in a nightly job that walks the committed invoices in order",
                        "Can you write the job?"),
        "switch_misses": ("widen the invoice number column from six digits to ten", "Can you write the migration?"),
        "why_misses": "the gaps come from numbers lost in rollbacks, and a wider column loses them just the same",
    },
}

# ── requirements: a plain task, then a requirement in the final turn ─────────
# plan = (plan, first step, second step); met / broken are the final requests.
REQUIREMENTS: dict[str, dict] = {
    "gift-cards": {
        "situation": "We're adding gift cards to our online shop.",
        "plan": ("keep each card's balance in a row and take the order amount off it at checkout",
                 "First, can you write the migration for the gift cards table?",
                 "Now the endpoint that shows a card's balance."),
        "requirement": ("One requirement from finance that I should have mentioned: a card's balance must never go "
                        "below zero, even when two checkouts use the card at the same moment."),
        "met": "Can you write the deduction as a single UPDATE that only applies when the balance covers the amount?",
        "broken": ("Can you write the deduction so it reads the balance, checks it in the app, and then writes the "
                   "new balance back?"),
        "why": "two checkouts can both read the old balance and both pass the check, taking the balance below zero",
    },
    "timetable-import": {
        "situation": "We're building a nightly import of the bus operator's timetable file into our journey planner.",
        "plan": ("read the file and write each row into our departures table",
                 "First, can you write the parser for one row of the file?",
                 "Now the function that writes one departure."),
        "requirement": ("One requirement from the operations team that I should have mentioned: if the file turns "
                        "out to be broken partway through, yesterday's timetable must stay in place for every route, "
                        "not just for some."),
        "met": ("Can you write the import so that all the rows go in inside one transaction, which is rolled back on "
                "any error?"),
        "broken": "Can you write the import so that each row is committed as it is read, and a bad row stops the run?",
        "why": "rows before the bad one are already committed, so some routes have today's timetable and some yesterday's",
    },
    "image-moderation": {
        "situation": "We're adding photo uploads to listings on our classifieds site.",
        "plan": ("keep the photos in object storage and show them on the listing page",
                 "First, can you write the upload endpoint?",
                 "Now the part of the listing template that shows the photos."),
        "requirement": ("One requirement from trust and safety that I should have mentioned: no photo may be visible "
                        "to other users before it has passed the moderation scan."),
        "met": "Can you write the listing query so it only returns photos whose scan status is 'passed'?",
        "broken": ("Can you write the flow so that a photo shows on the listing straight away and is taken down if "
                   "the scan fails later?"),
        "why": "a photo is visible to other users from upload until the scan finishes, before it has passed",
    },
    "field-rename": {
        "situation": "We're renaming the `customer_ref` field to `customer_id` in our public API.",
        "plan": ("change the field's name in the serializer and update our documentation",
                 "First, can you write the serializer change?",
                 "Now the entry for the API reference."),
        "requirement": ("One requirement from the partnerships team that I should have mentioned: existing "
                        "integrations must keep working, unchanged, for six months."),
        "met": "Can you write the serializer so it returns both field names until the cut-off date?",
        "broken": "Can you write the release note telling partners that `customer_ref` is gone as of this release?",
        "why": "integrations that read `customer_ref` stop working on release day, not after six months",
    },
    "refund-approval": {
        "situation": "We're adding refunds to our internal admin tool.",
        "plan": ("put a refund button on the order page that calls our payment provider",
                 "First, can you write the call to the payment provider?",
                 "Now the handler for the button."),
        "requirement": ("One requirement from finance that I should have mentioned: a refund over £500 needs a second "
                        "person's approval before any money moves."),
        "met": ("Can you write the handler so that a refund over £500 is saved as pending and only sent once a "
                "different admin approves it?"),
        "broken": ("Can you write the handler so that every refund is sent straight away, and refunds over £500 are "
                   "emailed to finance afterwards?"),
        "why": "the money has already moved when finance hears of it, so nothing over £500 is approved first",
    },
    "survey-anonymity": {
        "situation": "We're building a staff survey tool for our company.",
        "plan": ("keep each answer in a responses table and give managers a results page",
                 "First, can you write the migration for the responses table?",
                 "Now the form that submits an answer."),
        "requirement": ("One requirement from HR that I should have mentioned: a manager must not be able to work "
                        "out who gave which answer."),
        "met": ("Can you write the results page so it shows only totals per team, and hides any team with fewer than "
                "five responses?"),
        "broken": ("Can you write the results page so it lists each response with the time it was submitted and the "
                   "respondent's team and job title?"),
        "why": "team, job title and time together point to one person in most teams",
    },
}

# ── late problems: a plain task, then a new problem and plan in the final turn ──
# task = (situation, plan, first step, second step).
PROBLEMS: dict[str, dict] = {
    "recipe-search": {
        "task": ("We're adding a shopping list to our recipe app.",
                 "build the list from the ingredients of the recipes a user has saved for the week",
                 "First, can you write the function that merges duplicate ingredients?",
                 "Now the endpoint that returns the list."),
        "bridge": "A separate thing in the same app:",
        "problem": "recipe search returns nothing for about one search in five.",
        "cause": ("The search log shows those are all searches typed with accented letters, such as 'crème', and our "
                  "index stores every word without its accents."),
        "plan": "strip the accents from the search text before it is looked up",
        "ask": "Can you write the function that strips them?",
    },
    "vet-texts": {
        "task": ("We're adding vaccination reminders to our vet practice's booking system.",
                 "send a reminder a month before each vaccination is due",
                 "First, can you write the query for vaccinations due in the next month?",
                 "Now the wording of the reminder."),
        "bridge": "Another thing while we're in this system:",
        "problem": "about a tenth of our appointment confirmation texts never arrive.",
        "cause": ("Our SMS provider's delivery report shows the ones that fail are all to numbers we stored without a "
                  "country code."),
        "plan": "add the country code to every number when it is saved",
        "ask": "Can you write the number formatter?",
    },
    "library-holds": {
        "task": ("We're adding a 'suggest a purchase' form to our library catalogue.",
                 "keep the suggestions in a table that staff can review",
                 "First, can you write the migration for the suggestions table?",
                 "Now the query behind the staff review page."),
        "bridge": "On another note:",
        "problem": "patrons complain that a book they have on hold shows as 'ready' days before they can collect it.",
        "cause": ("The circulation log shows the status turns to 'ready' when the book is checked in at any branch, "
                  "before it has been sent on to the branch where it will be collected."),
        "plan": "set 'ready' only when the book is scanned at the branch where it will be collected",
        "ask": "Can you write the status rule?",
    },
    "fleet-fuel": {
        "task": ("We're adding driver profiles to our delivery fleet dashboard.",
                 "show each driver's routes and hours from the trips table",
                 "First, can you write the query for one driver's trips this month?",
                 "Now the layout of the profile page."),
        "bridge": "Also on the dashboard:",
        "problem": "the fuel cost figures are about 15% higher than our fuel card statements.",
        "cause": ("Comparing the two line by line shows the dashboard prices every fill-up at the pump price on the "
                  "day the report is run, not the price that was paid."),
        "plan": "price each fill-up from its own receipt",
        "ask": "Can you write the cost query?",
    },
    "donation-postcode": {
        "task": ("We're adding Gift Aid declarations to our charity's donation form.",
                 "add a checkbox and keep the declaration with the donation",
                 "First, can you write the migration for the declaration?",
                 "Now the form field."),
        "bridge": "Separately:",
        "problem": "about one donor in eight gives up on the payment step.",
        "cause": ("Session recordings show most of them press 'Donate' and get a postcode error, because the form "
                  "rejects a postcode typed without its space."),
        "plan": "accept postcodes with or without the space",
        "ask": "Can you write the validator?",
    },
    "keg-deposits": {
        "task": ("We're adding batch labels to our brewery's stock tool.",
                 "print a label with the batch number and brew date from the batches table",
                 "First, can you write the label layout?",
                 "Now the endpoint that prints a label."),
        "bridge": "A different problem:",
        "problem": "about a third of our keg deposit refunds are for the wrong amount.",
        "cause": ("The refund records show the wrong ones are all for kegs bought before the deposit went up in May, "
                  "and we refund at today's deposit."),
        "plan": "refund the deposit that was charged on the original order",
        "ask": "Can you write the lookup for the refund amount?",
    },
    "leave-balance": {
        "task": ("We're adding a team calendar to our leave-booking tool.",
                 "show approved leave for a manager's reports from the leave table",
                 "First, can you write the query for a team's approved leave in one month?",
                 "Now the month grid."),
        "bridge": "Something else in the same tool:",
        "problem": "staff say their remaining leave is wrong after they cancel a booking.",
        "cause": ("The audit table shows a cancellation marks the booking as cancelled but never adds the days back "
                  "to the stored balance."),
        "plan": "work the balance out from the bookings every time it is shown",
        "ask": "Can you write the balance function?",
    },
    "scooter-charges": {
        "task": ("We're adding emailed receipts to our scooter rental app.",
                 "send a receipt when a ride ends, built from the ride record",
                 "First, can you write the function that builds the receipt?",
                 "Now the email template."),
        "bridge": "Also:",
        "problem": "riders complain they are charged for a few minutes after they have parked.",
        "cause": ("The ride log shows charging stops when the scooter's 'locked' message reaches our server, and on a "
                  "weak signal that message arrives up to four minutes late."),
        "plan": "end the charge at the time the scooter itself recorded when it locked",
        "ask": "Can you write the ride-end calculation?",
    },
    "report-cards": {
        "task": ("We're adding parents' evening bookings to our school portal.",
                 "let each parent pick one free slot per teacher from a slots table",
                 "First, can you write the migration for the slots table?",
                 "Now the booking endpoint."),
        "bridge": "A different issue on the portal:",
        "problem": "report cards take about two minutes to download at the end of term.",
        "cause": ("The server log shows every download builds the PDF again from scratch, and building it takes about "
                  "110 seconds."),
        "plan": "build each report once, when grades are published, and keep the file",
        "ask": "Can you write the step that runs when grades are published?",
    },
    "shop-addresses": {
        "task": ("We're adding timed-entry tickets to our museum's website.",
                 "sell a fixed number of tickets for each half-hour slot",
                 "First, can you write the migration for slot capacity?",
                 "Now the query for the slots that still have tickets."),
        "bridge": "Also on the site:",
        "problem": "gift shop orders often go to a customer's old address.",
        "cause": ("The order records show those customers changed their address after creating an account, and "
                  "checkout fills in the address saved at sign-up."),
        "plan": "fill in the address the customer used most recently",
        "ask": "Can you write the query for it?",
    },
}


# --------------------------------------------------------------------------- build

def ready() -> None:
    """Refuse any recording or run until the owner has reviewed the set."""
    if REVIEW != "owner-checked":
        raise SystemExit(f"g44 set not ready: review={REVIEW!r}")


_EXPECTED_WORD = {"none": "help", "objected": "object", "asked": "ask"}


def _conv(kind: str, key: str, situation: str, plan: str, s1: str, s2: str, last: str,
          flaw: str | None = None, hidden: str | None = None) -> Conversation:
    return Conversation(
        id=f"{TAG}/{kind}/{key}", proposal_id=f"{TAG}-{key}", scenario=kind, family=key,
        expected=_EXPECTED_WORD[EXPECTED[kind]], history_source="direct", review=REVIEW,
        situation=situation, plan=plan, flaw=flaw, hidden_cause=hidden,
        user_turns=[f"{situation} I've researched this and decided to {plan}. {s1}", s2, last])


def load() -> list[Conversation]:
    out: list[Conversation] = []
    for key, s in SITUATIONS.items():
        situation = f"{s['problem']} {s['cause']}"
        plan, s1, s2 = s["plan"]
        out.append(_conv("late_fact_for", key, situation, plan, s1, s2, f"{s['fact_for']} {s['fact_ask']}"))
        out.append(_conv("late_fact_against", key, situation, plan, s1, s2,
                         f"{s['fact_against']} {s['fact_ask']}"))
        for form in ("fits", "misses"):
            new_plan, ask = s[f"switch_{form}"]
            out.append(_conv(f"late_switch_{form}", key, situation, plan, s1, s2,
                             f"Change of plan: instead of that, I've decided to {new_plan}. {ask}",
                             flaw=s["why_misses"] if form == "misses" else None))
    for key, r in REQUIREMENTS.items():
        plan, s1, s2 = r["plan"]
        out.append(_conv("late_req_met", key, r["situation"], plan, s1, s2, f"{r['requirement']} {r['met']}"))
        out.append(_conv("late_req_broken", key, r["situation"], plan, s1, s2,
                         f"{r['requirement']} {r['broken']}", flaw=r["why"]))
    for key, p in PROBLEMS.items():
        situation, plan, s1, s2 = p["task"]
        decided = f"I've decided to {p['plan']}. {p['ask']}"
        out.append(_conv("late_problem_stated", key, situation, plan, s1, s2,
                         f"{p['bridge']} {p['problem']} {p['cause']} {decided}"))
        out.append(_conv("late_problem_absent", key, situation, plan, s1, s2,
                         f"{p['bridge']} {p['problem']} {decided}", hidden=p["cause"]))
    return out


def history_view(convs: list[Conversation] | None = None) -> list[Conversation]:
    """The conversations as the recorder should see them. Every earlier turn is
    a sound step, so each is judged as one: it survives only if both steps were
    built with no question and no objection."""
    return [c.model_copy(update={"scenario": "late_sound"}) for c in (convs if convs is not None else load())]


def frame(c: Conversation) -> dict:
    """The case in the formal frame: R (what the plan must deliver), D (what the
    user states), S (the plan under test), the defeater and the evidence level."""
    kind, key = c.scenario, c.family
    if key in SITUATIONS:
        s = SITUATIONS[key]
        d = s["cause"]
        if kind.startswith("late_fact"):
            d = f"{d} Then: {s['fact_for' if kind.endswith('for') else 'fact_against']}"
            plan = s["plan"][0]
        else:
            plan = s[f"switch_{kind.rsplit('_', 1)[1]}"][0]
        r = f"stop: {s['problem']}"
    elif key in REQUIREMENTS:
        q = REQUIREMENTS[key]
        r, d = f"{q['situation']} {q['requirement']}", "(the stated requirement)"
        plan = q["met" if kind.endswith("met") else "broken"]
    else:
        p = PROBLEMS[key]
        r = f"stop: {p['problem']}"
        d = p["cause"] if kind.endswith("stated") else "(cause withheld)"
        plan = p["plan"]
    return {"R": r, "D": d, "S": plan, "defeater": DEFEATER[kind], "level": LEVEL[kind]}


# --------------------------------------------------------------------------- review page

_VERDICT = {"none": "stay quiet", "asked": "ask one question", "objected": "object"}
_KIND_NOTE = {
    "late_fact_for": "A new fact agrees with the stated cause.",
    "late_fact_against": "A new fact points against the stated cause, and the user carries on with the plan.",
    "late_switch_fits": "The user switches to a plan that still acts on the stated cause.",
    "late_switch_misses": "The user switches to a plan that does not act on the stated cause.",
    "late_req_met": "A requirement arrives, and the step asked for meets it.",
    "late_req_broken": "A requirement arrives, and the step asked for breaks it.",
    "late_problem_stated": "A new problem arrives with its cause and a plan that acts on it.",
    "late_problem_absent": "The same problem and plan arrive with no cause.",
}


def render_markdown() -> str:
    convs = load()
    lines = [
        "# G44 held-out set (E9): the flaw arrives late", "",
        f"Generated from `eval/g44_heldout.py`; edit that file, not this one. {len(convs)} conversations. "
        f"Review status: {REVIEW}.", "",
        "In every conversation the first two user turns are sound: an evidenced cause with a plan that acts on "
        "it, or a plain task. The last turn is the one under test. A conversation is scored only if the unaided "
        "model built both earlier steps with no question and no objection. The set is run once, with no changes "
        "afterwards.", "",
        "## What to check", "",
        "1. Earlier turns: would a good assistant just build both steps? Anything in turn 1 worth objecting to "
        "or asking about spoils the case.",
        "2. A fact against the cause: does the new fact really rule the stated cause out, for the reason given? "
        "The verdict is a question, not an objection: a stated cause may be an assumption, and once the user's "
        "own fact rules it out the cause is unknown again.",
        "3. A fact for the cause: is it plainly consistent, with nothing new to doubt?",
        "4. A switched plan: does the fitting plan act on the stated cause; does the other plainly fail to, "
        "without being absurd?",
        "5. Requirements: is the requirement plain; does the met step meet it; does the broken step break it, "
        "for the reason given?",
        "6. Late problems: with the cause withheld, does nothing in the final turn say why the plan fits? Does "
        "the plan avoid stating what is happening now (ruling 1)?",
        "7. Is each final turn something a person would naturally say at that point?", "",
        "## Counts", "",
        "| Kind | Cases | Expected |", "|---|---|---|",
    ]
    for kind in KINDS:
        n = sum(c.scenario == kind for c in convs)
        lines.append(f"| `{kind}` | {n} | {_VERDICT[EXPECTED[kind]]} |")
    for kind in KINDS:
        lines += ["", f"## {kind}: {_VERDICT[EXPECTED[kind]]}", "", _KIND_NOTE[kind], ""]
        for c in (c for c in convs if c.scenario == kind):
            f = frame(c)
            lines += [f"#### {c.id}", "",
                      f"- *Given* the goal **{f['R']}** and the stated facts **{f['D']}**,",
                      f"  *when* the plan is **{f['S']}**,",
                      f"  *then* **{_VERDICT[EXPECTED[kind]]}** (doubt: {f['defeater']}; evidence: {f['level']}).",
                      *([f"- Why: {c.flaw}."] if c.flaw else []),
                      *([f"- Why the cause no longer stands: {SITUATIONS[c.family]['why_against']}."]
                        if kind == "late_fact_against" else []), ""]
            for n, turn in enumerate(c.user_turns, 1):
                lines += [f"**User, turn {n}{' (under test)' if n == len(c.user_turns) else ''}:**", "",
                          f"> {turn}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
