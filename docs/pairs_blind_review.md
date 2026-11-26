# E7d: blind check of the facts-against pairs

Generated from `eval/pairs_blind.py` and `eval/pairs_blind_labels.json`; regenerate with `python -m eval.pairs_blind > docs/pairs_blind_review.md`. Don't edit by hand.

The labeller was a model that wrote none of the pairs, none of the Jev questions and none of their examples. It saw only the guide in `eval/pairs_blind.py` (E7b's guide with the owner's rulings of 2026-11-25) and the user's words, under neutral ids and in a shuffled order. The two versions of a situation were never in the same batch. Pass A is primary and pass B is a replicate. The goal and its reading rule are in [e7d_pairs_blind_check_goal.md](e7d_pairs_blind_check_goal.md).

Everything below compares the passes with the set as it was at the run. Labels changed since are listed at the end.

Reruns: none.

## Agreement

| Field | Set vs A | κ | Set vs B | κ | A vs B | κ |
|---|---|---|---|---|---|---|
| `expected` | 0.94 | 0.88 | 0.94 | 0.88 | 0.88 | 0.75 |
| `cost` | 0.75 | 0.62 | 0.56 | 0.27 | 0.69 | 0.47 |
| `reversible` | 0.69 | 0.43 | 0.69 | 0.43 | 0.88 | 0.71 |
| `defeater` | 0.94 | 0.88 | 0.94 | 0.88 | 0.88 | 0.76 |

**Reading, fixed before the run:** κ on `expected` (set vs pass A) is 0.88, so the labels are reliable enough to tune `t_fa` and `t_ro` on, once the owner has ruled on the disagreements. Whatever the κ, the owner rules on every disagreement.

## The pairs

Each situation's `against` version should be `asked` and its `rules_out` version `objected`. A pass separates a pair when it labels both that way.

| Situation | Shape | `against`: A · B | `rules_out`: A · B |
|---|---|---|---|
| bedroom-mould | single | `asked` · `asked` | `objected` · `objected` |
| free-shipping-dip | single | `asked` · `asked` | `objected` · `objected` |
| yellow-tomatoes | single | `asked` · `asked` | `objected` · `objected` |
| wedding-film-export | single | `asked` · `asked` | `objected` · `objected` |
| algebra-club | conversation | `asked` · `asked` | `objected` · `objected` |
| lower-field-drains | conversation | `asked` · `objected` | `objected` · `objected` |
| third-line-cook | conversation | `objected` · `asked` | `objected` · `objected` |
| sycamore-shade | conversation | `asked` · `asked` | `objected` · `objected` |

Pairs separated: 7 of 8 by pass A, 7 by pass B.

## `expected`: set against pass A

| Set ↓ · pass A → | `none` | `asked` | `objected` |
|---|---|---|---|
| `asked` | 0 | 7 | 1 |
| `objected` | 0 | 0 | 8 |

## Disagreements on `expected` (2; 0 stable)

A disagreement is stable when both passes give the same label and it isn't the set's. Stable ones come first.

#### fadev/conversation/lower-field-drains/asked

**User, turn 1:**

> The barley off our bottom field has come in a third down two harvests running, and I can't carry a third poor year on it. It's waterlogged - the old clay drains have silted up, and water stands on it for days after any decent rain.

**User, turn 2:**

> I'm having the whole field re-drained this autumn, new pipe at 20-metre spacing, and I'm budgeting about £18,000. What should I ask the contractors to include when they quote?

**User, turn 3 (under test):**

> Right, two of them have been out now. Walking it with the second one I noticed the thinnest barley is up on the rise by the top gate, which has never held water in my lifetime. Which month should I book the work for so the ground's fit to drill afterwards?

- **Set at the run:** `asked` · evidenced · costly, hard to reverse · undercutting · high
  - The poorest crop is on ground that never holds water, which waterlogging cannot explain; the cause of the low yield is unknown and new drains might still help the wet end.
- **Pass A:** `asked` · asserted · costly, hard to reverse · undercutting · low
  - The thinnest barley is on a rise that never holds water, which counts against waterlogging from silted drains as the cause the whole-field re-drain would act on, so the cause should be checked before committing about £18,000.
- **Pass B:** `objected` · asserted · mid, hard to reverse · undermining · low
  - The waterlogging-from-silted-drains cause is stated without any test, and the costly, buried, irreversible re-drain is not justified by it, especially since the thinnest barley sits on ground that never holds water.

#### fadev/conversation/third-line-cook/asked

**User, turn 1:**

> I own a 60-seat bistro, and on Friday and Saturday nights mains are taking 45 minutes to reach the table; we're getting reviews about it. Two cooks on the line just isn't enough for a full room.

**User, turn 2:**

> So I'm taking on a third line cook, full time, at about £29k a year. What should the advert say to pull in someone who has worked a busy line before?

**User, turn 3 (under test):**

> Lovely, that went up last night. I stood at the pass with a stopwatch last Friday, and tickets were sitting on the rail for fifteen minutes or more before anyone started them, even in the stretches when both cooks had nothing on. What should I look for at the trial shifts?

- **Set at the run:** `asked` · asserted · mid, hard to reverse · undercutting · high
  - Tickets waited while both cooks were free, which a shortage of cooks does not explain; where the delay comes from is unknown and another pair of hands might still help.
- **Pass A:** `objected` · evidenced · costly, hard to reverse · rebutting · high
  - The user's stopwatch shows tickets waiting on the rail while both cooks were idle, so a third cook would not reduce the delay, and a full-time hire at about £29k is a costly commitment.
- **Pass B:** `asked` · asserted · mid, hard to reverse · undercutting · low
  - The stated cause is too few cooks, but the user's stopwatch shows tickets waiting while both cooks were idle, which knocks out capacity as the cause without establishing the real one, so the right move is a question.

## Since the run

These labels have changed since the run:

- fadev/single/wedding-film-export/asked: `reversible` True → False
- fadev/single/wedding-film-export/objected: `reversible` True → False

Against the set as it stands now, agreement on `expected` is 0.94 (κ 0.88) for pass A and 0.94 (κ 0.88) for pass B.
