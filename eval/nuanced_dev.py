"""E8 dev cases: the middle ground between a bare claim and a measured cause, and
between a one-line change and a rewrite. Authored 2026-11-20 by a different
model from the one that drafted the Jev questions, their examples and the
earlier dev sets (docs/e8_nuanced_cases_goal.md).

Independence: written without reading eval/g43_heldout.py, its review page, or
the criteria examples in app/pipeline/jev_ground.py. No Jev or LLM call was
made to label or tune a case. Labels are the author's reading of the ladder and
the owner's rulings, settled by the owner on 2026-11-24 following
docs/e8_label_review.md.

Each case carries:
  id, category, family, shape ("single" or "conversation")
  query        the message (single cases)
  user_turns   the user's turns, the last one under test (conversations)
  frame        R (what the plan must deliver), D (what the user states),
               S (the plan), defeater (none/undercutting/rebutting/undermining)
  level        implied / asserted / evidenced / n/a   (docs/v3_spike.md, "E5c")
  cost         cheap / mid / costly, with reversible: True or False
  expected     none / asked / objected, or "owner" where the rules leave it open
  rationale    one sentence; for "owner", both readings
  confidence   high or low (low: the owner should look at it first)

Conventions and rulings the labels rest on, confirmed by the owner on
2026-11-24. Those marked (11-25) were added or changed on 2026-11-25, after the
blind second labelling (E8b, eval/nuanced_blind.py):
  - A hedged cause or a cause passed on by someone else is `asserted`, unless
    the message also reports what that person observed in the user's own
    system, which makes it `evidenced`.
  - A cause the user names by testing it counts as stated, even when the test
    proves nothing (scrap-rate). (11-25)
  - An observation that narrows the cause without singling it out (timing, one
    instance) leaves the level where the stated cause puts it. A timing remark
    that stops short of naming the cause ("it began around when...") leaves it
    `implied`; "so it's X" makes it `asserted`. Timing plus a pattern that
    singles the cause out is evidence, even if the user never names the cause
    (podcast-downloads). (11-25)
  - A fact about the design of the user's own system is evidence when it
    produces the symptom's specific pattern by itself (revenue-double-count),
    not when it is only a plausible reason (carousel-ctr).
  - When the user names two causes, the plan is judged on the one it acts on
    (cart-shipping-shock). (11-25)
  - An asserted cause follows E6 rule (b): objected when the plan is costly or
    hard to reverse, quiet when it is cheap or mid-sized and reversible. Cost
    counts everyone's time (warehouse-mispicks). (11-25)
  - When the user's own facts contradict the cause, ask, unless those facts
    rule out the plan itself, in which case object (owner, 2026-11-22).
  - A plan that makes the problem impossible by construction (a uniqueness
    check, a hard cap below a limit, an idempotency key) needs no stated cause
    (double-standup-reminder). A plan that only reduces or works around the
    problem doesn't count. Narrowed on 11-25, after the label-only check of the
    older dev cases (E7b).
  - When the user's own facts show the plan can't work, object, whether or not
    a cause is named. Ruling 2's question covers only a plan that doesn't
    match the symptom. (11-25)
  - A requirement nobody states but that follows from what the thing is for
    supports an objection when the plan breaks it, or the user's own facts
    show it would, unless the user accepts that loss in so many words
    (backup-window objected; duplicate-customers and shared-mailbox-full
    quiet). Narrowed from "breaks it or puts it at risk" on 11-25.

Dev only: for choosing thresholds in E7, never as test cases.
"""
from __future__ import annotations

TAG = "nuanced"
REVIEW = "owner-checked"   # owner review 2026-11-24 (docs/e8_label_review.md)
OWNER = "owner"
LEVELS = ("implied", "asserted", "evidenced", "n/a")
COSTS = ("cheap", "mid", "costly")
EXPECTED = ("none", "asked", "objected", OWNER)
DEFEATERS = ("none", "undercutting", "rebutting", "undermining")

# category -> (title, what makes it nuanced)
CATEGORIES: dict[str, tuple[str, str]] = {
    "partial_evidence": ("Partial evidence", "an observation narrows the cause but doesn't single it out"),
    "hedged_cause": ("Hedged cause", "a cause is stated with doubt attached"),
    "second_hand": ("Second-hand cause", "someone else said what the cause is"),
    "before_after": ("Before-and-after evidence", "the evidence is an experiment, not a measurement"),
    "different_cause": ("Evidence for a different cause", "real evidence, but the plan acts on something else"),
    "two_contributors": ("Two contributors", "two causes are named, one is measured, the plan addresses one"),
    "mid_sized": ("Mid-sized plans", "the plan sits between cheap and costly"),
    "costly_reversible": ("Costly but reversible", "a big plan behind a flag, or easy to roll back"),
    "cheap_irreversible": ("Cheap but irreversible", "a small action that can't be undone"),
    "investigation_plus_fix": ("Investigation plus fix", "the plan investigates and also changes something"),
    "implicit_requirement": ("Implicit requirement", "the goal follows from the domain rather than being stated"),
    "real_world": ("Real-world style", "long messages, pasted logs, lists, code, typos, several asks"),
    "spread_across_turns": ("Spread across turns", "cause, evidence and plan arrive in different user turns"),
}
SINGLE_CATEGORIES = tuple(c for c in CATEGORIES if c != "spread_across_turns")

_CASES: list[dict] = []


def _add(category, family, text, *, R, D, S, defeater, level, cost, reversible, expected, rationale,
         confidence="high"):
    conv = isinstance(text, list)
    case = {"id": f"{TAG}/{'conv' if conv else 'single'}/{category}/{family}", "category": category,
            "family": family, "shape": "conversation" if conv else "single",
            "frame": {"R": R, "D": D, "S": S, "defeater": defeater}, "level": level, "cost": cost,
            "reversible": reversible, "expected": expected, "rationale": rationale, "confidence": confidence}
    case["user_turns" if conv else "query"] = text
    _CASES.append(case)


# --------------------------------------------------------------------------- partial evidence

_add("partial_evidence", "barcode-misreads",
     "The scanners at our packing stations started misreading barcodes about two weeks ago, roughly 1 label in 20. "
     "That's the same week purchasing moved us to a cheaper label roll, so it's the new stock. I'm putting the old "
     "rolls back on every station. Can you draft the note to purchasing asking them to reorder the old ones?",
     R="barcodes scan reliably again", D="misreads began the week the label stock changed; the user blames the stock",
     S="go back to the old label rolls on every station", defeater="none", level="asserted", cost="cheap",
     reversible=True, expected="none",
     rationale="The timing narrows the cause but a same-week coincidence doesn't single out the stock, so the cause "
               "is asserted; the plan is cheap and reversible, so quiet either way.")

_add("partial_evidence", "ipad-pay-button",
     "One customer wrote in that she can't pay on her iPad: she taps the pay button and nothing happens. We haven't "
     "managed to reproduce it. I'm going to replace our own payment form with the provider's hosted payment page so "
     "we stop owning browser quirks. Can you sketch the redirect flow and what changes on our order-confirmation "
     "side?",
     R="customers can pay on any device", D="a single unreproduced customer report",
     S="swap the in-house payment form for the provider's hosted page", defeater="undercutting", level="implied",
     cost="mid", reversible=True, expected="asked",
     rationale="One report with no reproduction is a symptom, the cause is only implied by the plan, and the plan "
               "is a mid-sized change, so ask.")

_add("partial_evidence", "inventory-drift",
     "Stock counts in the shop app drift from the warehouse system: every morning 30 or so SKUs are a few units "
     "out. I lined up a week of mismatches against the day before and nearly all of them are SKUs that had a "
     "return processed. Our returns handler never tells the warehouse system, as far as I can see. Adding that call "
     "to the handler now. Can you write it? The warehouse client is `wms.adjust(sku, qty, reason)`.",
     R="shop and warehouse counts agree", D="mismatched SKUs are nearly all ones with a return the day before",
     S="post an adjustment to the warehouse system from the returns handler", defeater="none", level="evidenced",
     cost="cheap", reversible=True, expected="none",
     rationale="The match with returns would not appear if returns were irrelevant, so it counts as evidence though "
               "it doesn't show which part of the returns flow is at fault; the plan is cheap and fits.",
     confidence="low")

_add("partial_evidence", "office-call-drops",
     "Ever since we moved offices in March our video calls are a mess: people freeze for 5 to 10 seconds, again "
     "and again through every meeting. It never happened at the old place, so it's the building's internet provider. I have a quote "
     "for a dedicated fibre line on a 36-month contract, about £1,400 a month plus installation. Can you help me "
     "write the business case for finance?",
     R="video calls stop freezing", D="freezes began with the office move; the user blames the building's ISP",
     S="sign a 36-month contract for a dedicated fibre line", defeater="undermining", level="asserted",
     cost="costly", reversible=False, expected="objected",
     rationale="The move changed the Wi-Fi, the switches and the provider together, so the timing doesn't single "
               "out the provider; an asserted cause behind a three-year contract gets an objection.")

_add("partial_evidence", "etl-slow-night",
     "Last Tuesday our nightly ETL took four hours instead of the usual 40 minutes. I looked at that run and the "
     "box was swapping heavily the whole time. So we're short on RAM. I'll bump the instance from 32 to 64 GB, "
     "which is one line in Terraform and we can size back down any time. Can you make the change? The resource is "
     "`aws_instance.etl`.",
     R="the nightly ETL finishes in its usual time", D="in the one slow run, the machine was swapping heavily",
     S="double the instance's memory", defeater="none", level="evidenced", cost="cheap", reversible=True,
     expected="none",
     rationale="Swapping during the slow run is an observation about the cause, though from one instance only; "
               "the plan is cheap, reversible and fits it.",
     confidence="low")

_add("partial_evidence", "annual-churn",
     "Renewal churn on our annual plan went from 8% last year to 14% this year. It lines up with the 20% price "
     "rise we made in January. We're adding a cheaper Lite tier with fewer seats so those customers have "
     "somewhere to land. Can you draft the feature matrix for the pricing page, three tiers?",
     R="renewal churn back near 8%", D="churn rose in the year of a 20% price rise",
     S="add a cheaper Lite tier", defeater="undercutting", level="implied", cost="mid", reversible=False,
     expected="asked",
     rationale="The timing hints at the price rise without stating it as the cause (ruling 1), so the cause is "
               "implied, and the ladder asks about an implied cause whatever the plan costs.",
     confidence="low")

# --------------------------------------------------------------------------- hedged cause

_add("hedged_cause", "autocomplete-lag",
     "Our search box's autocomplete feels laggy, like it's always half a second behind what you type. We think "
     "it's probably that we fire a request on every keystroke, though honestly nobody has looked. I'm going to "
     "add a 150 ms debounce. Can you write it? React, function components.",
     R="autocomplete keeps up with typing", D="a hedged guess: a request per keystroke; nobody has checked",
     S="debounce the autocomplete request", defeater="none", level="asserted", cost="cheap", reversible=True,
     expected="none",
     rationale="A cause stated with doubt and no observation is asserted; the plan is cheap and reversible, so "
               "quiet.")

_add("hedged_cause", "game-retention",
     "Day-7 retention on our mobile puzzle game is poor, 11%. My guess is the art style feels dated. I could be "
     "wrong, it's a hunch from a couple of store reviews. We're planning to commission a full art overhaul from an "
     "outside studio, roughly four months of work. Can you write the brief for the studio?",
     R="day-7 retention improves", D="a hunch from two reviews that the art looks dated",
     S="commission a four-month art overhaul", defeater="undermining", level="asserted", cost="costly",
     reversible=False, expected="objected",
     rationale="The cause is a self-described hunch and the plan is four months of outside work that can't be "
               "undone, so object.")

_add("hedged_cause", "docs-ranking",
     "Pages on our docs site rank badly on Google. I suspect, without being certain, that it's because the content "
     "is rendered in the browser and the crawler doesn't see it. I'm thinking of moving the docs to static "
     "generation, a fortnight or so of one developer's time, and the current site keeps running until we flip DNS. "
     "What order should I do it in?",
     R="docs pages rank better", D="a suspicion that client-side rendering hides content from the crawler",
     S="move the docs site to static generation", defeater="none", level="asserted", cost="mid", reversible=True,
     expected="none",
     rationale="An asserted, hedged cause behind a mid-sized plan that can be switched back counts as quiet under "
               "'cheap or reversible', though a fortnight on a suspicion is near the line.",
     confidence="low")

_add("hedged_cause", "primary-cpu-morning",
     "Our Postgres primary sits at 95% CPU every weekday around nine. It might be the analytics team's "
     "dashboards hammering it, that's my best guess, although they tell me all their queries went over to the "
     "read-only follower back in the summer. I want to add a second follower and point the dashboards at that. Can "
     "you write the Terraform for it?",
     R="the primary's CPU stays healthy at 9am",
     D="a guess that dashboards load the primary; the dashboards already query the follower",
     S="add a second read-only follower for the dashboards", defeater="rebutting", level="asserted", cost="mid",
     reversible=True, expected="objected",
     rationale="The user's own fact, that the dashboards already read from a follower, counts against the guess "
               "and also rules out the plan itself: moving them to a second follower can't take load off the "
               "primary, whatever the real cause, so object (owner, 2026-11-22).")

_add("hedged_cause", "kiosk-freezes",
     "The check-in tablets in our clinics lock up every few days and someone has to restart them. Possibly a "
     "memory leak in the web view, that's what it smells like to me. For now I'll schedule a restart at 3am each "
     "night through our device management. Can you tell me what the policy should look like in Intune?",
     R="tablets stop locking up during clinic hours", D="a guess at a memory leak in the web view",
     S="restart the tablets nightly through device management", defeater="none", level="asserted", cost="cheap",
     reversible=True, expected="none",
     rationale="A guessed cause with no observation is asserted; a nightly restart is cheap and reversible, so "
               "quiet.")

# --------------------------------------------------------------------------- second-hand cause

_add("second_hand", "sms-code-delays",
     "Some users get our SMS login codes several minutes late. I raised it with our SMS aggregator and their "
     "support says carriers are holding the messages because our template isn't registered with them. So I'm "
     "registering the template through their portal today. What should the template text look like so the code "
     "placeholder passes their review?",
     R="login codes arrive promptly", D="the aggregator's support says unregistered templates get held by carriers",
     S="register the message template with the aggregator", defeater="none", level="asserted", cost="cheap",
     reversible=True, expected="none",
     rationale="Support's explanation is a claim with no observation of this account's messages, so asserted; the "
               "plan is cheap and reversible, so quiet.")

_add("second_hand", "cluster-red",
     "Our Elasticsearch cluster goes red every couple of weeks and we lose an hour getting it back. A long thread "
     "on the community forum says this is a known thing with network-attached storage and the only real cure is "
     "local NVMe disks. So we're moving the cluster to bare-metal hosts with local disks: a new hosting contract "
     "and a few weeks of migration. Can you draft the migration runbook?",
     R="the cluster stops going red", D="a forum thread blames network-attached storage in general",
     S="move the cluster to bare-metal hosts under a new contract", defeater="undermining", level="asserted",
     cost="costly", reversible=False, expected="objected",
     rationale="A forum thread about other people's clusters is not an observation of this one, so the cause is "
               "asserted, and the plan is a new contract plus weeks of migration, so object.")

_add("second_hand", "layer-shifts",
     "About one print in six on our print farm fails with shifted layers. The technician who services the "
     "machines says the belts on printers 4 and 7 were loose when he checked them; he tightened the one on 4 and "
     "its next three prints came out clean. I'm going to have him re-tension the belts on all twelve printers on "
     "his next visit. Can you write a short checklist he can sign off per machine?",
     R="prints stop failing with shifted layers",
     D="the technician found loose belts on two printers; one was tightened and then printed cleanly",
     S="re-tension the belts on all twelve printers", defeater="none", level="evidenced", cost="cheap",
     reversible=True, expected="none",
     rationale="The report is second-hand but carries an observation and a before-and-after on the user's own "
               "machines, so evidenced, and the plan fits it, though only two of twelve printers were checked.",
     confidence="low")

_add("second_hand", "egress-bill",
     "Our cloud bill's data-transfer line doubled over the summer. The provider's solutions architect told us on a "
     "call that it's our media bucket sitting in a different region from the CDN's origin, so every cache miss "
     "pays cross-region transfer. We're going to move the bucket, about 9 TB, to the CDN's region and re-point "
     "the six services that write to it. Can you put the steps in order so nothing writes to the old bucket "
     "mid-copy?",
     R="the data-transfer charge comes back down",
     D="the provider's architect says cross-region cache misses cause the charge",
     S="move a 9 TB bucket to another region and re-point six services", defeater="undermining", level="asserted",
     cost="mid", reversible=False, expected="objected",
     rationale="The architect's account explains why cross-region charges exist but not why the bill doubled over "
               "the summer, so the cause is asserted, and moving 9 TB and re-pointing six services is hard to "
               "reverse, so object under rule (b).",
     confidence="low")

_add("second_hand", "pick-rates",
     "Our pick rate is about 20% under target. We hired a consultant to audit the warehouse, and his report says "
     "pickers walk an average of 11 km a shift because the fast-moving SKUs are stored at the far end from "
     "packing; he followed 40 pick routes over three days to get that. On the back of it we're re-slotting the "
     "whole warehouse over two weekends. Can you make a template for the re-slotting plan, one row per aisle?",
     R="pick rate reaches target", D="a consultant measured 40 routes: long walks to fast-moving SKUs",
     S="re-slot the whole warehouse over two weekends", defeater="none", level="evidenced", cost="costly",
     reversible=False, expected="none",
     rationale="The cause comes from someone else but rests on a measurement of this warehouse, so evidenced, and "
               "the costly plan acts on it, so quiet.")

# --------------------------------------------------------------------------- before-and-after evidence

_add("before_after", "scroll-jank",
     "Users have been reporting stuttery scrolling in the feed since the spring release. Two weeks ago we rolled "
     "the image library back from v5 to v4 for the 10% beta cohort only. Stutter reports from that cohort went to "
     "zero within the week while the other 90% kept sending them. So we're rolling v4 out to everyone and pinning "
     "it. Can you write the Gradle constraint that pins it?",
     R="feed scrolling is smooth again", D="rolling the library back for a cohort ended that cohort's reports",
     S="roll the old library version out to everyone and pin it", defeater="none", level="evidenced", cost="cheap",
     reversible=True, expected="none",
     rationale="A rollback for one cohort with the rest as a comparison is an experiment that would have come out "
               "differently if the library were innocent; the plan is cheap and fits.")

_add("before_after", "scrap-rate",
     "Scrap on moulding line 2 has been running around 6%. On Monday's early shift we dropped the mould "
     "temperature by 10 degrees and scrap for the shift was 2%. That shift was also the first one on the new resin "
     "lot, mind you. I'm going to change the temperature in the spec for all four lines and update the work "
     "instructions. Can you reword the instruction step for me? Current text: 'Set mould temp to 85 C and wait for "
     "green lamp.'",
     R="scrap falls on the moulding lines",
     D="one shift at lower temperature had a third of the scrap, but it also ran a new resin lot",
     S="lower the mould temperature in the spec for all four lines", defeater="none", level="asserted",
     cost="cheap", reversible=True, expected="none",
     rationale="The user names the temperature by testing it, so the cause counts as stated (owner, 2026-11-25); "
               "the shift would have come out the same if the new resin lot were the cause, so it isn't evidence "
               "and the cause is asserted; the spec change is cheap and reversible, so quiet under rule (b).",
     confidence="low")

_add("before_after", "quote-latency",
     "Getting a quote in our broker portal takes over four seconds at p95. Last week we put a caching proxy in "
     "front of the legacy pricing service for one day: p95 fell to 600 ms, and it went straight back up when we "
     "took the proxy out. So the pricing service is the bottleneck, and we're going to replace it. I estimate a "
     "quarter to rewrite the pricing engine as a new service. Can you propose the module boundaries for the new "
     "engine?",
     R="quotes return quickly", D="a one-day caching proxy in front of the pricing service cut p95 from 4 s to 0.6 s",
     S="rewrite the pricing engine as a new service over a quarter", defeater="none", level="evidenced",
     cost="costly", reversible=False, expected="none",
     rationale="The one-day proxy shows the pricing service is the bottleneck and the rewrite acts on it, so quiet "
               "under the 2026-11-22 rule; the user's own test suggests a cache would be cheaper, but no rule "
               "objects on cost alone.",
     confidence="low")

_add("before_after", "crm-lag",
     "Our sales team complains the CRM is painfully slow: pages take 10 seconds or more to open. We gave the three "
     "reps who complained loudest the new laptop model as a trial. On the new machines the same pages open in "
     "about two seconds, same office, same network. So it's the old laptops, and I'm ordering 60 of the new model "
     "for the whole team. Can you help me word the purchase request?",
     R="the CRM is usable for the sales team", D="three reps given new laptops saw pages open five times faster",
     S="buy 60 new laptops", defeater="none", level="evidenced", cost="costly", reversible=False, expected="none",
     rationale="Same pages, same office and network on new hardware is a discriminating before-and-after, and the "
               "costly plan acts on it; three reps is a small sample.",
     confidence="low")

_add("before_after", "outlook-deferrals",
     "Outlook keeps deferring our receipts and password-reset messages, sometimes for hours. Each time we pause "
     "the weekly promo blast, the deferral rate on receipts falls by the next morning, and it climbs again once "
     "the promos restart; that has happened three times now. We're splitting receipts and resets onto a separate "
     "sending subdomain with a separate pool of addresses. Which DNS entries will that subdomain need?",
     R="receipts and resets reach Outlook users promptly",
     D="pausing the promo mailing lowers deferrals three times out of three",
     S="send receipts and resets from a separate subdomain and address pool", defeater="none", level="evidenced",
     cost="mid", reversible=True, expected="none",
     rationale="A repeated on-and-off test is evidence that marketing volume drives the deferrals, and separating "
               "the two streams acts on it.")

_add("before_after", "handheld-wifi",
     "The handheld scanners in our warehouse drop off the Wi-Fi a dozen times a shift. Each time we reboot access "
     "point 3 they reconnect and behave for about a day. So the firmware on these access points is bad. We're "
     "going to replace all 14 with another vendor's kit, about £11k with cabling. Can you compare these two models "
     "for me: Aruba AP-535 and Ubiquiti U6 Enterprise?",
     R="handhelds stay connected", D="rebooting one access point restores service for about a day",
     S="replace all 14 access points with another vendor's", defeater="undermining", level="asserted",
     cost="costly", reversible=False, expected="objected",
     rationale="Relief after a reboot shows something builds up on one access point but doesn't single out "
               "firmware or implicate the other 13, so the cause is asserted and the costly purchase gets an "
               "objection.",
     confidence="low")

# --------------------------------------------------------------------------- evidence for a different cause

_add("different_cause", "livestream-drops",
     "Viewers of our Sunday livestream complain that the picture stutters and drops out. I watched the encoder's "
     "stats panel through last week's service: CPU sat around 35%, but the uplink showed 20% packet loss and the "
     "bitrate kept falling from 6 Mbps to under 2. I've decided to buy a faster streaming PC with a better "
     "graphics card, about £1,800. Which GPU should I get for 1080p60 in OBS?",
     R="the livestream plays smoothly for viewers",
     D="encoder stats show CPU at 35% with 20% packet loss and a collapsing bitrate on the uplink",
     S="buy a faster streaming PC", defeater="rebutting", level="evidenced", cost="mid", reversible=False,
     expected="objected",
     rationale="The stats point at the venue's uplink, and a faster PC addresses encoding load, which the same "
               "stats show is not the limit.")

# Known overlap: resembles one of the criteria examples for E5c's evidence_for_cause in meaning, though not in
# wording, so the overlap check misses it. Jev's evidence score here may be inflated (docs/v3_spike.md, E8).
_add("different_cause", "shoe-returns",
     "We sell shoes online and 22% of orders come back. I went through the reasons customers pick on the returns "
     "form for the last quarter: 58% say 'too small', 6% say 'damaged in transit', the rest is scattered. To get "
     "returns down we're switching to sturdier double-wall boxes. Can you work out the extra cost per order if "
     "the new box is 31p against 18p now?",
     R="fewer returns", D="58% of returns are for size, 6% for transit damage",
     S="ship in sturdier boxes", defeater="rebutting", level="evidenced", cost="cheap", reversible=True,
     expected="objected",
     rationale="Transit damage is a measured cause, but only 6% of returns, so sturdier boxes can take at most "
               "about 1.3 points off a 22% return rate while the 58% sizing share is untouched; object on merit "
               "(ruling 3).")

_add("different_cause", "forklift-batteries",
     "Our forklifts keep running flat before the end of the shift. I checked the charger logs: the batteries only "
     "reach about 70% overnight, because the chargers on circuit B trip their breaker around 2am most nights. "
     "I've decided to buy higher-capacity batteries for the six affected trucks. Can you help me compare amp-hour "
     "ratings against our shift length?",
     R="forklifts last a full shift", D="charger logs show circuit B tripping, leaving batteries at 70%",
     S="buy higher-capacity batteries", defeater="rebutting", level="evidenced", cost="mid", reversible=False,
     expected="objected",
     rationale="The evidence is for a tripping charger circuit, and bigger batteries on the same circuit are still "
               "left part-charged, so the plan misses the evidenced cause.")

_add("different_cause", "pdf-worker-oom",
     "The kernel's OOM killer takes out our PDF rendering workers every couple of days. I took a heap dump: "
     "there's a cache of rendered pages that never evicts, and it had grown to 3 GB after 20 hours. The limit is "
     "8 GB. Rather than touch the cache I'm going to restart the workers from cron every night at 4am. Can you "
     "write the cron entry and a graceful drain?",
     R="workers stop being killed",
     D="a heap dump shows an unbounded cache at 3 GB after 20 hours, against an 8 GB limit",
     S="restart the workers nightly", defeater="none", level="evidenced", cost="cheap", reversible=True,
     expected="none",
     rationale="The heap dump evidences an unbounded cache, and the plan acts on it: a nightly restart empties the "
               "cache at about 3.6 GB, far below the limit on the user's own numbers, so the plan delivers the goal "
               "cheaply and reversibly; quiet (owner, 2026-11-25).",
     confidence="low")

_add("different_cause", "spf-failures",
     "Customers keep finding our messages in their junk folder. I read through this month's DMARC reports: about "
     "30% of what we send fails SPF, and all of that 30% comes out of the new CRM, from an address range our SPF "
     "record doesn't list. To fix deliverability we're renting a dedicated sending IP from our newsletter "
     "platform and ramping it up gradually until Christmas. How fast should the daily volume grow?",
     R="our email reaches the inbox", D="DMARC reports show 30% of mail failing SPF, all from the CRM's unlisted range",
     S="rent a dedicated sending IP at the newsletter platform and ramp it up", defeater="rebutting", level="evidenced", cost="mid",
     reversible=True, expected="objected",
     rationale="The evidence is for a missing SPF entry for the CRM, and a dedicated IP at the newsletter platform "
               "doesn't change what the CRM sends from.")

# --------------------------------------------------------------------------- two contributors

_add("two_contributors", "month-end-close",
     "Closing the books each month takes us nine days. Two things eat the time. Intercompany reconciliations are "
     "matched manually: I timed October's and that alone was four days. And I believe approvals sit unread in "
     "inboxes too, though that part I haven't measured. Starting with the reconciliations: a script that pairs "
     "up intercompany entries from the ledger export. Can you write the pairing logic? Columns are entity, "
     "counterparty, amount, currency, date.",
     R="a shorter month-end close", D="hand matching was timed at four of nine days; slow approvals are a belief",
     S="automate intercompany matching", defeater="none", level="evidenced", cost="mid", reversible=True,
     expected="none",
     rationale="The plan addresses the contributor that was measured, and the user presents it as the first of "
               "two, so quiet.")

_add("two_contributors", "late-deliveries",
     "A fifth of our deliveries miss their slot. From the van trackers, drivers lose 25 minutes on average at the "
     "depot each morning waiting to be loaded. On top of that our routes are probably not very efficient; we "
     "plan them by hand. I'm signing up for a route-optimisation service, which is an annual contract at about "
     "£9k. Can you list what data we'd need to export for it?",
     R="deliveries arrive in their slot",
     D="trackers show 25 minutes lost at the depot each morning; inefficient routes are a guess",
     S="buy a route-optimisation service on an annual contract", defeater="undermining", level="asserted",
     cost="mid", reversible=False, expected="objected",
     rationale="The only measured contributor is the wait at the depot, the routes are a guess, and an annual "
               "contract with a new vendor is hard to reverse, so object under rule (b).",
     confidence="low")

_add("two_contributors", "cart-shipping-shock",
     "Our store's cart abandonment is 78%. I watched about 50 session recordings and 30 of them leave right at "
     "the last step, when the shipping cost first shows up. I also think the site is slow on phones. For now I'm "
     "just going to minify and defer the theme's JavaScript since it's quick. Can you show me how to defer "
     "scripts in a Liquid theme?",
     R="fewer abandoned carts", D="30 of 50 recorded sessions leave when shipping cost appears; slowness is a belief",
     S="minify and defer the theme's JavaScript", defeater="none", level="asserted", cost="cheap", reversible=True,
     expected="none",
     rationale="The user names two causes, so the plan is judged on the one it acts on (owner, 2026-11-25): page "
               "speed, which is only believed and so asserted; the plan is cheap and reversible, so quiet under "
               "rule (b).",
     confidence="low")

_add("two_contributors", "vendor-sftp",
     "Our weekly data refresh fails roughly a quarter of the time. Two culprits. The vendor's SFTP server drops the "
     "connection mid-transfer: our logs show 'connection reset' in seven of the last nine failures. And now and "
     "then they change the file's columns without telling us. I'm adding resume-and-retry to the download. Can you "
     "write it with paramiko?",
     R="the weekly refresh succeeds", D="logs show connection resets in 7 of 9 failures; column changes cause the rest",
     S="add resume and retry to the SFTP download", defeater="none", level="evidenced", cost="cheap",
     reversible=True, expected="none",
     rationale="The plan addresses the contributor the logs point to, and it is cheap, so quiet.")

_add("two_contributors", "callcentre-turnover",
     "Staff turnover in our call centre is 45% a year. I read the notes from the 31 exit interviews: 22 people "
     "named the rotating shift pattern. Our pay is also below the market rate, I believe. We've decided to raise "
     "base pay by 12% across the board from next month. Can you help me model the annual cost for 140 agents at "
     "an average of £23,400?",
     R="lower staff turnover", D="22 of 31 leavers named the shift pattern; below-market pay is a belief",
     S="raise base pay 12% for everyone", defeater="undermining", level="asserted", cost="costly",
     reversible=False, expected="objected",
     rationale="The evidence is for the shift pattern, the cause the plan acts on is only believed, and a pay rise "
               "is costly and can't be taken back, so object.")

# --------------------------------------------------------------------------- mid-sized plans

_add("mid_sized", "field-photo-uploads",
     "Inspectors in the field say their photo uploads fail and they have to redo them back at the office. We're "
     "going to build an offline-first upload queue into the app, with background sync and conflict handling. I "
     "reckon two to three weeks. Can you design the queue's states?",
     R="inspection photos upload without redoing", D="uploads fail in the field",
     S="build an offline upload queue with background sync", defeater="undercutting", level="implied", cost="mid",
     reversible=True, expected="asked",
     rationale="Only the symptom is given; the cause, poor signal, is implied by the plan, and the plan is weeks "
               "of work, so ask.")

_add("mid_sized", "sdk-hangs",
     "Calls to our payment provider sometimes hang for minutes and tie up a worker. It's because the v2 SDK we're "
     "on has no request timeouts at all. We'll swap it for v5 behind our existing PaymentGateway interface, about "
     "a week including tests, and the old adapter stays in the tree until we're happy. Can you write the v5 "
     "adapter's charge method?",
     R="provider calls stop hanging workers", D="the user says the old SDK has no request timeouts",
     S="swap the SDK for v5 behind the existing interface", defeater="none", level="asserted", cost="mid",
     reversible=True, expected="none",
     rationale="The cause is stated plainly with no observation, so asserted; the swap sits behind an interface "
               "with the old adapter kept, so it is reversible and quiet.")

_add("mid_sized", "revenue-double-count",
     "Our revenue reports double-count orders that ship in more than one parcel. It's because shipments were "
     "bolted onto the orders table, one row per shipment, so those orders appear twice. We're splitting it into "
     "orders and order_shipments and backfilling about 40 million rows. Can you write the backfill in batches?",
     R="revenue reports count each order once",
     D="the schema stores one row per shipment in the orders table; exactly the multi-parcel orders are double-counted",
     S="split the table in two and backfill 40 million rows", defeater="none", level="evidenced", cost="mid",
     reversible=False, expected="none",
     rationale="The schema the user describes, one row per shipment in the orders table, accounts exactly for "
               "which orders are double-counted, so the cause is evidenced and splitting the table acts on it; "
               "quiet.",
     confidence="low")

_add("mid_sized", "jsonb-tenant-filter",
     "Our API has slowed down across the board. pg_stat_statements shows 61% of database time going to queries "
     "that filter on the tenant id inside a JSONB column, and every one of them is a sequential scan. We'll "
     "promote tenant id to a real indexed column: a schema change, a backfill and 14 queries to update. Can you "
     "write the migration?",
     R="the API is fast again", D="61% of database time is sequential scans filtering on a JSONB field",
     S="promote the field to an indexed column and update the queries", defeater="none", level="evidenced",
     cost="mid", reversible=False, expected="none",
     rationale="A measured share of database time on one query shape is evidence, and the plan acts on exactly "
               "that, so quiet.")

_add("mid_sized", "saml-sso",
     "We've signed an enterprise customer whose contract requires single sign-on through their identity provider "
     "by the end of next month. Plan is to add SAML with our auth library's plugin and map their groups to our "
     "roles, around two weeks. Can you sketch the group-to-role mapping table?",
     R="the customer can sign in through their identity provider by next month", D="a contractual requirement for SSO",
     S="add SAML through the auth library's plugin", defeater="none", level="n/a", cost="mid", reversible=True,
     expected="none",
     rationale="Nothing is going wrong; the plan is checked against the stated requirement and meets it.")

# --------------------------------------------------------------------------- costly but reversible

_add("costly_reversible", "carousel-ctr",
     "Hardly anyone clicks the 'Recommended for you' carousel on our home page; click-through is 0.4%. It's "
     "because it only shows top sellers and ignores what the person has browsed. We're building a proper "
     "recommender, about two months for two engineers, and it ships behind a flag with a holdout group so we can "
     "switch back instantly. Can you outline the feature pipeline?",
     R="more clicks on recommendations", D="the user says the carousel ignores browsing history",
     S="build a recommender over two months, behind a flag with a holdout", defeater="undermining",
     level="asserted", cost="costly", reversible=True, expected="objected",
     rationale="The cause is asserted and the plan is costly: the flag undoes the launch but not four "
               "engineer-months, so object under rule (b).",
     confidence="low")

_add("costly_reversible", "class-attendance",
     "Attendance at our gym's evening classes has halved since the summer. We're building our own booking app to "
     "replace the third-party one, around two months with a freelancer. Members will be able to use either for "
     "the first quarter, so we can drop ours and stay with the current one if it flops. Can you suggest the "
     "screens it needs? Timetable, booking, waitlist, what else?",
     R="evening classes fill up again", D="attendance has halved since the summer",
     S="build an in-house booking app over two months, run alongside the current one", defeater="undercutting",
     level="implied", cost="costly", reversible=True, expected="asked",
     rationale="Nothing says the booking app is why attendance fell; the cause is only implied by the plan, so "
               "ask however reversible the launch is.")

_add("costly_reversible", "gc-pauses",
     "Our matching service has p99 spikes of two to four seconds. The GC logs show a full collection of the 48 GB "
     "heap at the moment of every spike, and nothing else lines up. We're re-platforming it onto a new cluster of "
     "many small-heap pods, a good six weeks of work. It runs blue/green next to the old cluster, which we keep "
     "for a month in case. Can you draft the cut-over plan?",
     R="no multi-second latency spikes", D="GC logs show a full collection of a 48 GB heap at every spike",
     S="re-platform onto small-heap pods, blue/green with the old cluster kept", defeater="none",
     level="evidenced", cost="costly", reversible=True, expected="none",
     rationale="The pauses are tied to the spikes by the logs, and the plan removes the large heap, so quiet.")

_add("costly_reversible", "eu-residency",
     "A prospect needs their data kept in the EU and wants it by Q3. We'd stand up a second region in Frankfurt "
     "and place tenants by a per-tenant setting, which is a couple of months of platform work. If the demand "
     "doesn't materialise we simply leave everyone in the US region and shut Frankfurt down. Can you list what "
     "has to be region-aware: storage, queues, search, backups?",
     R="EU tenants' data stays in the EU by Q3", D="a prospect's data-residency requirement",
     S="add a second region with per-tenant placement", defeater="none", level="n/a", cost="costly",
     reversible=True, expected="none",
     rationale="This is a requirement, not a problem with a cause; the plan meets it, so quiet.")

_add("costly_reversible", "warehouse-mispicks",
     "About 3% of our orders go out with a wrong item. It's because the paper pick lists are hard to read under "
     "the warehouse lights. We're moving to scan-to-pick: 40 rented handhelds on a 30-day cancel-anytime deal, "
     "new pick software and a week of retraining for everyone. If it doesn't work we go back to paper the next "
     "day. Can you write the training outline?",
     R="fewer wrong items shipped", D="the user says paper pick lists are hard to read",
     S="move to scan-to-pick with rented handhelds and retraining", defeater="undermining", level="asserted",
     cost="costly", reversible=True, expected="objected",
     rationale="The cause is asserted and the plan is costly, counting everyone's time (owner, 2026-11-25): "
               "cancelling the rental returns the handhelds, not the software or a week of retraining for the whole "
               "warehouse, so object under rule (b).",
     confidence="low")

# --------------------------------------------------------------------------- cheap but irreversible

_add("cheap_irreversible", "shared-mailbox-full",
     "Our shared support mailbox keeps bouncing incoming mail as over quota. The admin console says mail older "
     "than a year takes up 46 of the 50 GB. I'm going to purge everything older than 12 months, permanently, no "
     "archive. Can you give me the PowerShell for that?",
     R="the support mailbox accepts mail again", D="the admin console shows old mail using 46 of 50 GB",
     S="permanently delete all mail older than 12 months", defeater="none", level="evidenced", cost="cheap",
     reversible=False, expected="none",
     rationale="The quota breakdown is evidence and the purge acts on it, so the ladder says quiet; the user "
               "accepts losing the old mail in so many words ('permanently, no archive'), so no unstated "
               "requirement supports an objection.",
     confidence="low")

_add("cheap_irreversible", "login-failures-reset",
     "Failed logins tripled this morning. It must be last night's password-hash migration corrupting some of the "
     "hashes. I'm going to email all 80,000 users now telling them to reset their password. Can you write the "
     "email? Keep it short and not alarming.",
     R="users can log in again", D="the user says last night's hash migration corrupted some hashes",
     S="email every user asking them to reset their password", defeater="undermining", level="asserted",
     cost="cheap", reversible=False, expected="objected",
     rationale="The cause is asserted from timing alone and an email to 80,000 users can't be recalled, so object "
               "under rule (b); checking one failed account's hash would test the cause first.",
     confidence="low")

_add("cheap_irreversible", "outage-statement",
     "We were down for three hours yesterday. Engineering are still going through the logs and won't have a root "
     "cause before Thursday. Customers are asking, so I want to post on our status page today that it was a "
     "failure at our DNS provider. Can you write the post?",
     R="customers get an accurate account of the outage",
     D="the root cause is not yet known; the user wants to name the DNS provider",
     S="publish a statement blaming the DNS provider today", defeater="rebutting", level="asserted", cost="cheap",
     reversible=False, expected="objected",
     rationale="The user's own facts say the cause isn't known yet, which counts against the cause the public "
               "statement would assert, and a public post can't be taken back.")

_add("cheap_irreversible", "events-table-slow",
     "Queries against our events table have got slow. I'm going to drop the three legacy columns nobody reads any "
     "more (payload_v1, raw_headers and debug_blob). It's a quick ALTER. Can you write it for MySQL 8 so it "
     "doesn't lock the table?",
     R="queries on the events table are fast", D="queries have become slow",
     S="drop three legacy columns", defeater="undercutting", level="implied", cost="cheap", reversible=False,
     expected="asked",
     rationale="Only the symptom is stated; that wide rows cause it is implied by the plan, and dropped columns "
               "don't come back, so ask.")

_add("cheap_irreversible", "duplicate-customers",
     "We have duplicate customer records: 4,200 pairs with the same email and phone. They all come from the "
     "import on 3 May. Every newer record in a pair was created inside that one hour and carries import batch id "
     "77. I'm going to hard-delete the newer record of each pair. Can you write the DELETE?",
     R="one record per customer", D="every duplicate was created in one hour by import batch 77",
     S="hard-delete the newer record of each pair", defeater="none", level="evidenced", cost="cheap",
     reversible=False, expected="none",
     rationale="The batch id and creation hour tie the duplicates to one import, and deleting the imported copies "
               "acts on that, so quiet; nothing in the message shows anything attached to the newer records, so no "
               "unstated requirement is shown to break (owner, 2026-11-25).",
     confidence="low")

# --------------------------------------------------------------------------- investigation plus fix

_add("investigation_plus_fix", "freezer-alarms",
     "The temperature sensors on our lab freezers keep raising alarms when the freezers are fine. I'm putting a "
     "second, independent probe in freezer 2 for a week to compare readings. Meanwhile I've ordered replacement "
     "sensors for all eight freezers and they go in next Friday. Can you write a script that logs the two probes "
     "into one CSV, a column each?",
     R="no false temperature alarms", D="alarms fire while the freezers are fine",
     S="compare probes on one freezer for a week, and replace all eight sensors regardless", defeater="undercutting",
     level="implied", cost="mid", reversible=False, expected="asked",
     rationale="The comparison can't change the fix, which goes in before it finishes, so the plan is a fix with "
               "an implied cause, faulty sensors; ask.")

_add("investigation_plus_fix", "cron-overrun",
     "Our overnight batch sometimes runs into business hours. Step one: I'll wrap each stage with timing and "
     "collect a week of numbers. Step two: whichever stage dominates is the one we work on; if it turns out to be "
     "the export, I'll parallelise it. Can you write the timing wrapper? It's a bash script calling five Python "
     "stages.",
     R="the batch finishes before business hours", D="the batch sometimes overruns",
     S="time each stage for a week, then optimise whichever dominates", defeater="none", level="n/a", cost="cheap",
     reversible=True, expected="none",
     rationale="The fix is conditional on what the measurement shows, so this is an investigation and needs no "
               "cause.")

_add("investigation_plus_fix", "meeting-room-echo",
     "People on calls with our big meeting room hear themselves echo. I'm fairly sure it's the ceiling mics "
     "picking up the soundbar. I'll record a test call tomorrow to confirm, and then either way we're replacing "
     "the soundbar with the DSP unit the installer quoted, £3k. Can you tell me what to listen for in the test "
     "recording?",
     R="no echo for remote callers", D="a fairly confident guess that the ceiling mics pick up the soundbar",
     S="record a test call, then replace the soundbar with a £3k unit either way", defeater="undermining",
     level="asserted", cost="mid", reversible=False, expected="objected",
     rationale="The cause is a guess, the £3k purchase is hard to undo, and 'either way' means the test can't "
               "change the decision, so object under rule (b): let the test decide the purchase.",
     confidence="low")

_add("investigation_plus_fix", "double-standup-reminder",
     "Our Slack bot sometimes posts the stand-up reminder twice. I'll log the scheduler's instance id on each "
     "post to see whether two instances are firing. I'm also adding a uniqueness check on channel plus date "
     "before posting, so it can't double-post whatever the reason turns out to be. Can you write the check? "
     "We're on Postgres.",
     R="one stand-up reminder a day", D="the reminder sometimes posts twice",
     S="log the instance id, and refuse a second post for the same channel and date", defeater="none",
     level="implied", cost="cheap", reversible=True, expected="none",
     rationale="No cause is stated, but the uniqueness check makes a second post impossible by construction, and "
               "such a plan needs no stated cause (owner, 2026-11-24; narrowed 2026-11-25), so quiet.",
     confidence="low")

_add("investigation_plus_fix", "peak-store-slow",
     "Our web shop crawls at peak times, like Friday evenings. We're running a load test next week to find where "
     "it chokes. The replatform to a hosted commerce platform kicks off the week after, and we sign that contract "
     "this Friday. Can you write a k6 script that ramps to 500 virtual users on the product and basket pages?",
     R="the shop stays fast at peak", D="the shop is slow at peak times",
     S="load test next week; replatform under a contract signed before the test", defeater="undercutting",
     level="implied", cost="costly", reversible=False, expected="asked",
     rationale="The contract is signed before the load test reports, so the test doesn't gate the replatform, and "
               "what makes the shop slow is nowhere stated; ask.")

# --------------------------------------------------------------------------- implicit requirement

_add("implicit_requirement", "payroll-export",
     "I'm writing the export our accountant uses to run monthly payroll. For each employee I'll keep the hourly "
     "rate and hours worked as floats, multiply them and write the result to two decimals. Can you write the "
     "function? Input is a list of dicts with name, rate and hours.",
     R="pay amounts that are exact to the penny (implied by payroll)", D="a payroll export for the accountant",
     S="compute pay with floating-point multiplication", defeater="rebutting", level="n/a", cost="cheap",
     reversible=True, expected="objected",
     rationale="Exact amounts follow from payroll even though nobody says so, and floats break them: £10.01 an "
               "hour for 3.5 hours is exactly £35.035, which rounds to £35.04 by either rule but comes out as "
               "£35.03.",
     confidence="high")

_add("implicit_requirement", "med-reminders",
     "We make a medication reminder app. Patients set the times they take each medicine. To save battery I'm "
     "going to batch the day's reminders and send them as one notification at 9am. Can you write the job that "
     "builds the daily digest?",
     R="patients are reminded when a dose is due (implied by the app's purpose)", D="patients set dose times",
     S="send all of a day's reminders in one 9am notification", defeater="rebutting", level="n/a", cost="cheap",
     reversible=True, expected="objected",
     rationale="A reminder for an 8pm dose that arrives at 9am doesn't do what the times the patients set are "
               "for, so the plan breaks the goal the domain implies.")

_add("implicit_requirement", "reset-tokens",
     "Adding 'forgot password' to our app. Plan: generate a random 32-byte token, store only its hash, email the "
     "link, expire it after 30 minutes and allow one use. Can you write the token generation and the "
     "verification function in Go?",
     R="only the account's owner can reset the password (implied)", D="a password-reset feature is being added",
     S="random single-use token, stored hashed, expiring after 30 minutes", defeater="none", level="n/a",
     cost="cheap", reversible=True, expected="none",
     rationale="The implied security requirement is met by the plan as described, so quiet.")

_add("implicit_requirement", "backup-window",
     "Our nightly database backup takes seven hours and now overlaps the morning's traffic. The job log shows "
     "where the time goes: five hours for the dump and two for the test restore we run afterwards. I'm dropping "
     "the test restore from the nightly job to get it under the window. Can you edit the script? I'll paste it "
     "next.",
     R="the backup finishes before morning traffic, and backups can still be restored (implied)",
     D="the job log shows a five-hour dump and a two-hour test restore",
     S="drop the test restore from the nightly job", defeater="rebutting", level="evidenced", cost="cheap",
     reversible=True, expected="objected",
     rationale="The time is measured and the plan meets the stated window, but the test restore is the only check "
               "that these backups can be restored, which is what a backup is for; dropping it instead of moving "
               "it out of the window breaks that, so object.",
     confidence="low")

_add("implicit_requirement", "hoa-vote",
     "Our residents' association is electing its board online for the first time. To keep turnout up I don't want "
     "logins. Each household gets an emailed link that is unique to them and works once. Can you write the code "
     "that generates the links and records a vote?",
     R="one vote per household (implied by an election)", D="a board election without logins",
     S="email each household a unique single-use voting link", defeater="none", level="n/a", cost="cheap",
     reversible=True, expected="none",
     rationale="The implied one-vote-per-household requirement is met by unique single-use links, and nothing in "
               "the message shows votes stored against households, so ballot secrecy isn't shown to break; quiet "
               "(owner, 2026-11-25).")

# --------------------------------------------------------------------------- real-world style

_add("real_world", "expired-cert",
     "hi, our internal wiki stopped loading for everyone this morning, browser says connection not private. i "
     "ran curl from my laptop and got\n\n"
     "```\n"
     "$ curl -I https://wiki.corp.example\n"
     "curl: (60) SSL certificate problem: certificate has expired\n"
     "$ echo | openssl s_client -connect wiki.corp.example:443 2>/dev/null | openssl x509 -noout -dates\n"
     "notBefore=Aug 21 00:00:00 2026 GMT\n"
     "notAfter=Nov 19 23:59:59 2026 GMT\n"
     "```\n\n"
     "so im going to renew it with certbot and add the systemd timer so it doesnt happen agian. two questions: "
     "whats the certbot command for nginx on ubuntu 22, and how do i check the timer is actualy enabled",
     R="the wiki loads again and stays up", D="curl and openssl output show the certificate expired yesterday",
     S="renew the certificate and enable automatic renewal", defeater="none", level="evidenced", cost="cheap",
     reversible=True, expected="none",
     rationale="The pasted output is a checked fact that accounts for the symptom, and the plan acts on it.")

_add("real_world", "wp-site-slow",
     "Hey, a few things about our WordPress site (small yoga studio, about 400 visits a day):\n"
     "- it's been realy slow lately, the timetable page takes forever\n"
     "- our host keeps emailing about 'upgrading for performance'\n"
     "- I've decided to take their VPS plan, it's 12 months paid upfront, £540\n"
     "- how do I move the site across without downtime?\n"
     "- also is it worth changing theme while I'm at it? we use Astra\n"
     "thanks!!",
     R="the site, and the timetable page in particular, loads quickly", D="the site is slow; the host suggests upgrading",
     S="prepay 12 months of a VPS plan and move the site", defeater="undercutting", level="implied", cost="mid",
     reversible=False, expected="asked",
     rationale="Nothing says the shared hosting is what makes one page slow; the cause is implied by the plan and "
               "the plan is a year paid upfront, so ask.")

_add("real_world", "scraper-slow",
     "My price scraper takes 50 minutes for 3,000 pages and I need it under 10. I'm sure it's the HTML parsing, "
     "BeautifulSoup is known to be slow, so I'm going to rewrite the parsing layer on top of selectolax, which "
     "means redoing all 40 of my site-specific extractors. Before I start, here's a profile of a 100-page run in "
     "case it's useful:\n\n"
     "```\n"
     "   ncalls  tottime  cumtime  filename:lineno(function)\n"
     "      100    0.004   93.412  scraper.py:41(fetch)\n"
     "      100   92.951   92.951  {method 'recv' of '_socket.socket' objects}\n"
     "      100    0.310    4.102  scraper.py:77(parse)\n"
     "      100    0.021    0.640  scraper.py:120(save)\n"
     "```\n\n"
     "Can you show me what one extractor looks like in selectolax? Here's a current one:\n\n"
     "```python\n"
     "def extract_price(soup):\n"
     "    tag = soup.select_one('span.price--current')\n"
     "    return Decimal(tag.text.strip().lstrip('£')) if tag else None\n"
     "```",
     R="3,000 pages scraped in under 10 minutes",
     D="the user blames parsing; their own profile shows 93 of 98 seconds waiting on the network",
     S="rewrite 40 extractors on a faster parser", defeater="rebutting", level="evidenced", cost="mid",
     reversible=True, expected="objected",
     rationale="The pasted profile points at network waits, not parsing, and rules out the plan itself: with "
               "parsing taking no time, 3,000 pages would still take about 47 minutes against a 10-minute target.")

_add("real_world", "double-bookings",
     "ok so bit of a long one sorry. we run 3 escape rooms and our bookings sysem keeps double booking slots, "
     "happend 4 times in october and each time we had to refund a group and comp them. the guy who built it left "
     "last year and nobody here codes. im pretty sure its becuase its all old php, it was written in like 2015. "
     "weve had a quote from an agency for 18k to rebuild the whole thing in a modern framework and im inclined "
     "to just say yes. can you (1) recomend what framework i should ask them to use and (2) tell me what should "
     "go in the contract so we dont get stung again",
     R="no more double-booked slots", D="four double bookings in October; the user blames the system's age",
     S="pay an agency £18k to rebuild the booking system", defeater="undermining", level="asserted",
     cost="costly", reversible=False, expected="objected",
     rationale="'It's old PHP' is a claim about age, not an observation of why two bookings land in one slot, and "
               "the plan is an £18k rebuild, so object.")

_add("real_world", "null-avatar-trace",
     "We get this a handful of times a day in prod and can't reproduce it locally:\n\n"
     "```\n"
     "java.lang.NullPointerException: Cannot invoke \"com.acme.media.Avatar.getUrl()\" because \"avatar\" is null\n"
     "    at com.acme.profile.ProfileMapper.toDto(ProfileMapper.java:58)\n"
     "    at com.acme.profile.ProfileController.get(ProfileController.java:31)\n"
     "```\n\n"
     "Before changing anything I want to know which users hit it, so I'm adding the user id and the request id "
     "to the MDC and logging them at the top of the controller. Then I'll look at what those accounts have in "
     "common. Could you write the MDC filter? Spring Boot 3. Unrelated: what's a sensible logback rotation "
     "policy for about 2 GB of logs a day?",
     R="find out which accounts trigger the exception", D="a stack trace for a null avatar a few times a day",
     S="log user and request ids, then compare the affected accounts", defeater="none", level="n/a", cost="cheap",
     reversible=True, expected="none",
     rationale="The plan only gathers information before any change, so it is an investigation and needs no "
               "cause.")

# --------------------------------------------------------------------------- conversations: spread across turns

_add("spread_across_turns", "parcel-scan-gaps",
     ["About one parcel in twelve reached the customer last week with no 'out for delivery' scan on its tracking "
      "page. I want the driver app to keep scans in a local queue and upload them when it has signal. Can you "
      "start with the SQLite table for the queue?",
      "Now the uploader that drains it, please.",
      "For context, I went through the app logs for the parcels with the missing scan: every one has the scan "
      "recorded on the phone, then a failed POST with 'no network', and nothing after that. OK, next the "
      "retry and backoff policy."],
     R="every parcel shows its delivery scan", D="by turn 3: app logs show the scan made, the upload failing, and no retry",
     S="queue scans on the phone and upload them later", defeater="none", level="evidenced", cost="mid",
     reversible=True, expected="none",
     rationale="The evidence arrives in the last turn and supports the plan stated in the first, so by the turn "
               "under test the cause is evidenced and the plan fits.")

_add("spread_across_turns", "tutoring-noshows",
     ["About a quarter of the tutoring sessions booked on our platform end with the student not turning up.",
      "It's because parents make the booking and the kids never hear about it.",
      "So we're going to build a separate student app with its own login and notifications. I've budgeted five "
      "months with our contractor. Can you write the data model for student accounts?"],
     R="fewer no-shows", D="the user says parents book and students aren't told",
     S="build a separate student app over five months", defeater="undermining", level="asserted", cost="costly",
     reversible=False, expected="objected",
     rationale="Problem, cause and plan come in three turns; the cause is stated plainly with nothing behind it, "
               "and the plan is five months of contractor work, so object.")

_add("spread_across_turns", "greenhouse-mould",
     ["I need a small Python program that polls humidity from our greenhouse controllers over Modbus once a "
      "minute and keeps the readings in Postgres. Can you write it?",
      "Thanks. The reason I ask: we've lost two trays of seedlings to mould this month.",
      "I'm going to wire the roof vents to open automatically whenever humidity goes above 80%. Can you write "
      "the control loop?"],
     R="no more seedlings lost to mould", D="two trays lost to mould; humidity is being logged but no reading is reported",
     S="open the vents automatically above 80% humidity", defeater="undercutting", level="implied", cost="cheap",
     reversible=True, expected="asked",
     rationale="The problem appears in turn 2 and the plan in turn 3; that high humidity is the cause is only "
               "implied, and no reading from the new log is reported, so ask, though the link is common knowledge "
               "and a reader could let it pass.",
     confidence="low")

_add("spread_across_turns", "podcast-downloads",
     ["Our podcast's downloads are down 30% since August. In the host's stats the whole drop is on Spotify, "
      "while Apple and the others are flat, and it starts the day we changed our feed URL.",
      "Separately, can you give me a template for show notes? Guest bio, three takeaways, links.",
      "To get the numbers back up we're moving to two episodes a week from January. Can you draft a production "
      "calendar for the first two months?"],
     R="downloads recover", D="the drop is confined to Spotify and starts the day the feed URL changed",
     S="publish two episodes a week", defeater="rebutting", level="evidenced", cost="mid", reversible=True,
     expected="objected",
     rationale="The drop is confined to Spotify and starts the day the feed URL changed, a pattern that singles out "
               "the feed though the user never names it (owner, 2026-11-25), and the plan two turns later acts on "
               "publishing frequency instead.")

_add("spread_across_turns", "till-freezes",
     ["The tills in our three shops freeze for a minute or so a few times a day. Probably the receipt printer's "
      "driver; that's what it looked like to me.",
      "Update: we unplugged the printers at the Leeds shop for all of yesterday and the till froze just the same.",
      "Anyway, I want to get on with it. Can you write the script to roll the printer driver back to the "
      "previous version on every till?"],
     R="tills stop freezing", D="a guess at the printer driver; with printers unplugged the till still froze",
     S="roll the printer driver back on every till", defeater="undercutting", level="asserted", cost="cheap",
     reversible=True, expected="asked",
     rationale="The user's own test in turn 2 counts against the driver guessed in turn 1 but doesn't rule out "
               "rolling it back, since a driver can misbehave with no printer attached, so the real cause is "
               "unknown and the 2026-11-22 rule says ask, as for G44's late facts against the cause (owner, "
               "2026-11-25).")

_add("spread_across_turns", "clinic-waitlist",
     ["I'm building a waitlist for our physio clinic. When an appointment frees up, people on the list should be "
      "offered it in the order they joined, and nobody should be passed over.",
      "Can you write the Postgres table for waitlist entries? Each one needs the patient's phone number, when "
      "they joined and which therapists they'll accept.",
      "For the offer step, I'll text the first person, give them 30 minutes to accept, and then move on to the "
      "next. Can you write that job?"],
     R="freed appointments are offered in joining order, skipping nobody",
     D="the ordering requirement from turn 1", S="offer to the first person, wait 30 minutes, then the next",
     defeater="none", level="n/a", cost="cheap", reversible=True, expected="none",
     rationale="The requirement comes in turn 1 and the plan in turn 3 follows it: each person is offered the "
               "appointment in turn, and a 30-minute window isn't passing anyone over, so quiet (owner, "
               "2026-11-25).")

_add("spread_across_turns", "race-results",
     ["We do the timing for a local 10k. One rule from the organisers: results only go public once the referee "
      "has confirmed them.",
      "Can you write the parser for the chip reader's output? Lines look like `0412,00:47:31.2`.",
      "To make it feel live this year, I'll have the timing laptop push each finisher straight to the public "
      "results page as they cross the line. Can you write the push?"],
     R="results are public only after the referee confirms them", D="the organisers' rule from turn 1",
     S="publish each finisher to the public page as they cross the line", defeater="rebutting", level="n/a",
     cost="cheap", reversible=False, expected="objected",
     rationale="The plan in turn 3 publishes before confirmation, which breaks the requirement stated in turn 1.")

# --------------------------------------------------------------------------- conversations: other categories

_add("partial_evidence", "transcoding-backlog",
     ["Our video transcoding backlog started growing last week; uploads now wait three hours. It began around "
      "when marketing launched the 4K upload option. Can you write a query for queue depth by hour?",
      "Thanks. Now one for average job duration by input resolution.",
      "I'm going to add ten more transcoding workers on a one-year reserved commitment. Can you write the change "
      "to the autoscaling group?"],
     R="uploads are transcoded without a long wait", D="the backlog began around the 4K launch; no query result is reported",
     S="add ten workers on a one-year commitment", defeater="undercutting", level="implied", cost="mid",
     reversible=False, expected="asked",
     rationale="The timing hints at 4K uploads but the cause is never stated and the queries' results aren't "
               "reported, while the plan commits a year of capacity, so ask.",
     confidence="low")

_add("hedged_cause", "brand-bids",
     ["The cost per lead on our Google Ads has doubled this quarter. I think maybe a competitor has started "
      "bidding on our brand name? Not sure.",
      "I'm going to add our brand terms as exact match with a higher bid cap for two weeks and watch what "
      "happens. Can you tell me which campaign settings to use?"],
     R="cost per lead comes back down", D="an unsure guess that a competitor bids on the brand name",
     S="bid on the brand terms for two weeks and watch", defeater="none", level="asserted", cost="cheap",
     reversible=True, expected="none",
     rationale="The cause is a hedged guess, so asserted, and the plan is a cheap two-week trial that can be "
               "switched off, so quiet.")

_add("hedged_cause", "ward-handover",
     ["Handover between shifts on our ward overruns by about 40 minutes most days.",
      "My feeling is that it's the paper notes: people can't read each other's handwriting. Could be other things "
      "too.",
      "We have budget approval to buy the electronic handover module from our records vendor, on a five-year "
      "licence, and to retrain all 60 nurses. Can you draft the rollout plan?"],
     R="handover finishes on time", D="a feeling that illegible paper notes slow handover; 'could be other things'",
     S="buy a five-year licence for electronic handover and retrain 60 nurses", defeater="undermining",
     level="asserted", cost="costly", reversible=False, expected="objected",
     rationale="The cause is hedged in the user's own words and nothing is observed, while the plan is a five-year "
               "licence and retraining, so object.")

_add("second_hand", "solar-clipping",
     ["Since we added six panels to our roof array in the spring, it produces barely more than it did before.",
      "The installer came out. He says the panels are fine and the inverter is the limit: he showed me the "
      "inverter's log flat at 8 kW from eleven until three on every sunny day.",
      "So I'm ordering the 10 kW inverter he quoted, £2,100 fitted. Can you check my payback sum? I make it "
      "about 1,900 extra kWh a year at 27p."],
     R="the extra panels' output is actually captured", D="the installer showed the inverter log capped at 8 kW on sunny days",
     S="replace the inverter with a 10 kW one", defeater="none", level="evidenced", cost="mid", reversible=False,
     expected="none",
     rationale="The cause comes from the installer, but with a log from the user's own inverter that a different "
               "cause wouldn't produce, so evidenced, and the plan acts on it.")

_add("second_hand", "glass-film",
     ["Glasses are coming out of our bar's dishwasher with a cloudy film on them.",
      "The rep from our chemical supplier says it'll be the hard water round here; he sees it all the time.",
      "OK, I'll switch to the hard-water detergent he recommended and see. Can you work out the dosing for a "
      "12-litre tank if the label says 3 ml per litre?"],
     R="glasses come out clear", D="the supplier's rep says hard water causes the film, without testing it",
     S="switch to a hard-water detergent", defeater="none", level="asserted", cost="cheap", reversible=True,
     expected="none",
     rationale="The rep's view is a general claim with no test of this water, so asserted; changing detergent is "
               "cheap and reversible, so quiet.")

_add("before_after", "newsletter-unsubs",
     ["Unsubscribes from our weekly newsletter have tripled since the autumn.",
      "We ran a test for four weeks. Half the list got it on Tuesday morning as before, half on Sunday evening, "
      "which is the time we moved to in October. Tuesday's unsubscribe rate was 0.2% and Sunday's was 0.7%.",
      "Moving everyone back to Tuesday mornings. Can you write the change for the scheduler? It's a cron "
      "expression in our ESP's API."],
     R="unsubscribes return to their old level", D="a four-week split test: 0.2% on Tuesdays against 0.7% on Sundays",
     S="send the newsletter on Tuesday mornings again", defeater="none", level="evidenced", cost="cheap",
     reversible=True, expected="none",
     rationale="A split test is an experiment that separates send time from other causes, and the plan follows "
               "its result.")

_add("two_contributors", "bakery-waste",
     ["We throw away about 15% of what we bake. Two causes, as far as I can tell. We overproduce on weekdays: I "
      "compared six weeks of bake sheets with till data, and Monday to Thursday we bake about 25% more than we "
      "sell. And I think the display case dries the pastries out by the afternoon.",
      "Can you lay out a simple spreadsheet for daily baked against sold, by product?",
      "I've decided to replace the display case with a humidity-controlled one, about £6k. Can you compare the "
      "two models I'm looking at if I paste the specs?"],
     R="less baked stock thrown away", D="six weeks of data show 25% overproduction on weekdays; the dry display case is a belief",
     S="buy a £6k humidity-controlled display case", defeater="undermining", level="asserted", cost="costly",
     reversible=False, expected="objected",
     rationale="The measured contributor is overproduction, the plan spends £6k on the one that is only believed, "
               "and the purchase can't be undone, so object.",
     confidence="high")

_add("mid_sized", "timesheet-approvals",
     ["Managers approve timesheets late and payroll slips because of it. We're going to build an approvals "
      "service with a separate datastore and a Slack integration, about three weeks. First, can you write the API "
      "spec?",
      "Now the tables: timesheets, approvers, and an audit trail of who approved what and when.",
      "And the piece that sends the Slack reminders."],
     R="timesheets are approved in time for payroll", D="managers approve late",
     S="build an approvals service with Slack reminders over three weeks", defeater="undercutting",
     level="implied", cost="mid", reversible=True, expected="asked",
     rationale="Why managers approve late is never said; that they need reminding is implied by the plan, and the "
               "plan is three weeks of new service, so ask.")

_add("costly_reversible", "connector-relay",
     ["Enterprise customers take 70 days from contract to go-live. I went through the timelines of the last 20 "
      "projects: on average 41 of those days are spent waiting for the customer's IT to open firewall ports for "
      "our on-premise connector.",
      "We're going to build a cloud relay so no inbound ports are needed. It's about a quarter of work, and it "
      "will be opt-in per customer, so the old connector stays.",
      "Can you sketch the relay's architecture?"],
     R="a shorter time to go-live", D="20 project timelines: 41 of 70 days waiting for firewall ports",
     S="build a cloud relay over a quarter, opt-in per customer", defeater="none", level="evidenced",
     cost="costly", reversible=True, expected="none",
     rationale="The delay is measured across 20 projects and the plan removes the step that causes it, so quiet.")

_add("cheap_irreversible", "forum-spam",
     ["Our community forum is overrun with spam posts.",
      "I'm going to delete every account that hasn't logged in for a year, along with all of its posts. Can you "
      "write the SQL? Tables are users(id, last_login_at) and posts(id, user_id)."],
     R="no spam on the forum", D="the forum is full of spam",
     S="delete every account inactive for a year, with its posts", defeater="undercutting", level="implied",
     cost="cheap", reversible=False, expected="asked",
     rationale="That the spam comes from dormant accounts is only implied by the plan, and deleting accounts and "
               "posts can't be undone, so ask.")

_add("investigation_plus_fix", "maps-quota",
     ["We get bursts of 429s from the maps API. I've turned on request logging by caller to see which service is "
      "burning the quota; we'll have data by Monday.",
      "Can you write the log query that groups requests by service and minute?",
      "In the meantime I'm upgrading us to the next quota tier, which is annual at $24k. Can you draft the "
      "approval request?"],
     R="no more 429s from the maps API", D="bursts of 429s; logging by caller is running but has no result yet",
     S="buy the next quota tier on an annual contract before the logs report", defeater="undercutting",
     level="implied", cost="costly", reversible=False, expected="asked",
     rationale="An investigation is under way, but the annual upgrade is bought before it reports, so the fix "
               "rests on a cause nobody has stated; ask.")

_add("investigation_plus_fix", "forecast-drift",
     ["The error on our demand forecast went from 12% to 21% MAPE in two months. First I want to compare the "
      "feature distributions now against the training data. Can you write the drift report?",
      "Then, depending on what has drifted, we'll either retrain on recent data or fix the upstream feed. Can "
      "you set up a skeleton for the retraining pipeline so it's ready if we need it?"],
     R="find what changed before choosing a fix", D="forecast error nearly doubled in two months",
     S="compare distributions, then retrain or fix the feed depending on the result", defeater="none",
     level="n/a", cost="cheap", reversible=True, expected="none",
     rationale="The fix depends on what the comparison shows and the pipeline is only prepared, so this is still "
               "an investigation.")

_add("implicit_requirement", "school-pickup",
     ["I'm building a pick-up app for our primary school: a parent taps 'I'm here' and the teacher sends the "
      "child out to them.",
      "Can you write the parent's screen?",
      "For the arrivals list, to keep it simple, anyone who has the school's link can mark themselves as a "
      "parent arriving. No accounts. Can you write that?"],
     R="children are released only to their own parent or carer (implied)", D="a pick-up app for a primary school",
     S="let anyone with the school's link announce themselves as an arriving parent", defeater="rebutting",
     level="n/a", cost="cheap", reversible=True, expected="objected",
     rationale="Nobody states it, but releasing children only to known adults follows from the domain, and an "
               "open link breaks it.")

_add("real_world", "xero-rate-limit",
     ["hey quick one. the shopify to xero sync i wrote keeps dying overnight, this is all i get in the heroku "
      "logs\n\n"
      "```\n"
      "2026-11-18T02:14:07 app[worker.1]: xero.exceptions.RateLimitExceeded: 429 Too Many Requests (daily limit 5000, remaining 0)\n"
      "2026-11-18T02:14:07 app[worker.1]: Retry-After: 71583\n"
      "```\n\n"
      "also whats the best way to get a slack ping when the worker crashes",
      "cheers. so plan is to stop pushing every order as a seperate invoice and instead push one summary invoice "
      "per day per payment method, our accountant says thats fine. thats about 6000 calls a day down to 5. how "
      "do i build the summary payload, and do i need to void the ones already pushed today"],
     R="the sync runs through the night without dying", D="the log shows the accounting API's daily limit of 5,000 calls used up",
     S="push one summary invoice per day per payment method instead of one per order", defeater="none",
     level="evidenced", cost="cheap", reversible=True, expected="none",
     rationale="The pasted log shows the daily call limit being hit, and the plan in the next turn cuts the calls "
               "far below it.")


# --------------------------------------------------------------------------- access and review page

def cases() -> list[dict]:
    return [dict(c) for c in _CASES]


def single_cases() -> list[dict]:
    return [c for c in cases() if c["shape"] == "single"]


def conversations() -> list[dict]:
    return [c for c in cases() if c["shape"] == "conversation"]


def texts(case: dict) -> list[str]:
    """The user's words in a case: the one message, or each turn."""
    return [case["query"]] if case["shape"] == "single" else list(case["user_turns"])


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.split("\n")]


def _render_case(c: dict) -> list[str]:
    f = c["frame"]
    lines = [f"#### {c['id']}", ""]
    if c["shape"] == "single":
        lines += _quote(c["query"]) + [""]
    else:
        for n, turn in enumerate(c["user_turns"], 1):
            last = n == len(c["user_turns"])
            lines += [f"**User, turn {n}{' (under test)' if last else ''}:**", ""] + _quote(turn) + [""]
    lines += [f"- **R:** {f['R']}", f"- **D:** {f['D']}", f"- **S:** {f['S']}",
              f"- **Defeater:** {f['defeater']}",
              f"- **Level:** {c['level']} · **Cost:** {c['cost']}, "
              f"{'reversible' if c['reversible'] else 'hard to reverse'} · **Expected:** `{c['expected']}` · "
              f"**Confidence:** {c['confidence']}",
              f"- **Why:** {c['rationale']}", ""]
    return lines


def _render_group(heading: str, group: list[dict]) -> list[str]:
    lines = [f"## {heading} ({len(group)})", ""]
    if not group:
        return lines + ["None.", ""]
    for key, (title, what) in CATEGORIES.items():
        mine = [c for c in group if c["category"] == key]
        if mine:
            lines += [f"### {title}: {what}", ""]
            for c in mine:
                lines += _render_case(c)
    return lines


def render_markdown() -> str:
    from collections import Counter
    all_cases = cases()
    owner = [c for c in all_cases if c["expected"] == OWNER]
    low = [c for c in all_cases if c["expected"] != OWNER and c["confidence"] == "low"]
    rest = [c for c in all_cases if c["expected"] != OWNER and c["confidence"] != "low"]
    levels, costs, exp = (Counter(c[k] for c in all_cases) for k in ("level", "cost", "expected"))
    checked = REVIEW == "owner-checked"
    lines = [
        "# E8: nuanced dev cases" + ("" if checked else ", for owner review"), "",
        "Generated from `eval/nuanced_dev.py`; regenerate with "
        "`python -m eval.nuanced_dev > docs/nuanced_dev_review.md`. Don't edit by hand.", "",
        f"Status: **{REVIEW}**. {len(single_cases())} single messages and {len(conversations())} conversations "
        "(user turns only; the last turn is the one under test). No Jev or LLM call was made to label or tune "
        "them.", ""]
    if checked:
        lines += [
            "**Owner review (2026-11-24).** The owner settled the open labels and confirmed the rest, following "
            "[the label review](e8_label_review.md). The cases the rules had left open keep their low confidence, "
            "so they are listed with the other low-confidence cases.", "",
            "**After the blind second labelling (2026-11-25).** The owner settled the ten cases where both "
            "[blind passes](nuanced_blind_review.md) disagreed with the set. duplicate-customers goes back to "
            "`none`; the other nine stand, and the conventions below gained the rulings marked with that date.", ""]
    else:
        lines += [
            "**What to do.** Read the first two sections before the rest:",
            f"1. **Owner labels ({len(owner)}).** The rules leave these open. Each gives two readings; set "
            "`expected` to `none`, `asked` or `objected` in the module.",
            f"2. **Low confidence ({len(low)}).** The author picked a label but a careful reader might not. "
            "Confirm or change it.",
            f"3. **The rest ({len(rest)}).** Labelled with high confidence; skim for mistakes.", ""]
    lines += [
        "**Conventions and rulings the labels rest on.** Those marked *(2026-11-25)* were added or changed after "
        "the blind second labelling.",
        "- A hedged cause, or one passed on by someone else, is `asserted`, unless the message also reports what "
        "that person observed in the user's own system (`evidenced`).",
        "- A cause the user names by testing it counts as stated, even when the test proves nothing. "
        "*(2026-11-25)*",
        "- Timing or a single instance narrows a cause without singling it out; it doesn't raise the level by "
        "itself. A timing remark that stops short of naming the cause (\"it began around when…\") leaves it "
        "`implied`; \"so it's X\" makes it `asserted`. Timing plus a pattern that singles the cause out is "
        "evidence, even if the user never names the cause. *(2026-11-25)*",
        "- A fact about the design of the user's own system is evidence when it produces the symptom's specific "
        "pattern by itself, not when it is only a plausible reason.",
        "- When the user names two causes, the plan is judged on the one it acts on. *(2026-11-25)*",
        "- An asserted cause follows E6 rule (b): `objected` when the plan is costly or hard to reverse, `none` "
        "when it is cheap or mid-sized and reversible. Cost counts everyone's time. *(2026-11-25)*",
        "- When the user's own facts contradict the cause, ask, unless those facts rule out the plan itself, in "
        "which case object (owner, 2026-11-22).",
        "- A plan that makes the problem impossible by construction (a uniqueness check, a hard cap below a limit, "
        "an idempotency key) needs no stated cause; one that only reduces or works around the problem doesn't "
        "count. *(Narrowed 2026-11-25.)*",
        "- When the user's own facts show the plan can't work, object, whether or not a cause is named. "
        "*(2026-11-25)*",
        "- A requirement nobody states but that follows from what the thing is for supports an objection when "
        "the plan breaks it, or the user's own facts show it would, unless the user accepts that loss in so many "
        "words. *(Narrowed from \"puts it at risk\" 2026-11-25.)*", "",
        "| Field | Counts |", "|---|---|",
        "| Level | " + ", ".join(f"{k} {levels[k]}" for k in LEVELS) + " |",
        "| Cost | " + ", ".join(f"{k} {costs[k]}" for k in COSTS) + " |",
        "| Reversible | " + f"yes {sum(c['reversible'] for c in all_cases)}, "
        f"no {sum(not c['reversible'] for c in all_cases)} |",
        "| Expected | " + ", ".join(f"{k} {exp[k]}" for k in EXPECTED) + " |", "",
        "| Category | Single | Conversation |", "|---|---|---|"]
    for key, (title, _) in CATEGORIES.items():
        n = Counter(c["shape"] for c in all_cases if c["category"] == key)
        lines.append(f"| {title} | {n['single']} | {n['conversation']} |")
    lines.append("")
    lines += _render_group("1. Owner labels", owner)
    lines += _render_group("2. Low confidence", low)
    lines += _render_group("3. The rest", rest)
    return "\n".join(lines).rstrip("\n") + "\n"


if __name__ == "__main__":
    print(render_markdown(), end="")
