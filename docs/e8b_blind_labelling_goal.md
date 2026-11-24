# E8b: a blind second labelling of the E8 dev set

**Status:** fixed 2026-11-24, before any labelling run. A follow-on to [E8](e8_nuanced_cases_goal.md) ("After this goal", step 2).

## Why

E7 will pick Jev's thresholds on the E8 set, so its labels need a reliability check. So far they have one author, one review and the owner's rulings, and the review read the labels before judging them. The question is whether an independent reader, given the same written standard, reaches the same labels.

The E8 goal planned this step: "A second, different model labels the set blind. Agreement is reported per field as a reliability check on the labels." Where the labeller disagrees, either the label or the written standard needs another look.

## Independence rules

- **Who labels.** The labeller is a model other than:
  - the set's authors;
  - the model that reviewed its labels;
  - the model that wrote the Jev questions.
- **What it sees.** Only the guide and the case texts. No labels, rationales, frames, categories or case names. Cases carry neutral ids (`k01` to `k83`) and appear in a shuffled order.
- **What it may do.** Each labelling agent may make exactly two tool calls: read its prompt file, and write its answer file. Its transcript is checked afterwards. A batch that made any other call is discarded and run again, and the rerun is reported.
- **The guide.** It restates the written standard:
  - the E5c ladder;
  - rulings 1 to 3;
  - E6 rule (b);
  - the owner's rule of 2026-11-22;
  - the conventions confirmed on 2026-11-24.

  It names no case and gives no example from any case, criteria list or held-out set. Where the written rules leave a case open, the guide doesn't settle it: finding those places is part of the check.
- **No Jev calls.** No case text or label changes in this goal.

## Procedure

- **Two passes:** A (primary) and B (a replicate). Each covers all 83 cases in its own shuffled order and is split into three batches, so there are six labelling agents, one per batch. Each batch is run once.
- **Fields per case:**
  - `level`, `cost`, `reversible`, `expected`, `defeater` and `confidence`, with the values the set uses;
  - a one-sentence rationale.
- **Reruns.** A batch is rerun only if its answer is malformed, misses a case, or its transcript shows a call other than the two allowed.
- **Record.** The prompts are built by `eval/nuanced_blind.py` from the case texts. Hashes of the guide and of every prompt are stored with the labels, so a later edit to either shows up.

## Measures (fixed now)

**Primary.** Agreement on `expected` between the set and pass A: raw agreement and Cohen's kappa.

**Also reported:**
- the same two numbers for `level`, `cost`, `reversible` and `defeater`;
- the confusion matrix of the set against pass A, for `expected` and `level`;
- agreement on `expected` for the set's high- and low-confidence cases, separately;
- pass B against the set;
- pass A against pass B, which measures the labeller's own consistency.

**Disagreements.** Every disagreement on `expected` is listed for the owner. It is marked **stable** when both passes give the same other label.

## Reading rule (fixed now)

| Kappa on `expected`, set against pass A | Reading |
|---|---|
| 0.6 or more | Reliable enough for E7's dev. The owner looks at the stable disagreements. |
| 0.4 to 0.6 | Usable with care. The owner reviews every disagreement on `expected` before E7 picks thresholds. |
| Below 0.4 | Not reliable yet. E7 doesn't pick thresholds on this set until the owner has reconciled the labels. |

No label changes automatically. Any relabel is the owner's decision, recorded with its date, and made before any Jev run on the set.

## Deliverables

1. **`eval/nuanced_blind.py`:** the guide, the prompt builder, the collector and the agreement measures.
2. **`eval/nuanced_blind_labels.json`:** both passes' labels, with the guide and prompt hashes and any reruns.
3. **`docs/nuanced_blind_review.md`:** the results page, generated from the module, with the disagreements listed for the owner.
4. **`tests/test_nuanced_blind.py`:**
   - every case appears once per pass;
   - the prompts show no label, rationale, case name or category;
   - the labels cover every case with valid values;
   - the hashes match the current guide and prompts;
   - the page matches the module.
5. **A section in `docs/v3_spike.md`:** the spec in brief, and the result read by the rule above.

## Known limits

- **A smaller model.** The only model available that meets the independence rules is smaller than the ones that wrote and reviewed the set. A disagreement can reflect the labeller's limits as much as a label error, which is why stable disagreements and the owner's reading decide.
- **Who wrote the guide.** The guide was written by the reviewing session, which knows the labels. It restates only the written rules, and it is committed so the owner can check it.
- **An unsettled question in the rules.** They don't say which row applies when one cause is evidenced and the plan acts on another, merely asserted one. The guide doesn't settle this, so disagreements may cluster there.

## After this goal

1. The owner reviews the disagreements as the reading rule says.
2. E7.
