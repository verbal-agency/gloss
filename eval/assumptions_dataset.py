"""Assumptions evaluation dataset — hand-labeled loaded vs. clean queries.

Two batches, tagged so the harness can report generalization per-type:
  - "factual"  — the original G27 set: queries whose premise is factually dubious.
  - "framing"  — the G28 set: cognitive-framing bias — collapsed option space,
                 leading structure with no opinion keyword, presupposed solution,
                 loaded comparison, embedded causal assumption. This is the harder,
                 truer v2 target (NOT social/demographic bias).

LOADED: (query, intended premise/bias to surface, category). The intended text is
for human eyeball — premise-matching is not automated.
CLEAN: (query, kind). kind "near_miss" mirrors a loaded query and differs ONLY in
whether the framing bakes in a conclusion — the hardest faithfulness cases;
"neutral" is a plainly well-posed query. A faithful extractor returns an EMPTY
questionable list for every clean query.

Honest limit (carried from G27): the queries are model-drafted and user-vetted, so
"independent authorship" is only partly achieved — the vetting filters designer
bias, it does not eliminate it. Directional, not a benchmark.
"""
from __future__ import annotations

# (query, intended premise/bias, category)
LOADED: list[tuple[str, str, str]] = [
    # ── factual-premise batch (G27) ──────────────────────────────────────────
    ("How should I use React, Redux, and MongoDB to build a simple to-do list?",
     "that this stack is appropriate/necessary for a simple to-do list (overkill)", "factual"),
    ("Why is Python faster than C for heavy numerical loops?",
     "that Python is faster than C for numerical work (false)", "factual"),
    ("What's the safest way to lose 20 pounds in a week?",
     "that losing 20 lb in a week is safe or achievable", "factual"),
    ("Since coffee is bad for you, what should I switch to in the mornings?",
     "that coffee is bad for you (contested/overgeneralized)", "factual"),
    ("What's the most effective essential oil for curing anxiety?",
     "that essential oils cure anxiety", "factual"),
    ("How can I invest to guarantee a 20% annual return?",
     "that a guaranteed 20% annual return exists", "factual"),
    ("Everyone knows tabs are better than spaces — how do I convert my repo to tabs?",
     "that tabs are objectively better than spaces (contested preference)", "factual"),
    ("How do I get my 2-year-old to stop being manipulative?",
     "that a 2-year-old is capable of manipulation (developmental mischaracterization)", "factual"),
    ("What supplements should I take to detox my liver?",
     "that a healthy liver needs supplement-driven 'detoxing'", "factual"),
    ("How do I convince my team we should rewrite the whole system from scratch?",
     "that a full from-scratch rewrite is the right move", "factual"),

    # ── cognitive-framing-bias batch (G28) ───────────────────────────────────
    # collapsed option space / false dichotomy
    ("Should I go to grad school or start working right away?",
     "false dichotomy — ignores gap year, part-time study, apprenticeship", "framing"),
    ("Do I fix my old car or buy a new one?",
     "collapsed options — ignores certified-used, repair-vs-replace math, going car-free", "framing"),
    ("Should I pay off my mortgage early or invest the extra?",
     "presupposes these are the only two options and one is universally smarter", "framing"),
    # leading, no opinion keyword
    ("What's the fastest way to get my team to adopt Kubernetes?",
     "presupposes Kubernetes is the right choice", "framing"),
    ("How do I get my kids to stop watching so much TV?",
     "presupposes the amount / that TV is the problem", "framing"),
    ("What's the best framework to rewrite our frontend in?",
     "presupposes a rewrite (vs incremental) is the move", "framing"),
    ("How do I get better sleep by taking melatonin?",
     "presupposes melatonin is the solution", "framing"),
    # unconsidered alternative (presupposed solution)
    ("How do I add more indexes to speed up my slow database?",
     "presupposes indexing is the fix — ignores query rewrite, N+1, schema", "framing"),
    ("What's the best way to motivate my team with bonuses?",
     "presupposes bonuses motivate — ignores autonomy, purpose, workload", "framing"),
    ("How much protein powder should I take to build muscle?",
     "presupposes powder is needed vs whole-food protein + training", "framing"),
    # loaded comparison (presupposed ranking)
    ("Why is remote work more productive than in-office?",
     "presupposes remote is more productive (contested)", "framing"),
    ("What makes Rust safer than Go?",
     "presupposes a context-free 'safer' ranking", "framing"),
    ("Why do startups move faster than big companies?",
     "presupposes they always do", "framing"),
    # embedded factual/causal assumption in framing
    ("How do I detox the microplastics from my body?",
     "presupposes a definable, achievable 'detox'", "framing"),
    ("What's the best diet to fix my slow metabolism?",
     "presupposes 'slow metabolism' is the cause", "framing"),
    ("How do I use both sides of my brain to be more creative?",
     "left/right-brain myth", "framing"),
    ("How do I stop my introverted coworker from dragging down the team?",
     "presupposes introversion = not a team player", "framing"),
    # presupposed necessity / urgency
    ("How quickly can I scale my app to a million users?",
     "presupposes that scale is needed now", "framing"),
    ("What's the healthiest oil to fry everything in?",
     "presupposes frying everything is fine / that one oil is healthiest for all high-heat use", "framing"),
    ("How do I convince my manager to let me lead the rewrite?",
     "double-presupposes the rewrite is worth doing", "framing"),
]

# (query, kind)  kind in {"near_miss", "neutral"}
CLEAN: list[tuple[str, str]] = [
    # ── original neutral batch (G27) ─────────────────────────────────────────
    ("What's the difference between a list and a tuple in Python?", "neutral"),
    ("How does HTTPS keep data secure in transit?", "neutral"),
    ("What are the tradeoffs between REST and GraphQL for a public API?", "neutral"),
    ("How do I vertically center a div with flexbox?", "neutral"),
    ("What's a reasonable way to structure a weekly meal plan on a budget?", "neutral"),
    ("How does compound interest work?", "neutral"),
    ("What are common causes of a slow SQL query?", "neutral"),
    ("How should I think about whether to rent or buy a home?", "neutral"),
    ("What's the process for setting up SSH key authentication?", "neutral"),
    ("How do vaccines train the immune system?", "neutral"),
    # ── near-misses (G28): mirror a loaded query, but genuinely open ─────────
    ("What are the tradeoffs between buying and leasing a car?", "near_miss"),
    ("What factors should I weigh between grad school and working?", "near_miss"),
    ("How do I write a Kubernetes deployment manifest?", "near_miss"),
    ("How does melatonin affect sleep?", "near_miss"),
    ("What are the pros and cons of remote vs. in-office work?", "near_miss"),
    ("How do Rust and Go differ in memory safety?", "near_miss"),
    ("What's a healthy amount of screen time for kids by age?", "near_miss"),
    ("How does the body eliminate waste?", "near_miss"),
    ("What are evidence-based ways to build muscle?", "near_miss"),
    ("What should I consider when choosing a cloud provider for a side project?", "near_miss"),
    ("What are the risks of rewriting a codebase vs. refactoring incrementally?", "near_miss"),
    ("How do I help a quieter teammate contribute more?", "near_miss"),
    ("What determines an oil's smoke point?", "near_miss"),
    # ── extra neutrals (G28) ─────────────────────────────────────────────────
    ("What's the difference between TCP and UDP?", "neutral"),
    ("How do I set up CI for a Python project?", "neutral"),
]
