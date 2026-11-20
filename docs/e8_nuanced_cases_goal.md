# E8: nuanced dev cases, authored by a different model

**Status:** ready. Written 2026-11-20. To be done in a separate session by a model other than Claude Opus 5.5, which drafted the Jev questions, their examples and every dev set so far.

## Why

**The problem.** E5c and E5d passed on dev cases written by the same model, in the same style, as the Jev questions' own examples. The questions are the evidence question (`evidence_for_cause`) and the cost questions (`plan_reversible`, `plan_large`). Those cases are clean extremes:
- a bare claim against a measured cause;
- a one-line config change against a rewrite.

Real messages fall in between. The results may partly reflect one author's style, not the distinctions themselves.

**What this goal builds.** A dev set from a different author that targets the middle cases. E7 then chooses Jev's thresholds on cases the questions weren't written alongside.

Background, in this order:
1. `docs/v3_spike.md`: the sections "A formal frame", "E5c", "E5d" and their results.
2. `docs/g42_jev_diagnosis.md`: the owner's three rulings.
3. `eval/evidence_dev.py` and `eval/stakes_dev.py`, for format only.

## Independence rules

- **Don't read the G43 test set:** `eval/g43_heldout.py` and `docs/g43_heldout_review.md`. It's held out, and this set must not be shaped by it. The overlap test below checks against it mechanically.
- **Don't read the Jev criteria examples** in `app/pipeline/jev_ground.py`. Don't change that file or any question.
- Make no Jev or LLM calls to label or tune cases. This goal is authoring and review only.

## Scope

**In scope.** About 60 single messages and 20 conversations (user turns only, in the G37 shape), in new situations. The categories:

| Category | What makes it nuanced | Example of the kind (write your own) |
|---|---|---|
| **Partial evidence** | An observation that narrows the cause but doesn't single it out: timing that correlates, one instance, a single customer report | "It started the day we upgraded the driver" |
| **Hedged cause** | A stated cause with doubt attached | "We think it's probably the cache" |
| **Second-hand cause** | A vendor, colleague or forum said so | "Our provider's support says it's our retry rate" |
| **Before-and-after evidence** | Evidence written as an experiment, not a measurement | "We turned the job off for a day and the errors stopped" |
| **Evidence for a different cause** | Real evidence, but the plan acts on something else | A trace pins it on X; the plan changes Y |
| **Two contributors** | Evidence for one of two causes; the plan addresses one | Both are named; only one is measured |
| **Mid-sized plans** | Between cheap and costly: a schema change, a new queue, swapping an SDK behind an interface | |
| **Costly but reversible** | A big plan behind a flag, or easy to roll back | |
| **Cheap but irreversible** | A small action that can't be undone | Deleting old data, emailing every customer, a public announcement |
| **Investigation plus fix** | Investigate, then change something either way | "Log it for a day, then add retries" |
| **Implicit requirement** | The goal follows from the domain rather than being stated | |
| **Real-world style** | Long messages, pasted logs, bullet lists, code, typos, several asks | |
| **Spread across turns** | Cause, evidence and plan arrive in different user turns | Conversations only |

**Out of scope.**
- Changing any question, rule or threshold.
- Running anything against Jev or the LLM.
- Editing the G43 set.

## Format

Write the set in `eval/nuanced_dev.py`, following `eval/evidence_dev.py`. Each case carries:

| Field | Meaning |
|---|---|
| `id`, `category`, `family` | Identifiers |
| `query` | The message (single cases) |
| `user_turns` | The user's turns (conversations) |
| `frame` | `R` (what the plan must deliver), `D` (what the user states), `S` (the plan), `defeater` (none / undercutting / rebutting / undermining) |
| `level` | implied / asserted / evidenced / n/a, as defined in "E5c" |
| `cost` | cheap / mid / costly, plus `reversible`: true or false |
| `expected` | none / asked / objected, under the ladder and the owner's rulings |
| `rationale` | One sentence on why the level, cost and expected verdict are what they are |
| `confidence` | high or low, from the author. Low marks a case the owner should look at first |

The ladder in brief:

| Level | Action |
|---|---|
| `implied` | ask |
| `asserted` | quiet if cheap or reversible; object if costly and hard to reverse, or if the user's own facts point against the cause |
| `evidenced` | quiet, unless the plan misses the cause or breaks a stated requirement |
| `n/a` | checked against the stated goal only |

Where the rules leave a case genuinely open, label it `"owner"` with both readings in `rationale`. Don't force it.

## Deliverables

1. `eval/nuanced_dev.py`: the cases.
2. `tests/test_nuanced_dev.py`, which checks:
   - counts per category (at least 4 each);
   - required fields;
   - valid values;
   - unique ids;
   - no situation shared with any earlier set (`g41_heldout`, `g42_heldout`, `g43_heldout`, `multiturn_heldout`, `proposals_dataset`, `evidence_dev`, `stakes_dev`);
   - the word and phrase overlap check from `tests/test_g43_heldout.py`, run against the criteria examples and the G43 cases, as code only, without reading them by eye.
3. `docs/nuanced_dev_review.md`: a review page generated from the module, grouped by category. Low-confidence cases and `"owner"` labels come first.
4. A short section in `docs/v3_spike.md` saying what was authored, by which model, and what is left for the owner.

## Acceptance

- **Coverage.** Every category in the scope table has at least four single cases. At least 20 conversations, with at least five spread across turns.
- **Balance.** Each of implied, asserted and evidenced has at least 12 cases. Each of cheap, mid and costly has at least 10.
- **Completeness.** Every case has a rationale. Every `"owner"` label states both readings.
- **Tests.** `python -m pytest -q` passes, including the new overlap test.
- **Nothing else touched.** No file outside the deliverables changes, apart from the new section in `docs/v3_spike.md`.

## After this goal (not part of it)

1. The owner reviews the set and settles the `"owner"` labels.
2. A second, different model labels the set blind. Agreement is reported per field as a reliability check on the labels.
3. E7 uses the set as dev when it picks thresholds.
