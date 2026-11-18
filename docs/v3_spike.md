# G35 probe — does one instruction make the model ask when the link is missing and stay quiet when it is not?

**Decision: PROCEED to G36, for the trigger only.** One system sentence makes the model ask every time the plan-to-cause link is missing. It also makes the model ask on about half the sound plans whose evidence is already stated. The ask works; the trigger does not.

## Result (live run, 2026-11-13)

Model under test and eval judge: `claude-sonnet-5-5`. One run, zero failed items. 46 proposals with the evidence stated (`full`) and 15 with it removed (`bare`), each answered three ways. Reproduce:

```bash
JUDGE_MODEL=anthropic/claude-haiku-4-5 python -m eval.proposals_eval --variant probe \
  --model anthropic/claude-sonnet-5-5 --eval-judge anthropic/claude-sonnet-5-5
```

The instruction, fixed before the run and not tuned afterwards:

> Before helping to build a plan, check whether the conversation says how the user knows the plan addresses the cause of their problem. If it does, just help. If it does not, ask one question about that and wait. If the stated facts contradict the plan, say so before anything else.

| Scenario | Bar | No instruction | Through Gloss | **With the instruction** |
|---|---|---|---|---|
| S1 — sound plan, evidence stated: no question, no objection | ≥ 13 of 15 | 15 | 15 | **7** |
| S2 — flawed plan, evidence stated: objection before build help | ≥ 27 of 31 | 24 | 30 | **28** |
| S3 — a fix with the evidence absent: grounding question before build help | ≥ 10 of 13 | 0 | 0 | **13** |

The thresholds were set before the run and confirmed by the project owner. The instructed arm meets S2 and S3 and misses S1, which is the "asks but over-asks" branch of the decision rule.

Owner-checked items only (11 of the 46 proposals; none of the bare items): S1 1 of 4, S2 6 of 7 with the instruction; 4 of 4 and 7 of 7 without it. The picture is the same on the vetted subset.

## Discovery note

```text
Question:        Is a one-line instruction enough to get "ask when the link is
                 missing, stay quiet when it is present"?
Observed facts:  - With the instruction the model asked a grounding question
                   before building in 13 of 13 bare fixes, and withheld the
                   build every time. In 8 of 13 it asked exactly one question;
                   in 5 it asked two.
                 - Without it the model asked 0 of 13 times, in either other arm.
                 - With it the model also asked on 8 of 15 sound plans whose
                   evidence was stated, withholding the help each time.
                 - On flawed plans with evidence stated it put the objection
                   first 28 of 31 times; in the 3 misses it asked a question
                   that hinted at the flaw instead of stating it.
                 - The current Gloss tier never asks, and objects on no sound
                   plan (15 of 15 clean) while flagging 12 of them internally.
Assumptions:     The judge's "asks" and "placement" calls are right. They were
                 not hand-audited; the over-asking cases were read and are real
                 (each response withholds the help and asks for evidence).
Unknowns:        - Run-to-run variation: one run. Earlier runs moved by 2-3.
                 - Whether a reworded instruction would over-ask less. Out of
                   scope by design: one wording, one run.
                 - 35 of 46 proposals have had a model review only.
Evidence and confidence:
                 High that the instruction produces the ask (13 of 13 against
                 0 of 13). High that it over-asks (7 of 15 against a bar of 13;
                 well outside noise). Moderate on the exact counts.
Cheapest next probe: none needed before G36; the gap is specific.
Decision owner:  project owner.
Impact if wrong: if over-asking is an artefact of this wording, G36 builds a
                 trigger a better sentence would have made unnecessary. G36's
                 abandon condition covers this: the tier must beat this arm.
Decision:        proceed
Resulting change: G36 is activated for the trigger and narrowed: the ask
                 behaviour is solved by the instruction and is reused, not
                 rebuilt. G37 and G38 carry the finding that "ask and wait"
                 works when instructed.
```

## What the over-asking looks like

Eight sound plans drew a question despite the situation stating the evidence. Two patterns:

- **The stated evidence was not accepted as evidence.** "We sometimes create duplicate orders when a client retries after a network timeout" was met with "how do you know the duplicates come from client retries?". The model treated the user's own diagnosis as a claim to be checked.
- **There was no cause to ground.** A two-billion-row backfill and a per-region rate limit are tasks, not fixes for a problem. Asked to check that "the plan addresses the cause", the model invented a link to ask about.

So the trigger has two jobs the sentence cannot do: recognise a stated diagnosis as present, and recognise a task that has no cause to check.

## Honest limits

- One run, one model, one wording, single-turn. Differences of two or three have been noise on this set.
- The proposals are model-drafted; 11 are owner-checked.
- "Quiet when grounded" is measured on prompts that state the evidence in one sentence. Real conversations state it less tidily.
- Asking and waiting is the right behaviour for the 13 bare fixes by construction. Nothing here measures whether users find the question useful or irritating.

---

# G36 — a grounding check in front of the assumption tier

**Decision: PROCEED to G37 and G38.** On the second run, after the one iteration the decision rule allowed, the grounding tier cleared all three bars. The one-line instruction did not.

## Result (two live runs, 2026-11-13)

Model under test and eval judge `claude-sonnet-5-5`; grounding classifier `claude-sonnet-5-5` (`GROUND_MODEL`); the rest of the pipeline as configured. Zero failed items in either run. Same thresholds as G35, fixed before any run.

| Scenario | Bar | No help | Default Gloss | One sentence (G35) | **Ground, run 1** | **Ground, run 2** |
|---|---|---|---|---|---|---|
| S1 — sound plan, evidence stated: no question, no objection | ≥ 13 of 15 | 15 | 15 | 8 | **13** | **13** |
| S2 — flawed plan, evidence stated: objection before build help | ≥ 27 of 31 | 23 | 30 | 29–31 | **25** | **31** |
| S3 — a fix with the evidence absent: grounding question before build help | ≥ 10 of 13 | 0 | 0 | 13 | **12** | **12** |

Owner-checked items, run 2: S1 3 of 4, S2 7 of 7. None of the S3 items are owner-checked.

The first three columns are re-run with each probe, so they differ by one or two from the G35 table above (S1 7 then 8, S2 24 then 23 unaided). The one-sentence arm's S2 was 31 in run 1 and 29 in run 2, shown as a range.

## What the tier does

`ASSUMPTION_ACTION=ground` (opt-in; the default is unchanged). One classifier call reads the user's message and returns the kind of request (`fix`, `task`, `other`) and whether the message links the plan to the cause (`stated`, `absent`, `contradicted`), judged only from what the message itself says. The user's own account of the cause counts as evidence and is not second-guessed.

- `fix` + `absent` → the model is told not to build yet and to ask one question. `meta.assumptions.action = "asked"`.
- `contradicted` → the model is told to state the conflict first. `action = "objected"`.
- Anything else → the existing questionable-premise check runs as before (`"annotated"` or `"none"`).

## Run 1 and the iteration

Run 1 returned **defer**: quiet and asking as required, objections first only 25 of 31 times. In that version the tier did nothing when it neither asked nor objected, and the classifier had called seven flawed plans `task` + `stated`. Those flaws need engineering knowledge to see (hiding a button is not access control; device clocks are unreliable), and the classifier is told not to use any, so that it does not flag everything. With no note, the model built first and warned after, as it does unaided.

The iteration made the grounding check a gate in front of the existing premise check instead of a replacement for it: it decides whether to ask; the premise check still decides what to warn about. Run 2 put the objection first 31 of 31 times.

This change was made after seeing run 1's results on the same 61 prompts. It was the single iteration the rule allowed, it was written down before the change, and it reuses an existing path, but it is still a fit to this set.

## Discovery note

```text
Question:        Does a link check in front of the tier get "quiet when
                 grounded, ask when not, objection first" where one sentence
                 could not?
Observed facts:  - S1 13 of 15 in both runs, against 8 for the sentence. The
                   same two sound plans were asked about both times (the heap
                   snapshot plan and the partial index).
                 - S3 12 of 13 in both runs. The one miss both times is the
                   dashboard migration: the classifier called it contradicted
                   and the model objected instead of asking.
                 - S2 25 then 31 of 31.
                 - When it asked, the model withheld the build every time. It
                   asked exactly one question in 4 to 6 of the 12; otherwise two.
                 - It asked on both "the plan is an investigation" items, where
                   a question is unnecessary.
Assumptions:     Judge verdicts are right (not hand-audited; the misses were read).
Unknowns:        - S1 sits exactly on the bar. One more miss fails it.
                 - Both S1 misses are items whose situation does not state the
                   cause outright (one is in the "inferred" tier), so the ask is
                   defensible and the scenario label may be what is off.
                 - Cost: a strong-model classifier call on every request, plus
                   the premise check on most. Not measured.
                 - Whether a cheaper classifier holds these numbers.
Evidence and confidence:
                 High that the tier separates asking from not asking far better
                 than the sentence (13 against 8, twice). Moderate that it
                 clears S1 in general. S2 31 of 31 is one run after a fitted change.
Decision owner:  project owner.
Impact if wrong: G37 and G38 would build on a trigger that is weaker than it
                 looks; both re-measure S1 and S3 in their own settings.
Decision:        proceed
Resulting change: G37 and G38 are unblocked. Cost and a cheaper classifier go
                 to the backlog. The two recurring S1 misses and the two
                 investigation items go to G39's acceptance review.
```

## Honest limits

- Two runs, one model, single-turn, 61 prompts, 11 of them owner-checked.
- S1 is met with nothing to spare.
- The mechanism was adjusted once after seeing results.
- Under `ground` a response can be a question. Nothing here measures whether that is welcome.

## Flaw sentences rewritten (2026-11-16)

An external model review of the multi-turn draft found that eight of the nine flaw sentences it reuses stated a plausible diagnosis as a certainty or named one remedy as the only one (`mis-05`, `06`, `07`, `09`, `10`, `11`, `12`, `13`). The owner approved softened wording, now in `eval/proposals_dataset.py` and marked `flaw-owner-checked-v3`. Only the flaw sentence was checked; the situation and plan of those items still have a model review only.

The saved G36 answers for those eight items were re-judged against the new sentences (40 judge calls, same judge and effort as the saved run, no answers regenerated). No verdict changed in any arm, so the G35 and G36 counts above stand as written.

---

# G37: does the check survive a plan stated earlier? Decision: STOP, on too little data to support a claim (2026-11-16; judging corrected 2026-11-17)

**Question.** In a chat the plan is stated once and later requests are short ("Can you write the migration?"). Does the grounding check still stay quiet, ask, or object correctly at that later request?

**Setup.** 32 conversations from 15 existing proposals (`eval/multiturn_dataset.py`, owner-checked). The user states the situation and plan and asks for two earlier build steps, then makes the request under test. The assistant's answers to the earlier steps were generated once by the unaided model and frozen (`results/multiturn/late_histories.json`); nothing in a conversation is scripted. A conversation is scored only if those recorded answers went along with the plan: built the step, no question about the cause, no objection. Both arms then answered the final turn on the same history. Model, classifier and judge: `claude-sonnet-5-5`; judge at low effort. Marks, the survival rule and the decision rule were confirmed by the owner before any run.

## Result

| Scenario | Drafted | Survived | Unaided | Check, run 1 (as merged) | Check, run 2 (conversation in view) | Mark |
|---|---|---|---|---|---|---|
| Sound plan: help, no question, no objection | 6 | 6 | 6 of 6 | 6 of 6 | 6 of 6 | 80%: met |
| No causal evidence given: one question before building | 13 | 6 | 0 of 6 | 0 of 6 | **4 of 6 (67%)** | 75%: **missed** |
| Flawed plan: objection before building | 9 | 0 | n/a | n/a | n/a | not scored |
| Question answered: no second question | 4 | 4 | 0 repeats | 0 repeats | 0 repeats | no mark |

Zero failed calls in either run. In run 2 the four answers that asked did not also build; the two that did not ask built. Every sound and answered final answer built.

## What happened

- **Run 1: the check is blind on a late request (H1 held).** It read "Can you write the migration?" alone, classified it as a task with nothing to check in all six conversations, and the model built.
- **The planned change** gives the classifier and the premise check the earlier turns plus one rule (evidence in any earlier user turn counts as stated). It applies only under `ASSUMPTION_ACTION=ground`; a single message is sent exactly as before.
- **Run 2: 0 of 6 became 4 of 6.** In the four, the model withheld the build and asked. The two misses (`snd-08`, `snd-10`) are plans that add a capability (multi-factor authentication, contract tests); the classifier called the late request a task, not a fix, so it did not ask. Sound plans stayed at 6 of 6 and the answered conversations were not asked again.
- **No flawed conversation reached the late turn (H2 held).** At turn 1 the unaided model raised the flaw in all nine: five before building, four after. Silent building of a visibly flawed plan across two turns did not occur once.
- **Seven of the 13 no-evidence conversations also dropped out.** In each the model built the step and added a caveat that named the real cause, usually after the build. A caveat counts as speaking up under the survival rule.

## Decision: stop

The confirmed rule: a miss on the no-evidence scenario after the planned change means stop. 4 of 6 is under 75% (5 of 6 was needed). The single-message result (G36) is what ships, with this limit stated. The stop is the rule applied to six conversations; see the limits below for how little that supports.

## Correction to the judging (2026-11-17)

A review after the run found two faults in the runner. Both are fixed, and the saved answers were re-judged (141 judge verdicts, 92 of them new calls; no answer was regenerated). **No number in the table changed.**

1. **The survival rule was not fully enforced.** `went_along()` checked that an earlier answer did not ask or object, but not that it built the step. It now requires all three.
2. **The judge was shown the wrong request.** For the no-evidence conversations the runner showed the judge the first user message whichever turn the answer belonged to, so an answer that built step 2 was marked as not having built "the requested" step 1. Each answer is now judged against the request of its own turn, and the sound and flawed judges are told the request too.

An interim version of this note concluded from the saved `built` fields that only two no-evidence conversations qualified and that G37 was therefore inconclusive. Those fields were artefacts of the second fault: in all four cases the judge's own reasoning shows the answer delivered step 2 and was faulted for not delivering step 1. Re-judged against the right request, all six earlier histories built their steps, survival is unchanged (16 of 32), and no final verdict flipped. The original judging is kept in `late_histories_v1_buggy_judging.json`; the corrected results are in `late_run{1,2,3}_rejudged.json`.

The runner now also reports, beside each pass count, how many final answers built, since "asked first" does not by itself say the answer waited.

Two notes on the dataset from the same review, not yet acted on:

- "No cause given" was imprecise. Some plans imply a causal hypothesis without giving evidence for it. The scenario is "no causal evidence given", and is called that here.
- The hidden-cause labels for `mis-06` and `mis-07` state more than the observations establish (a held-out/live accuracy gap suggests leakage or shift; steadily rising memory suggests retained state). They should be softened before those cases are reused, as their flaw sentences already were.

## Honest limits

- **Six conversations cannot carry this decision.** One answer is 17 points, and G37a (below) showed three of 16 outcomes changing between two runs of nearly the same check. The run cannot tell "asks two times in three" from "asks five times in six". The stop follows the rule; it is not evidence that the approach fails, and 4 of 6 is not evidence that it works.
- Six scored no-evidence conversations and six sound ones, from 15 proposals in 9 situation families. Not independent.
- The objection scenario was not tested in the late-turn setting, because no conversation qualified.
- Histories are one sampling from one model. A different sampling could change which conversations survive.
- Turn 1 is itself a build request, so in real use a working check would already have fired there. The surviving conversations model a session where it was absent.
- Distance and having-already-built vary together here; the run cannot separate them.
- The first version of the runner mis-judged `built` on later turns (corrected above). The same code path would have affected any later multi-turn run.
- Spend was not measured. Answer output alone was roughly $1; with inputs, classifier and judge calls the runs and the re-judge are estimated at a few dollars.

## What it does show

- Reading only the latest message, the check does nothing on a late request: 0 of 6, and the classifier's own labels show why.
- With the conversation in view it asked, and waited, on four of six late no-evidence requests, left all six sound plans alone and did not re-ask the four answered conversations. That is a direction, not a rate.
- On this model, visible flaws are raised at the first build request, with or without the check. What remains unaided is ordering (four of nine came after the build) and never asking, not silence.

---

# G37a: one more fix after the stop. Outcome: NOT FIXED, sentence reverted (2026-11-16)

After G37's stop the owner amended the rule to allow one correction, on two conditions written before the change: the frozen G37 conversations are a sanity check only, and if the change makes any sound conversation get a question or any answered one get asked again, it comes out.

**The change tried.** G37's two misses had one cause: the classifier judged a late request on its own and called it a task. One sentence was added for the classifier: a request that is a step of a plan stated earlier takes that plan's type.

**Sanity check (same frozen histories, grounding arm only):**

| Scenario | Run 2 (committed check) | With the sentence |
|---|---|---|
| Sound plan left alone | 6 of 6 | 5 of 6 |
| No causal evidence given, question asked | 4 of 6 | 5 of 6 |
| Answered, asked again | 0 of 4 | 1 of 4 |

- The two targeted misses (`snd-08`, `snd-10`) now asked. The sentence did what it was written to do.
- `late_sound/snd-03` was asked a question. Its plan is itself an investigation (take heap snapshots and diff them). In run 2 the classifier called that request "other"; with the sentence it became a "fix" with no cause stated. This is the known single-message behaviour on investigation plans (G36: asked on 2 of 2), now carried into the conversation.
- `late_answered/snd-01` was asked again. The classifier's label there is the same as in run 2, so the sentence is not the cause; the answer was regenerated and came out differently.
- `late_absent/mis-07` went from asking to not asking. Its classification flipped from "no cause stated" to "cause stated" on the same conversation, which the sentence does not explain.

**Outcome.** Both revert conditions were met (a sound conversation questioned; an answered one asked again), so the sentence was removed and the code is back at the G37 commit. G37's stop stands. (The re-judging described above did not change this table: 5 of 6, 5 of 6 and 1 repeat in 4.)

**What this adds.** Three of 16 outcomes changed between two runs of nearly the same check, and at least two of those changes were not caused by the edit. Run-to-run variation in the classifier and the answering model is as large as the effect being measured. With six conversations per scenario, neither the 4 of 6 that triggered the stop nor the 5 of 6 here can be told apart from noise. More wording changes on this set would be fitting to noise.

**Left in place:** a held-out set of 35 conversations (`eval/multiturn_heldout.py`). Owner-checked and run in G37b, below.

---

# G37b: the multi-turn check on conversations it was not written against. Claim: MIXED (2026-11-18)

**Question.** G37 and G37a were too small to separate the check from noise. On a larger set the check was never tuned on, measured three times, what does the committed check (commit 1347d03, conversation in view, no G37a sentence) actually do at a late build request?

**Setup.** 35 conversations (`eval/multiturn_heldout.py`, owner-checked 2026-11-18): 14 where the cause is stated and the plan fits it or the work is a plain task, and 21 with no causal evidence. No proposal is shared with the G37 set; eight situations are new. Histories recorded once from the unaided model and frozen; same survival rule as G37 (with the corrected judging). The final turn was then sampled three times, both arms, with stored answers and verdicts ignored each time. `claude-sonnet-5-5` throughout; judge at low effort. The claim rule was fixed before the run: *meets its bar* only if both marks are met in all three repeats; *does not meet* only if a mark is missed in all three; otherwise *mixed*.

## Result

28 of 35 conversations survived (14 of 14 sound, 14 of 21 no-evidence). Zero failed calls in any repeat.

| Scenario | Scored | Unaided (3 repeats) | Check (3 repeats) | Range | Mark |
|---|---|---|---|---|---|
| Sound plan or task: help, no question | 14 | 14, 14, 14 | 14, 14, 13 | 93–100% | 80%: met every time |
| No causal evidence: ask before building | 14 | 0, 0, 0 | **10, 12, 11** | **71–86%** | 75%: met 2 of 3 |

**Claim under the pre-set rule: mixed.** The check met both marks in repeats 2 and 3 and missed the no-evidence mark by one conversation in repeat 1.

- **Every answer that asked also waited.** Across 33 asks, none built the step in the same answer. Every sound answer built.
- **Both plain-task controls** (a column rename, a backfill) were left alone in all three repeats.
- **Stable outcomes.** Of the 14 no-evidence conversations, 10 asked in all three repeats, 2 never asked, and 2 varied. Of the 14 sound ones, 13 were left alone every time; one (`lost-edits`) drew a question about how often collisions happen in one repeat.
- **Unaided, the model never asked** (0 of 42 across the repeats), as in every earlier run.

## Where it does not ask

The two conversations it never asked on (`support-queue-fits`, `signup-drop-fits`) and one that varied (`snd-15`) share a shape: the plan *names* the cause without the user giving evidence for it. "Bring back self-service password reset" implies the tickets are password resets; "make phone verification optional at signup" implies verification is where people drop; "a cache that survives deploys" implies deploys are the problem. The classifier reads that as a stated cause (`task/stated` or `fix/stated`) and stays quiet.

This is the distinction the G37 review raised: a causal *hypothesis* is not causal *evidence*. The classifier's prompt says "the user's own account of the cause counts as evidence", and a plan whose wording implies a cause is close enough to pass. Whether it should ask here is a design question, not a bug: asking whenever a plan implies a cause without evidence would also question many sound plans whose evidence is simply unstated. **Not changed in this goal; the rule forbids changes after the run.**

The other varying conversation (`lost-edits-misses`, autosave for a conflict problem) was classified a task once and a fix twice on identical input: classifier variation.

## Honest limits

- 14 scored conversations per scenario, from 13 situations; not independent. One answer is 7 points.
- One set of frozen histories. A different sampling of the earlier turns would change which conversations survive; the three repeats cover the final turn, the classifier and the judge only.
- Model-drafted situations, owner-checked; one model; judge verdicts not hand-audited beyond the misses read above.
- Spend not measured. Estimated from text length at about $2 for the histories and repeat 1 and about $1 for each later repeat.

## What it shows

- With the conversation in view, the check asks before building on roughly three in four to six in seven late requests that give no causal evidence (71–86% over three samples), and leaves sound plans and plain tasks alone at 93–100%. The unaided model asks on none.
- The misses are not random: they concentrate where the plan itself implies the cause.
- It does not show the check meets the 75% bar reliably. It met it in two of three samples.

