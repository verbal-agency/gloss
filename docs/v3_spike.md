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
