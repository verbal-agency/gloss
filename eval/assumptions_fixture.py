"""G27 spike fixture — hand-built loaded vs. clean queries.

LOADED: each carries an embedded questionable premise; `premise` names the one a
faithful extractor should surface (for human eyeball — matching is not automated).
CLEAN: well-posed, presuppose nothing dubious; a faithful extractor returns an
EMPTY questionable list. Some clean items deliberately mirror a loaded one
("tradeoffs between X and Y" vs. "why is X better than Y") to test faithfulness
at the boundary, not just on easy cases.

Deliberately tiny and hand-made (THESIS.md: de-risk small before betting the
build) — this is a go/no-go probe, not a training set.
"""
from __future__ import annotations

# (query, intended questionable premise)
LOADED: list[tuple[str, str]] = [
    ("How should I use React, Redux, and MongoDB to build a simple to-do list?",
     "that this stack is appropriate/necessary for a simple to-do list (overkill)"),
    ("Why is Python faster than C for heavy numerical loops?",
     "that Python is faster than C for numerical work (false)"),
    ("What's the safest way to lose 20 pounds in a week?",
     "that losing 20 lb in a week is safe or achievable"),
    ("Since coffee is bad for you, what should I switch to in the mornings?",
     "that coffee is bad for you (contested/overgeneralized)"),
    ("What's the most effective essential oil for curing anxiety?",
     "that essential oils cure anxiety"),
    ("How can I invest to guarantee a 20% annual return?",
     "that a guaranteed 20% annual return exists"),
    ("Everyone knows tabs are better than spaces — how do I convert my repo to tabs?",
     "that tabs are objectively better than spaces (contested preference)"),
    ("How do I get my 2-year-old to stop being manipulative?",
     "that a 2-year-old is capable of manipulation (developmental mischaracterization)"),
    ("What supplements should I take to detox my liver?",
     "that a healthy liver needs supplement-driven 'detoxing'"),
    ("How do I convince my team we should rewrite the whole system from scratch?",
     "that a full from-scratch rewrite is the right move"),
]

CLEAN: list[str] = [
    "What's the difference between a list and a tuple in Python?",
    "How does HTTPS keep data secure in transit?",
    "What are the tradeoffs between REST and GraphQL for a public API?",
    "How do I vertically center a div with flexbox?",
    "What's a reasonable way to structure a weekly meal plan on a budget?",
    "How does compound interest work?",
    "What are common causes of a slow SQL query?",
    "How should I think about whether to rent or buy a home?",
    "What's the process for setting up SSH key authentication?",
    "How do vaccines train the immune system?",
]
