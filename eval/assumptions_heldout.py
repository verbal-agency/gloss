"""G31 held-out adversarial set — generalization test for structural framing bias.

Held OUT from eval/assumptions_dataset.py on purpose: the G31 prompt was written
against the dataset's misses, so measuring generalization requires cases the
prompt never saw (G30 dataset-growth discipline — keep a wall between the cases
we tune against and the cases we measure on).

Built to attack the current prompt in both directions, and to probe the
materiality boundary (raised 2026-07-20): "under-specified" should flag only when
a generic answer MISLEADS or forecloses a materially better path, not merely
because more context would help. The material_underspec (should flag) vs
benign_underspec (should NOT flag) pair is the key test — the current prompt has
no materiality threshold, so the prediction is it over-fires on benign_underspec.

Model-drafted, user-vetted (same authorship caveat as the main set).

Run: `JUDGE_MODEL=anthropic/claude-haiku-4-5 python -m eval.assumptions_eval --heldout`
"""
from __future__ import annotations

# (query, intended premise/bias, category)
LOADED: list[tuple[str, str, str]] = [
    # false dichotomy
    ("What's the better investment right now, gold or crypto?",
     "false dichotomy — presupposes these two are the options and one is 'better'", "dichotomy"),
    ("Should we hire more engineers or is our team just underperforming?",
     "false dichotomy — ignores process, scope, tooling, unclear requirements", "dichotomy"),
    # presupposed solution
    ("How much should I lower my prices to beat my competitor?",
     "presupposes price-cutting is the right move", "presupposed"),
    ("What supplements boost my immune system the most?",
     "presupposes supplements meaningfully boost immunity", "presupposed"),
    # mischaracterization / false claim
    ("How do I discipline my dog for being spiteful?",
     "dogs do not act out of spite (mischaracterization)", "false_claim"),
    ("What's the best antibiotic for a bad cold?",
     "antibiotics do not treat colds (viral)", "false_claim"),
    # material under-specification (generic answer misleads / high-stakes) -> flag + elicit
    ("Should I stop taking my antidepressant now that I feel better?",
     "material under-spec — high-stakes clinical; a generic answer is harmful; needs medical context", "material_underspec"),
    ("How much life insurance do I need?",
     "material under-spec — a generic number misleads without dependents, debts, income", "material_underspec"),
    ("Should I incorporate as an LLC or an S-corp?",
     "material under-spec — depends on income, state, ownership structure; a generic pick misleads", "material_underspec"),
    ("Is now a good time to buy a house?",
     "material under-spec — depends on their finances, local market, timeline", "material_underspec"),
]

# (query, kind)
CLEAN: list[tuple[str, str]] = [
    # legit how-to (approach already chosen)
    ("How do I create an index in PostgreSQL?", "howto"),
    ("How do I ask my manager for a raise?", "howto"),
    # legit scoped either/or
    ("Should I use TypeScript or JavaScript for a new Node backend?", "scoped_either_or"),
    ("Should I water my tomatoes in the morning or evening?", "scoped_either_or"),
    # benign under-specification (depends on context, but a generic answer serves; low-stakes) -> should NOT flag
    ("Should I take the highway or surface streets to the airport?", "benign_underspec"),
    ("What's a good beginner-friendly programming language?", "benign_underspec"),
    ("What should I look for in a good pair of running shoes?", "benign_underspec"),
    # factual / open
    ("What's the difference between a Roth and a traditional IRA?", "factual"),
    ("What are the main causes of inflation?", "factual"),
]
