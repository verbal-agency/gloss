# E7d: a blind check of the facts-against pairs' labels

**Status:** fixed 2026-11-25, before any labelling. The owner chose this check on 2026-11-25 (E7, decision 3).

## Why

E7 tunes `t_fa` and `t_ro`, the thresholds of its two new questions, mainly on the 16 facts-against pairs ([E7a](e7a_facts_against_pairs_goal.md)). Their labels have one author and haven't been reviewed. This check asks whether an independent reader, given the written rules and only the user's words, reaches the same labels.

## Procedure

**The same method as E8b and E7b:**
- **The labeller** is a model that wrote none of the pairs, none of the Jev questions and none of their examples.
- **What it sees:** only the guide and the user's words, under neutral ids (`t01` to `t16`) and in a shuffled order. For a conversation, it sees the user's turns only.
- **What it may do:**
  - each labelling agent may read its prompt file and write its answer file, and nothing else;
  - every transcript is checked;
  - a batch that does anything else is discarded and rerun, and the rerun is reported.

**The guide** is E7b's, with the owner's rulings of 2026-11-25 added. They are listed in `eval/pairs_blind.py`:
- **Narrowed.** "A plan that works whatever the cause" becomes a plan that makes the problem impossible by construction.
- **The user's own facts, at any level.** They are judged before the rule for the cause's level:
  - object when they show the plan can't deliver the goal, whether or not a cause is named;
  - otherwise, ask when they count against the cause the plan acts on.

  E7b's guide had the second part only for asserted causes. E7's table applies it before the evidence row, so the guide now does too.

**Twins apart.**
- The two versions of a situation never share a batch, so each version is judged without its twin, as the classifier will judge it.
- Each batch holds one version of every situation. In each shape, two versions are `asked` and two `objected`.
- The pass's seed fixes which version goes in which batch, and the order within a batch.

**Two passes,** A (primary) and B (a replicate), of two batches each: four labelling agents, each run once.

**Fields:** the same as E8b's. `level` is collected but not compared: the set records the cause as stated before the fact, and this branch doesn't score it.

## Measures (fixed now)

**Primary.** Agreement on `expected` between the set and pass A: raw agreement and Cohen's kappa.

**Also reported:**
- the same for pass B against the set, and for pass A against pass B;
- agreement on `cost`, `reversible` and `defeater`;
- for each situation, whether each pass separates the two versions the set's way: `asked` for the version whose fact counts against the cause, `objected` for the one whose fact rules out the plan;
- every disagreement on `expected`, with both passes' labels and rationales. A disagreement is stable when both passes give the same other label.

## Reading rule (fixed now)

| Kappa on `expected`, set against pass A | Reading |
|---|---|
| 0.6 or more | Reliable enough to tune `t_fa` and `t_ro` on, once the owner has ruled on the disagreements. |
| 0.4 to 0.6 | Usable with care. Tuning waits for the owner's rulings, and E7 reports the agreement as a limit. |
| Below 0.4 | Not reliable yet. E7 doesn't tune `t_fa` and `t_ro` on the pairs until the owner has reconciled the labels. |

- **Every disagreement goes to the owner,** stable or not, whatever the kappa: there are at most 16.
- **No label changes automatically.** Any relabel is the owner's, recorded with its date, before E7 picks thresholds.

## Deliverables

1. **`eval/pairs_blind.py`:** the guide, the batches, the prompts, the collector and the results page.
2. **`eval/pairs_blind_labels.json`:** both passes, the guide and prompt hashes, any reruns, and the set's labels at the run.
3. **`docs/pairs_blind_review.md`:** the results page.
4. **`tests/test_pairs_blind.py`.**
5. **A note in `docs/v3_spike.md`,** and E7's spec updated with the outcome.

## Known limits

- **A smaller model,** as in E8b and E7b. A disagreement can reflect the labeller's limits as much as a label error.
- **Who wrote the guide.** The session that drafted E7 wrote it, and has read the pairs' labels. The guide restates only the owner's written rulings.
- **Sixteen cases.** One case moves the kappa by about 0.12, so the disagreements say more than the number.
