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

# G37: does the check survive a plan stated earlier? Decision: STOP (2026-11-16)

**Question.** In a chat the plan is stated once and later requests are short ("Can you write the migration?"). Does the grounding check still stay quiet, ask, or object correctly at that later request?

**Setup.** 32 conversations from 15 existing proposals (`eval/multiturn_dataset.py`, owner-checked). The user states the situation and plan and asks for two earlier build steps, then makes the request under test. The assistant's answers to the earlier steps were generated once by the unaided model and frozen (`results/multiturn/late_histories.json`); nothing in a conversation is scripted. A conversation is scored only if those recorded answers went along with the plan: built the step, no question about the cause, no objection. Both arms then answered the final turn on the same history. Model, classifier and judge: `claude-sonnet-5-5`; judge at low effort. Marks, the survival rule and the decision rule were confirmed by the owner before any run.

## Result

| Scenario | Drafted | Survived | Unaided | Check, run 1 (as merged) | Check, run 2 (conversation in view) | Mark |
|---|---|---|---|---|---|---|
| Sound plan: help, no question, no objection | 6 | 6 | 6 of 6 | 6 of 6 | 6 of 6 | 80%: met |
| No cause given: one question before building | 13 | 6 | 0 of 6 | 0 of 6 | **4 of 6 (67%)** | 75%: **missed** |
| Flawed plan: objection before building | 9 | 0 | n/a | n/a | n/a | not scored |
| Question answered: no second question | 4 | 4 | 0 repeats | 0 repeats | 0 repeats | no mark |

Zero failed calls in either run.

## What happened

- **Run 1 confirmed the check is blind on a late request (H1 held).** It read "Can you write the migration?" alone, classified it as a task with nothing to check in all six no-cause conversations, and the model built.
- **The planned change** gives the classifier and the premise check the earlier turns plus one rule (evidence in any earlier user turn counts as stated). It applies only under `ASSUMPTION_ACTION=ground`; a single message is sent exactly as before.
- **Run 2: 0 of 6 became 4 of 6.** In the four, the model withheld the build and asked. The two misses (`snd-08`, `snd-10`) are plans that add a capability (multi-factor authentication, contract tests); the classifier called the late request a task, not a fix, so it did not ask. Sound plans stayed at 6 of 6 and the answered conversations were not asked again.
- **No flawed conversation reached the late turn (H2 held).** At turn 1 the unaided model raised the flaw in all nine: five before building, four after. Silent building of a visibly flawed plan across two turns did not occur once.
- **Seven of the 13 no-cause conversations also dropped out.** In each the model built the step and added a caveat that named the real cause, usually after the build. A caveat counts as speaking up under the survival rule.

## Decision: stop

The confirmed rule: a miss on the no-cause scenario after the planned change means stop. 4 of 6 is under 75% (5 of 6 was needed). So the multi-turn check is not shown to meet its mark; the single-message result (G36) is what ships, with this limit stated. No further tuning under this goal.

## Honest limits

- **The mark was missed by one conversation out of six.** With six scored conversations one answer is 17 points. This run cannot tell "works about two times in three" from "works five times in six". It is a stop under the rule, not evidence the approach fails.
- Six scored no-cause conversations and six sound ones, from 15 proposals in 9 situation families. Not independent, and too few to estimate a rate.
- The objection scenario was not tested at all in the late-turn setting, because no conversation qualified.
- Histories are one sampling from one model. A different sampling could change which conversations survive.
- Turn 1 is itself a build request, so in real use a working check would already have fired there. The surviving conversations model a session where it was absent.
- Distance and having-already-built vary together here; the run cannot separate them.
- Spend was not measured. Answer output alone was roughly $1; with inputs, classifier and judge calls the two runs are estimated at a few dollars.

## What it does show

- Reading only the latest message, the check does nothing on a late request. That part is certain (0 of 6, and the classifier's own labels show why).
- With the conversation in view it asks on most late no-cause requests without starting to question sound plans or re-asking answered ones.
- On this model, visible flaws are raised at the first build request, with or without the check. The gap that remains unaided is ordering (four of nine came after the build) and never asking, not silence.

