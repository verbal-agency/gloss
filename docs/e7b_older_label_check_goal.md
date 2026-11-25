# E7b: a label-only check of the older dev cases

**Status:** fixed 2026-11-25, before any labelling. The owner chose this check in place of the Jev-based check in E7's spec.

## Why

The older dev pool (G40 to G42, 239 cases) was labelled before rule (b), the owner's 2026-11-22 rule and the conventions of 2026-11-24 and 2026-11-25. E7 tunes its thresholds on that pool. A label the current rules would change pulls the tuning toward the old rules. This check finds those labels before tuning, without Jev.

## Procedure

**The same method as E8b:**
- **The labeller** is a model that wrote none of these cases and none of the Jev questions.
- **What it sees:** only the guide and the user's words, under neutral ids and in a shuffled order.
- **What it may do:**
  - each labelling agent may read its prompt file and write its answer file, and nothing else;
  - every transcript is checked;
  - a batch that does anything else is discarded and rerun, and the rerun is reported.

**The guide** is E8b's, with the owner's 2026-11-25 clarifications added. They are listed in `eval/older_blind.py`.

**Cases:**
- all 137 older single messages;
- all 143 older conversations, as user turns only, taken from their source sets.

The dev pool holds 102 of those conversations: the ones whose recorded histories survived.

**Two passes,** A and B, of six batches each.

**Only `expected` is compared,** because the older sets record nothing else. The labeller's other fields are kept to explain disagreements.

## Output

- **Agreement on `expected`** with the stored labels, for single messages and conversations separately, and the labeller's agreement with itself.
- **Every disagreement,** listed with:
  - the case's words;
  - its stored label;
  - both passes' labels and rationales.

  Stable disagreements, where both passes give the same other label, come first.

## Reading

- **No label changes automatically.** The owner rules on the stable disagreements. Any relabel is recorded with its date, before E7 picks its thresholds.
- **Conversations count only if they are in the dev pool.** A conversation's disagreement is acted on only after that is checked against the recorded histories.

## Deliverables

1. **`eval/older_blind.py`:** the cases, guide, prompts, collector and results page.
2. **`eval/older_blind_labels.json`:** both passes, the guide and prompt hashes, and the stored labels at the run.
3. **`docs/older_blind_review.md`:** the results page.
4. **`tests/test_older_blind.py`.**
5. **A note in `docs/v3_spike.md`.**
