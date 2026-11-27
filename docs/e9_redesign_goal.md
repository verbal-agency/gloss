# E9: narrower Jev questions after E7 (dev only)

**Status:** drafted 2026-11-27; the wordings were simplified and the owner approved them the same day. Run on dev the same day: no variant beat E7 (`docs/v3_spike.md`, "E9 result").

## Why

E7 found that Jev alone can't replace the LLM classifier ([v3_spike.md](v3_spike.md), "E7 result"). E7h then found that E7's candidate matches the LLM when about 30% of its decisions go to the LLM ("E7h"). The projects in [jev_projects_survey.md](jev_projects_survey.md) ask Jev narrow questions and keep the broad judgment in code.

E9 tests whether narrower questions let Jev decide more turns on its own, so fewer go to the LLM.

## Where E7 lost

On held-out, E7's misses by table row:
- **Rows 3 and 5, `achieves_goal`:** about 29 misses. It objected to sound plans late in conversations, and stayed quiet on some plans that miss.
- **Rows 5 and 6:** about 15 misses. The cause was absent, but `link_stated` or `evidence_for_cause` fired.
- **Row 1, `investigation`:** 9 misses on held-out and 18 on dev, all confidently wrong, so no fallback band catches them. On dev it fired on two kinds of plan:
  - a detector, benchmark or grader built as the product (`full/mis-01`, `mis-04`, `inf-01`, `inf-15`);
  - an investigation run next to a fix already committed to (`freezer-alarms`, `peak-store-slow`).

## The changes

Each change is scored alone and with the others. Every other part of E7's candidate stays as it is: its questions, its chosen configuration, and its moved question.

**A. `only_investigation` replaces `investigation` in row 1.**
> Is the user's plan only to find out what is causing a problem, for example by measuring, logging or testing, with no fix chosen yet? Answer no if they have also chosen a fix. Answer no if what they are building is itself a measuring tool, like a detector or a benchmark.

**B. One `cause_level` choice replaces `link_stated` and `evidence_for_cause` in rows 5 to 7.**
> How well does the user back up the cause their plan acts on? Judge only what the user says, not whether they are right. If they name two causes, judge the one the plan acts on.

- **none:** the user gives no cause, or nothing is going wrong. Naming the error is not a cause.
- **implied:** only the plan hints at a cause. The user never says what is happening now.
- **asserted:** the user states the cause but gives nothing to back it up. Saying they researched it doesn't count.
- **evidenced:** the user backs the cause with something they saw, like a measurement, log or test, or a fact about their setup that explains the exact symptom. Measuring only the symptom (how often, how bad) doesn't count.

How the table reads it:
- row 5 fires when P(evidenced) ≥ 0.5;
- row 6 fires when P(asserted) + P(evidenced) ≥ 0.5;
- otherwise row 7.

Why a choice: the benchmarking paper found choice probabilities close to calibrated, while many yes/no questions over one state over-predict "yes".

**C. The broad `achieves_goal` goes.**
- **Row 3** (nothing going wrong) objects only when `plan_ruled_out` ≥ t_ro: the user's own facts show the plan can't deliver. This follows the owner's convention of 2026-11-25: an unstated requirement supports an objection only when the plan breaks it, or the user's own facts show it would.
- **Row 5** (evidenced cause) objects when the new question is under 0.5:
  > Does the plan change the thing the user's evidence points to? Don't judge whether the change will be enough. Answer yes if there is no evidence.

**Not changed: the input.** Dev conversations are three user turns and about 3,700 characters, so there is little to trim.

**Examples.** Each question has paired examples, in situations used in no dev or held-out set and no other question: a choir's recordings, a pottery kiln, a village hall's heating. `tests/test_e9_questions.py` checks them against every dev text, G43 and G44 included, and against every other question's examples.

**Thresholds.** The new ones are fixed at 0.5. There is no grid, to keep fitting to dev small.

## The run

- **The questions:** the three go in one request of their own, three repeats, on all 384 unique dev cases. That is 1,152 Jev requests, well under a dollar.
- **E7's answers are reused,** merged repeat by repeat.
- **Each response's `model` field is stored.** The run stops if more than one version answers.
- **In the app,** each turn would make three Jev requests, in parallel.

## Scoring

For each variant (E7, A, B, C and ABC), on dev:
- **Jev alone:** cells within tolerance of the LLM, and utility, as E7 scored them;
- **with the fallback band** of E7h, at each band from 0 to 0.30: the share of decisions sent to the LLM, cells and utility;
- **parity:** the smallest band where every cell is within tolerance and utility is within 0.02 of the LLM's. A lower fallback rate at parity is better.

## What decides next

- **If ABC reaches parity with a clearly lower fallback rate than E7's 30%,** it goes to the new held-out set (G45). The set is written and blind-checked before any tuning, as G43 and G44 were.
- **If not,** E7's candidate with the fallback goes to G45 instead.
- **Either way,** the band and the rule for choosing it are fixed before G45 runs.

## Limits

- **One author.** The same model wrote the questions, this spec and the E7h analysis.
- **Fitted on dev.** A and C were shaped by dev and held-out misses. G45 is where they are really tested.
- **Replayed fallback.** It uses the LLM's recorded answers, not live calls.
