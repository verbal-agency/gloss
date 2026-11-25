# E7c: examples for E7's new and reworded Jev questions, written by a different model

**Status:** ready, 2026-11-25.
- The owner chose to have these examples written by a model other than the one that wrote the questions.
- That model has seen some of the dev cases, and the examples must not be shaped by them.

## Why

Each Jev question carries criteria: a meaning for "yes" and for "no", each with example messages. E5c and E5d found that paired examples, set in one situation used nowhere else, are what make a question work.

E7's spec ([e7_heldout_run_goal.md](e7_heldout_run_goal.md), "The candidate") has two new questions and three rewordings, approved by the owner, and all five need examples. The examples must not resemble any dev or held-out case, so that E7 measures the questions rather than their examples.

## Independence rules

- **Read only:**
  - this goal;
  - `docs/e7_heldout_run_goal.md`, for the questions' wording;
  - `app/pipeline/jev_ground.py`, for the format and for the existing examples to stay clear of.
- **Open no other file in the repository.** In particular, not any file whose name contains:
  - `g40`, `g41`, `g42`, `g43`, `g44` or `heldout`;
  - `nuanced`, `facts_against`, `evidence_dev` or `stakes_dev`;
  - `proposals` or `multiturn`.

  Also not the review pages in `docs/` or `docs/v3_spike.md`.
- **Make no Jev or LLM calls** from code.
- **Run the overlap checks as code.** Report only question names and example positions, never the text matched. Run pytest with `--tb=no -q`.

## What to write

**In `app/pipeline/jev_ground.py`,** add a new block after E5d's: `_E7_NOULS: dict[str, tuple[str, dict, dict]]`. Each entry follows the E5c and E5d format: `(question, {"meaning": ..., "examples": [...]}, {"meaning": ..., "examples": [...]})`, for yes and no. Change nothing else in the file.

1. **`facts_against_cause`** (new). Use the spec's wording.
   - Give at least two "yes" and two "no" examples, in one new situation.
   - Each "yes" has a "no" twin that differs only in what the user reports.
   - Make the "no" twins show the two things a careless reader confuses with "yes": a fact that only shows *another* cause is also at work, and a fact that supports the stated cause.
2. **`plan_ruled_out`** (new). Use the spec's wording.
   - Give at least two "yes" and two "no" examples, in one new situation, paired the same way.
   - A "yes" fact shows the plan cannot deliver whatever the cause.
   - A "no" twin's fact counts against the stated cause but leaves the plan possibly useful.
3. **`evidence_for_cause`** (reworded: "the cause the plan acts on").
   - Keep E5c's examples by taking them from `_E5C_NOULS`.
   - Add one pair in a new situation where the user names two causes and measures only one. "No": the plan acts on the merely believed cause. "Yes": the plan acts on the measured one.
4. **`plan_large`** (reworded: "counting the time of everyone involved").
   - Keep E5d's examples.
   - Add one pair in a new situation: "yes" is a plan short in calendar time that takes many people's time; "no" is a small team's few days.
5. **`plan_reversible`** (reworded to the set's definition).
   - Keep E5d's examples.
   - Add one pair in a new situation: "yes" is a rebuilt system run alongside the old one until a switch-over; "no" is the same rebuild, but it migrates the data and retires the old system.

**Style:**
- Examples are user messages, a sentence or three long, in plain language.
- Spread the new situations across different domains, not all software.
- Avoid template phrasing such as "I've researched this and decided to".

## Tests

**`tests/test_e7_questions.py` checks:**
- **The five questions exist,** and the two new ones use the spec's wording.
- **Every question has at least two "yes" and two "no" examples.**
- **No new example is close to:**
  - any dev or held-out text: the earlier sets gathered by `tests/test_nuanced_dev.py` (`_earlier_texts`), G44's user turns, E8's texts, and the facts-against pairs (`eval.facts_against_dev`);
  - any other question's examples.

  Use `from tests.test_g43_heldout import _too_close`, and import the sets as code. Report only question names and example positions.

**Also run** the existing overlap tests that cover every criteria example, which now include the new ones: in `tests/test_g44_heldout.py`, `tests/test_nuanced_dev.py` and `tests/test_facts_against_dev.py`.

## Acceptance

- The new test passes, and the existing overlap tests named above still pass.
- `app/pipeline/jev_ground.py` gains only the new block.
- No other file changes apart from the new test.

## After this goal

The battery and the decision table are wired in E7's code. The owner reviews the examples.
