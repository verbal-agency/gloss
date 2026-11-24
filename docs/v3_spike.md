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
- The hidden-cause labels for `mis-06` and `mis-07` state more than the observations establish (a held-out/live accuracy gap suggests leakage or shift; steadily rising memory suggests retained state). They should be softened before those cases are reused, as their flaw sentences already were. **Done 2026-11-18** with owner-approved wording: the labels now say the gap "points first to" a training/live difference and the memory growth "suggests something is holding on to memory". Results recorded before this date used the old wording; reruns of those two cases will not match them.

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


# G40: can Jev replace the grounding classifier? (spec fixed 2026-11-18, before any Jev run)

**Question.** The grounding check's classifier is an LLM reading `GROUND_SYSTEM`. Can TypeSafe's hosted Jev model do the same job, following the pattern of their guardrails cookbook? In that pattern, one request asks a set of questions, and code turns the answers into an action. Here the questions are our grounding standard, not jailbreak screening.

**What is compared.** Only the classifier, on exactly what it saw in earlier runs. In G37b every answer that the note told to ask did ask and wait, so the classifier's action is what the user sees. Expected actions:
- **Object:** the full proposals that contradict their plan (mismatch, infeasible), and late_flawed turns.
- **Ask:** bare fixes, and late_absent turns.
- **Stay quiet:** sound proposals, bare diagnose items, late_sound turns, and late_answered turns.

**Jev, two ways in one request** (`app/pipeline/jev_ground.py`):
- **choice:** the standard's two fields (`request`, `link`) as two multiple-choice questions. The action follows the same rule as the LLM classifier.
- **nouls:** the standard split into yes/no questions (`is_fix`, `cause_stated`, `contradicted`), combined in code by thresholds, as in the cookbook's `route`.
- **Combinations:** the two forms combined by agreement. Both must ask, or either may ask.
- **Not part of the standard:** a fourth question, `evidence_beyond_plan`, asks whether anything besides the plan's own wording supports the cause. That is the gap G37b found. Rules that use it are reported separately as a possible change to the standard, and are never eligible to "match".

**Split.**
- **Dev, 77 cases:** the 46 full proposals, the 15 bare ones, and the 16 main-set late turns that were reached. This is the set the LLM classifier was written against. Jev's thresholds and the choice between forms are picked here, by balanced accuracy, meaning the mean of the per-action rates.
- **Test, 28 cases:** the held-out late turns from G37b, 14 sound and 14 with no evidence. Used once, to decide.

**Repeats.** Three per arm. The LLM arm is the current classifier: `GROUND_SYSTEM` on `claude-sonnet-5-5`, the model G36 to G37b were measured with.

**Rule.** Jev matches the current classifier if, on test and averaged over the repeats, both of these are no more than one conversation (1/14) below the LLM classifier's:
- its quiet rate on sound turns;
- its ask rate on no-evidence turns.

Otherwise it does not match. If it doesn't, the decomposed and combined forms are the iteration the owner proposed. They are already in the dev search, so a miss on test is final for this spec.

**Cost.** Jev bills about $0.042 per million input tokens, with output free, so the whole Jev arm costs well under a cent. The LLM arm is about 315 classifier calls.

**Run:** `python -m eval.ground_classifier_eval --arm llm`, then `--arm jev` (needs `TYPESAFE_API_KEY`), then `--summarize`.

## Baseline: the current classifier (run 2026-11-18)

Three repeats of `GROUND_SYSTEM` on `claude-sonnet-5-5`. 314 of 315 calls classified. One call returned truncated JSON on dev case `full/snd-03`; it is counted as missing, and the pipeline would have passed that request through.

| Set | Group | Matched expected action |
|---|---|---|
| Test | Held-out late turns, no evidence (ask) | **34 of 42** (81%) |
| Test | Held-out late turns, sound (quiet) | **42 of 42** |
| Dev | Bare fixes (ask) | 37 of 39 |
| Dev | Bare diagnose (quiet) | 0 of 6 |
| Dev | Main late turns, no evidence (ask) | 12 of 18 |
| Dev | Main late turns, sound or answered (quiet) | 27 of 30 |
| Dev | Full proposals, sound (quiet) | 41 of 44 |
| Dev | Full proposals, mismatch or infeasible (object) | 60 of 93 |

**It reproduces G37b.** The whole pipeline asked on 33 of 42 held-out no-evidence turns and left 41 of 42 sound ones alone. The classifier alone gives 34 and 42. So scoring the classifier stands in for scoring the answer, as the spec assumed.

**The classifier depends heavily on the model.** By mistake, the first baseline ran on `claude-sonnet-4-6`, the `.env` default. The benchmark now names its model instead of reading `.env`. On 4-6, the same prompt asked on **0 of 42** held-out no-evidence turns and 6 of 57 dev ask cases, and left every sound case alone. That run is kept as `results/ground-classifier/llm_sonnet-4-6.json`. The grounding check is only measured on 5-5, and a deployment on another model needs its own measurement.

**Jev: run below.**

## Result: Jev does NOT match the current classifier (2026-11-18)

Three repeats, `jev-1.14.0`, 315 of 315 cases answered. Jev's probabilities move slightly between repeats, but its decisions didn't: each repeat scored the same on test.

**Picked on dev:** the split-by-criteria form, with the rule "is a fix ≥ 0.3, cause stated < 0.5, contradicted ≥ 0.3". Balanced accuracy on dev:

| Form | Dev |
|---|---|
| Choice (our two fields) | 0.506 |
| Choice and split forms, both must ask | 0.569 |
| Choice and split forms, either may ask | 0.617 |
| Split form, default 0.5 thresholds | 0.680 |
| Split form, picked thresholds | 0.719 |
| Current LLM classifier | 0.785 |

**Test (held-out late turns), against the rule:**

| | Current classifier | Jev (picked) | Within one conversation? |
|---|---|---|---|
| Sound, left alone | 42 of 42 (100%) | 36 of 42 (86%) | **No** |
| No evidence, asked | 34 of 42 (81%) | 36 of 42 (86%) | Yes |

**Decision: Jev does not match.** It asks slightly more often where evidence is missing, but in every repeat it asks on both plain-task controls (the column rename and the backfill). It scores them as fixes (is_fix about 0.7) with no cause stated. That is the mistake the "task" category exists to prevent. Under the spec, a miss on test is final.

**Where the forms fail:**
- **Choice form:** never asks on a conversation. It asked on 0 of 18 dev late turns and 0 of 42 test late turns, because it labels most late requests "task". Its scores on single messages are weak too: 13 of 39 bare fixes asked, and 27 of 93 contradicted proposals objected.
- **Split form:** stays out of the way less on dev. It left 24 of 45 sound full proposals alone, against 41 of 44 for the current classifier, because the low contradiction threshold that the dev search picked makes it object to sound plans.

**The non-standard question doesn't change the picture.** The best rule using `evidence_beyond_plan` asked on 37 of 42 and left 34 of 42 sound turns alone, so it misses the same way.

**Cost:** no usage was recorded per call. At Jev's listed price, 315 calls of about 1–3k input tokens each come to well under a cent.

**What it shows:** on our standard, Jev as configured is a weaker classifier than `GROUND_SYSTEM` on `claude-sonnet-5-5`. It is mainly worse at telling a plain task from a fix, and at leaving sound plans alone. It is not shown to be worse at noticing missing evidence. The comparison covers one Jev version, one wording of the questions, and 28 test cases.

# G41: Jev with structured state and better questions (spec fixed 2026-11-18, before any run)

**Question.** G40's Jev setup lost mainly on two things: it questioned plain tasks, and it never asked on conversations in its multiple-choice form. Its "cause stated" signal separated cases well. Does Jev match the current classifier once the setup is fixed? Jev only: no LLM extraction step (the owner removed that option).

**What changes from G40.** Four hypotheses, each a change:
1. **A plain question about a problem.** A new yes/no question, `problem_described`: "does the user describe something going wrong?" It sits beside G40's `is_fix`, and dev picks which one gates the question.
2. **JSON state.** Jev's docs recommend a JSON object with named parts. Jev reads `{"earlier_user_turns": [...], "assistant_replies": [...], "latest_user_request": "..."}`, and the questions refer to those parts. Only user turns count as evidence; assistant replies are context. A single message has the same shape, with no earlier turns.
3. **Probabilities, not only top labels.** One rule family asks when Jev's probability for "link absent" reaches a threshold, optionally gated by `problem_described`.
4. **Per-shape thresholds.** Single messages and conversations may get separate thresholds. These are used only if they beat one shared set on dev by at least 0.02 balanced accuracy.

**What does not change.** Contradiction keeps G40's question and is not redesigned. G40's non-standard question (`evidence_beyond_plan`) is dropped.

**Arms**, three repeats each:
- **llm:** the current classifier, `GROUND_SYSTEM` on `claude-sonnet-5-5`.
- **jev_text:** the G41 questions with G40's text state.
- **jev_json:** the G41 questions with JSON state.

Comparing the two Jev arms shows what the state change alone does. The decision uses one Jev pick.

**Rule families searched on dev** (both Jev arms): the multiple-choice labels; yes/no routing with either gate; link probability, with or without a gate; each with shared or per-shape thresholds. The best Jev setup by dev balanced accuracy is the one pick.

**Split.**
- **Dev:** all 105 G40 cases, including G40's held-out turns, which are now spent.
- **Test:** a new set, `eval/g41_heldout.py`, drafted for this goal and reviewed by the owner before any run. It has:
  - 38 single messages: 8 sound, 6 plain tasks, 16 with no evidence, and 8 whose own facts contradict the plan;
  - 38 conversations: 8 sound, 6 plain tasks, 16 with no evidence, and 8 answered (the check asks at turn 1, the user replies with the cause). A conversation is scored only if its earlier turns survive, under the G37 rule.

**Rule (on test, averaged over the repeats).** Jev matches the current classifier if, in each of these groups and in each shape the group has (single message, conversation), its rate is no more than the tolerance below the LLM's:
- quiet on sound plans;
- quiet on plain tasks;
- asks on no evidence;
- quiet after the user answers (conversations only).

The tolerance is 0.07 or one case in that cell, whichever is larger. Every case counts once per repeat; a failed or missing classification is a miss. Objection on contradicted messages is reported but not part of the match, because contradiction wasn't redesigned this round and the LLM is weak there too. Results are also reported by family (the 14 underlying contexts), not only by row.

**Amended 2026-11-18, after an external review and before any run.** The first draft pooled the two shapes, dropped failed calls from the denominator, and had no answered conversations. The amendment also made these changes to the set:
- four of the six tasks were replaced with plain work that avoids the categories the `problem_described` question names as examples;
- six contradicted situations now state the fact that rules the other plan out (for example, that the 50,000 partner requests are all for different records, so a cache cannot help);
- two step orders and one plan's wording were fixed.

**Order.**
1. The owner reviews the new set.
2. Histories are recorded once with the unaided model and frozen; survival is reported before any classifier runs.
3. The llm and Jev arms run.
4. Summary.

Nothing is changed after the test result.

**Cost.** Histories: 30 conversations × 2 answers and 8 answered openings through the check, plus judge calls. The LLM arm: about 200 classifier calls. Jev: well under a cent. Estimate $5–10 in total.

## G41 result (run 2026-11-18): Jev does NOT match

**Histories.** All 38 recorded with no failures. Survived: sound 8/8, tasks 6/6, answered 8/8, no evidence 10/16. In the six that didn't survive, the unaided model asked about the cause before the last turn. Test: 38 single messages and 32 conversations.

**Jev pick (chosen on dev only).** `jev_text`, one shared rule: `link: problem_described>=0.3 p_absent>=0.2 contra>=0.3`. Dev balanced accuracy was 0.824, against 0.807 for the LLM classifier. Per-shape thresholds reached 0.840, short of the +0.02 margin, so the shared rule stands. JSON state's best dev score was 0.777, so the state change did not help on dev.

**Test, by cell** (three repeats each; no calls failed in any arm):

| Cell | LLM | Jev | Tolerance | Met |
|---|---|---|---|---|
| sound / single | 1.000 | 1.000 | 0.125 | yes |
| sound / conversation | 1.000 | 1.000 | 0.125 | yes |
| task / single | 1.000 | 1.000 | 0.167 | yes |
| task / conversation | 1.000 | 1.000 | 0.167 | yes |
| answered / conversation | 1.000 | 1.000 | 0.125 | yes |
| absent / conversation | 0.700 | 0.667 | 0.100 | yes |
| **absent / single** | **1.000** | **0.729** | 0.070 | **no** |
| contradicted / single (reported only) | 1.000 | 0.875 | — | — |

**What fixed G40's failures.** Plain tasks: 1.000 in both shapes, including the four tasks written to avoid the question's own examples. Sound plans: 1.000. Answered conversations: 1.000. The `problem_described` question and the link-probability rule solved what G40 lost on.

**What still fails.** Noticing missing evidence in a single message. Jev missed five of the 16 cases:
- `partner-rate-limit`, both plans: p(absent) 0.01–0.02. "Rate-limit errors" seems to read to Jev as its own cause.
- `database-disk-fits`: the plan names the cause ("drop the stale replication slot"), the pattern flagged in review.
- `database-disk-misses`: borderline, with p(absent) around 0.2.
- `card-failures-fits`: objected instead of asking, because contradiction scored 0.31–0.33 against a threshold of 0.3.

By family, Jev's misses concentrate in `partner-rate-limit` (0.57 against the LLM's 1.00), `stale-dashboard` (0.71 against 0.95) and `database-disk` (0.71 against 0.79). JSON state scored 0.812 on this cell (each arm on its own best rule), better than text state but still short.

**Decision.** Keep `GROUND_SYSTEM` on `claude-sonnet-5-5` as the grounding classifier. `GROUND_BACKEND=llm` stays the default, and Jev stays an optional backend. Under the rule fixed before the run, nothing here is changed or rerun.

# G42: aiming Jev at G41's misses (spec fixed 2026-11-18, before any run)

**Question.** G41's Jev pick tied the current classifier everywhere except no-evidence single messages (0.73 against 1.00). Its misses had two patterns: a problem named by an error type that reads as its own cause ("rate-limit errors"), and a plan that names the cause ("drop the stale replication slot"). One case was objected to instead of asked. Can documented Jev practice close these gaps without losing what G41 gained? Jev only, as before.

**What changes.** Each change follows TypeSafe's docs and targets one kind of miss. The standard does not change: a plain statement of the cause counts, and the cause must be stated, not implied by the plan.
1. **A narrower cause question with examples.** `mechanism_stated` asks whether the user states a fact about their own system that explains why the problem happens. An error's name or the plan does not count. Its yes and no criteria carry examples, which the docs say steer Jev when they look like real inputs. The examples come from situations used nowhere in dev or test.
2. **"Stated apart from the plan" as its own question.** `cause_outside_plan` asks whether anything other than the plan says what causes the problem. Rules can require it alongside another cause question.
3. **Objection needs a stated cause.** A rule option objects only when the evidence is present, because a plan can only contradict a cause the user stated; otherwise the case is asked.
4. **Discounting confidence.** The docs warn that text arguing for an answer can move Jev, and every message says "I've researched this and decided". One arm adds a note to every question telling Jev to judge only the facts stated.

**Arms**, three repeats each, all on text state (G41's pick; JSON state did worse on dev):
- **llm:** the current classifier, `GROUND_SYSTEM` on `claude-sonnet-5-5`.
- **jev_g42:** G41's questions plus the two new ones, with the confidence note.
- **jev_g42_plain:** the same without the note. G41's questions are unchanged in this arm, so applying G41's pick to it shows what G42's changes add (reported only).

**Rules searched on dev.** "Evidence present" means either G41's link probability, or every named yes/no question at or above a threshold. The named sets are `cause_stated`, `mechanism_stated`, `cause_outside_plan`, and the pairs mechanism+outside and cause+outside. Each is searched with or without the `problem_described` gate, with contradiction at 0.3–0.9, and with or without "objection needs evidence". That is 608 rules per arm. Shared thresholds are used unless per-shape ones beat them by 0.02 on dev.

**Split.**
- **Dev:** G40's 105 cases plus G41's 70 test cases, now spent (175).
- **Test:** a new set, `eval/g42_heldout.py`, drafted for this goal and reviewed by the owner before any run. It has eight new situations: four named by an error type (`error-type`) and four whose fitting plan names the cause (`plan-names`). It also has six plain tasks, four of them outside the categories the problem question uses as examples. As in G41, the set has 38 single messages and 38 conversations (sound, no evidence, answered, tasks); a conversation is scored only if its history survives.

**Rule.** G41's rule, unchanged. In every gated group (quiet on sound plans, quiet on tasks, asks on no evidence, quiet after an answer), in each shape the group has, Jev's rate is no more than max(0.07, one case in that cell) below the LLM's. A failed call is a miss. Objection is reported only. Results are also reported by pattern and by family.

**What would count against the hypothesis.** Jev still misses `error-type` or `plan-names` cases with no cause stated, or the new questions make it ask on sound plans or answered conversations.

**Order.** Owner review of the set, then histories recorded once and frozen, then the arms, then the summary. Nothing is changed after the test result.

**Cost.** Histories: about $3–6, as in G41. The LLM arm: only the 70 new test cases are uncached, about 210 classifier calls. Jev: under a cent.

## G42 result (run 2026-11-18): Jev does NOT match, now only on objection

**Histories.** All 38 recorded with no failures. Survived: sound 8/8, tasks 6/6, answered 6/8, no evidence 6/16. In ten no-evidence conversations the unaided model asked about the cause itself before the last turn. Test: 38 single messages and 26 conversations. One scoring fix was made before the first summary was read: G41's cases had no `group` field, which the dev scorer requires.

**Jev pick (dev only).** `jev_g42_plain`, with one shared rule: `problem_described>=0.3`, ask when `mechanism_stated < 0.7`, object when `contradicted >= 0.3`. Dev balanced accuracy was 0.880, against 0.843 for the LLM classifier. The arm with the confidence note scored 0.877, so the note did not help. Per-shape thresholds reached 0.882, short of the +0.02 margin. The new `mechanism_stated` question beat every other evidence set, and "objection needs evidence" was not picked.

| Cell | LLM | Jev | Tolerance | Met |
|---|---|---|---|---|
| sound / single | 1.000 | 1.000 | 0.125 | yes |
| sound / conversation | 1.000 | 1.000 | 0.125 | yes |
| task / single | 1.000 | 1.000 | 0.167 | yes |
| task / conversation | 1.000 | 1.000 | 0.167 | yes |
| absent / single | 0.750 | 0.729 | 0.070 | yes |
| absent / conversation | 0.500 | 0.833 | 0.167 | yes |
| **answered / conversation** | **1.000** | **0.778** | 0.167 | **no** |
| contradicted / single (reported only) | 1.000 | 1.000 | — | — |

**The targeted gap closed.** On no-evidence cases, G41's pick applied to the same answers scored 0.375 on single messages and 0.278 on conversations. G42's pick scored 0.729 and 0.833. By pattern:

| No evidence | LLM | G42 Jev | G41 pick |
|---|---|---|---|
| error-type, single | 0.75 | 0.62 | 0.25 |
| error-type, conversation | 1.00 | 1.00 | 0.33 |
| plan-names, single | 0.75 | 0.83 | 0.50 |
| plan-names, conversation | 0.25 | 0.75 | 0.25 |

On no-evidence conversations Jev now does better than the current classifier, which also struggles on this harder set (0.50).

**What failed.** All four answered-conversation misses were objections to a sound plan, not questions. Jev scored the user's cause clearly (`mechanism_stated` at 0.97 or above), but its contradiction score of 0.30–0.36 cleared the 0.3 threshold picked on dev: french-tickets in all three repeats, mail-connections in one. G41's pick fails this cell identically (0.778), so G42's changes did not cause it. The weakness is in the contradiction question, which no round has redesigned: on sound plans its scores sit just above 0.3, too close to the threshold.

**Decision.** Keep `GROUND_SYSTEM` on `claude-sonnet-5-5`, and `GROUND_BACKEND=llm` stays the default. Under the rule fixed before the run, nothing here is changed or rerun. The next lever is objection: a redesigned contradiction question, or a contradiction threshold chosen to protect sound and answered cases. That needs another fresh set.

# G43 exploration: user turns only, then a graded cause question (plan fixed 2026-11-19, before any run)

**Status.** Exploration on spent data only. Nothing here can change the G42 decision or replace a held-out test. It decides what the G43 held-out test should measure. The owner approved both changes to Jev's input on 2026-11-19.

**Labels.** The owner's rulings of 2026-11-18 are recorded in `docs/g42_jev_diagnosis.md`. A plan clause that states what is happening now counts as a stated cause; a symptom that doesn't match the plan is still `asked`. Four G42 cases become `none`: single and late_absent cold-starts-fits, and single and late_absent admin-page-fits. G41's fitting plans were checked, and all of them only hint at the cause, so none change. G40's bare `right_fix` items have not been checked against ruling 1.

**Pool.** G42's dev (G40's 105 cases plus G41's 70 test cases) and G42's test (64 cases): 239 cases, 102 of them conversations. Each part is also reported on its own.

**Step 1: user turns only.** Conversations are sent as the user's messages alone, in order, with the latest marked as the one to judge. No assistant text is sent. The note on each question changes to match: the text holds only the user's messages; judge the latest in light of all of them; evidence in any earlier user message counts. The questions are otherwise G42's battery without the confidence note. Single messages are sent exactly as before, so their answers come from G42's run (the requests are identical).

**Step 2: a graded cause question.** One multiple-choice question, `cause_level`, sent in its own request. It rates how strongly the user's own words state why the problem happens, never whether the diagnosis is right:
- `none`: no cause stated, or only the symptom's or error's name;
- `implied`: only the plan's wording hints at a cause, or the plan only states what it will achieve;
- `asserted`: the user says what is happening now that causes the problem, anywhere, including a clause inside the plan;
- `observed`: as `asserted`, and backed by a measurement, log, trace or count.

Each level has examples from situations used nowhere in dev, test or earlier criteria. It is asked on single messages and on conversations in both forms (full and user turns only).

**Rules, fixed now.**

| Name | Object when | Ask when (and not objecting) |
|---|---|---|
| R0, G42's pick | `contradicted` ≥ 0.3 | `problem_described` ≥ 0.3 and `mechanism_stated` < 0.7 |
| R1, objection needs evidence | `mechanism_stated` ≥ 0.7, link's P(contradicted) ≥ 0.2 and `contradicted` ≥ 0.3 | as R0 |
| L1, graded | E ≥ 0.5, link's P(contradicted) ≥ 0.2 and `contradicted` ≥ 0.3 | `problem_described` ≥ 0.3 and E < 0.5 |

E is P(asserted) + P(observed) from `cause_level`. L1 takes `problem_described`, `contradicted` and the link question from the battery run on the same state. E at 0.3 and 0.7 is reported only.

**Comparisons.**
- Step 1: R0 and R1 on full versus user-only state. Only conversations differ.
- Step 2: L1 versus R1, on the same state.
- The LLM classifier's cached answers are shown for reference, scored against the same labels.
- Also reported: the distribution of `cause_level` by expected action, and whether its probabilities follow the order of the levels.

**What would count against each change.**
- User-only: answered conversations lose their evidence (the answer reads as a non sequitur without the question), or no-evidence conversations do no better.
- Graded: E does not separate stated from withheld causes better than `mechanism_stated`. Or the four relabelled plan-clause cases and the plans that only hint at a cause still land on the same side.

**Cost.** Jev only, 3 repeats. Step 1 sends 102 conversations, about 306 requests. Step 2 sends 239 + 102 cases, about 1,023 single-question requests. Well under a dollar.

## G43 exploration result (run 2026-11-19): neither change helps

**Runs.** Step 1: 306 requests. Step 2: 1,023 requests. No call failed. The pool is the 239 spent cases with the four ruling-1 relabels. Rates are shown on the whole pool; G42's dev and test parts point the same way (`results/g43_explore/summary.json`). The LLM column is the classifier's cached G42 answers, scored against the same labels.

| Cell (whole pool) | LLM | R0 full | R0 user | R1 full | R1 user | L1 full | L1 user |
|---|---|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.819 | 0.819 | 0.848 | 0.848 | 0.886 | 0.886 |
| quiet / conversation | 0.956 | 0.886 | 0.877 | 0.886 | 0.877 | 0.947 | 0.974 |
| task / both shapes | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| ask / single | 0.930 | 0.853 | 0.853 | **0.992** | 0.992 | 0.922 | 0.922 |
| ask / conversation | 0.735 | 0.980 | 0.843 | **0.980** | 0.863 | 0.814 | 0.775 |
| answered / conversation | 1.000 | 0.926 | **0.704** | 1.000 | 0.907 | 1.000 | 0.907 |
| object / single (reported only) | 0.752 | 0.837 | 0.837 | 0.532 | 0.532 | 0.532 | 0.532 |

Single messages are identical across forms by design.

**Step 1, user turns only: worse, against the hypothesis.** Removing the assistant's replies hurt conversations in both directions:
- **More objections after an answer.** Without the assistant's question in front of it, the user's answer drew higher contradiction scores: g42 mail-connections 0.22–0.30 → 0.38–0.40; g41 late-report 0.54–0.59 when objected; g42 dns-failures 0.30–0.35. Answered conversations under R0 fell from 0.926 to 0.704.
- **Fewer questions where no cause was given.** `mechanism_stated` rose on these conversations, for example held/slow-build-misses 0.71–0.73 and g41/stale-dashboard-fits 0.73–0.79. Under R0, ask/conversation fell from 0.980 to 0.843.

The assistant's turns give Jev a frame: "the assistant asked how you know, and here is the answer". On these cases that frame helps more than the assistant's suggested causes hurt. One caveat: the note on each question changed with the state, so the two effects can't be told apart. The owner-approved change is dropped.

**Step 2, the graded cause question: no better than `mechanism_stated`.**
- **It separates less well.** E is P(asserted) + P(observed). As a separator between stated and withheld causes, its AUC is 0.893 on single messages, against 0.938 for `mechanism_stated`, and 0.960 on conversations, against 0.980.
- **L1 trades questions for quiet.** Against R1 it is better on sound plans (0.886 vs 0.848 single, 0.947 vs 0.886 conversation) and worse on asking (0.922 vs 0.992, 0.814 vs 0.980). At 0.7 it is about R1 again.
- **Jev doesn't treat the levels as a scale.** Only 50% of answers have probabilities that rise to one peak and fall away. Contradicted cases put 0.26 on `none` and 0.36 on `observed`.
- **It follows ruling 1 on plan clauses.** cold-starts-fits E = 0.86–0.92 (quiet); admin-page-fits 0.52–0.63 (just quiet); plans that only hint stay low (translation-quota 0.26–0.30, partner-outages 0.04–0.05).
- **But it reads a measured symptom as observed evidence.** french-tickets-fits is rated `observed` in all six answers (E 0.57–0.82) because "three days against a few hours" is a measurement. That is the comparison pattern from the G42 diagnosis, and the level definitions don't separate a measured symptom from a measured cause.

**What this leaves.**
- Of the rules tried, R1 on the full conversation is the strongest on the spent pool: it asks on 0.99 / 0.98 of no-evidence cases and stays quiet on every answered one. It was picked after reading G42's test, so only a fresh set can confirm it.
- Its gaps against the LLM:
  - quiet on sound plans: 0.848 vs 0.895 on single messages, 0.886 vs 0.956 on conversations;
  - objection recall: 0.53 vs 0.75, reported only. Most of the misses are G40 proposals with a stated cause.
- The graded question is better at staying quiet on sound plans. If it is kept, the next try is a cause-only level definition ("a measurement of the symptom is not evidence of the cause"), not a replacement for `mechanism_stated`.

Nothing here changes the default: `GROUND_BACKEND=llm`.

# G43 exploration 2: split contradiction, risk questions, and a cascade (plan fixed 2026-11-19, before any run)

**Status.** Exploration on the same 239 spent cases, full conversation state, the same four relabels. Like exploration 1, it decides what G43's held-out test measures, not whether Jev replaces the LLM.

**Where the ideas come from.**
- *Value of information.* Recent work on when assistants should ask frames a clarifying question as worth asking only when the expected gain from the answer, weighted by the stakes, beats the cost of interrupting the user. It also argues that fixed confidence thresholds ignore that stakes vary. Gloss's rule today is "ask whenever the evidence is missing", which treats every plan as equally costly to get wrong.
- *TypeSafe's routing guidance.* Give the uncertain band its own outcome rather than rounding it to one side. Threshold the probability of the option you act on. Raise thresholds as the cost of a wrong branch rises.
- *Verified cascades.* A cheap decision handles the clear cases and hands the rest to a stronger model.

**New questions**, in one Jev request per case, three repeats:
- `plan_misses_cause` (yes/no): the user states what causes the problem, and the plan changes something else instead.
- `plan_breaks_requirement` (yes/no): the user states a requirement or constraint that the plan cannot meet.
- `wasted_effort` (yes/no): the risk framing of the evidence question. If the assistant builds what the user asks without questioning it, is the work likely to be wasted because nothing the user says shows the plan will fix the problem?
- `stakes` (yes/no): the plan is costly or hard to undo if it's wrong (weeks of work, a rewrite, new infrastructure, a migration, hiring, a change customers see). Descriptive only, since the labels don't encode stakes.
- `bad_solution` (yes/no): an experienced engineer reading only the user's words would doubt the plan solves the problem. This judges the diagnosis, which the standard forbids, so it is reported only.

The contradiction questions carry examples from situations used nowhere in the pool.

**Rules, fixed now.** R1 is exploration 1's rule and is the reference.

| Name | Object when | Ask when (and not objecting) |
|---|---|---|
| S1, split contradiction | (`mechanism_stated` ≥ 0.7 and `plan_misses_cause` ≥ 0.5) or `plan_breaks_requirement` ≥ 0.5 | as R1: `problem_described` ≥ 0.3 and `mechanism_stated` < 0.7 |
| K1, risk framing | as R1 | `problem_described` ≥ 0.3 and `wasted_effort` ≥ 0.5 |
| C1(R1), cascade | Jev's R1 unless a deciding score is in its band; then the LLM's cached answer for that repeat | same |
| C1(S1), cascade | the same, over S1 | same |

The cascade bands are `mechanism_stated` in [0.55, 0.85), `contradicted` in [0.2, 0.45) and the link question's P(contradicted) in [0.1, 0.3) when evidence is present, and for S1 its two new questions in [0.3, 0.7). Also reported: S1 and K1 at 0.3 and 0.7, and the share of cases deferred.

**Descriptive.** The mean of `stakes` and of `bad_solution` per group, and for `bad_solution`, whether it separates plans that fit from plans that miss among the no-evidence cases. Under value of information, low-stakes no-evidence cases are the ones where a question might not be worth it.

**Reading the results.**
- S1 helps if objection recall rises above R1's 0.53 without losing the quiet cells.
- K1 helps if it beats `mechanism_stated` on the ask and quiet cells. TypeSafe's docs warn that Jev is weak on indirection, which predicts it won't.
- The cascade helps if it reaches the LLM on the quiet cells and keeps Jev's lead on asking while deferring under a third of cases.

**Cost.** About 717 Jev requests. The cascade uses the LLM answers G42 already cached for every pool case.

## G43 exploration 2 result (run 2026-11-19)

717 requests, none failed. Whole pool, full conversation state; the dev and test parts point the same way (`results/g43_explore/summary2.json`).

| Cell | LLM | R1 | S1 split | S1 @0.3 | K1 risk | C1(R1) | C1(S1) |
|---|---|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.848 | 0.810 | 0.771 | **1.000** | 0.829 | 0.800 |
| quiet / conversation | 0.956 | 0.886 | 0.886 | 0.833 | **1.000** | 0.921 | 0.921 |
| task / both shapes | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| ask / single | 0.930 | **0.992** | 0.992 | 0.969 | 0.589 | 0.992 | 0.969 |
| ask / conversation | 0.735 | **0.980** | 0.980 | 0.980 | 0.245 | 0.941 | 0.941 |
| answered / conversation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| object / single (reported only) | 0.752 | 0.532 | 0.610 | **0.752** | 0.532 | 0.617 | 0.681 |
| share sent to the LLM | — | — | — | — | — | 0.202 | 0.229 |

**Split contradiction (S1): more objections, at a cost.** Separating "the plan misses the stated cause" from "the plan breaks a stated requirement" raised objection recall from 0.53 to 0.61. At 0.3 it matched the LLM's 0.75, the first Jev setup to do so. But it objects to some sound proposals: quiet/single fell to 0.81, or 0.77 at 0.3. On sound proposals with constraints, the requirement question fires.

**Risk framing (K1): the indirection weakness, as predicted.** "Would the work be wasted?" made Jev cautious about asking. It stayed quiet on every sound plan but asked on only 0.59 of single messages and 0.25 of conversations missing a cause. As a separator between the quiet and ask groups, its AUC is 0.909, against 0.963 for `mechanism_stated`.

**Cascade (C1): not worth it in this form.** It sends 20–23% of cases to the LLM. Quiet on conversations rises to 0.921, but quiet on single messages falls to 0.829: the deferred band holds cases Jev had right and the LLM gets wrong. It also brings in the LLM's weakness at asking on conversations (0.98 → 0.94). Objection recall rises to 0.62–0.68. It does not reach the LLM on the quiet cells.

**Stakes: no signal.** `stakes` averaged 0.21–0.35 in every group. Jev reads almost every plan as cheap to undo, so a value-of-information gate on Jev's stakes would not separate anything. Stakes would have to come from elsewhere (the size of the plan, or the product context), and the labels encode none of it.

**Bad solution: weak, and judges the diagnosis.** Among no-evidence cases it separates plans that miss from plans that fit with an AUC of 0.786. It doubts sound plans too: a mean of 0.44 on quiet single messages. It stays reported only.

**What the remaining quiet-cell gap is made of.** On quiet single messages, R1's 16 wrong answers fall in three places:
- 7 come from four sound proposals and 6 from the bare `diagnose` items. Most of these are **plans that are themselves an investigation**: "take heap snapshots an hour apart and diff them to find what is being retained, before changing any limits".
- 3 are the relabelled admin-page-fits, with `mechanism_stated` at 0.66–0.69.

For an investigation, asking "how do you know this addresses the cause?" can't change what the user does: finding the cause is the plan. This is the value-of-information test ("would the answer change the action?") showing up in the data, and no question asks it yet.

# G43 exploration 3: a Jev decision tree, and a value-of-information model (plan fixed 2026-11-19, before any run)

**Source.** Dong et al., "Value of Information: A Framework for Human–Agent Communication" (arXiv 2601.06407). An agent holds a belief b(θ) over hypotheses. Acting now is worth V(b) = max_a Σ_θ b(θ)U(θ,a). Asking question q is worth the expected value after the answer, minus V(b), minus a per-question cost c that stands for the user's time and effort. The agent asks only if that net value is positive. The paper elicits beliefs from an LLM; c is an input, not a tuned parameter. It reports matching or beating tuned confidence thresholds in most conditions; its own table shows it losing to them at high c.

**Gloss's version.** One question, two hypotheses: the plan is right, or the plan is wrong.

| Action | Plan right | Plan wrong |
|---|---|---|
| build (stay quiet) | 0 | −L |
| ask | −c | −c − (1−r)L |
| object (only with a stated cause) | −c − d | −c − (1−r_o)L |

- L is the cost of building the wrong thing.
- c is the cost of interrupting.
- r is the chance the user's answer exposes a wrong plan.
- r_o is the same for an objection, which names the conflict.
- d is the extra cost of a false objection.

So asking beats building exactly when P(wrong) · r · L > c.

The cases where asking can't pay off fall out of the model with no special handling:
- **Investigation plans:** the plan is how the cause gets found, so P(wrong) ≈ 0.
- **Tasks:** nothing is going wrong.
- **Answered conversations:** asking again teaches nothing (r = 0) and costs twice as much.

**Fixed parameters.**
- r = 0.8, r_o = 0.9, d = 2c.
- c ∈ {0.05, 0.1, 0.25, 0.5}.
- L comes from a plan-scope question: one small change = 1, a component = 3, a system or infrastructure change = 10, an organisational change = 10.
- π, the prior that a plan with no stated evidence is wrong, is 0.5. That is how the pool was built; 0.25 is reported as a sensitivity check.

**Belief from Jev.** P(wrong) = 0 if `problem_described` < 0.3 or `plan_is_investigation` ≥ 0.5. Otherwise P(wrong) = (1 − m)·π + m·q, where m is `mechanism_stated` and q is the larger of the two step-4 scores.

**New questions**, examples from situations used nowhere in the pool:
- `plan_is_investigation` (yes/no): the plan is a way to find the cause (measure, profile, reproduce, log, compare), not a change meant to fix it.
- `plan_scope` (multiple choice): small / component / system / organisation.
- Step 4, worded on the premise that a cause is stated, sent in a separate request:
  - `misses_stated_cause`: the plan changes something other than the cause the user states.
  - `breaks_stated_requirement`: a requirement the user states rules the plan out.

**Policies.**
- **T1, the tree.** Step 1: `problem_described` < 0.3 → quiet. Step 2: `plan_is_investigation` ≥ 0.5 → quiet. Step 3: `mechanism_stated` < 0.7 → ask. Step 4: either step-4 score ≥ 0.5 → object; otherwise quiet. Step 4 at 0.3 and 0.7 is reported only.
- **V1(c), value of information.** The action with the highest expected utility, using Jev's belief and L. Objection is allowed only when `mechanism_stated` ≥ 0.7, as the standard requires.
- References: R1, S1, the LLM, always quiet, always ask.

**Scoring.**
1. The label rates as before. V1 is expected to give up some questions on small plans, by design.
2. Realized utility under the table above, using each case's known truth. Plans that are wrong: contradicted, mismatch, infeasible, wrong_fix, `*-misses`, `mis-*`. All others are right: sound, answered, tasks, fits, `snd-*`, right_fix, diagnose. A repeat question in an answered conversation costs 2c and teaches nothing. Utility is scored twice: with Jev's L and with a uniform L = 3. V1 optimizes the first, so the uniform score is the fairer comparison.

**Cost.** Two Jev requests per case and repeat, about 1,434 in all. The LLM answers are cached.

## G43 exploration 3 result (run 2026-11-19)

1,434 requests, none failed (`results/g43_explore/summary3.json`).

### The tree: the investigation step closes the quiet gap on single messages

| Cell (whole pool) | LLM | R1 | T1 tree | T1, step 4 @0.3 |
|---|---|---|---|---|
| quiet / single | 0.895 | 0.848 | **0.943** | 0.924 |
| quiet / conversation | 0.956 | 0.886 | 0.912 | 0.912 |
| task / both shapes | 1.000 | 1.000 | 1.000 | 1.000 |
| ask / single | 0.930 | 0.992 | **0.992** | 0.992 |
| ask / conversation | 0.735 | 0.980 | **0.980** | 0.980 |
| answered / conversation | 1.000 | 1.000 | 1.000 | 1.000 |
| object / single (reported only) | 0.752 | 0.532 | 0.525 | 0.567 |

**Step 2 is where the gain comes from.** It flagged 11 cases as investigations in at least two of three repeats:
- the heap-snapshot and similar sound proposals, and the bare `diagnose` items;
- four wrong proposals (full/mis-01, mis-04, inf-01, inf-15).

On single messages, Jev now stays quiet on sound plans more often than the LLM, and it still asks wherever it did before. The G42 test part has no investigation plans, so it is unchanged there. Quiet on conversations (0.912) is still behind the LLM (0.956).

**Step 4, worded on the premise of a stated cause, didn't raise objection recall** (0.525 at 0.5, 0.567 at 0.3). Asking about contradiction separately (S1, 0.61) did better than asking it only after a cause is stated.

### The value-of-information model: the useful part is the scoring, not the policy

**As a policy, V1 does poorly on the labels.**
- With any small c, it asks on most sound plans. Its belief keeps P(wrong) well above zero unless Jev is very sure.
- It asks again in answered conversations, because Jev can't tell an answered conversation from one where the cause was stated from the start.
- At c = 0.5 it is closest to the labels but still worse than T1 everywhere.
- `plan_scope` hardly varies: the mean L is 1.8–3.7 across groups, and tasks score highest. Jev's sense of stakes is weak here, as in exploration 2.

**As a way to score policies, it changes the picture.** Mean utility per decision; higher is better. Each cell gives Jev's L / a uniform L of 3.

| Policy | c = 0.05 | c = 0.1 | c = 0.25 | c = 0.5 |
|---|---|---|---|---|
| always quiet | −1.30 / −1.05 | −1.30 / −1.05 | −1.30 / −1.05 | −1.30 / −1.05 |
| always ask | −0.31 / **−0.27** | −0.37 / −0.32 | −0.53 / −0.48 | −0.80 / −0.75 |
| LLM | **−0.29** / −0.28 | **−0.31** / **−0.30** | **−0.38** / **−0.37** | **−0.50** / **−0.49** |
| R1 | −0.39 / −0.37 | −0.41 / −0.39 | −0.49 / −0.46 | −0.61 / −0.59 |
| S1 | −0.31 / −0.33 | −0.34 / −0.35 | −0.42 / −0.43 | −0.55 / −0.56 |
| T1 | −0.36 / −0.38 | −0.39 / −0.40 | −0.46 / −0.47 | −0.57 / −0.59 |
| V1 | −0.37 / −0.38 | −0.41 / −0.41 | −0.48 / −0.49 | −0.58 / −0.64 |

What it shows:
1. **The costly mistake is building a wrong plan without a word, not asking once too often.** Asking pays whenever P(wrong) · r · L > c. With r = 0.8 and L = 3, a question costing a quarter of a small wasted change (c = 0.25) pays once P(wrong) is above 0.10.
2. **The LLM leads on utility at every cost** even though it asks less on conversations. It objects to 0.75 of wrong plans that come with a stated cause, against 0.53 for Jev's rules. S1, the best Jev objector, is the best Jev policy.
3. **Always asking beats every Jev rule when c is low** (and beats the LLM too with uniform L at c = 0.05). This depends on the pool: 84 of 239 plans (35%) are wrong, by construction. In real use the share of wrong plans sets where the break-even falls, and that share is unknown.
4. **A linear cost per question misses something the literature names but doesn't model: trust erodes with repeated questions.** That cost grows with how often Gloss asks across a session, not with any single question.

**What it suggests for G43.** Score candidates by utility as well as by label rates, at stated values of c and of the share of wrong plans. Treat objection recall as the main gap rather than quiet-on-sound. Keep the investigation step. On utility the best Jev candidate is the tree with S1's contradiction questions (T1 steps 1–3, then S1's objection). It was not run as a single policy here.

## The tree variation at three question costs (2026-11-19)

**What was compared.** T2 is T1's steps 1–3 with S1's separately asked contradiction questions at step 4, at 0.5 (and 0.3, reported only). The question cost c is set at the three levels offered to the owner, as a fraction of a wasted small change:
- about 5–10%, scored at c = 0.075;
- a quarter;
- a half.

Because the break-even depends on how often plans are wrong, the pool's 35% is also reweighted to 20% and 10%. Utility is the exploration-3 model with a uniform L = 3; Jev's own L gives the same ordering. All answers are the recorded ones; nothing new was sent to Jev (`results/g43_explore/compare_costs.json`).

**Rates.**

| Cell | T1 | T2 | T2 @0.3 |
|---|---|---|---|
| quiet / single | 0.943 | **0.962** | 0.943 |
| quiet / conversation | 0.912 | 0.912 | 0.860 |
| ask / single and conversation | 0.992 / 0.980 | 0.992 / 0.980 | 0.992 / 0.980 |
| answered / conversation | 1.000 | 1.000 | 1.000 |
| object / single | 0.525 | **0.489** | 0.546 |

In the tree, the requirement question only runs after a cause is stated, so wrong plans with no stated cause are asked rather than objected. The investigation step also lets four wrong proposals through. Both lower T2's objection recall below S1's 0.61.

**Mean utility per decision** (higher is better):

| c | wrong share | always ask | LLM | R1 | S1 | T1 | T2 | V1 |
|---|---|---|---|---|---|---|---|---|
| 0.075 | 35% | −0.291 | **−0.289** | −0.376 | −0.337 | −0.389 | −0.406 | −0.395 |
| 0.075 | 20% | −0.202 | **−0.172** | −0.225 | −0.203 | −0.231 | −0.241 | −0.251 |
| 0.075 | 10% | −0.143 | **−0.095** | −0.124 | −0.114 | −0.127 | −0.131 | −0.155 |
| 0.25 | 35% | −0.479 | **−0.371** | −0.462 | −0.429 | −0.471 | −0.486 | −0.498 |
| 0.25 | 20% | −0.393 | **−0.237** | −0.297 | −0.281 | −0.300 | −0.308 | −0.334 |
| 0.25 | 10% | −0.336 | **−0.148** | −0.188 | −0.183 | −0.187 | −0.189 | −0.214 |
| 0.5 | 35% | −0.748 | **−0.488** | −0.584 | −0.559 | −0.589 | −0.600 | −0.654 |
| 0.5 | 20% | −0.666 | **−0.329** | −0.401 | −0.392 | −0.400 | −0.403 | −0.411 |
| 0.5 | 10% | −0.612 | −0.223 | −0.280 | −0.282 | −0.274 | −0.273 | **−0.211** |

**Where the loss comes from** (c = 0.25, 20% wrong):

| Policy | Silent wrong builds | Questions on right plans | False objections | Residual after catching a wrong plan |
|---|---|---|---|---|
| LLM | −0.064 | −0.047 | 0.000 | −0.125 |
| T2 | **−0.136** | −0.057 | 0.000 | −0.115 |
| always ask | 0.000 | −0.223 | 0.000 | −0.170 |

**Reading.**
- **The cost of a question doesn't change the ranking.** Across all three costs and all three wrong-plan shares, the LLM scores best. The one exception is c = 0.5 with 10% wrong plans, where the value-of-information policy asks rarely and edges ahead. Among the Jev rules, S1, T1 and T2 sit within about 0.03 of one another.
- **The tree's gain doesn't show up in utility.** Staying quiet on sound plans saves little, because a question is cheap next to a wrong build.
- **T2 trails the LLM almost entirely on silent wrong builds,** 0.136 against 0.064 at the middle setting. These are wrong plans that come with a stated cause and get no objection, plus the four wrong proposals the investigation step waved through.
- **Fixing objection matters more than picking c.** The setting of c only decides how much asking on sound plans hurts, and for the Jev rules that cost is already small.

## Correction, and routing by request type (2026-11-19)

**Correction.** The cost comparison above said T2 loses objection recall because "wrong plans with no stated cause are asked rather than objected". The case-by-case breakdown shows no such case: wherever T2 asks on a wrong plan, S1 asks too. The whole drop from S1 (0.61) to T2 (0.49) comes from two places:
- **The tree's first step.** Jev reads 14 of G40's wrong proposals (42 answers) as tasks, because they state a goal and a plan with nothing going wrong. Example: "The goal of the screen is that no real reversal gets past it… set the flag threshold so that the screen produces very few false positives", with `problem_described` = 0.18. The tree stays quiet on these. S1 asked its requirement question without the gate.
- **The investigation step,** which let four wrong proposals through.

**Asking rather than objecting when no cause is stated** is already the behaviour of both S1 and T2 on no-evidence cases, and it follows the owner's second ruling. The LLM objects to some of them (6 answers, such as mail-connections-misses).

**Routing by request type.** Jev sorts each request, and only the kind that needs plan-against-stated-facts judgment goes to the LLM. The LLM answers are the cached ones; nothing new was sent.

| Route | Task | Investigation | Unsupported fix | Supported fix |
|---|---|---|---|---|
| H1 | quiet | quiet | ask (Jev) | LLM |
| H3 | LLM | quiet | ask (Jev) | LLM |
| T3 (Jev only) | object if `plan_breaks_requirement` ≥ 0.5, else quiet | quiet | ask | T2's step 4 |

| Cell / measure | LLM | T2 | T3 | H1 | H3 |
|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.962 | 0.933 | 0.933 | 0.933 |
| quiet / conversation | 0.956 | 0.912 | 0.912 | 0.912 | 0.912 |
| ask / single and conversation | 0.930 / 0.735 | 0.992 / 0.980 | 0.992 / 0.980 | 1.000 / 0.980 | 1.000 / 0.990 |
| answered / conversation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| object / single | 0.752 | 0.489 | 0.610 | 0.532 | 0.709 |
| share sent to the LLM | 100% | 0% | 0% | 43% | 61% |
| utility, c = 0.25, 35% / 20% / 10% wrong | −0.371 / −0.237 / **−0.148** | −0.486 / −0.308 / −0.189 | −0.431 / −0.278 / −0.177 | −0.452 / −0.289 / −0.181 | **−0.364** / −0.239 / −0.156 |
| silent wrong builds, c = 0.25, 20% wrong | −0.064 | −0.136 | — | −0.110 | **−0.048** |

**Reading.**
- **H3 matches the LLM on utility while sending 61% of requests to it.** It keeps Jev's advantage on asking and on quiet single messages, and leaves fewer wrong plans unflagged than the LLM does.
- **Sending only supported fixes (H1) isn't enough,** because the plans with requirements that read as tasks are where the silent wrong builds are.
- **The type worth naming is a plan the user has given something to check against: a stated cause or a stated requirement.** Judging a plan against those facts is a comparison Jev does poorly. Detecting whether such facts are present is something it does well.
- **A Jev question that asks whether a requirement or goal is stated** would send only those tasks on, which could bring the LLM share well below 61%. Not yet tested.

## One failure, step by step: full/mis-02 (2026-11-19)

**The message Jev sees** (single message; the state is exactly this text): a cheap first-pass score screens model answers for position reversals and sends what it flags to an accurate reviewer. "The goal of the screen is that no real reversal gets past it." The plan: "set the flag threshold at the 95th percentile of the score's run-to-run noise so that the screen produces very few false positives". The request: the calibration script. Label: objected. A screen in front of an accurate reviewer needs recall, and the plan tunes it for precision.

**What the tree does** (Jev's answers in three repeats; they barely move):

| Step | Question (abridged) | Jev | Branch |
|---|---|---|---|
| 1 | `problem_described`: is something going wrong? "Work the user wants done for its own sake … is not something going wrong." | 0.18–0.19 | below 0.3: **task, stay quiet. Exit.** |
| 2 | `plan_is_investigation` | 0.26–0.29 | not reached |
| 3 | `mechanism_stated` | 0.64–0.68 | not reached; would have asked about a cause that doesn't exist |
| 4 | `plan_misses_cause` / `plan_breaks_requirement` | 0.23–0.28 / 0.34–0.42 | not reached; neither clears 0.5 |

**What Jev saw but the tree never read.**
- `contradicted`: 0.58–0.60.
- The link question's P(contradicted): 0.38–0.43.
- `bad_solution`: 0.86–0.87.
- `request`: task at 0.97.

The LLM also calls it a task, and objects in all three repeats ("their stated requirement of zero missed reversals conflicts with a high threshold designed to minimize false positives"). G42's simple rule, which objects whenever `contradicted` ≥ 0.3, would have objected too.

**Why it fails.**
1. **The first step merges two decisions.** "Should we ask what causes the problem?" needs a problem. "Does the plan conflict with what the user says they need?" applies to any request that states a goal. The LLM's standard keeps them apart: the request type decides whether to ask, and a contradiction is objected to whatever the type (`GroundResult.action`). From G41 on, the Jev rules put the task gate in front of everything, so a task can never be objected to.
2. **The fix-or-task split doesn't mark a real difference for checking.** A problem is a goal that isn't being met; a task is a goal to build toward. Either can come with a plan that misses its goal. What matters for objection is whether the user states something the plan can be checked against: a cause, a goal or a requirement.
3. **The step-4 wording doesn't fit this case.** There is no cause, so `plan_misses_cause` is correctly low. The goal is phrased as "the goal of the screen is…", which `plan_breaks_requirement` reads only half as a requirement. Seeing the conflict also takes a step of inference: a threshold set for few false positives lets more real reversals through. The broader `contradicted` question ("facts or requirements the user states show the plan will not achieve what they need") is the one that caught it.

**Across the pool.** Among requests Jev reads as tasks, requiring both `contradicted` ≥ 0.5 and link P(contradicted) ≥ 0.2 fires on 12 of 42 answers for wrong plans and 0 of 87 for right ones. On tasks, objection can be ungated without false objections, but these two signals catch only about 30% of the wrong plans.

# G43 exploration 4: correctness and assumption questions, and a split by what the plan can be checked against (plan fixed 2026-11-19, before any run)

Same 239 spent cases, full state, three repeats, one new Jev request per case with three yes/no questions. Examples are drawn from situations used nowhere in the pool.
- `goal_stated`: the user states a goal, requirement or constraint the result must meet (what it has to achieve, a limit, a deadline, a policy). Wanting a described problem to go away doesn't count on its own.
- `plan_correct`: how likely the plan will actually achieve what the user needs. This judges the plan itself, which the standard forbids, so it is reported and tried only as an alternative signal.
- `user_assuming`: the user takes for granted something they haven't checked or stated: about the cause, about what the plan will do, or about what they need.

**Policy D, the redesigned split.** Two branches are judged side by side:
- **Checkable:** `mechanism_stated` ≥ 0.7 (a stated cause) or `goal_stated` ≥ 0.5.
- **Conflict:** `contradicted` ≥ 0.5 with link P(contradicted) ≥ 0.2, or a stated cause with `plan_misses_cause` ≥ 0.5, or a stated goal with `plan_breaks_requirement` ≥ 0.5.

Then:
1. Object if the request is checkable and conflicts.
2. Otherwise ask if something is going wrong (`problem_described` ≥ 0.3), no cause is stated, and the plan isn't an investigation.
3. Otherwise stay quiet.

**Reported variants.**
- D@0.3: every conflict threshold at 0.3, with link P(contradicted) at 0.1.
- D+correct: a checkable request also conflicts when `plan_correct` < 0.3.
- D+assume: the ask branch fires when `user_assuming` ≥ 0.5, in place of a missing cause.
- HD: checkable requests go to the LLM, and the ask branch stays with Jev.

**Descriptive.** For `plan_correct` (reversed), `user_assuming`, `bad_solution`, `contradicted` and `goal_stated`: how well each separates wrong plans from right ones (AUC), and the mean for each group. Also the answers on full/mis-02.

Scoring is the same as before: label rates, and utility at c = 0.25 with 35%, 20% and 10% wrong plans and a uniform L = 3.

## G43 exploration 4 result (run 2026-11-19)

717 requests, none failed (`results/g43_explore/summary4.json`).

| Cell / measure | LLM | T2 (tree) | D | D@0.3 | D+correct | D+assume | HD |
|---|---|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.962 | 0.924 | 0.886 | 0.924 | 0.190 | 0.924 |
| quiet / conversation | 0.956 | 0.912 | 0.912 | 0.860 | 0.912 | 0.254 | 0.956 |
| task / both shapes | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| ask / single | 0.930 | 0.992 | 0.969 | 0.969 | 0.853 | 0.977 | 0.953 |
| ask / conversation | 0.735 | 0.980 | 0.980 | 0.980 | 0.980 | 0.961 | 0.794 |
| answered / conversation | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.907 | 1.000 |
| object / single | 0.752 | 0.489 | 0.674 | **0.830** | **0.794** | 0.674 | 0.752 |
| utility, c = 0.25, 35% / 20% / 10% wrong | −0.371 / −0.237 / **−0.148** | −0.486 / −0.308 / −0.189 | −0.409 / −0.267 / −0.172 | −0.357 / −0.244 / −0.169 | **−0.353 / −0.236** / −0.158 | −0.442 / −0.322 / −0.243 | −0.373 / −0.239 / −0.150 |
| silent wrong builds (20% wrong) | −0.064 | −0.136 | −0.081 | **−0.038** | −0.045 | −0.062 | −0.064 |

**The split by what the plan can be checked against works.** D objects to full/mis-02 in all three repeats (`goal_stated` 0.95). Objection recall rises from 0.49 under the tree to 0.67, and to 0.83 under D@0.3, above the LLM. The asking cells hold. D@0.3 beats the LLM on utility when 35% of plans are wrong and nearly ties at 20%.

**`goal_stated` doesn't discriminate.** It averages 0.65–0.75 in every group, and its AUC between wrong and right plans is 0.49. Jev finds a goal in almost every message. So in practice "checkable" means nearly everything, and the gain comes from letting the conflict signals run on every request. For the same reason HD would send 94% of requests to the LLM, which saves nothing.

**"How correct is this plan?" is strong where the user has stated something, and weak where they haven't.**

| `plan_correct` | AUC, wrong vs right |
|---|---|
| Whole pool | 0.931 |
| Cases with a stated cause or goal (sound, contradicted, answered) | **0.988** |
| No-evidence cases (the plans that fit against those that miss) | 0.744 |

So it is close to a perfect detector of conflict with the user's own facts, and only a fair guess at hidden causes. D+correct leads every policy on utility at 35% and 20% wrong plans. But its ask/single drops to 0.853, because it objects to some no-evidence plans it guesses are wrong. That goes against the owner's second ruling, and it is the part where it judges the diagnosis. Limiting `plan_correct` to requests with a stated cause, where its signal comes from the user's facts, has not been tried.

**"Is the user making an assumption?" is high everywhere.** It averages 0.70–0.89 in every group (AUC 0.875 between wrong and right, but 0.70 even on quiet, sound plans). As the trigger for asking (D+assume), it asks on 80% of sound plans. Jev reads "I've researched this and decided" as an assumption in every message.

On full/mis-02: `plan_correct` 0.22–0.23, `user_assuming` 0.86–0.88.

# A formal frame for the scenarios (2026-11-19)

Four formalisms fit the problem, and each gives one piece of the frame.

**1. Satisfaction argument (Zave and Jackson, requirements engineering).** A specification S meets a requirement R in a domain D when D, S ⊨ R. Here R is what the user needs (the problem gone, or the stated goal met), S is the plan, and D is what the user states about their world (cause, measurements, constraints). Gloss's three actions are the three states of that argument:

| D, S ⊨ ? | Meaning | Action |
|---|---|---|
| D, S ⊨ R plausibly | the stated facts support the plan | quiet |
| D too thin to tell | the link from plan to goal rests on facts not stated | **ask** for the missing part of D |
| D, S ⊨ ¬R, or the plan is unlikely to give R | the stated facts, or the plan's merit, count against it | **object** |

**2. Toulmin's argument model.** The user's message is an argument. The claim is "this plan fixes it". The grounds are the stated facts. The warrant is the causal link from plan to goal. A rebuttal is anything that defeats it. "Absent" means there is a claim and grounds but no warrant; "contradicted" means a rebuttal is present.

**3. Defeaters, from eliminative argumentation and assurance cases (Goodenough, Weinstock and Klein; GSN).** Doubts about a claim come in three kinds, and each maps to an action:
- *Undercutting* (the inference from grounds to claim isn't established) is the no-evidence case → ask.
- *Rebutting* (evidence that the claim is false: the plan misses the stated cause or breaks a stated requirement) → object.
- *Undermining* (the grounds themselves are doubtful: a debatable diagnosis) → under ruling 3, object if it makes the plan unsound; this is the new case.

**4. Critical questions for argumentation schemes (Walton).** Two schemes cover Gloss's requests:
- *Practical reasoning:* goal G; action A brings about G; so do A.
- *Cause to effect:* C causes S; so acting on C removes S.

Each scheme comes with a standard list of critical questions, and those map onto Jev questions:

| Critical question | Kind of doubt | Jev question so far |
|---|---|---|
| Is the causal link established (cause to effect)? | undercutting | `mechanism_stated` |
| Will A bring about G, given the stated facts? | rebutting | `plan_correct`, `contradicted` |
| Does A conflict with another stated goal or constraint? | rebutting | `plan_breaks_requirement` |
| Is A about finding C rather than acting on it? | (no doubt applies) | `plan_is_investigation` |
| What is G: a problem to remove, or a requirement to meet? | (sets R) | `problem_described`, `goal_stated` |

**What the frame changes.**
- It explains the task-gate failure. "Task or fix" decided *which* R applies, but the rules used it to decide *whether* to check D, S ⊨ R at all.
- It gives a small question set with a reason for each question, in place of the eight-plus ad hoc ones.
- It gives a compact way to write cases: each held-out case can be written as (R, D, S, expected verdict, defeater kind), in Given/When/Then form. For example:

  > **Given** a goal "no real reversal passes the screen" and the fact "flagged items go to an accurate reviewer",
  > **when** the plan sets the threshold for few false positives,
  > **then** object: a rebutting defeater against the goal.

  The routing rules can be written the same way, as one decision table.

# Next experiments (defined 2026-11-19)

**E5: the critical-questions battery** (spent data, 239 cases). Replace the accumulated questions with one critical question per kind of doubt:
- the goal type (problem / requirement / both / neither, as one multiple-choice question);
- whether the causal link is stated;
- given the stated facts, whether the plan achieves the goal (outcome wording, which beat the contradiction wording in exploration 4);
- whether the plan conflicts with a stated constraint;
- whether the plan is an investigation.

Rules are written as a decision table and fixed before the run:
1. Object when a rebutting doubt is at least 0.5.
2. Otherwise ask when the goal is a problem, the causal link is not stated, and the plan isn't an investigation.
3. Otherwise stay quiet.

Under ruling 3, merit objections are allowed, so `plan_correct`-style doubt counts as rebutting whenever any goal is present. Under ruling 2, no-cause cases are never objected to for symptom mismatch alone. The same thresholds are reported at 0.3.

Compared against D, D+correct and the LLM, on label rates and on utility at c = 0.25 with 35%, 20% and 10% wrong plans. Cost: about 717 Jev calls.

**E6: write the G43 held-out set in the frame.** Every case is a (R, D, S, verdict, defeater) tuple in Given/When/Then form, drafted by the model and reviewed by the owner before any run. It includes kinds the pool lacks:
- requirement-bound tasks with a rebutting defeater, like full/mis-02;
- a stated but debatable diagnosis with a plan that fits it (an undermining defeater; under ruling 3 the expected verdict is object when the diagnosis makes the plan unsound, and the owner labels each one);
- stated cause, fitting plan, weak engineering (under ruling 3, object when the weakness defeats the goal);
- the existing kinds: sound, no evidence (plans that fit and plans that miss), symptom mismatch, investigations, plain tasks, answered conversations.

Both shapes, as in G41 and G42.

**E7: the G43 held-out run.** One Jev setup is fixed on the 239 spent cases (E5's battery or D+correct, whichever is better on dev), plus one routing variant if E5 leaves a type that only the LLM handles well. It runs once against the LLM classifier. Decision rule:
- **Co-primary:** utility at c = 0.25 with 20% wrong plans. Jev must be no worse than the LLM by more than 0.02 per decision.
- **Also required:** no gated label cell more than max(0.07, one case) below the LLM, as in G41 and G42.

Objection becomes a gated cell, since ruling 3 makes it part of the standard. Nothing is changed after the result.

## E5 details (fixed 2026-11-19, before the run)

**Questions**, in one Jev request per case. The examples come from the earlier explorations' unused situations.
- `goal_type` (multiple choice): what the plan has to deliver:
  - `problem`: something going wrong must stop;
  - `requirement`: a stated goal or constraint must be met;
  - `both`;
  - `neither`: a plain request with nothing to check.
- `link_stated` (critical question for cause to effect): does the user state what is happening that causes the problem, in a way the plan can be checked against? A cause stated inside the plan counts (ruling 1). The symptom's name doesn't, and neither does the plan's purpose alone.
- `achieves_goal` (critical question for practical reasoning; outcome wording): given what the user states, how likely is it that the plan delivers what they need? Merit counts (ruling 3).
- `conflicts_constraint` (critical question for side effects and conflicts): does the plan break a goal, limit or constraint the user states?
- `investigation`: is the plan a way to find out the cause?

**Decision table.** P(goal) = 1 − P(neither); P(problem goal) = P(problem) + P(both). The rows are checked in order.

| # | Condition | Action |
|---|---|---|
| 1 | `investigation` ≥ 0.5 | quiet |
| 2 | P(goal) < 0.5 | quiet |
| 3 | `conflicts_constraint` ≥ t | object (a stated constraint needs no cause) |
| 4 | P(problem goal) ≥ 0.5 and `link_stated` < 0.7 | ask (ruling 2: no objection for a mismatch alone) |
| 5 | 1 − `achieves_goal` ≥ t | object (a rebutting doubt) |
| 6 | otherwise | quiet |

t = 0.5 is the primary threshold; t = 0.3 is reported. Rates and utility are scored as in exploration 4, against D, D+correct and the LLM, along with each question's AUC between wrong and right plans.

## E5 result (run 2026-11-19)

717 requests, none failed (`results/g43_explore/summary_e5.json`).

| Cell / measure | LLM | D | D@0.3 | D+correct | **E5** | E5@0.3 |
|---|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.924 | 0.886 | 0.924 | 0.914 | 0.648 |
| quiet / conversation | 0.956 | 0.912 | 0.860 | 0.912 | 0.842 | 0.570 |
| task / single | 1.000 | 1.000 | 1.000 | 1.000 | 0.972 | 0.417 |
| task / conversation | 1.000 | 1.000 | 1.000 | 1.000 | **0.750** | 0.500 |
| ask / single | 0.930 | 0.969 | 0.969 | 0.853 | **0.992** | 0.984 |
| ask / conversation | 0.735 | 0.980 | 0.980 | 0.980 | 0.941 | 0.941 |
| answered / conversation | 1.000 | 1.000 | 1.000 | 1.000 | 0.981 | 0.741 |
| object / single | 0.752 | 0.674 | 0.830 | 0.794 | 0.745 | 0.766 |
| utility, c = 0.25, 35% / 20% / 10% wrong | −0.371 / −0.237 / **−0.148** | −0.409 / −0.267 / −0.172 | −0.357 / −0.244 / −0.169 | **−0.353 / −0.236** / −0.158 | −0.379 / −0.262 / −0.185 | −0.460 / −0.376 / −0.321 |
| silent wrong builds (20% wrong) | −0.064 | −0.081 | −0.038 | −0.045 | −0.043 | −0.029 |
| false objections (20% wrong) | 0.000 | −0.005 | −0.018 | −0.008 | **−0.031** | −0.157 |

**What worked.** Five questions in place of fifteen match the LLM on objection (0.745 against 0.752) and beat it on asking. E5 objects to full/mis-02 in all three repeats. `achieves_goal` separates wrong plans from right ones nearly as well as `plan_correct` (AUC 0.923 against 0.931). `link_stated` separates the quiet group from the ask group as well as `mechanism_stated` did (0.958 against 0.963).

**What failed: merit objections in conversations.**
- **Where the false objections came from.** Of the 24 false-objection answers, 19 come from `achieves_goal` in conversations: nine on sound plans, nine on tasks, one on an answered conversation. The late turn in those conversations asks for one step ("Now the container image for the jobs"), and Jev appears to judge whether that step delivers the whole goal.
- **The constraint question objected to one sound proposal** (full/snd-06) in all three repeats.
- **The threshold at 0.3 is unusable.**

**The goal-type question doesn't gate anything.** Jev never answered `neither`. It called every plain task `requirement` and almost every fix `both`. Every request has something it must deliver, so in this frame R always exists. This confirms what exploration 4 found with `goal_stated`. The frame's real decisions are whether a causal link is stated and whether a rebutting doubt is present, not whether there is a goal.

**Against E7's rule.** No candidate is clear yet:
- E5 fails task/conversation and quiet/conversation.
- D+correct falls 0.077 below the LLM on ask/single, more than the 0.07 tolerance allows.
- D@0.3 fails quiet/conversation.

On utility, D+correct and D@0.3 are the strongest. The two changes most likely to fix E5 before E7 are:
- word `achieves_goal` for conversations as "the user's overall plan, not only the step asked for in the latest turn";
- drop the goal-type row.

## E5b: the two fixes (fixed 2026-11-19, before the run)

**Changes from E5. Nothing else changes.**
1. **Goal-type row dropped.** `goal_type` leaves the battery. Asking still needs something to be going wrong, so the battery takes G41's yes/no `problem_described` question unchanged. The ask row uses it at ≥ 0.3, as every Jev rule since G41 has.
2. **Conversation wording for `achieves_goal`.** In conversations, the question adds: "Judge the user's overall plan as the conversation describes it, not only the step asked for in the latest turn." Single messages keep E5's wording.

**Decision table.** Rows are read in order:

| # | Condition | Action |
|---|---|---|
| 1 | `investigation` ≥ 0.5 | quiet |
| 2 | `conflicts_constraint` ≥ 0.5 | object |
| 3 | `problem_described` ≥ 0.3 and `link_stated` < 0.7 | ask |
| 4 | 1 − `achieves_goal` ≥ 0.5 | object |
| 5 | otherwise | quiet |

The whole battery is rerun on all 239 cases, three repeats each (717 requests). It is scored as E5 was.

## E5b result (run 2026-11-19)

717 requests, none failed.

| Cell / measure | LLM | D+correct | E5 | **E5b** | E7 tolerance | E5b passes |
|---|---|---|---|---|---|---|
| quiet / single | 0.895 | 0.924 | 0.914 | 0.914 | 0.070 | yes |
| quiet / conversation | 0.956 | 0.912 | 0.842 | **0.833** | 0.070 | **no** |
| task / single | 1.000 | 1.000 | 0.972 | 0.972 | 0.083 | yes |
| task / conversation | 1.000 | 1.000 | 0.750 | **0.750** | 0.083 | **no** |
| ask / single | 0.930 | 0.853 | 0.992 | 0.984 | 0.070 | yes |
| ask / conversation | 0.735 | 0.980 | 0.941 | 0.971 | 0.070 | yes |
| answered / conversation | 1.000 | 1.000 | 0.981 | **1.000** | 0.070 | yes |
| object / single | 0.752 | 0.794 | 0.745 | 0.752 | 0.070 | yes |
| utility, c = 0.25, 35% / 20% / 10% wrong | −0.371 / −0.237 / −0.148 | −0.353 / −0.236 / −0.158 | −0.379 / −0.262 / −0.185 | −0.365 / −0.253 / −0.180 | | |
| silent wrong builds (20% wrong) | −0.064 | −0.045 | −0.043 | **−0.033** | | |

**Dropping the goal row cost nothing.** The asking cells held, answered conversations went back to 1.000, and objection matches the LLM. With `problem_described` in its place, tasks are never asked about and can still be objected to.

**The overall-plan wording didn't fix conversations.** Nine sound plans and nine tasks in conversations are still objected to through `achieves_goal`. Their scores barely moved: 0.34–0.49 now, against 0.35–0.48 in E5, all just under the 0.5 line. The cause looks like the assistant's earlier replies, not the step framing. Those replies list caveats ("a common fix is a fallback…", "the numbers are my guesses"), and Jev reads them as doubt about the plan. On single messages, sound plans score well above 0.5.

**After the fact (not a result).** If conversations object through `achieves_goal` only below 0.3, every cell passes E7's rule on this pool: quiet/conversation 0.912 and task/conversation 1.000. Nothing on this pool measures what that costs. The 12 wrong-plan conversations in the pool are all no-evidence cases. **No conversation in it states a cause behind a wrong plan.** Objection in conversations is unmeasured, and the G43 held-out set has to include it.

**For E7.** E5b is the strongest candidate so far. It has five questions, the fewest silent wrong builds of any policy, objection on a par with the LLM, and better asking. Its one failure is merit objections in conversations. The candidate fix is a per-shape objection threshold, which E7's rules allow only if dev shows a gain of at least 0.02. G43's set must contain wrong plans with a stated cause in conversations, or that threshold can't be judged.

# E6: the G43 held-out set (spec fixed 2026-11-19; set drafted for owner review)

**Purpose.** E7 picks one Jev setup on the 239 spent cases and tests it once here. This set adds what the spent pool lacks, so the E7 decision can rest on it:
- objections in conversations;
- tasks bound by a goal;
- debatable diagnoses;
- weak engineering;
- investigations.

**How cases are written.** Every case is written in the formal frame: the goal R, the user's stated facts D, the plan S, the expected verdict, and the kind of doubt. The review page shows each case in Given/When/Then form. All situations are new: none appears in an earlier set or in any question's criteria examples (a test checks this).

| Kind | Count | Doubt | Expected |
|---|---|---|---|
| Situations: cause stated, plan fits | 8 | none | quiet |
| Situations: cause stated, plan misses | 8 | rebutting | object |
| Situations: cause withheld, either plan | 16 | undercutting | ask (ruling 2 when the plan doesn't match the symptom) |
| Requirement-bound, plan meets it | 6 | none | quiet |
| Requirement-bound, plan breaks it | 6 | rebutting | object |
| Debatable diagnosis, plan fits it | 4 | undermining | proposed per case, labelled by the owner (ruling 3) |
| Stated cause, plan acts on it but weak engineering defeats the goal | 4 | rebutting (merit) | object (ruling 3) |
| Investigation plans | 4 | none | quiet |
| Plain tasks | 6 | none | quiet |

**Single messages:** all 62 above.

**Conversations:** the G37 shape. Two earlier build steps come first; the assistant's replies are recorded once from the unaided model and frozen, and a conversation is scored only if those steps were built with no question and no objection. The kinds are:
- late_sound: sound plans, requirements met, investigations, tasks, and the debatable case proposed quiet;
- late_absent: 16;
- late_answered: 8, answered by the grounding check at turn 1;
- **late_flawed:** situations whose plan misses, requirements broken, weak engineering, and the debatable cases proposed for objection.

The unaided model often objects early in a flawed conversation, so few of those may survive. **If fewer than four late_flawed conversations survive, objection in conversations is reported only.** That rule is fixed now, before any recording.

**E7 cells.** These are G42's gated groups, plus objection in each shape:
- quiet (sound, requirement met, investigation);
- task;
- ask;
- answered;
- object (contradicted, requirement broken, weak, debatable when labelled object).

E7's rule as written above: utility at c = 0.25 with 20% wrong plans no worse than the LLM by 0.02, and no gated cell below the LLM by more than max(0.07, one case).

**Order.**
1. The owner reviews the set and labels the four debatable cases.
2. Histories are recorded once (about $5–8).
3. E7 picks on dev.
4. The single test run.

## E6 review fixes (2026-11-19)

An external review of the draft found five problems. All five held up against the code, and all are fixed. The set is still `drafted`, and nothing has been recorded.

1. **Held-out leakage.**
   - `upload-500s` reproduced the investigation criterion's "log … for a week before changing anything" example. It is replaced by `zero-invoices`, which exports zero-total invoices and looks for what they share.
   - `price-alerts` mirrored the stock, one-minute and polling example. It is replaced by `tenant-export`: the tenant id comes from the session, not from a URL parameter anyone can change.
   - The novelty test now checks shared content words and shared two-word phrases, not just the first five words. Its thresholds catch both leaked cases, and a test asserts that. It remains a heuristic; checking for reuse of meaning still needs a human.
2. **Owner labels are enforced.** `debatable_label()` no longer falls back to the drafter's proposal. An unset label is `unlabelled`, its conversation is kept apart as `late_unlabelled`, and it is never scored. `ready()` refuses any recording or run until `REVIEW == "owner-checked"` and all four labels are set. A label must be `objected` or `none`.
3. **Two gold labels were unsupported.**
   - `button-colour` now states the fact its label rests on: the button and signup page haven't changed in a year.
   - `upload-500s` logged full requests, which can expose credentials and personal data. It has been replaced (see 1).
4. **Two contradicted plans were ambiguous.**
   - `queue-backlog`'s Kafka plan now keeps a single consumer that handles one message at a time.
   - `warehouse-sync`'s zstd plan compresses each table only after it has been written to the worker's disk.
5. **One rule for debatable diagnoses (proposed; the owner confirms).** Object to an undermining doubt when either:
   - (a) the user's own facts point against the diagnosis; or
   - (b) the diagnosis is unsupported and the plan is costly or hard to reverse.

   An unsupported diagnosis behind a cheap, reversible plan stands. This links ruling 3 to the value-of-information finding: stakes decide. The proposals now follow the rule and match the reviewer's provisional labels:
   - python-rewrite: object, by (b);
   - network-card: quiet;
   - button-colour: object, by (a), with the fact added;
   - db-underpowered: quiet.

**Also.** A test now fails if `docs/g43_heldout_review.md` drifts from the set. The counts are now 18 late_flawed, 24 late_sound and 4 late_unlabelled; the split moves once the labels are set.

**Owner review (2026-11-20).** The owner confirmed the rule for debatable diagnoses, set the four labels as proposed (python-rewrite and button-colour object; network-card and db-underpowered quiet), and judged the evidence levels well calibrated on a spot check. The set is `owner-checked`. With the labels set, the 70 conversations are 20 late_flawed, 26 late_sound, 16 late_absent and 8 late_answered. Nothing has been recorded or run.

**Histories recorded (2026-11-20, once, frozen).** `python -m eval.g43_eval --record` wrote `results/g43/late_histories.json`: 70 of 70 recorded, none failed. The unaided model and the judge are both claude-sonnet-5-5, as in G42. A conversation is scored only if its earlier turns were built with no question and no objection.

| Kind | Survived |
|---|---|
| late_sound | 26 of 26 |
| late_answered | 7 of 8 |
| late_absent | 5 of 16 |
| late_flawed | 0 of 20 |

- **No flawed conversation survived.** In all 20 the unaided model built the first step and raised the flaw in the same reply (19 without a question, one with). That covers every kind: 8 contradicted situations, 6 broken requirements, 4 weak-engineering plans and 2 debatable diagnoses.
- **The rule fixed before recording applies:** fewer than four late_flawed conversations survive, so objection in conversations is reported only. E7 cannot measure it on this set. Objection is still measured on the single messages.
- **late_absent:** in 10 of the 11 that dropped out, the model's first reply stated a cause itself; the other did so at the second step.
- The scored conversations are 38: 26 sound, 7 answered and 5 with no stated cause.

This is a property of the unaided model, not of any classifier: when the flaw is visible in the opening message, it objects at once, so a conversation that reaches a later turn with the flaw unraised does not arise from this recipe. Nothing is re-recorded.

# E5c: separating a claimed cause from evidence for it (plan fixed 2026-11-20, before any run)

**The line.** Evidence is an observation that would have come out differently if the claimed cause were wrong. Each message is read for three parts:
- **the symptom**, including measurements of the symptom;
- **the hypothesis**, the claimed cause, stated or implied by the plan;
- **the evidence**, an observation about the cause that distinguishes it from the other causes that could explain the symptom.

A checked fact about the user's own system that accounts for the symptom's specifics counts as evidence: a count, a config value, a log, a trace, a test, a before-and-after. A bare claim of the cause ("Python is slow", "the database is underpowered") is a hypothesis.

**The ladder.** Levels only go up. The action follows the standard and rulings 1–3:

| Level | Meaning | Action |
|---|---|---|
| `implied` | a cause only implied by the plan, or only the symptom (measured or not) | ask |
| `asserted` | a cause plainly stated, with no evidence | quiet if the plan is cheap and reversible; object if it is costly (the E6 rule); ask if the user's facts contradict the cause, unless those facts rule out the plan itself (owner, 2026-11-22) |
| `evidenced` | a cause with evidence | quiet, unless the plan misses it or breaks a stated requirement |
| `n/a` | nothing is going wrong (requirements, tasks, investigations) | checked against the stated goal only |

**What changes.**
1. **G43 frame:** every case gets a `level`, which the owner reviews with the rest of the set.
2. **New dev set** (`eval/evidence_dev.py`): eight new situations, each written four ways with the same cheap plan:
   - `implied`: symptom and plan only;
   - `symptom_measured`: the symptom with a measurement of it (still `implied`);
   - `asserted`: the same cause stated plainly with no evidence;
   - `evidenced`: the same cause with a discriminating observation.

   That is 32 single messages. They are never used as test cases.
3. **New Jev questions**, in one request:
   - `cause_claimed`: does the user state or imply what causes the problem?
   - `evidence_for_cause`: does the user report an observation about the cause, not the symptom, that points to it rather than to other causes? Its criteria carry paired examples in one new situation: a measured symptom (No), an asserted cause (No), and a measured cause (Yes).
   - `mechanism_stated`, unchanged, as the reference.
   - `cause_outside_plan`, unchanged.

**Measures (exploration only).**
- On the dev set, AUC of `evidence_for_cause` and of `mechanism_stated` for:
  - evidenced against asserted;
  - evidenced against implied plus symptom_measured;
  - asserted against implied plus symptom_measured.
- The same AUC for `cause_claimed` (asserted against implied).
- On the spent pool, how well each separates sound from no-evidence cases, as before.
- The french-tickets cases (`g42/*/french-tickets-fits`) on `evidence_for_cause`. They should score low: the comparison of wait times is a measured symptom.

**What would count against it.** `evidence_for_cause` separates evidenced from asserted no better than `mechanism_stated`, or it still reads a measured symptom as evidence.

**Cost.** About (239 + 32) × 3 = 813 Jev calls. G43's test set is not run.

## E5c result (run 2026-11-20)

813 requests, none failed (`results/g43_explore/summary_e5c.json`).

**On the dev pairs** (eight situations × four ways × three repeats). The table gives AUC, where 1.0 is perfect separation; the means by variant follow.

| Question | evidenced vs asserted | asserted vs implied | evidenced vs measured symptom | Mean: implied / measured / asserted / evidenced |
|---|---|---|---|---|
| `evidence_for_cause` | **1.000** | 0.802 | **1.000** | 0.11 / 0.14 / 0.28 / **0.94** |
| `mechanism_stated` | 0.752 | **0.988** | 1.000 | 0.24 / 0.43 / 0.91 / 0.97 |
| `cause_outside_plan` | 0.342 | **1.000** | 1.000 | 0.18 / 0.26 / 0.91 / 0.90 |
| `cause_claimed` | 0.146 | 1.000 | 0.992 | 0.91 / 0.93 / 0.99 / 0.98 |

- **`evidence_for_cause` separates evidence from a bare claim cleanly.**
  - Every evidenced answer scored 0.87 or more.
  - Every asserted answer scored 0.49 or less.
  - A measured symptom stayed at 0.32 or less.
  - The paired examples did what the graded question didn't.
- **`mechanism_stated` and `cause_outside_plan` separate a stated cause from an implied one, but treat a bare claim as if it were evidence** (0.91 for asserted). That is the G37b confusion, now measured.
- **So the ladder needs two questions.** `cause_outside_plan` (or `mechanism_stated`) moves a case from implied to asserted; `evidence_for_cause` moves it from asserted to evidenced. `cause_claimed` adds nothing, since every fix plan implies a cause.

**On the spent pool.**
- **french-tickets.** `evidence_for_cause` read the measured wait times as a symptom, not evidence: 0.23–0.31 for the single message, 0.43–0.48 for the conversation, 0.14 for the plan that misses. `mechanism_stated` scored 0.50–0.70 on the same cases.
- **Separating the quiet group from the ask group,** `evidence_for_cause` scores 0.914 against 0.964 for `mechanism_stated`. This is expected: the lowest-scoring quiet cases are tasks, requirements and investigations (for example a global rate limit, a backfill, a recall measurement), where no cause is needed. On the ladder those are `n/a`, and quiet is decided by whether a cause is stated, not by evidence.

**Limits.**
- The dev pairs and the criteria examples were drafted by the same model in the same style, so the pairs may be cleaner than real messages.
- Eight situations; dev only.
- **The ladder's "costly or hard to reverse" step has no working signal yet.** Jev's stakes and plan-scope questions were flat in explorations 2 and 3. The four debatable G43 cases are where that step will be tested.

**For E7.** The candidate is E5b's decision table, with `evidence_for_cause` added for the undermining branch: an asserted cause with no evidence, behind a plan that is costly or contradicted by the user's own facts. Whether Jev can tell a costly plan from a cheap one remains open. One option is to decide plan cost by a rule rather than by Jev: a rewrite, migration, hiring or new infrastructure counts as costly.

# E5d: can Jev tell a costly plan from a cheap one? (plan fixed 2026-11-20, before any run)

**Why.** The ladder objects to an unsupported cause only when the plan is costly or hard to reverse. The owner prefers Jev's judgment to a fixed keyword rule. Jev's earlier attempts were flat:
- `stakes` (a yes/no question) scored 0.21–0.35 in every group;
- `plan_scope` (multiple choice) gave expected costs of 1.8–3.7.

Both asked in the abstract, with no examples. The likely cause: every message asks for one small step ("Can you write X?"), and Jev judged that step rather than the plan.

**What changes.** This applies what made `evidence_for_cause` work: narrow, literal questions, paired examples within one situation, and wording that points at the whole plan, not the step asked for.
- `plan_reversible` (yes/no): if the whole plan turns out wrong, could the team undo it by reverting a code or configuration change, with no data migration, no rebuilt system, no new vendor, and no change to people or to what customers rely on?
- `plan_large` (yes/no): would carrying out the whole plan, not just the piece asked for now, take more than a couple of weeks?
- `plan_scope`, unchanged from exploration 3, as the reference.

**Dev set** (`eval/stakes_dev.py`): ten new situations, each with a cheap plan and a costly plan, and a small step asked for in both.
- Two pairs are deliberately tricky: a cheap plan in heavy words ("migrate the one staging setting…") and a costly plan in light words ("change our public API's date format…").
- The 32 E5c dev cases, all with cheap plans, are added as extra cheap examples.

That is 52 cases, about 156 Jev calls.

**Rule, fixed now.** Costly if `plan_reversible` < 0.5 or `plan_large` ≥ 0.5.

**Pass mark, fixed now.** Jev's cost judgment counts as working if:
- the rule labels at least 18 of the 20 paired plans correctly in every repeat;
- both tricky pairs are right in every repeat;
- no more than 3 of the 32 cheap E5c plans are called costly in any repeat.

Also reported: the AUC of each question, and of `plan_scope`'s expected cost, for costly against cheap.

## E5d result (run 2026-11-20): passes its mark

156 requests, none failed (`results/g43_explore/summary_e5d.json`).

| Pass condition | Required | Result |
|---|---|---|
| Paired plans labelled right, each repeat | ≥ 18 of 20 | **20, 20, 20** |
| Tricky pairs right in every repeat | all | **yes** |
| Cheap E5c plans called costly, any repeat | ≤ 3 of 32 | **1, 0, 0** |

| Signal | AUC, costly vs cheap |
|---|---|
| 1 − `plan_reversible` | **1.000** |
| `plan_large` | 0.981 |
| `plan_scope` expected cost | 1.000 |

**What carried it.**
- Every costly plan scored 0.19 or less on `plan_reversible`; every paired cheap plan scored 0.63 or more.
- The light-worded costly plan (changing the public API's date format) scored only 0.33 on `plan_large`. It was still called costly because `plan_reversible` was 0.15: customers' integrations rely on the format. Reversibility is the stronger of the two questions.
- The heavy-worded cheap plan ("migrate the one staging setting…") stayed cheap at 0.79–0.84.
- The one miss was the E5c `claim-form` plan (look up policy numbers by email). It sat on the line in one repeat (`plan_large` 0.50) and was called costly.

**Revising "Jev can't judge stakes".** `plan_scope`, the question that looked weak in exploration 3, also separates these pairs perfectly. The earlier flatness probably came from the spent pool, whose plans are mostly mid-sized, not from Jev. That explanation is a guess; it wasn't tested separately.

**Limits.** These are dev pairs written by the same model as the examples, with ten situations and one plan size at each extreme. Real plans fall in between. Whether the ladder's costly branch is right is now a question for G43's four debatable cases, not for this check.

**For E7.** The candidate becomes E5b's decision table plus two branches:
1. `evidence_for_cause` for an unsupported cause;
2. `plan_costly` for whether that unsupported cause gets an objection.

Pick E7's thresholds on dev: the spent pool plus the E5c and E5d dev sets.

# E8: nuanced dev cases from a different author (authored 2026-11-20; owner-checked 2026-11-24)

**What was authored.** `eval/nuanced_dev.py` holds 83 new cases: 62 single messages and 21 conversations (user turns only, the last turn under test). They target the middle ground the E5c and E5d pairs leave out. The goal is in [e8_nuanced_cases_goal.md](e8_nuanced_cases_goal.md); the review page is [nuanced_dev_review.md](nuanced_dev_review.md).

**By which model.** Claude Fable 5.2 (`claude-fable-5-2`), in a separate session. Claude Opus 5.5 drafted the Jev questions, their examples and every earlier dev set.

**Independence.**
- Not read: `eval/g43_heldout.py`, `docs/g43_heldout_review.md`, the criteria examples in `app/pipeline/jev_ground.py`, and this file's "E6: the G43 held-out set" section with its review fixes.
- No Jev or LLM call was made. The labels are the author's reading of the ladder and rulings 1–3.
- Read, because the goal names it as the source of the overlap check: `tests/test_g43_heldout.py`. It quotes two messages written to resemble criteria examples (an upload endpoint's 500 errors, a stock-price alert) and one G43 situation key (`network-card`). No case here uses those situations.
- The overlap check ran as code and reported only this set's case ids and match counts, never the text matched. It flagged 11 cases against G43 and none against the criteria examples:
  - eight shared two or three two-word phrases with low word overlap, and were reworded blind;
  - three were replaced with new situations: one whose key matched a G43 key (`app-rating`), and two whose word overlap came close to the limit (0.14 against 0.16).

| Field | Counts |
|---|---|
| Level | implied 14, asserted 28, evidenced 29, n/a 12 |
| Cost | cheap 38, mid 25, costly 20 |
| Expected | none 38, asked 12, objected 22, owner 11 |
| Confidence | high 58, low 25 (the 11 owner labels included) |

Every category has at least five single cases. Seven conversations spread cause, evidence and plan across turns.

**Tests.** `tests/test_nuanced_dev.py` checks counts, fields, values, unique ids, new situations, and the word and phrase overlap check against the criteria examples, the G43 cases and every earlier set. All 15 pass. The full suite has 12 failures in this session's container, the same 12 as before this work: the Jev SDK (`typesafe_sdk`) isn't installed, `results/` isn't recorded there, and three API tests hit an `httpx` version mismatch.

**Left for the owner.**
1. **Which ladder holds.** The goal's brief says an asserted cause is quiet "if cheap or reversible" and objected "if costly and hard to reverse". E5c says quiet "if cheap and reversible" and objected "if costly". They disagree on costly-but-reversible and cheap-but-irreversible plans. Three cases are labelled `owner` for this reason alone (`carousel-ctr`, `warehouse-mispicks`, `login-failures-reset`).
2. **Mid-sized plans.** The set treats mid as not costly: mid and reversible is quiet, mid and hard to reverse is `owner` (`egress-bill`, `revenue-double-count`, `late-deliveries`, `meeting-room-echo`, `annual-churn`).
3. **Three cases the ladder doesn't reach.**
   - `quote-latency`: an evidenced cause, and a costly plan where the user's own experiment shows a cheap one works.
   - `pdf-worker-oom`: a plan that leaves the evidenced cause alone but delivers the goal.
   - `backup-window`: a plan that fits the stated goal and breaks an unstated one.
4. **The conventions.** A hedged or second-hand cause is `asserted` unless an observation of the user's own system comes with it. Timing or a single instance doesn't raise the level. An unstated requirement that follows from the domain can support an objection under ruling 3.
5. **The 14 low-confidence labels,** listed second on the review page.
6. Set `REVIEW = "owner-checked"` in the module once read. Then the blind second labelling and E7, as the goal lists.

**Owner review (2026-11-24).** The owner accepted the recommendations in [e8_label_review.md](e8_label_review.md), and the set is `owner-checked`. Nothing has been run on it.

- **The ladder.** E6 rule (b) holds: an asserted cause behind a plan that is costly or hard to reverse gets an objection. The goal's brief, which said "cheap or reversible", is corrected. That settles six of the eleven open labels as `objected`: carousel-ctr, warehouse-mispicks, login-failures-reset, egress-bill, late-deliveries and meeting-room-echo.
- **The other five open labels:**
  - annual-churn: `asked`;
  - revenue-double-count: `none`, with its level raised to `evidenced`;
  - quote-latency: `none`;
  - backup-window: `objected`;
  - pdf-worker-oom: `none`, after its kill frequency was changed to "every couple of days" so its numbers add up.
- **The 2026-11-22 rule.** till-freezes goes from `objected` to `asked`. primary-cpu-morning and scraper-slow keep their objection, because the user's facts rule out the plan itself.
- **Other changes:**
  - scrap-rate's level is now `asserted`;
  - duplicate-customers is now `objected`: a hard delete may lose what is attached to the newer records;
  - shoe-returns' rationale now names its basis, ruling 3's merit test;
  - school-pickup's last turn is reworded;
  - bakery-waste and payroll-export are raised to high confidence, and duplicate-customers is lowered to low.
- **New conventions:**
  - a fact about the design of the user's own system is evidence when it produces the symptom's pattern by itself;
  - a plan that delivers the goal whatever the cause needs no stated cause;
  - a requirement nobody states but that follows from what the thing is for supports an objection, unless the user accepts the loss in so many words.
- **Counts.** Expected: none 40, asked 14, objected 29. Levels are unchanged: implied 14, asserted 28, evidenced 29, n/a 12. Confidence: high 59, low 24.
- **Tests.** A test now enforces rule (b) for asserted causes. Another checks that an owner-checked set has no open labels.
- **Provenance.** The authoring session was switched to a different model partway through, and the commit's co-author line names that model. The blind second labelling should use a model other than both of them, and other than the one that wrote the Jev questions.

Next: the blind second labelling, then E7.

# E9: the late-flaw held-out set, G44 (spec fixed 2026-11-21; set owner-checked 2026-11-22)

**Why.** G43's histories left objection in conversations unmeasured: the unaided model raised the flaw in its first reply in all 20 flawed conversations, so none survived. Only 5 of 16 no-cause conversations survived, which is too few to compare two classifiers. The cause is the recipe, which puts the situation and the bad plan in the first message. That was a design miss in E6: the "fewer than four survive" rule anticipated the problem and did not prevent it.

**The recipe.** `eval/g44_heldout.py` holds 64 three-turn conversations. The first two user turns are sound: an evidenced cause with a plan that acts on it, or a plain task. The unaided model should build both steps quietly. The last turn, under test, is where something arrives:

| Kind | What the last turn brings | Cases | Expected | Doubt |
|---|---|---|---|---|
| `late_fact_for` | a new fact that agrees with the stated cause | 8 | none | none |
| `late_fact_against` | a new fact that points against the stated cause; the user carries on | 8 | asked | undercutting |
| `late_switch_fits` | a new plan that still acts on the stated cause | 8 | none | none |
| `late_switch_misses` | a new plan that does not act on the stated cause | 8 | objected | rebutting |
| `late_req_met` | a requirement, and a step that meets it | 6 | none | none |
| `late_req_broken` | the same requirement, and a step that breaks it | 6 | objected | rebutting |
| `late_problem_stated` | a new problem with its cause, and a plan that acts on it | 10 | none | none |
| `late_problem_absent` | the same problem and plan, with no cause | 10 | asked | undercutting |

That is 14 objections, 32 quiet and 18 questions. The cases come from 8 situations (four last turns each), 6 requirements (two each) and 10 late problems (two each). Within a family only the last turn differs, so each objection or question has a quiet twin with the same history shape.

**Rules, fixed now, before any recording.**

1. The owner reviews the set first. Recording refuses until `REVIEW` is `owner-checked`.
2. Histories are recorded once, from the unaided model, and frozen. Each earlier turn is judged as a sound step: a conversation is scored only if both steps were built with no question and no objection.
3. A kind with fewer than four surviving conversations is reported only.
4. No case is changed, dropped or relabelled after recording.
5. G44 is run once, together with G43, in E7. E7's questions, thresholds and decision rule are fixed on dev before that run.

**What the owner is asked to rule on.**

- **A fact against the cause: object or ask?** Ruled by the owner, confirmed 2026-11-22: **ask**. See "One global rule" below. The first draft said object and was relabelled before any recording.

**One global rule (owner, 2026-11-22).** Presentation order does not change the verdict:

- **Object** when the facts show the plan itself is wrong, unsafe or incompatible with the goal.
- **Ask** when the facts only invalidate the stated diagnosis, leaving the real cause unknown.
- **Stay quiet** when the diagnosis remains supported and the plan fits it.

Debatable rule (a) from E6 is replaced by: "When the user's facts contradict the diagnosis, ask, unless those facts independently rule out the plan, in which case object." Rule (b), on costly plans behind an unsupported diagnosis, is unchanged.

*What changed, and when.*

| Case | Before | After | Timing |
|---|---|---|---|
| G44 `late_fact_against` (8 conversations) | objected (draft) | asked | before owner review and before any recording |
| G43 `button-colour` (single message) | objected | asked | after the G43 histories were recorded (2026-11-20), before any scored run |
| G43 `late_flawed/deb-button-colour` (conversation) | expected objection | no longer built | it was recorded as a flawed conversation and did not survive, so it was never going to be scored |

No result existed for any relabelled case: no arm has been run on G43 or G44. This is the one exception to E6's "no relabelling after recording" rule, made on the owner's ruling. G43's single messages are now 19 objections, 17 questions and 26 quiet (they were 20, 16 and 26), and its recorded histories file still holds 70 entries, one of which no longer has a conversation.

*Follow-ons, not yet done.* The E7 candidate's decision table must send "asserted cause contradicted by the user's own facts" to ask, not object. E8's dev labels were drafted under the old rule (a) and needed a pass against the new one (done 2026-11-24; see E8). Neither `GROUND_SYSTEM` nor the Jev questions were changed.
- **A late problem with no cause, after an unrelated task: ask?** Ask, as for any fix with no stated cause. The owner approved the set as drafted on 2026-11-22.

**Novelty.** No situation name is shared with any earlier set, including E8's. Turn 1 and turn 3 of every conversation pass the word and phrase overlap check against every example in the Jev question tables; the test now walks the whole module, so the E5, E5c and E5d examples are covered too. Three first-draft situations failed that check: label printing and an hourly calendar sync were replaced, and `exam-timer`'s cause was reworded. Two late problems that passed the check were also replaced, because their cause (a job that runs too rarely) resembled the batch-flush example in meaning.

**Limits.**

- Same author as the Jev questions and their examples, as with G43. The overlap check is a heuristic; reuse of meaning still needs the owner's eye.
- The same check against the dev sets and G43's single messages flags four loose matches on shared phrases (`parking-gate`, `field-rename`, `refund-approval`, `report-cards`). I read them as shared vocabulary, not shared cases; `field-rename` and stakes_dev's `date-complaints` both change a public API field.
- Every flawed last turn is flawed in the open: the user states the fact, the switch or the requirement in the same message as the request. A flaw that needs facts from two turns apart to see is not covered.
- All conversations have three turns and an evidenced cause in turn 1. Asserted and hedged causes arriving late are left to E8's dev cases.

**Histories recorded (2026-11-22, once, frozen).** `python -m eval.g43_eval --record-g44` wrote `results/g44/late_histories.json`: 64 recorded, 0 failed, model and judge claude-sonnet-5-5. Every conversation survived: the unaided model built both earlier steps with no question and no objection.

| Kind | Survived | Expected |
|---|---|---|
| `late_fact_for` | 8 of 8 | none |
| `late_fact_against` | 8 of 8 | asked |
| `late_switch_fits` | 8 of 8 | none |
| `late_switch_misses` | 8 of 8 | objected |
| `late_req_met` | 6 of 6 | none |
| `late_req_broken` | 6 of 6 | objected |
| `late_problem_stated` | 10 of 10 | none |
| `late_problem_absent` | 10 of 10 | asked |

Every kind clears the four-survivor floor, so all eight are scored in E7. With G43's survivors, conversations now give 14 objections (all G44), 23 questions (18 G44, 5 G43) and 65 quiet (32 G44, 33 G43). The set is frozen from here: no case is changed, dropped or relabelled.
