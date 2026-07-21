# G27 spike — assumption extraction: go/no-go

**Verdict: GO.** Faithful detection of questionable premises is achievable, and it
is the necessary precondition for the whole v2 input-layer direction (THESIS.md).

## Result (live run, 2026-07-18)

Judge model `claude-haiku-4-5`, 20-query hand-labeled dataset (`eval/assumptions_dataset.py`).

| Metric | Result |
|---|---|
| Detection rate (loaded, n=10) | **100%** (10/10) — and the *correct* premise surfaced on eyeball, not just "something" |
| False-positive rate (clean, n=10) | **0%** (0/10) — no clean query wrongly flagged |

Reproduce: `JUDGE_MODEL=anthropic/claude-haiku-4-5 python -m eval.assumptions_eval`

## What it tells us

1. **Faithful detection works.** 0% false-positive on clean queries is the number
   that mattered — the faithfulness guardrail (v1 finding 14, relocated to the
   input layer) holds. This clears the central technical risk enough to build on.
2. **The "treat unconditionally" default is validated.** With 0% over-firing on
   clean input, a faithful combined call can run on every query and no-op on clean
   ones — so a targeting gate (G28) is a cost optimization, not a correctness need.
   A keyword gate remains rejected (cue-dependence; see REMEDIATION.md G28).
3. **Frame-expansion is fundable.** The extractor already surfaced *unconsidered
   alternatives*, not just stated premises — e.g. "rewrite from scratch" →
   "incremental refactoring is frequently the better path"; "2-year-old
   manipulative" → "normal developmental testing of boundaries." That is the
   wider "surface limited thinking" ambition appearing spontaneously, faithfully,
   at 0% FP. Worth a dedicated goal, grounded in the counterfactual *mirror*
   (show the reframing by demonstration, not by the model diagnosing the user).

## Honest limits

- **n=20, single author.** The prompt and the dataset were written by the same
  person, so a perfect score partly measures designer bias. Directional go, not a
  benchmark. Before betting the build, widen the dataset (independent authorship,
  harder boundary cases, more domains) and re-measure.
- **Coarse metric.** "detection rate" only checks that *a* questionable premise
  fired; "the right premise" was confirmed by eyeball, not automated matching.

---

# G28 — widened dataset (framing bias): partial GO, one clear gap

**Verdict: the extractor generalizes to framing bias that carries a dubious
*claim*, but misses framing bias that is purely *structural* (a narrow frame with
no false claim).** Faithfulness holds. Detection needs a prompt-iteration pass
before the re-pose tier (G29) is built on it.

## Result (live run, 2026-07-20)

Judge `claude-haiku-4-5`; dataset grown to 30 loaded / 25 clean, model-drafted +
user-vetted, tagged by category (see `eval/assumptions_dataset.py`).

| Metric | Result |
|---|---|
| Detection — **factual** premises (n=10) | **100%** (10/10) — G27 holds |
| Detection — **framing** bias (n=20) | **60%** (12/20) — the drop is the finding |
| Detection — overall (n=30) | 73% (22/30) |
| False-positive — **neutral** (n=12) | **0%** (0/12) |
| False-positive — **near-miss** (n=13) | 15% (2/13) — both defensible boundary flags |
| False-positive — overall (n=25) | 8% (2/25) |

## What it tells us

1. **Designer bias confirmed, quantified.** G27's 100% was partly because one
   author wrote easy cases. A harder, vetted set drops framing detection to 60%.
   This is exactly why G28 existed.
2. **The miss has a shape.** All 8 misses are **false-dichotomy** ("grad school or
   work?", "pay the mortgage or invest?") or **presupposed-solution** ("more
   indexes to speed up my DB", "how much protein powder", "scale to a million")
   cases — where *no single claim is false*, only the frame is narrow. The
   extractor caught every loaded *comparison* and *embedded false claim* but is
   still fundamentally a "spot the dubious claim" detector, not a "spot the narrow
   frame" one. That is the precise capability gap.
3. **Faithfulness holds under pressure.** 0% on neutrals; the only 2 near-miss
   false positives ("healthy screen-time threshold", "quieter teammate contributes
   too little") are arguably *correct* cautious flags, not noise.

## The gap → follow-on goal (do NOT tune in-place here)

Teach the extractor to catch **structural framing bias** — collapsed option space
/ false dichotomy / presupposed solution / under-specified questions that need
context before they can be answered well. Measure before/after on this same
dataset (the misses are the target). This is a prompt-iteration goal and should
land **before** G29 (re-pose), since a re-pose tier built on a detector that
silently ignores false-dichotomy questions would ship that blind spot to users.

## Honest limits (carried)

- Model-drafted + user-vetted: vetting filters designer bias, doesn't eliminate it.
- n=55; directional, not a benchmark. "Detection" = *a* premise fired, eyeballed
  for correctness, not automated matching.

---

# G31 — teach structural framing bias: gap closed IN-SAMPLE

**Verdict: the prompt revision closes the G28 gap on the known set — framing
detection 60% → 95% — with zero faithfulness regression. But this is an in-sample
result; generalization is not yet proven (see caveat).**

## Result (live run, 2026-07-20)

`EXTRACT_SYSTEM` revised to name two kinds of questionable premise explicitly —
DUBIOUS CLAIM vs. NARROW FRAME (false dichotomy / presupposed solution /
under-specified) — and to protect queries that *ask for* tradeoffs/factors as
frame-opening, not frame-presupposing.

| Metric | G28 (before) | G31 (after) |
|---|---|---|
| Detection — framing (n=20) | 60% | **95%** (19/20) |
| Detection — factual (n=10) | 100% | 100% |
| Detection — overall (n=30) | 73% | 97% (29/30) |
| False-positive — neutral (n=12) | 0% | **0%** |
| False-positive — near-miss (n=13) | 15% (2) | **15% (same 2)** |

The one remaining framing miss ("kids watching too much TV" — presupposed-problem).
The 2 near-miss false positives are the identical defensible cases from G28
(screen-time "threshold", teammate "contributes too little") — no new over-firing.
The under-specification behavior now works as intended: e.g. "pay off the mortgage
or invest" and "guarantee 20% return" both surface "depends on the user's rate /
risk tolerance / timeline / financial situation".

## The caveat that matters (per G30 discipline)

**This is in-sample.** The prompt was revised *after* seeing the G28 misses — the
revision names the categories those misses fell into. So 95% confirms the fix
**targets** the gap; it does **not** prove the extractor generalizes to false
dichotomies / presupposed solutions it was not written against. The fix is
category-level (naming types), not case-level (memorizing queries), which is more
defensible than pure overfitting — but the generalization claim still awaits a
**held-out** set of fresh structural-framing queries the prompt never saw. No
faithfulness was traded to get here, which is the encouraging part.

## Held-out generalization run (2026-07-20)

A separate adversarial set (`eval/assumptions_heldout.py`, 10 loaded / 9 clean,
fresh domains, `--heldout`) the prompt was never written against. Built to attack
both directions and to probe the **materiality boundary**: under-specification
should flag only when a generic answer *misleads or forecloses* (material), not
merely because more context would help (benign).

| Metric | In-sample (G31) | Held-out |
|---|---|---|
| Detection (recall), all categories | 95–100% | **100%** (10/10) |
| False-positive (faithfulness) | 8% | **22%** (2/9) |

**Recall generalized — the fix is real, not memorized.** 100% on unseen cases
across every category (dichotomy, presupposed, false claim, material under-spec).
The concept transferred to new domains.

**Faithfulness generalized worse, exactly as predicted.** The two false positives:
- **benign under-spec** — "highway or surface streets to the airport" flagged
  ("assumes only two route options exist"). This is the materiality gap: a benign
  two-option framing where the omitted context is cheap. Fired via the *dichotomy*
  detector, so materiality is missing from dichotomy handling, not just under-spec.
- **factual** — "main causes of inflation" pedantically flagged ("assumes a small
  set of 'main' causes"). Over-firing from the narrow-frame priming.

The other benign cases held clean, so it's inconsistent, not uniform — but the
in-sample 8% understated the real faithfulness cost. **Verdict: the G31 concept
generalizes on recall but not yet on faithfulness. It needs a materiality/pedantry
guard** — flag a narrow frame only when answering within it materially misleads or
forecloses — before the re-pose tier (G29) is built on it. Follow-on goal.
