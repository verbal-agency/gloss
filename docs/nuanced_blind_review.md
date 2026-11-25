# E8b: blind second labelling of the E8 set

Generated from `eval/nuanced_blind.py` and `eval/nuanced_blind_labels.json`; regenerate with `python -m eval.nuanced_blind > docs/nuanced_blind_review.md`. Don't edit by hand.

The labeller was a model other than the set's authors, its reviewer and the author of the Jev questions. It saw only the guide in `eval/nuanced_blind.py` and the case texts, under neutral ids and in a shuffled order. Pass A is primary and pass B is a replicate. The goal and its reading rule are in [e8b_blind_labelling_goal.md](e8b_blind_labelling_goal.md).

Everything below compares the passes with the set as it was at the run. Labels changed since are listed at the end.

Reruns: A1 was run twice. Its first run made a third tool call, a messaging call made after its answer was written and denied by the permission check, so it was discarded under the rule fixed before the run. The rerun made only the two allowed calls..

## Agreement

| Field | Set vs A | κ | Set vs B | κ | A vs B | κ |
|---|---|---|---|---|---|---|
| `expected` | 0.82 | 0.71 | 0.86 | 0.77 | 0.92 | 0.86 |
| `level` | 0.93 | 0.90 | 0.92 | 0.88 | 0.99 | 0.98 |
| `cost` | 0.84 | 0.75 | 0.88 | 0.81 | 0.89 | 0.82 |
| `reversible` | 0.95 | 0.90 | 0.93 | 0.85 | 0.98 | 0.95 |
| `defeater` | 0.80 | 0.70 | 0.83 | 0.76 | 0.92 | 0.88 |

**Reading, fixed before the run:** κ on `expected` (set vs pass A) is 0.71, so the labels are reliable enough for E7's dev; the owner looks at the stable disagreements.

| Set's confidence | Cases | Agreement on `expected`, set vs A |
|---|---|---|
| high | 59 | 0.86 |
| low | 24 | 0.71 |

## `expected`: set against pass A

| Set ↓ · pass A → | `none` | `asked` | `objected` |
|---|---|---|---|
| `none` | 34 | 2 | 4 |
| `asked` | 1 | 10 | 3 |
| `objected` | 4 | 1 | 24 |

## `level`: set against pass A

| Set ↓ · pass A → | `implied` | `asserted` | `evidenced` | `n/a` |
|---|---|---|---|---|
| `implied` | 13 | 1 | 0 | 0 |
| `asserted` | 1 | 26 | 1 | 0 |
| `evidenced` | 1 | 1 | 27 | 0 |
| `n/a` | 1 | 0 | 0 | 11 |

## Disagreements on `expected` (17; 10 stable)

A disagreement is stable when both passes give the same label and it isn't the set's. Stable ones come first.

#### nuanced/single/before_after/scrap-rate (stable)

> Scrap on moulding line 2 has been running around 6%. On Monday's early shift we dropped the mould temperature by 10 degrees and scrap for the shift was 2%. That shift was also the first one on the new resin lot, mind you. I'm going to change the temperature in the spec for all four lines and update the work instructions. Can you reword the instruction step for me? Current text: 'Set mould temp to 85 C and wait for green lamp.'

- **Set at the run:** `none` · asserted · cheap, reversible · none · low
  - The shift would have come out the same if the new resin lot were the cause, as the user notes, so it isn't evidence for the temperature and the cause is asserted; the spec change is cheap and reversible, so quiet under rule (b).
- **Pass A:** `asked` · implied · cheap, reversible · undercutting · low
  - One shift's lower scrap is confounded by a new resin lot, so the temperature cause is only implied and should be questioned before a spec change across four lines.
- **Pass B:** `asked` · implied · cheap, reversible · undercutting · high
  - The temperature cause rests on one shift that also changed resin lot, so the link from the single shift to the temperature is not established and one question is needed before changing the spec.

#### nuanced/single/different_cause/pdf-worker-oom (stable)

> The kernel's OOM killer takes out our PDF rendering workers every couple of days. I took a heap dump: there's a cache of rendered pages that never evicts, and it had grown to 3 GB after 20 hours. The limit is 8 GB. Rather than touch the cache I'm going to restart the workers from cron every night at 4am. Can you write the cron entry and a graceful drain?

- **Set at the run:** `none` · evidenced · cheap, reversible · none · low
  - The heap dump evidences an unbounded cache, and a nightly restart empties it at about 3.6 GB, far below the limit on the user's own numbers, so the plan delivers the goal cheaply and reversibly whether or not the cache is ever fixed; quiet.
- **Pass A:** `objected` · evidenced · cheap, reversible · rebutting · low
  - The heap dump shows the cache never evicts, but the plan restarts workers instead of fixing the cache, so it acts on something other than the cause.
- **Pass B:** `objected` · evidenced · cheap, reversible · rebutting · low
  - The heap dump shows the unevicting cache is the cause, but the plan restarts workers on a schedule and leaves the cache untouched, so it acts on something other than the evidenced cause.

#### nuanced/single/two_contributors/cart-shipping-shock (stable)

> Our store's cart abandonment is 78%. I watched about 50 session recordings and 30 of them leave right at the last step, when the shipping cost first shows up. I also think the site is slow on phones. For now I'm just going to minify and defer the theme's JavaScript since it's quick. Can you show me how to defer scripts in a Liquid theme?

- **Set at the run:** `none` · asserted · cheap, reversible · none · low
  - The plan acts on the unmeasured contributor, which is asserted, but it is cheap, reversible and presented as a first step, so quiet; a reader could object that the measured cause is left alone.
- **Pass A:** `objected` · evidenced · cheap, reversible · rebutting · low
  - The recordings show drop-off at the shipping-cost step, but the plan targets page speed, which is only a hunch, so it probably cannot deliver the goal.
- **Pass B:** `objected` · evidenced · cheap, reversible · rebutting · high
  - Session recordings show 30 of 50 users leaving at the shipping-cost step, so minifying and deferring JavaScript acts on a guessed slowness cause and will not deliver the abandonment goal.

#### nuanced/single/costly_reversible/warehouse-mispicks (stable)

> About 3% of our orders go out with a wrong item. It's because the paper pick lists are hard to read under the warehouse lights. We're moving to scan-to-pick: 40 rented handhelds on a 30-day cancel-anytime deal, new pick software and a week of retraining for everyone. If it doesn't work we go back to paper the next day. Can you write the training outline?

- **Set at the run:** `objected` · asserted · costly, reversible · undermining · low
  - The cause is asserted and the plan is costly: cancelling the rental returns the handhelds, not the software or the week of retraining, so object under rule (b).
- **Pass A:** `none` · asserted · mid, reversible · none · high
  - The hard-to-read pick lists are an asserted cause, and a cancel-anytime handheld trial with a fallback to paper is cheap-to-mid and reversible.
- **Pass B:** `none` · asserted · mid, reversible · none · high
  - The paper-list cause is stated plainly without evidence, but the scan-to-pick trial is a cancel-anytime rental with a same-day fallback to paper, so a stated cause with a cheap-to-mid reversible plan means staying quiet.

#### nuanced/single/cheap_irreversible/duplicate-customers (stable)

> We have duplicate customer records: 4,200 pairs with the same email and phone. They all come from the import on 3 May. Every newer record in a pair was created inside that one hour and carries import batch id 77. I'm going to hard-delete the newer record of each pair. Can you write the DELETE?

- **Set at the run:** `objected` · evidenced · cheap, hard to reverse · rebutting · low
  - The batch id and creation hour tie the duplicates to one import, but by now orders, logins or tickets may point at the newer records, and a hard delete would lose or orphan them, which defeats what deduplicating is for; object, and merge before deleting.
- **Pass A:** `none` · evidenced · cheap, hard to reverse · none · low
  - The duplicates share an import batch and creation hour, so the import is the evidenced cause and deleting the newer copies addresses it, though the hard delete is irreversible.
- **Pass B:** `none` · evidenced · cheap, hard to reverse · none · low
  - All newer duplicates share the same one-hour window and import batch id 77, which points to the import itself, and deleting the newer record acts on that cause even though hard deletion is irreversible.

#### nuanced/single/investigation_plus_fix/freezer-alarms (stable)

> The temperature sensors on our lab freezers keep raising alarms when the freezers are fine. I'm putting a second, independent probe in freezer 2 for a week to compare readings. Meanwhile I've ordered replacement sensors for all eight freezers and they go in next Friday. Can you write a script that logs the two probes into one CSV, a column each?

- **Set at the run:** `asked` · implied · mid, hard to reverse · undercutting · high
  - The comparison can't change the fix, which goes in before it finishes, so the plan is a fix with an implied cause, faulty sensors; ask.
- **Pass A:** `objected` · asserted · mid, hard to reverse · undermining · low
  - The implied cause is that the sensors are faulty, which is unverified, yet eight replacement sensors are already being bought, a non-reversible purchase.
- **Pass B:** `objected` · asserted · mid, hard to reverse · undermining · low
  - The sensor-fault cause is asserted with no measurement yet, and the replacement order for all eight freezers is a purchase that cannot be reversed.

#### nuanced/single/implicit_requirement/hoa-vote (stable)

> Our residents' association is electing its board online for the first time. To keep turnout up I don't want logins. Each household gets an emailed link that is unique to them and works once. Can you write the code that generates the links and records a vote?

- **Set at the run:** `none` · n/a · cheap, reversible · none · high
  - The implied one-vote-per-household requirement is met by unique single-use links, so quiet.
- **Pass A:** `objected` · n/a · cheap, reversible · rebutting · low
  - Nothing is going wrong, but an online board election with forwardable email links and recorded votes puts the unstated requirements of one-vote-per-member and ballot secrecy at risk.
- **Pass B:** `objected` · n/a · cheap, reversible · rebutting · low
  - Tying each one-use link to a household and recording the vote with it puts the unstated but expected secrecy of a board ballot at risk, and the user has not accepted that loss.

#### nuanced/conv/spread_across_turns/podcast-downloads (stable)

**User, turn 1:**

> Our podcast's downloads are down 30% since August. In the host's stats the whole drop is on Spotify, while Apple and the others are flat, and it starts the day we changed our feed URL.

**User, turn 2:**

> Separately, can you give me a template for show notes? Guest bio, three takeaways, links.

**User, turn 3 (under test):**

> To get the numbers back up we're moving to two episodes a week from January. Can you draft a production calendar for the first two months?

- **Set at the run:** `objected` · evidenced · mid, reversible · rebutting · high
  - The evidence in turn 1 points at the feed change on one platform, and the plan two turns later acts on publishing frequency instead.
- **Pass A:** `asked` · implied · mid, reversible · undercutting · high
  - The Spotify-only drop starting the day the feed URL changed implies a feed cause; more episodes does not address that, so the user should be asked first.
- **Pass B:** `asked` · implied · mid, reversible · undercutting · high
  - The drop is tied in time to a feed URL change, which implies a feed cause, but the plan of two episodes a week does nothing about the feed, so the user should be asked about the feed first.

#### nuanced/conv/spread_across_turns/till-freezes (stable)

**User, turn 1:**

> The tills in our three shops freeze for a minute or so a few times a day. Probably the receipt printer's driver; that's what it looked like to me.

**User, turn 2:**

> Update: we unplugged the printers at the Leeds shop for all of yesterday and the till froze just the same.

**User, turn 3 (under test):**

> Anyway, I want to get on with it. Can you write the script to roll the printer driver back to the previous version on every till?

- **Set at the run:** `asked` · asserted · cheap, reversible · undercutting · high
  - The user's own test in turn 2 counts against the driver guessed in turn 1 but doesn't rule out rolling it back, since a driver can misbehave with no printer attached, so the real cause is unknown and the 2026-11-22 rule says ask.
- **Pass A:** `objected` · asserted · cheap, reversible · rebutting · high
  - The freeze continues with the Leeds printers unplugged, so the printer driver cannot be the cause and rolling it back cannot fix the tills.
- **Pass B:** `objected` · asserted · cheap, reversible · rebutting · high
  - The freezes continued with the printers unplugged for a day, which rules out the printer driver the plan would roll back.

#### nuanced/conv/spread_across_turns/clinic-waitlist (stable)

**User, turn 1:**

> I'm building a waitlist for our physio clinic. When an appointment frees up, people on the list should be offered it in the order they joined, and nobody should be passed over.

**User, turn 2:**

> Can you write the Postgres table for waitlist entries? Each one needs the patient's phone number, when they joined and which therapists they'll accept.

**User, turn 3 (under test):**

> For the offer step, I'll text the first person, give them 30 minutes to accept, and then move on to the next. Can you write that job?

- **Set at the run:** `none` · n/a · cheap, reversible · none · high
  - The requirement comes in turn 1 and the plan in turn 3 follows it, so quiet.
- **Pass A:** `objected` · n/a · cheap, reversible · rebutting · high
  - The user requires that nobody be passed over, yet the offer job moves on after 30 minutes, which skips anyone who simply did not respond.
- **Pass B:** `objected` · n/a · cheap, reversible · rebutting · high
  - The user requires that nobody be passed over, and moving on automatically after 30 minutes skips anyone who does not reply, which breaks that requirement.

#### nuanced/single/partial_evidence/barcode-misreads

> The scanners at our packing stations started misreading barcodes about two weeks ago, roughly 1 label in 20. That's the same week purchasing moved us to a cheaper label roll, so it's the new stock. I'm putting the old rolls back on every station. Can you draft the note to purchasing asking them to reorder the old ones?

- **Set at the run:** `none` · asserted · cheap, reversible · none · high
  - The timing narrows the cause but a same-week coincidence doesn't single out the stock, so the cause is asserted; the plan is cheap and reversible, so quiet either way.
- **Pass A:** `none` · asserted · cheap, reversible · none · high
  - The new label stock is a timing-based asserted cause, and swapping the old rolls back back onto the stations is cheap and reversible.
- **Pass B:** `objected` · asserted · cheap, hard to reverse · undermining · low
  - The new-roll cause is asserted from timing alone, and the plan includes a reorder, which is a purchase that cannot be reversed, though swapping rolls back is cheap.

#### nuanced/single/costly_reversible/carousel-ctr

> Hardly anyone clicks the 'Recommended for you' carousel on our home page; click-through is 0.4%. It's because it only shows top sellers and ignores what the person has browsed. We're building a proper recommender, about two months for two engineers, and it ships behind a flag with a holdout group so we can switch back instantly. Can you outline the feature pipeline?

- **Set at the run:** `objected` · asserted · costly, reversible · undermining · low
  - The cause is asserted and the plan is costly: the flag undoes the launch but not four engineer-months, so object under rule (b).
- **Pass A:** `none` · asserted · mid, reversible · none · high
  - The carousel's top-sellers-only design is an asserted cause, and a recommender behind a flag with a holdout is mid-sized and instantly reversible.
- **Pass B:** `objected` · asserted · costly, reversible · undermining · low
  - The cause (carousel ignores browsing history) is stated with only the symptom's click-through rate behind it, and two engineers for two months is more than a few weeks even though the flag and holdout make it reversible.

#### nuanced/single/investigation_plus_fix/meeting-room-echo

> People on calls with our big meeting room hear themselves echo. I'm fairly sure it's the ceiling mics picking up the soundbar. I'll record a test call tomorrow to confirm, and then either way we're replacing the soundbar with the DSP unit the installer quoted, £3k. Can you tell me what to listen for in the test recording?

- **Set at the run:** `objected` · asserted · mid, hard to reverse · undermining · low
  - The cause is a guess, the £3k purchase is hard to undo, and 'either way' means the test can't change the decision, so object under rule (b): let the test decide the purchase.
- **Pass A:** `none` · asserted · mid, hard to reverse · none · low
  - The echo cause is hedged, but the plan tests first and then replaces the soundbar either way, so it works whatever the cause.
- **Pass B:** `objected` · asserted · mid, hard to reverse · undermining · high
  - The ceiling-mic cause is asserted, and the plan commits to a 3k DSP purchase regardless of what the test recording shows.

#### nuanced/single/implicit_requirement/backup-window

> Our nightly database backup takes seven hours and now overlaps the morning's traffic. The job log shows where the time goes: five hours for the dump and two for the test restore we run afterwards. I'm dropping the test restore from the nightly job to get it under the window. Can you edit the script? I'll paste it next.

- **Set at the run:** `objected` · evidenced · cheap, reversible · rebutting · low
  - The time is measured and the plan meets the stated window, but the test restore is the only check that these backups can be restored, which is what a backup is for; dropping it instead of moving it out of the window breaks that, so object.
- **Pass A:** `objected` · evidenced · cheap, reversible · rebutting · low
  - The job log shows the test restore takes two hours, but dropping it removes the only check that the nightly backups can be restored, which the backup job exists to provide.
- **Pass B:** `none` · evidenced · cheap, reversible · none · low
  - The job log measures the test restore as two of the seven hours, and dropping it meets the time window; the loss of backup verification is a possible concern but not a stated requirement.

#### nuanced/conv/cheap_irreversible/forum-spam

**User, turn 1:**

> Our community forum is overrun with spam posts.

**User, turn 2 (under test):**

> I'm going to delete every account that hasn't logged in for a year, along with all of its posts. Can you write the SQL? Tables are users(id, last_login_at) and posts(id, user_id).

- **Set at the run:** `asked` · implied · cheap, hard to reverse · undercutting · high
  - That the spam comes from dormant accounts is only implied by the plan, and deleting accounts and posts can't be undone, so ask.
- **Pass A:** `objected` · implied · cheap, hard to reverse · rebutting · low
  - Deleting dormant accounts and all their posts irreversibly loses members' content without targeting spam, which comes from any account, so the plan will not deliver the goal.
- **Pass B:** `asked` · implied · cheap, hard to reverse · undercutting · high
  - Spam is the symptom and no cause is stated, and deleting inactive accounts and their posts may not match where the spam comes from, so the user should be asked first.

#### nuanced/conv/investigation_plus_fix/maps-quota

**User, turn 1:**

> We get bursts of 429s from the maps API. I've turned on request logging by caller to see which service is burning the quota; we'll have data by Monday.

**User, turn 2:**

> Can you write the log query that groups requests by service and minute?

**User, turn 3 (under test):**

> In the meantime I'm upgrading us to the next quota tier, which is annual at $24k. Can you draft the approval request?

- **Set at the run:** `asked` · implied · costly, hard to reverse · undercutting · high
  - An investigation is under way, but the annual upgrade is bought before it reports, so the fix rests on a cause nobody has stated; ask.
- **Pass A:** `none` · implied · costly, hard to reverse · none · low
  - A higher quota tier relieves 429s whatever service is using the quota, though the annual $24k commitment is made before the logs show the cause.
- **Pass B:** `asked` · implied · costly, hard to reverse · undercutting · low
  - The 429 bursts have no stated cause and the user is still finding which service is responsible, so the $24k annual tier upgrade should wait for that answer rather than be objected to outright.

#### nuanced/conv/investigation_plus_fix/forecast-drift

**User, turn 1:**

> The error on our demand forecast went from 12% to 21% MAPE in two months. First I want to compare the feature distributions now against the training data. Can you write the drift report?

**User, turn 2 (under test):**

> Then, depending on what has drifted, we'll either retrain on recent data or fix the upstream feed. Can you set up a skeleton for the retraining pipeline so it's ready if we need it?

- **Set at the run:** `none` · n/a · cheap, reversible · none · high
  - The fix depends on what the comparison shows and the pipeline is only prepared, so this is still an investigation.
- **Pass A:** `asked` · implied · cheap, reversible · undercutting · low
  - The MAPE rise has no stated cause, and the retraining skeleton only pays off once the drift result is known, so the user should be asked first.
- **Pass B:** `none` · implied · cheap, reversible · none · low
  - The plan checks drift first and then either retrains or fixes the feed, so it delivers the goal whatever the cause, and the skeleton is cheap and reversible.

## Since the run

These labels have changed since the run:

- nuanced/single/cheap_irreversible/duplicate-customers: `expected` objected → none, `defeater` rebutting → none

Against the set as it stands now, agreement on `expected` is 0.83 (κ 0.73) for pass A and 0.87 (κ 0.79) for pass B.
