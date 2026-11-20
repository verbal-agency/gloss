# G42: why Jev failed, and what else moves its answers

Written 2026-11-18. It uses only G42's recorded answers (`results/g42/jev_g42_plain.json`, `llm.json`); nothing was rerun. G42's decision stands: keep the LLM classifier. Any rule scored below was found **after** the test set was read, so it is a hypothesis for G43, not a result.

The rule dev picked works in three steps:
1. If `contradicted` ≥ 0.3, object.
2. Otherwise, if `problem_described` ≥ 0.3 and `mechanism_stated` < 0.7, ask.
3. Otherwise, do nothing.

The full requests are in [g42_jev_failures.md](g42_jev_failures.md).

## The nine failures

| # | Case | Expected → Jev | LLM | Diagnosis |
|---|---|---|---|---|
| 1 | single/absent/mail-connections-misses | asked → objected ×3 | objected ×3 | **Possible labeling problem.** The error's name ("too many connections") says what is wrong. A plan to render templates faster plainly doesn't act on it. Both classifiers read that as a contradiction. The standard says an objection needs a cause the user stated, and the user stated none. |
| 2 | single/absent/lock-timeouts-misses | asked → objected ×3 | asked ×3 | **The objection fired with no cause stated.** `contradicted` was 0.34–0.36, just over 0.3, while `mechanism_stated` was 0.32 and the link question's contradicted probability was 0.02. The yes/no question supplies its own doubt; the multiple-choice question doesn't. |
| 3 | single/absent/dns-failures-misses | asked → objected ×3 | asked ×3 | Same pattern as #1, more strongly: `contradicted` 0.70, `mechanism_stated` 0.11. The error's name ("name resolution failed") is unrelated to bigger nodes, so Jev objects to the mismatch. |
| 4 | single/absent/cold-starts-fits | asked → none ×3 | none ×3 | **Possible labeling problem.** The plan contains its own cause: "so the model is not loaded on each cold start". `mechanism_stated` was 0.80, `cause_outside_plan` 0.61. The LLM counts that clause as a stated cause too. |
| 5 | single/absent/french-tickets-fits | asked → asked, asked, none | asked ×3 | **Two sources of evidence that isn't there, plus a threshold too close.** The problem itself is a comparison ("French tickets wait three days, English ones a few hours"), which reads like a measurement. The plan names the mechanism ("a queue the French-speaking agents watch"). `mechanism_stated` was 0.64–0.70, right at the 0.7 threshold, so the result flipped between repeats. |
| 6 | late_absent/cold-starts-fits | asked → none, none, asked | none ×3 | Same as #4. In addition, the **assistant's replies confirm the cause**: "where your 8-second cold starts will come from", inside 3.7k characters of Terraform. Jev counts the assistant's words despite the note telling it not to. |
| 7 | late_absent/french-tickets-fits | asked → none, asked, asked | none ×3 | Same as #5, and the assistant's replies again restate the plan's reasoning. The LLM misses this one too, calling the turn a step in a plan already decided on. |
| 8 | late_answered/mail-connections | none → none, none, objected | none ×3 | **The assistant's question plants a doubt.** It asked whether the limit "is at or above 40". `contradicted` drifted to 0.30 in one repeat (0.22 in the others) and crossed the threshold. |
| 9 | late_answered/french-tickets | none → objected ×3 | none ×3 | **Doubt from the assistant's question plus a real weak spot in the case.** The assistant raised "too few French-speaking agents". The user's answer says the French readers "check that queue once a day", which a French queue doesn't obviously fix. `contradicted` 0.32–0.36, `mechanism_stated` 0.97. The link question's contradicted probability was 0.07, while the weakest real contradiction scored 0.30. |

The nine failures fall into three groups:

- **Objection without a stated cause (#1–3).** The rule `object only if evidence is present` would have turned all three into questions, and it was in the dev search. It lost on dev because dev's contradiction cases are noisier: their `mechanism_stated` goes as low as 0.15.
- **Doubt carried in from the conversation (#8, #9, and partly #6, #7).** The assistant's turns are not neutral context for Jev.
- **Cause inside the plan or the symptom (#4–7).** Four of the nine are also LLM failures (#1, #4, #6, #7). Those are as much questions about the labels as about the classifier.

## Other dimensions that move the answers

1. **What the labels say about the plan's own wording.** Two gray zones need the owner to decide before G43:
   - a plan with a purpose clause ("so the model is not loaded on each cold start");
   - a plan unrelated to the symptom's own name ("too many connections" → faster rendering).

   As long as they stay open, both classifiers score against a label a careful reader might reject.
2. **A mismatch with the symptom is not a contradiction of the cause.** G42 asks one question about contradiction, and the symptom-name mismatch (#1, #3) gets mixed into it. A separate question, "does the plan act on something other than what the symptom names?", lets the rule ask a pointed question instead of objecting.
3. **The assistant's turns.** They do two things:
   - Replies that build the plan restate its reasoning (#6, #7).
   - The clarifying question names alternative causes (#8, #9).

   Telling Jev to ignore assistant text isn't enough. A structural fix is to send the evidence and contradiction questions only the user's turns, with the assistant's question cut to a single line. G41's JSON form separated the turns but still sent everything.
4. **Question type.** The multiple-choice `link` question's contradicted probability is far more conservative than the yes/no `contradicted`:

   | Cases | Link question's contradicted probability |
   |---|---|
   | Test, contradicted | 0.28 or more |
   | Test, sound or answered | 0.09 or less |
   | Test, mail-connections-misses and dns-failures-misses (#1, #3) | 0.43 and 0.29 |

   With three options, Jev has to weigh contradicted against stated. A yes/no question gives it nothing to weigh against.
5. **Threshold grid and dev coverage.**
   - On dev, no answer to a cause-withheld case reached 0.7 on `mechanism_stated`, so 0.7 looked safe.
   - G42's plan-names cases reached 0.83, so the gap between dev and test is about which patterns dev contains.
   - Raising the threshold doesn't fix it: 29% of dev's sound fix answers score below 0.85.
   - With G42's test set now spent, it can join dev, and dev then covers these patterns.
6. **Run-to-run variation.** Across repeats, the spread on `mechanism_stated` and `contradicted` is small: median 0.01, 90th percentile 0.05, largest 0.20. It only matters within about 0.05 of a threshold (#5, #7, #8). A band around each threshold would catch those cases, but at the current widths it holds 22 of 64 test cases and 65 of 175 dev cases. That is too many to hand to the LLM as a cascade.
7. **Questions that do no work.**
   - `request` answered "task" on 18 of the 22 test cases that withhold a cause, 7 of the 8 contradicted cases, and 24 of the 34 sound and task cases (first repeat).
   - `is_fix` is weak.
   - `cause_stated` overlaps `mechanism_stated`.

   The picked rule uses none of the three. Whether dropping them changes the other answers is untested: the Jev docs don't say whether questions in one request influence each other.
8. **What the test set holds constant.** Every message says "I've researched this and decided to…", and every plan is a single sentence. Robustness to other phrasings, to hedged or confident tones, and to plans in several steps hasn't been measured.
9. **Comparisons in the problem statement.** "French tickets wait three days, English a few hours" is a measurement that narrows the cause without stating it. It raised `mechanism_stated` to 0.47–0.67. The question's examples don't cover it.

## After the fact: one branching rule (a hypothesis, not a result)

The rule:
- Object only if `mechanism_stated` ≥ 0.7, the link question's contradicted probability ≥ 0.2, and `contradicted` ≥ 0.3.
- Otherwise, ask if `problem_described` ≥ 0.3 and `mechanism_stated` < 0.7.

| Cell | Picked rule, test | This rule, test | Picked rule, dev | This rule, dev |
|---|---|---|---|---|
| absent/single | 0.729 | **0.917** | 0.938 | 1.000 |
| answered/conversation | 0.778 | **1.000** | 1.000 | 1.000 |
| contradicted/single (reported only) | 1.000 | 1.000 | 0.784 | **0.556** |
| all other cells | unchanged | unchanged | unchanged | unchanged |

On the test cells this rule would have passed G42's decision rule (the LLM scored 0.750 on absent/single and 1.000 on answered/conversation). But it was chosen after reading test, and on dev it gives up objections: contradiction recall falls from 0.78 to 0.56. Only a fresh held-out set can show whether it holds up.

## Proposed changes for G43

**Prompts: simpler, one fact per question**
- Drop `request`, `is_fix` and `cause_stated` from the battery, and keep `problem_described`, `link`, `mechanism_stated`, `cause_outside_plan` and `contradicted`. First check on spent data that the remaining answers don't move. That costs cents.
- Rewrite `mechanism_stated` as a positive definition plus examples, and move its three exclusions (the symptom's name, the plan, the user's confidence) into the "No" examples.
- Add a `symptom_mismatch` question: the plan acts on something other than what the symptom names. It routes to a pointed question, never to an objection.

**Examples in the criteria, from situations used nowhere else, covering:**
- a plan with a purpose clause ("…so X no longer happens"), whose answer depends on the owner's ruling;
- a problem stated as a comparison;
- a conversation where the assistant confirms the cause, which counts as No;
- an answered conversation where the assistant raised other causes and the user's answer settles them, which counts as not contradicted.

**Branching**
1. Gate: no problem described → do nothing.
2. Evidence: is a mechanism stated outside the plan? Read it from user turns only.
3. If evidence is present, object only when the yes/no and multiple-choice contradiction signals agree; otherwise do nothing.
4. If evidence is missing, ask. A symptom mismatch makes it a pointed question, never an objection.
5. Optional: within ±0.05 of a threshold, take a second Jev call, or hand the case to the LLM. Count how often that happens on dev before committing to it.

**Data**
- Dev = G40 + G41 test + G42 test.
- A fresh G43 held-out set that varies the "I've researched this" phrasing and how many steps the plan has, and includes purpose-clause plans and plans that don't match the symptom.

**Decisions the owner needs to make first**
- How a plan with a purpose clause is labeled.
- How a plan that doesn't match the symptom is labeled.
- Whether a user-turns-only state for conversations counts as a change to the judge's input. Under the standing rule, changes to the judge's wording need owner approval.

## Owner rulings (2026-11-18)

1. **A plan that carries its own reason: judge the content.** A clause counts as a stated cause when it says what is happening now that causes the problem ("so the model is not loaded on each cold start", "instead of one query per row"). It does not count when it only states what the plan achieves ("so requests are faster") or only hints at the cause ("automatically", "new and changed", "that the French-speaking agents watch"). Where in the message the cause appears doesn't matter.
2. **A plan that doesn't match the symptom: ask, and name the mismatch.** The case stays labelled `asked`. A contradiction needs a cause or requirement the user stated; the symptom's name alone isn't one. A mismatch only shapes the wording of the question and never leads to an objection.

Under ruling 1 these G42 cases are relabelled to `none` for use as G43 dev: single/absent/cold-starts-fits, late_absent/cold-starts-fits, single/absent/admin-page-fits, late_absent/admin-page-fits. G42's recorded result is unchanged.

## Owner ruling 3 (2026-11-19)

**Objecting to a plan that isn't sound is within scope.** The owner sees no real difference between checking whether a plan is grounded and objecting when the plan isn't sound. Gloss may therefore object on the merit of a plan, not only when the user's own words rule it out. Ruling 2 still holds: when no cause is stated, a plan that doesn't match the symptom gets a question, not an objection.
