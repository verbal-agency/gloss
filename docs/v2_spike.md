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
