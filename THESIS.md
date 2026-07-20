# Gloss v2 — Thesis: responsible compensation for executive function

*This supersedes v1's north star. v1 ("detect and correct LLM sycophancy") was a
useful proxy that taught us the real target. Its machinery mostly carries over;
its **purpose** is what changes here.*

## The pitch

Turn the assistant into an **advisor** — one that surfaces the limited framing a
question takes for granted (framing the model was trained to *accept*, not
challenge) for users whose own capacity to catch that framing is atrophying. The
line that keeps it honest: an advisor whose job is to hand judgment **back** to
you, not to become the new authority you defer to.

Located precisely: the foible is not pretraining but the RLHF-trained tendency to
accommodate a user's premises (DESIGN.md files "framing capture" under sycophancy).
v2 sits at the intersection of two complementary failures — a model that won't
challenge a bad frame because accommodation is what it was optimized for, and a
user decreasingly able to challenge it themselves. The model foible is why the gap
exists and can't self-correct; the executive-function atrophy is why it now
compounds. The advisor upgrade supplies the frame-challenge the model withholds,
to the user who can no longer reliably supply it alone.

## The real problem

The point was never anti-sycophancy. Sycophancy is one symptom of a larger shift:
as people rely on AI assistants, the executive functions they used to exercise —
judgment, checking their own assumptions, weighing alternatives, self-monitoring —
get **offloaded, and weaken**. Cognitive offloading, automation complacency. The
model bending to the user is just the most visible case; the deeper harm is the
atrophy of the user's own capacity to evaluate.

So the goal is: **help a user with weakening executive function still arrive at
well-grounded outcomes** — without pretending they'll do the work themselves.

## Two theories of the response

- **Preserve (the gym).** Make the user do the executive work — scaffold it,
  add friction that forces reflection. Honest, but it fights the product's grain:
  people use assistants precisely *to* offload, so friction loses — and it fails
  hardest for the users who need it most.
- **Compensate (the prosthetic).** The system does the executive work well and
  transparently — deconstruct the assumptions, re-pose the query responsibly — so
  a low-executive-function user still gets a well-grounded result without extra
  effort.

**We choose responsible compensation.** It's the more honest bet about how people
actually use AI, and it serves the people who need it most.

## The irony — and why it doesn't sink the bet

A better prosthetic gets leaned on harder. If the system reliably checks your
assumptions for you, your own assumption-checking atrophies *faster* — compensation
risks accelerating the very thing it addresses. Two things soften this:

1. **Responsibility (faithfulness + disclosure).** Do the work *and expose it* —
   "your question assumed X; here's the answer without that assumption, and why I
   set it aside." The user can engage if they choose; the door to judgment stays
   open. That is the line between a prosthetic and silent paternalism.
2. **Passive modeling.** Repeatedly ingesting holistic, assumption-aware,
   transparent responses exposes the user to good executive-function patterns —
   the way reading well-reasoned writing improves your reasoning without
   deliberate practice. A preservation side-effect with no friction cost.

So responsible, holistic compensation is a prosthetic that also **teaches by
example**. It doesn't require the user to try harder; it makes the ambient input
they absorb more responsible.

## The layer inversion

v1 lived at the **interpretation layer**: read the model's output, judge it,
substitute a "better" one. But that *still offloads the executive work* — it just
swaps which authority the user defers to (the model → the detector). Same
dependency, new master.

v2 moves the center of gravity to the **input layer**: responsibly reconstruct
what goes *in*, so there's less to interpret and the exchange the user relies on
is better-grounded from the start. The old "externalized second observer" framing
(the system holds the vigilance the user lacks) is inverted — the aim is not to be
vigilant *for* the user, but to make the input/output exchange responsible enough
that a low-vigilance user can safely rely on it and passively learn from it.

## The three input-layer jobs

1. **Deconstruct assumptions** — surface the premises a query presupposes. (This is
   "framing capture," which v1's design flagged as the *hardest* open problem:
   evaluating premise validity is genuinely hard. It is the core technical bet.)
2. **Re-pose responsibly** — normalize into a well-formed query, faithfully (never
   rewrite what didn't need it) and conservatively.
3. **Disclose** — always show what was deconstructed or changed, and why.

## The guardrail — what "responsibly" means

- **Faithfulness:** don't rewrite queries that didn't need it (v1's G21 — already
  built).
- **Disclosure:** always expose what changed (`meta.normalized_query`,
  `signals_removed` — already built).

Without both, "compensate" collapses into paternalistic silent query-rewriting —
the trust paradox (v1 finding 14) relocated to the input layer.

## What carries over, what gets demoted

- **Carries over:** the proxy, config, LLM wrapper, per-request call budget,
  Docker, the eval harness, the dataset, the normalizer, G21's faithfulness guard,
  the disclosure fields, the counterfactual generator (repurposed as a *mirror*
  that shows the user how their framing moved the answer), and the goal-loop
  process itself.
- **Demoted to means, not product:** detect-and-substitute, the judge apparatus,
  the divergence/stance metrics. They become **measurement and evidence** — how we
  check whether compensation is working — not the user-facing point.

## Open problems v2 must answer honestly

- **Measurement.** "Executive function compensated/preserved" is a behavioral,
  longitudinal property; no request-level metric captures it. A flip rate won't
  transfer — we need a different evidence story (closer to a user study than an
  eval run).
- **Friction vs. value.** Even responsible compensation must not annoy. *Which*
  queries get the treatment (targeting) is a real problem — factual, low-stakes
  queries shouldn't be re-posed at all.
- **Assumption deconstruction is hard.** Detecting and questioning embedded
  premises without solving general reasoning is the central technical risk;
  de-risk it small before betting the build on it.
