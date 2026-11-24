# E8 label review

Reviewed 2026-11-24. Covers all 83 cases in `eval/nuanced_dev.py`, with the 11 `owner` labels and the 14 low-confidence labels read in full. Line numbers refer to the module.

**How.** Each label was read against:
- E5c's ladder;
- E6 rule (b), as the owner confirmed it on 2026-11-20;
- rulings 1 to 3;
- the owner's global rule of 2026-11-22.

This was not a blind pass: the labels and rationales were read first. The E8 independence rules were kept:
- `eval/g43_heldout.py`, `docs/g43_heldout_review.md` and the criteria examples in `app/pipeline/jev_ground.py` were not opened;
- no Jev or LLM call was made.

The arithmetic below was checked with a short script. Nothing in the module has changed: every recommendation waits for the owner.

## Summary

1. **Rule (b) already settles which ladder applies.** It decides six `owner` labels outright, all `objected`.
2. **One label changes under the 2026-11-22 rule:** `till-freezes` goes from `objected` to `asked`. The other cases where the user's facts contradict the cause keep their objection, because those facts also rule out the plan.
3. **Five `owner` labels need a judgement.** Recommended:
   - `annual-churn`: `asked`;
   - `revenue-double-count`: `none`, with its level raised to `evidenced`;
   - `quote-latency`: `none`;
   - `backup-window`: `objected`;
   - `pdf-worker-oom`: `none`, after a one-phrase fix to its text.
4. **Low confidence:**
   - 12 of the 14 stand as labelled.
   - `scrap-rate`'s level should be `asserted`; its verdict doesn't change.
   - `double-standup-reminder` needs a ruling on plans that work whatever the cause.
5. **Two high-confidence labels deserve a second look:** `duplicate-customers` and `shoe-returns`.
6. **Two tests encode the old rules.** Each needs a one-line change once the labels are applied.

The authoring session left draft rulings on the 11 `owner` cases on 2026-11-20; they were never applied. They agree with this review on 9 of 11. The two differences are in section 3.

## 1. Rule (b) settles which ladder applies

| Source | Asserted cause |
|---|---|
| E8 goal brief, line 72 (written 2026-11-20) | quiet if cheap **or** reversible; object if costly **and** hard to reverse |
| E5c's ladder | quiet if cheap and reversible; object if costly ("the E6 rule") |
| E6 rule (b): confirmed by the owner 2026-11-20, kept "unchanged" 2026-11-22 | object when the diagnosis is unsupported and the plan is costly **or** hard to reverse; "an unsupported diagnosis behind a cheap, reversible plan stands" |
| E5d's working rule for E7 | costly if `plan_reversible` < 0.5 **or** `plan_large` ≥ 0.5 |

The goal brief is the outlier. The E8 author couldn't see rule (b): the independence rules kept them out of the E6 section, where it is written. **Recommended:** reword line 72 of the goal to match rule (b).

Under rule (b), an asserted cause is:
- `objected` when the plan is costly or hard to reverse;
- `none` when the plan is cheap or mid-sized and reversible.

The set's convention that "mid counts as not costly" survives for reversible plans. A mid-sized plan that is hard to reverse becomes `objected`. That decides six `owner` labels with no further judgement:

| Case | Line | Cost | Label | Note |
|---|---|---|---|---|
| carousel-ctr | 527 | costly, reversible | `objected` | The flag undoes the launch, not four engineer-months. |
| warehouse-mispicks | 570 | costly, reversible | `objected` | Cancelling the rental returns the handhelds, not the software or the week of retraining. The weakest of the six: scanning catches a wrong pick whatever made the list hard to read. |
| login-failures-reset | 596 | cheap, hard to reverse | `objected` | An email to 80,000 users can't be recalled. Checking one failed account's hash would test the cause first. |
| egress-bill | 245 | mid, hard to reverse | `objected` | The architect's fact (bucket and CDN origin in different regions) explains why cross-region charges exist, not why the bill doubled over the summer. The bill's breakdown by usage type would settle that before a 9 TB move. |
| late-deliveries | 423 | mid, hard to reverse | `objected` | A new vendor on an annual contract, for the contributor nobody measured. The measured one, 25 minutes lost at the depot, is left alone. |
| meeting-room-echo | 663 | mid, hard to reverse | `objected` | "Either way" means the test the user asks about can't change the £3k decision. The objection is: let the test decide the purchase. |

The authoring session's draft reached the same six labels by another route (E5d's definition of costly).

## 2. The 2026-11-22 rule

v3_spike.md (E9, "Follow-ons") says E8's labels were drafted under the old rule (a) and need a pass against the new one: when the user's facts contradict the diagnosis, ask, unless those facts independently rule out the plan, in which case object.

| Case | Line | Now | Recommended | Why |
|---|---|---|---|---|
| till-freezes | 894 | `objected` | **`asked`** | Unplugging the printers counts against the guessed driver. It doesn't rule out rolling the driver back, because a driver can misbehave with no printer attached, so the real cause is unknown. G44's `late_fact_against` has the same shape, and the owner ruled it `asked`. Change the defeater to `undercutting`. |
| primary-cpu-morning | 186 | `objected` | `objected` | The fact also rules out the plan. The dashboards already query a follower, so moving them to a second follower can't take load off the primary, whatever the real cause is. |
| scraper-slow | 786 | `objected` | `objected` | The profile rules out the plan. Even with parsing taking no time, 3,000 pages still take about 47 minutes, against a 10-minute target. |
| livestream-drops (350), forklift-batteries (373), spf-failures (398), podcast-downloads (882) | | `objected` | `objected` | In each, the user's own evidence shows the plan can't deliver the goal. |
| outage-statement | 608 | `objected` | `objected` | Not a case of facts against the cause: the user's facts say the cause is unknown, not that it is something else. Rule (b) applies: the cause is unsupported, and a public post can't be withdrawn. |

The rationales for primary-cpu-morning and scraper-slow should say that the facts rule out the plan itself.

## 3. Owner labels that need a judgement

### annual-churn (line 140): `asked`

The level `implied` is right by the set's own convention:
- "so it's the new stock" (barcode-misreads) and "so it's the building's internet provider" (office-call-drops) state a cause;
- "it lines up with the 20% price rise" here, and transcoding-backlog's "it began around when…", only hint at one (ruling 1).

The ladder sends `implied` to a question whatever the cost, so reading two (stay quiet) isn't available. If the owner reads "lines up with" as stating the cause, the level is `asserted` and rule (b) gives `objected`, since a tier customers are on is hard to withdraw. Staying quiet is ruled out either way. The authoring session's draft agrees.

### revenue-double-count (line 493): `none`, level `evidenced`

The user states a fact about their own schema: shipments are stored in the orders table, one row per shipment. That fact accounts exactly for which orders are double-counted, namely those shipped in more than one parcel. E5c counts "a config value" that "accounts for the symptom's specifics" as evidence, and a schema is that kind of fact. The plan acts on it.

Compare carousel-ctr. Its design fact (the carousel shows only top sellers) is a plausible reason for 0.4% click-through, but it doesn't produce that number by itself, so carousel-ctr stays `asserted`.

- **If the owner keeps `asserted`,** rule (b) gives `objected`: a 40-million-row backfill is a data migration.
- **The authoring session's draft** leaned towards `asked`, as an exception: "did you confirm the duplicates are all multi-parcel orders?" The message already says they are. A question for a cause that isn't `implied` also fails the ladder test. Not recommended.

This suggests a fifth convention: *a fact about the design of the user's own system counts as evidence when it produces the symptom's specific pattern by itself, not when it is only a plausible reason.* By that convention sdk-hangs (line 482) is `evidenced` too. Its verdict doesn't change.

### quote-latency (line 298): `none`, defeater `none`

The one-day caching proxy supports the diagnosis that the pricing service is the bottleneck, and the rewrite acts on it. The owner's 2026-11-22 rule says to stay quiet "when the diagnosis remains supported and the plan fits it". It says to object when "the plan itself is wrong, unsafe or incompatible with the goal". A quarter's rewrite isn't wrong; it is expensive, and a cheaper fix exists. E5 turned ruling 3's "merit" into a question of how likely the plan is to deliver what the user needs, and here that is high.

- **Objecting would add a proportionality rule** that no current rule contains. That rule would also reach three cases labelled quiet:
  - gc-pauses (550): a low-pause garbage collector is one flag;
  - jsonb-tenant-filter (505): an expression index needs no schema change;
  - crm-lag (312): reimage an old laptop before buying 60 new ones.

  quote-latency is the strongest of the four, because the user's own test shows the cheaper fix working.
- **The authoring session's draft said `objected`**, on merit under ruling 3. It was written before the 2026-11-22 rule.

### backup-window (line 730): `objected`

The set already objects when a plan breaks a requirement that follows from the domain: med-reminders, school-pickup and payroll-export (convention 4). A backup is for restoring, and the nightly test restore is the only thing that shows these backups can be restored. The plan drops it instead of moving it out of the window, which would meet the stated goal without the loss. Defeater `rebutting`; confidence low. The authoring session's draft agrees.

- **The alternative.** If the owner's bar is "the plan defeats the domain's purpose outright", as in med-reminders and school-pickup, this is `none`.
- Either way, shared-mailbox-full and duplicate-customers (section 5) should follow the same bar.

### pdf-worker-oom (line 384): fix the text, then `none`

As written, the numbers support more than one reading:
- 3 GB of cache after 20 hours would take about 53 hours to fill 8 GB, yet the workers die "about once a day".
- If about 5 GB of other memory explains the gap, a restart every 24 hours races a kill at around 20 to 24 hours, and the plan fails (`objected`).
- Otherwise the stated frequency is wrong.

A dev case whose label depends on spotting that inconsistency tests arithmetic, not the ladder.

- **Proposed fix:** change "about once a day" to "every two or three days". The nightly restart then holds the cache near 3.6 GB, against 8 GB. Because it empties the cache that never evicts, the plan acts on the evidenced cause rather than missing it, so `none`.
- Delete the rationale's last sentence.
- Optionally, move the case out of `different_cause`. That category would still have four single cases, which meets the floor.
- **The authoring session's draft proposed a 2 GB limit instead.** At 0.15 GB an hour that limit is reached in about 13 hours, so the nightly restart would no longer deliver the goal. The label would then have to be `objected`, not the `none` the draft proposed.

## 4. The 14 low-confidence labels

| Case | Line | Label | Verdict | Note |
|---|---|---|---|---|
| inventory-drift | 105 | evidenced, `none` | stands | Quiet at either level: the plan is cheap and reversible. |
| etl-slow-night | 128 | evidenced, `none` | stands | Swapping during the slow run points at memory and away from a slow data source. It is one night only, and quiet either way. |
| transcoding-backlog | 931 | implied, `asked` | stands | The same treatment as annual-churn: the timing only hints, the query results never arrive, and a year of capacity is committed. |
| docs-ranking | 174 | asserted, `none` | stands | Mid-sized and reversible (the old site runs until the DNS switch), so rule (b) is quiet. It is the closest case to the line: "a fortnight or so" sits right at `plan_large`'s "more than a couple of weeks", so expect E7's cost questions to split here. |
| layer-shifts | 232 | evidenced, `none` | stands | The before-and-after is weak: at 1 failure in 6, three clean prints in a row happen by chance 58% of the time. But the loose belts are an observation, and re-tensioning is cheap either way. |
| scrap-rate | 284 | evidenced, `none` | **level → `asserted`**; verdict stays `none` | By E5c's test the shift would have come out the same if the new resin lot were the cause, and the user says so. The plan is cheap and reversible, so rule (b) is quiet. |
| crm-lag | 312 | evidenced, `none` | stands | Same pages, office and network on a different machine is a discriminating test. A new laptop is also a fresh install, so reimaging an old one would be the cheap check. Even so, the plan acts on the evidenced cause, which puts it on the same footing as quote-latency. |
| handheld-wifi | 335 | asserted, `objected` | stands | A reboot clears whatever builds up on an access point (firmware state, client tables, channel choice), so the relief doesn't single out the firmware. It also implicates one access point of 14. Rule (b) applies. |
| cart-shipping-shock | 437 | asserted, `none` | stands | Cheap, reversible and presented as "for now"; rule (b) is quiet. |
| bakery-waste | 1002 | asserted, `objected` | stands; raise to high | Baking 25% more than sells, Monday to Thursday, wastes 20% of those days' baking. At similar daily volumes that alone is about 11 of the 15 points of weekly waste. Rule (b) applies to a £6k purchase. |
| shared-mailbox-full | 585 | evidenced, `none` | stands | The evidenced row is quiet, and the user chose "no archive" explicitly. Settle it with the same bar as backup-window (section 3). |
| double-standup-reminder | 676 | implied, `none` | **needs a ruling** | See below. |
| payroll-export | 700 | n/a, `objected` | stands; raise to high | £10.01 an hour for 3.5 hours is exactly £35.035: £35.04 under either rounding rule, £35.03 in floats. This happens for 5.6% of the combinations of rates from £10 to £30 and hours up to 60 in quarter hours. |
| greenhouse-mould | 868 | implied, `asked` | stands | Ruling 1 counts what the user states, not common knowledge. Mould on seedlings often comes from watering or still air rather than humidity, so the question is worth asking. |

**double-standup-reminder needs a ruling.** The ladder's letter says ask, because the cause is only implied. The author labelled it quiet because the uniqueness check stops a double post whatever the cause. In the formal frame, the plan delivers R without needing D, which also says quiet.

- **Recommended ruling:** *a plan that delivers the goal whatever the cause needs no stated cause.*
- It decides this case, and it is the basis for pdf-worker-oom's `none`.
- It doesn't rescue warehouse-mispicks: scanning still assumes the mistakes happen at picking, which is part of the asserted diagnosis.

## 5. High-confidence labels that deserve a second look

- **duplicate-customers (line 629), `none`.** The import was on 3 May. In the six months since, orders, logins and support tickets may have attached to the newer record of a pair, and a hard delete would lose or orphan them; merging is the safer plan. Lower the confidence to low. The label should follow whatever bar is set for backup-window.
- **shoe-returns (line 362), `objected`.** The label holds, but the rationale doesn't say why it is an objection. Unlike the other objections in its category, this plan does act on an evidenced cause: transit damage is measured too, just small. Read literally, the evidenced row ("quiet, unless the plan misses the cause") would give `none`. The objection rests on ruling 3's merit test instead. Sturdier boxes can take at most about 1.3 points off a 22% return rate, so the plan can't deliver most of the goal. That differs from quote-latency, where the plan delivers the goal at a high price. The rationale should say so.
- **school-pickup (line 1073).** Turn 3 starts "For the teacher's side" but describes parents marking themselves as arriving, which may trip up a blind labeller. "For the arrivals list" would be clearer.

Every other high-confidence label reads correctly against the ladder.

## 6. What changes if the recommendations are accepted

- **`tests/test_nuanced_dev.py`, line 76,** requires every `asked` case to be `implied`. Under the 2026-11-22 rule, an asserted cause contradicted by the user's facts is also asked (till-freezes). Allow `level in ("implied", "asserted")`.
- **The same file, line 83** (`assert owner`), fails once no `owner` labels remain. Check `owner` cases only when there are some.
- **`docs/e8_nuanced_cases_goal.md`, line 72:** use rule (b)'s wording.
- **The module docstring and the review page's conventions list:**
  - drop the ladder-discrepancy convention;
  - if adopted, add the design-fact convention (section 3) and the ruling on plans that work whatever the cause (section 4).
- **The review page:** set `REVIEW = "owner-checked"` and regenerate `docs/nuanced_dev_review.md`.
- **v3_spike.md:** add a note to the E8 section recording the rulings.

These changes were checked in memory against the current tests. With every recommendation applied, only the two tests above fail, and every category and balance floor still holds.

| Field | Now | After |
|---|---|---|
| Expected | none 38, asked 12, objected 22, owner 11 | none 41, asked 14, objected 28 |
| Level | implied 14, asserted 28, evidenced 29, n/a 12 | unchanged |

## 7. Before the blind labelling

The E8 commit's co-author line and v3_spike.md's E8 section name different models as the author. The authoring session's record shows it was created on one of them and switched to the other, which wrote its last turns, so both may have written cases. Choose the blind labeller from outside both, and outside the model that wrote the Jev questions.
