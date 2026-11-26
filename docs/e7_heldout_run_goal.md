# E7: the held-out run on G43 and G44

**Status:** fixed 2026-11-26, before any Jev or LLM call. Nothing in it has run.
- The owner approved the question changes on 2026-11-25: three rewordings and two new questions.
- Every decision is settled; they are listed at the end.
- A later change needs the owner's approval, recorded with its date, before the held-out run. Nothing changes after it.

## Why

E7 decides whether Jev can replace the LLM grounding classifier. One Jev setup is fixed on dev data, then run once on the held-out sets, G43 and G44, against the LLM classifier. The decision rule was fixed on 2026-11-19 (`docs/v3_spike.md`, "Next experiments") and is unchanged here.

## What has changed since E7 was defined

E7 was defined around E5b's decision table. Since then:
- **Rule (b).** An asserted cause gets an objection only when the plan is costly or hard to reverse (E6 rule (b), confirmed 2026-11-20).
- **Evidence (E5c).** `evidence_for_cause` separates evidence from a bare claim (AUC 1.0 on paired dev).
- **Cost (E5d).** `plan_reversible` and `plan_large` tell costly plans from cheap ones (E5d passed its mark).
- **The owner's 2026-11-22 rule.** When the user's own facts count against the stated cause, ask, unless those facts rule out the plan itself, in which case object.
- **E8 and E8b.** 83 owner-checked dev cases in the middle ground, checked by a blind second labelling (κ 0.71), and the conventions of 2026-11-24 and 2026-11-25.
- **G44.** 64 late-flaw conversations, all of which survived recording, so objection in conversations can now be measured.

E5b's table objects whenever Jev doubts that the plan will deliver. Under the rules above, that is wrong in two places E7 scores:
- **Cheap plans on an asserted cause.** These should stay quiet under rule (b), but E5b objects whenever Jev doubts the plan.
- **A fact against the stated cause.** This should get a question, as in G44's eight `late_fact_against` conversations, but E5b has no question for it and objects through `achieves_goal`.

E5b's own failure also stands: in conversations it objected to nine sound plans and nine tasks through `achieves_goal`, at scores of 0.34 to 0.49.

## The candidate

### Questions, asked in one Jev request

**Kept as they are.** These held up in E5b:
- `problem_described`;
- `investigation`;
- `link_stated`;
- `conflicts_constraint`;
- `achieves_goal`, with E5b's overall-plan note in conversations.

**Reworded (approved by the owner, 2026-11-25):**
- **`evidence_for_cause`** asks about *the cause the plan acts on*, not "the cause". This follows the ruling of 2026-11-25: when the user names two causes, judge the one the plan acts on. As worded now, a message with one measured cause and a plan acting on a second, believed one reads as evidenced.
- **`plan_large`** adds "counting the time of everyone involved" (2026-11-25: cost counts everyone's time).
- **`plan_reversible`** aligns with the set's definition. The plan is reversible if the team can switch back without losing data or being held to a commitment: by reverting a change, turning off a flag, returning to an old system kept running alongside, or cancelling a rental. It is not reversible if it deletes or migrates data; buys, signs or prepays; publishes or sends something that can't be taken back; or changes something customers already rely on.

  As worded now, any rebuilt or replaced system, new vendor or change to people counts as irreversible. That would make rule (b) object to a site rebuilt while the old one keeps running.

**New (approved by the owner, 2026-11-25).** These two carry the 2026-11-22 rule:
- **`facts_against_cause`:** "Does something the user reports show that the cause their plan acts on, stated or only implied by the plan, is not what is happening? Not merely that another cause is also at work."
- **`plan_ruled_out`:** "Do the user's own facts show that the plan cannot deliver what they need, whatever the real cause turns out to be?"

**Examples.** Each reworded or new question keeps or gets paired examples, in situations used in no dev or held-out set and no other criteria list. The word-and-phrase overlap test checks this.

**Conversation state.** Conversations are sent whole, with the conversation note, as in E5b. G43's first exploration found that sending only the user's turns made conversations worse, so that change is not proposed.

**One request.** E5c and E5d asked their questions in separate requests. If, on dev, any of their questions' AUCs drops by more than 0.02 in the combined request, those questions go back to their own requests.

### Decision table (rows in order)

| # | Condition | Action | What it encodes |
|---|---|---|---|
| 1 | `investigation` ≥ 0.5 | `none` | finding the cause needs no cause |
| 2 | `conflicts_constraint` ≥ 0.5 | `objected` | a stated requirement broken |
| 3 | `problem_described` < 0.3 | `objected` if `achieves_goal` < t_ach, else `none` | nothing going wrong: checked against the goal only, including requirements that follow from the domain |
| 4 | `facts_against_cause` ≥ t_fa or `plan_ruled_out` ≥ t_ro | `objected` if `plan_ruled_out` ≥ t_ro, else `asked` | the 2026-11-22 rule, and an objection whenever the user's facts rule the plan out |
| 5 | `evidence_for_cause` ≥ t_ev | `objected` if `achieves_goal` < t_ach, else `none` | an evidenced cause: quiet unless the user's facts show the plan can't deliver |
| 6 | `link_stated` ≥ t_link | `objected` if costly, else `none` | an asserted cause: rule (b) |
| 7 | otherwise | `asked` | an implied cause (ruling 2) |

Costly means `plan_reversible` < 0.5 or `plan_large` ≥ 0.5 (E5d's rule, fixed).

**Objection without a named cause.** When the user's facts rule the plan out, row 4 objects even though no cause is named (owner, 2026-11-25). `facts_against_cause` covers a cause that is only implied by the plan.

**Facts that rule out the plan but not the cause.** `plan_ruled_out` triggers row 4 on its own (owner, 2026-11-26). In all eight `objected` pairs, the user's fact rules out the plan without counting against the cause, so `facts_against_cause` alone would miss them. Without this, those cases fall through to the level rows, where a cheap plan on an asserted cause gets no objection.

**Gaps not encoded.** A plan that makes the problem impossible by construction, like `double-standup-reminder`, needs no stated cause (narrowed 2026-11-25). The table still sends it to row 7, which asks. It is rare on dev, so it is left as a known miss.

### Thresholds

- **Fixed:**
  - `investigation` and `conflicts_constraint` at 0.5;
  - `problem_described` at 0.3;
  - the cost rule's thresholds.
- **Picked on dev from a grid fixed now (32 configurations):**
  - `t_link` ∈ {0.5, 0.7};
  - `t_ev` ∈ {0.5, 0.7};
  - `t_ach` for conversations ∈ {0.5, 0.3}. For single messages, `t_ach` is fixed at 0.5. The 0.3 setting is chosen only if it gains at least 0.02 of utility on dev, as E7's rules require.
  - `t_fa` for `facts_against_cause` and `t_ro` for `plan_ruled_out`, each ∈ {0.5, 0.7}. These are tuned mainly on the facts-against pairs (owner, 2026-11-25).

### Selection on dev

Each configuration is scored the way E7 scores the held-out run, against the LLM classifier:
- utility at c = 0.25 with 20% wrong plans, on the spent pool, the only dev set that records whether each plan is right;
- the rate in every label cell on every dev set with end-to-end labels, against the LLM's.

The configuration with the most cells within max(0.07, one case) of the LLM wins, with ties broken by utility. All 32 are reported. E5b's table is scored on the same answers as the baseline.

## Dev data

| Set | Cases | Used for |
|---|---|---|
| Spent pool (G40–G42) | 239, 102 of them conversations | utility and label cells |
| E5c dev | 32 | level routing on cheap plans: implied and measured-symptom get `asked`; asserted and evidenced get `none` |
| E5d dev | 52 | the cost rule, which must still pass E5d's mark with the new wording |
| E8 | 83, 21 of them conversations | label cells; the only dev source of objections in conversations |
| Facts-against pairs ([E7a](e7a_facts_against_pairs_goal.md)) | 16 | the 2026-11-22 branch, and tuning `t_fa` and `t_ro`. A blind check of their labels ([E7d](e7d_pairs_blind_check_goal.md)) gave κ 0.88 on `expected` |

**Before the dev run.** The candidate reads whole conversations, so E8's 21 conversations and the four conversation pairs get assistant replies recorded once, from the unaided model, as G43 and G44 did. A conversation is used only if its earlier turns were answered with no question and no objection.

**Before selection:**
1. **Check the spent pool against the current rules.** Its labels predate rule (b) and the 2026-11-22 rule.
   - **The label-only check.** The owner chose [E7b](e7b_older_label_check_goal.md), run on 2026-11-25.
   - **The rulings on its 22 stable disagreements (2026-11-25):** five relabels from `asked` to `none`, listed as `RELABELS` in `eval/older_blind.py`. A conversation's relabel applies only if that conversation is in the dev pool. The other 17 keep their stored labels.
   - **Also after the dev run,** a code check lists:
   - every quiet case the candidate reads as an asserted cause behind a costly plan;
   - every case with facts against its cause.

   The owner relabels or excludes them, with the date recorded, before any configuration is picked.
2. **The facts-against pairs.** Today the new branch has almost no dev cases:
   - in E8, `till-freezes` (`asked`) and `primary-cpu-morning` and `scraper-slow` (`objected`), plus the different-cause objections;
   - G44's eight `late_fact_against` conversations, which are held out.

   The owner chose to have 8 situations each written twice. In one version a fact counts against the stated cause but the plan might still work (`asked`); in the other a fact rules the plan out (`objected`). The set is written by a model other than the one that wrote the questions ([E7a](e7a_facts_against_pairs_goal.md)), and reviewed by the owner: blind-checked in [E7d](e7d_pairs_blind_check_goal.md) and owner-checked on 2026-11-26.

## The held-out run

- **G43:**
  - 62 single messages: 19 `objected`, 17 `asked`, 26 `none`;
  - the 38 scored conversations: 26 sound, 7 answered, 5 with no cause;
  - with the histories recorded on 2026-11-20.
- **G44:** 64 conversations (14 `objected`, 18 `asked`, 32 `none`), with the histories recorded on 2026-11-22.
- **Arms:** the LLM classifier (`GROUND_SYSTEM` on the judge model, as in G40 to G42) and the fixed candidate. Three repeats each, run once.
- **Gated cells:** expected action by shape, wherever a cell exists:
  - quiet, task, ask, answered and object, for single messages and conversations;
  - G44 supplies object/conversation;
  - G43's object/conversation stays reported only, under E6's survival rule.
- **Utility:** c = 0.25 with 20% wrong plans.
  - Each held-out case's plan counts as wrong or right from its recorded frame: an `objected` case's plan is wrong, and a withheld-cause case takes its family's fits or misses.
  - G44's `late_fact_against` plans count as a 50% chance of being wrong (owner, 2026-11-25). The fact counts against the cause they act on, but the plan might still help. Their utility is the average of the two outcomes, which makes asking the best-scoring action.
  - A test checks this on every held-out case before the run, as code only.
- **Decision rule (unchanged):**
  - utility no worse than the LLM's by more than 0.02 per decision;
  - no gated cell more than max(0.07, one case) below the LLM's.
- **Nothing changes after the result.**

## Decisions for the owner

**Settled on 2026-11-25:**
1. **The wording changes.** The three rewordings and the two new questions are approved.
2. **Reversibility.** Switching back to an old system kept running alongside counts as reversible, as the reworded `plan_reversible` says.
3. **The facts-against pairs.** Another model writes them (E7a), and their labels get a blind check (E7d) before tuning.
4. **Spent-pool relabels.** Five, from E7b's stable disagreements.
5. **Scoring G44's fact-against plans.** A 50% chance of being wrong.
6. **Thresholds.** The two new questions' thresholds are tuned on dev, not fixed.
7. **"Works whatever the cause."** Narrowed to plans that make the problem impossible by construction.
8. **Objection without a named cause.** An objection doesn't need a named cause when the user's facts rule the plan out.

**Settled on 2026-11-26:**
9. **E7d's outcome.** The pairs' labels stand (κ 0.88). Both disagreements keep the set's `asked`, and wedding-film-export's plan becomes hard to reverse, a purchase under the written definition.
10. **Row 4.** It fires when either new question does, and objects when `plan_ruled_out` reaches `t_ro`.
11. **The facts-against pairs** are owner-checked.

## Cost

- **Jev:** about 1,800 requests (dev about 420 cases and held-out 164, three repeats each). Well under a dollar.
- **LLM classifier:** about 900 calls. That's E8, E5c and the new pairs on dev (the spent pool's answers are cached), plus the held-out sets, three repeats each.

## Limits

- **One author.** The model that wrote the Jev questions also wrote G43, G44 and this spec.
- **Thin dev for the new branch.** Even with the 16 pairs, the 2026-11-22 branch rests on little dev data. G44 is where it is really tested.
- **Conversation merit objections.** E5b's false objections in conversations are addressed only by the conversation threshold, and by the table using `achieves_goal` in fewer rows.
