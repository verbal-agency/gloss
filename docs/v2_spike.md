# G27 spike — assumption extraction: go/no-go

**Verdict: GO.** Faithful detection of questionable premises is achievable, and it
is the necessary precondition for the whole v2 input-layer direction (THESIS.md).

## Result (live run, 2026-07-18)

Judge model `claude-haiku-4-5`, 20-query hand fixture (`eval/assumptions_fixture.py`).

| Metric | Result |
|---|---|
| Detection rate (loaded, n=10) | **100%** (10/10) — and the *correct* premise surfaced on eyeball, not just "something" |
| False-positive rate (clean, n=10) | **0%** (0/10) — no clean query wrongly flagged |

Reproduce: `JUDGE_MODEL=anthropic/claude-haiku-4-5 python -m eval.assumptions_spike`

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

- **n=20, single author.** The prompt and the fixture were written by the same
  person, so a perfect score partly measures designer bias. Directional go, not a
  benchmark. Before betting the build, widen the fixture (independent authorship,
  harder boundary cases, more domains) and re-measure.
- **Coarse metric.** "detection rate" only checks that *a* questionable premise
  fired; "the right premise" was confirmed by eyeball, not automated matching.
