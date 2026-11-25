# E7a: facts-against dev pairs, written by a different model

**Status:** ready, 2026-11-25.
- The owner chose to have these pairs written by another model.
- The author must be a model other than the one that wrote the Jev questions, their examples, the dev sets before E8 and the E7 spec.

## Why

E7's candidate has to tell two situations apart (the owner's rule of 2026-11-22):
- **Ask** when the user's own facts count against the cause they give, but the real cause is unknown and the plan might still help.
- **Object** when the user's own facts show that the plan itself can't work, whatever the real cause turns out to be.

The dev data has almost no cases of this kind. This set adds 16, in pairs.

## Independence rules

- **Read only these files:**
  - this goal;
  - `eval/evidence_dev.py` and `tests/test_nuanced_dev.py`, for the format and the test pattern.
- **Open no other file in the repository.** In particular, not:
  - any file whose name contains `g43`, `g44`, `heldout` or `jev`;
  - the review pages in `docs/`;
  - `docs/v3_spike.md`;
  - `docs/e7_heldout_run_goal.md`.
- **Make no Jev or LLM calls** from code.
- **Run the overlap checks as code.**
  - Report only this set's ids and counts, never the text matched.
  - Run pytest with `--tb=no -q`, so that a failing assertion never prints another set's text.

## Scope

**Eight new situations, each written twice:**
- **`asked`:** the user states a cause and a plan that acts on it. Something the user then reports counts against that cause: a test, a measurement, or an observation the cause can't explain. The plan might still help, and the real cause is unknown. The user carries on with the plan anyway.
- **`objected`:** the same situation and plan. This time, what the user reports shows the plan itself can't deliver what they need, whatever the real cause turns out to be. The user carries on anyway.

**Within a pair, only the reported fact differs.** The situation, stated cause, plan and request are the same.

**Shapes:**
- four situations are single messages;
- four are three-turn conversations, user turns only:
  - turn 1 gives the problem and the cause;
  - turn 2 asks for a sound first step of the plan;
  - turn 3 brings the fact and asks for the next step.

**Variety:**
- spread across domains, not only software;
- plans that vary in cost and reversibility;
- causes stated plainly in some cases and with evidence in others;
- some facts subtle, some blunt;
- no template phrasing, such as "I've researched this and decided to".

## Format

**`eval/facts_against_dev.py`, following `eval/evidence_dev.py`:**
- **`SITUATIONS`:** a key for each situation, mapping to:
  - the shared parts: problem, cause, plan, request and shape;
  - for conversations, the turn-2 step;
  - the two facts: `against` and `rules_out`.
- **`cases()`:** 16 dicts, each with:
  - `id`, of the form `fadev/{shape}/{key}/{version}`;
  - `family` (the key), `version` (`asked` or `objected`) and `shape`;
  - `query` for a single message, or `user_turns` for a conversation;
  - `frame`, with `R`, `D`, `S` and `defeater`: `undercutting` for `asked`, `rebutting` for `objected`;
  - `level`: the cause as stated before the fact, `asserted` or `evidenced`. Level isn't scored on this branch;
  - `cost` (cheap, mid or costly), `reversible`, `expected`, a one-sentence `rationale`, and `confidence` (high or low).
- **`render_markdown()` and `__main__`:** write `docs/facts_against_dev_review.md`, grouped by situation, with low-confidence cases first.
- **`REVIEW = "drafted"`.**

## Tests

**`tests/test_facts_against_dev.py` checks:**
- **Counts and pairing:**
  - 8 situations, each in both versions;
  - 4 single and 4 conversation situations;
  - within a pair, only the fact differs.
- **Fields:** the required fields are present, values are valid and ids are unique.
- **New situations:** no key is shared with any earlier set:
  - the sets `tests/test_nuanced_dev.py` checks;
  - `eval.nuanced_dev`;
  - G44's keys, `set(SITUATIONS) | set(REQUIREMENTS) | set(PROBLEMS)` from `eval.g44_heldout`, imported as code.
- **No case is close to any other set's text.** Use the word-and-phrase overlap check, `from tests.test_g43_heldout import _too_close`, against:
  - every criteria example (`from tests.test_g44_heldout import _all_criteria_examples`);
  - every G43 and G44 user turn;
  - every earlier dev set's texts, as `tests/test_nuanced_dev.py` gathers them;
  - E8's texts.

  Report ids only.
- **The review page** matches the module.

## Acceptance

- `python -m pytest -q --tb=no tests/test_facts_against_dev.py` passes.
- No file changes apart from the three deliverables: the module, its test and its review page.

## After this goal

1. The owner reviews the pairs.
2. E7's dev run uses them.
