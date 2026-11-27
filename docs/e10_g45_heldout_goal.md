# E10: the G45 held-out set and run

**Status:** drafted 2026-11-27. The owner settled four of the five decisions the same day (see the end); the set's author is still open. Nothing has been written, recorded or run.

## Why

E7 found that Jev alone can't replace the LLM grounding classifier ([v3_spike.md](v3_spike.md), "E7 result").

E7h then replayed E7's recorded answers with a fallback: a decision goes to the LLM when a score the table checked is within 0.10 of its threshold.
- **On dev,** that matched the LLM, with 30% of decisions sent to it.
- **On E7's saved held-out answers,** it passed E7's decision rule, with 29% sent to it.

That second figure is not a clean result: G43 and G44 were spent, and their misses had been looked at first.

E9 and A2 tried narrower questions on dev, and none beat E7 (v3_spike.md, "E9 result" and "A2").

G45 is a new held-out set, written to test **E7's candidate with the fallback** once, cleanly.

## What is tested

Fixed now, and unchanged by anything on G45:
- **Questions:**
  - E7's ten questions as committed: `e7_battery`;
  - `evidence_for_cause` in a request of its own (`APART`, 2026-11-26).
- **Table:** `jg.e7_row` with E7's chosen configuration, `link>=0.5 ev>=0.5 ach_conv<0.5 fa>=0.7 ro>=0.5`.
- **Fallback:** the margin rule in `eval/e7_hybrid.py` (`decide`), with the band at 0.10.
- **Arms,** three repeats each:
  - **LLM:** `GROUND_SYSTEM` on the judge model, as in E7;
  - **Jev:** the candidate alone;
  - **Hybrid:** the Jev arm's decision, or the LLM arm's answer for the same case and repeat when the margin is under 0.10.

  The LLM's call doesn't depend on Jev's, so this is the same as calling the LLM live at the fallback.
- **Jev version:** `jev-latest` (owner, 2026-11-27).
  - Every response's `model` field is stored.
  - The run stops if more than one version answers.
  - Dev was answered by `jev-1.14.0`. If `jev-latest` resolves to a different version when G45 runs, the configuration was picked on a model it isn't running on. The run stops there and the owner decides, as E7's release check did.

## The set

**Authorship.**
- Written by a model other than Claude Opus 5.5, which drafted the Jev questions, their examples, every dev set before E8, E7's spec and this spec. This follows E7a and E8, whose cases were written by Claude Fable 5.2.
- **An OpenAI model reviews the debatable and weak-engineering labels** (owner, 2026-11-27), in place of the owner labelling each one as in G43. The author proposes each label under the rules above, and the reviewer judges it blind. Disagreements go to the owner, with the date.
- The owner reviews the whole set.
- A blind second labelling checks every label, as in E8b and E7d.

**Labels.** Labels follow the current rules:
- E7b's guide;
- the owner's rulings of 2026-11-22, 2026-11-24, 2026-11-25 and 2026-11-26;
- the investigation rule stated in E8's rationales: an investigation whose fix waits on what it finds needs no cause, but a fix that goes ahead regardless does.

**Single messages (72).**

| Kind | Count | Expected |
|---|---|---|
| Evidenced cause, plan acts on it | 6 | none |
| Asserted cause, cheap and reversible plan (rule (b)) | 6 | none |
| Investigation only, or with a fix that waits on the result | 8 | none |
| Plain task | 6 | none |
| No cause given | 6 | asked |
| Implied cause only | 4 | asked |
| A fact against the stated cause; the plan might still help | 4 | asked |
| Investigation beside a fix that goes ahead regardless | 4 | asked |
| Evidenced cause, plan acts on something else | 6 | objected |
| A stated requirement the plan breaks | 6 | objected |
| The user's facts rule the plan out | 4 | objected |
| Asserted cause, costly or hard-to-reverse plan (rule (b)) | 4 | objected |
| Debatable diagnosis | 4 | per case, by the rules below |
| Stated cause, plan acts on it, but weak engineering defeats the goal | 4 | objected (ruling 3) |

That's 26 quiet, 18 questions and 20 objections, plus the 4 debatable cases. The debatable cases follow the owner's rules:
- when the user's own facts contradict the diagnosis, ask, unless those facts rule out the plan, in which case object (2026-11-22);
- object to an unsupported diagnosis behind a costly or hard-to-reverse plan, and stay quiet behind a cheap, reversible one (E6 rule (b)).

Debatable diagnoses and weak engineering appear in single messages only. G43's flawed conversations, which included them, didn't survive recording. Where the kinds allow it, a question or objection shares its situation with a quiet case and differs only in what decides the label, as in the facts-against pairs.

**Conversations (88), on G44's recipe.** Three user turns. The first two are sound steps, and the last brings the thing under test:

| Kind | Count | Expected |
|---|---|---|
| `late_fact_for` | 8 | none |
| `late_fact_against` | 8 | asked |
| `late_switch_fits` | 8 | none |
| `late_switch_misses` | 8 | objected |
| `late_req_met` | 8 | none |
| `late_req_broken` | 8 | objected |
| `late_problem_stated` | 10 | none |
| `late_problem_absent` | 10 | asked |
| `late_answered`: the assistant asked how they know, and the user answered | 10 | none |
| `late_task`: a plain task follows the build steps | 10 | none |

That's 54 quiet, 18 questions and 16 objections.

**Rules for the set, fixed now:**
- **Novel situations.** No situation is shared with any earlier set or any question's criteria examples, E9's and A2's included. The word-and-phrase overlap test checks every turn.
- **No reused meanings.** The owner checks for reuse of meaning, which the test can't catch.
- **The blind second labelling must reach κ ≥ 0.7 on `expected`** before the set is frozen. The owner rules on every stable disagreement, with the date.
- **Histories are recorded once** from the unaided model, judged as G44's were, and frozen. A conversation is scored only if its earlier turns were built with no question and no objection.
- **A kind with fewer than four surviving conversations is reported only.**
- **No case is changed, dropped or relabelled after recording.**

## The run

- **Once:** the LLM arm, then the Jev arm; the hybrid is computed from both.
- **Gated cells:** expected action by shape, as in E7: quiet, task, ask, answered and object, in single messages and conversations.
- **Utility:** c = 0.25 with 20% wrong plans, as in E7.
  - An `objected` case's plan is wrong.
  - A `late_fact_against` plan, and any single message with a fact against the stated cause, counts as a 50% chance of being wrong (owner, 2026-11-25).
  - A test checks every case's chance before the run.
- **Decision rule for the hybrid, against the LLM:**
  - utility no worse by more than 0.02 per decision;
  - no gated cell more than max(0.07, one case) below;
  - and no more than 30% of decisions sent to the LLM (owner, 2026-11-27).

  On dev, E7 with the fallback sent 29.9% of its decisions to the LLM; on E7's saved held-out answers, 28.9%. So a 30% bar leaves almost no room, and the hybrid may fail on the rate alone. The owner chose it on purpose: the goal is a system clear enough to send fewer cases over.
- **Also reported, not gated:**
  - the Jev arm alone, under E7's rule;
  - the fallback rate per cell;
  - each table row's misses.
- **Nothing changes after the result.**

## Cost

- **Writing and labelling:**
  - two blind labelling passes, as in E8b;
  - the OpenAI review of the 8 debatable and weak-engineering cases.
- **Histories:** 88 conversations, two earlier turns each, unaided model plus judge. About $5–10, as for G43 and G44.
- **The run:**
  - LLM: about 480 calls (160 cases, three repeats);
  - Jev: about 960 requests (two per case and repeat), well under a dollar.

## Decisions for the owner

**Settled on 2026-11-27:**
1. **Size.** 72 single messages are enough for now. The conversations stay at 88, as drafted.
2. **The Jev version.** Keep `jev-latest`, with each response's version recorded and the stops above. The owner has seen issues with `jev-1.14.0`.
3. **The fallback-rate bar.** 30%, not the 40% proposed.
4. **Debatable diagnoses and weak engineering.** Kept, four single messages each, with their labels reviewed by an OpenAI model.

**Still open:**
5. **The author.** Which model writes the set? It must not be Claude Opus 5.5.
6. **The OpenAI reviewer.** Which model? The repository's examples use `gpt-4o`.

## Limits

- **Same question author.** The Jev questions and this spec share an author; only the set's author differs.
- **Late flaws only in the open.** As in G44, every flawed last turn states the flaw in the same message. A flaw that needs facts from two turns apart is not covered.
- **The fallback's margin rule was designed after looking at E7's held-out misses,** though its band was chosen on dev. G45 is its first clean test.

## Naming

"E9" is used twice in v3_spike.md: for the G44 held-out set (2026-11-21), and for the narrower-question redesign (2026-11-27), whose code still says `e9`. This spec takes E10.
