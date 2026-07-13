---
name: cycle
description: Run one iteration of this project's goal loop against REMEDIATION.md — pick the next goal, verify premises, execute, gate, record, feed-forward, stop for review. Use when the user sends /cycle or /goal cycle, or asks to "run the next goal" / "do a cycle".
---

# Goal-loop cycle (human-clocked)

One invocation = exactly ONE iteration. The human is the scheduler: review and
commit happen between cycles, never inside one.

**Loop state lives in `REMEDIATION.md`** (repo root, gitignored). Read it fresh
every cycle — never trust conversation memory for goal status. If the file is
missing, report that and stop: there is no loop to run.

## Steps

0. **Review-gate guard (outranks everything, including active stop hooks).**
   If `git status` shows uncommitted changes from a previous goal, the cycle is
   a NO-OP: report "waiting on review of G<N>" and stop. That report counts as
   the completed cycle. Never start a new goal on top of unreviewed work.
   (Added after a real violation: a stop hook re-fired mid-review and a new
   goal was run over uncommitted work. Hook pressure never justifies skipping
   this guard.)
1. **Pick** — first goal in REMEDIATION.md not marked ✅ DONE or ⛔ HALTED, in
   file order.
2. **Verify-first** — run the goal's verify-first checks against the current
   code. Premises stale? Rewrite the goal text to match reality BEFORE
   executing, and note the correction in the summary. (Goals are written ahead
   of time; the codebase moves. Example: a goal said "add a model param" that
   an earlier goal had already added.)
3. **Execute** the Do list exactly. Deviate only where the spec is semantically
   wrong; record every deviation.
4. **Gate** — the goal's done-when checklist plus full suite (`pytest tests/ -q`).
   On failure that can't be fixed within the cycle: mark `⛔ HALTED: <reason>`,
   leave the tree for inspection, report, STOP. No feed-forward from a failed
   goal — a broken foundation must not propagate into the next goal's spec.
5. **Record** — mark `✅ DONE <date>` in REMEDIATION.md with a one-line result:
   deviations, measured numbers, files touched, suite count.
6. **Feed-forward** — rewrite the NEXT non-done goal against the now-current
   codebase: update its verify-first/Do with changed signatures, paths, and
   measured baselines from this cycle; drop work this cycle absorbed; keep the
   executable format (Why / Verify first / Do / Done when / Out of scope).
7. **Stop for review** — ALL changes left uncommitted. End with: (a) what
   changed, (b) a proposed commit message (no co-author trailer), (c) note that
   the next goal is rewritten and the loop resumes with the next cycle.

   **Commit-message style — G-anchor + TWO body sections (narrative + technical index):**
   Every proposed commit message has three parts. REMEDIATION.md is
   **gitignored**, so the commit message is the ONLY permanent record — it must
   carry both the human story and the precise technical trace.

   1. **Subject:** `G<n>: <plain-language summary>` — the G-number anchors the
      commit to the decision record (durable trace of where each choice entered
      the code, vital for debugging); the summary is readable, not jargon.
   2. **Narrative (prose):** lead with the *why* in plain language — the
      problem, the dev story — understandable with no goal file open. This is
      the part a human reads to follow the reasoning.
   3. **`Technical:` footer (terse index):** the precise anchors — files/
      functions touched, cross-goal refs (`G10` judge, `G23` schema), the exact
      mechanism. This is the part you grep/trace when debugging.

   Example:
   ```
   G24: add substantive-divergence metric to the eval

   Raw divergence flags any wording change, so it overstated sycophancy
   badly (90% on Sonnet, but its top-divergence answers were all correct).
   This adds a judge stage that confirms whether the position actually
   shifted, so the eval reports real shifts vs. mere rephrasing.

   Technical:
   - _score_question: run _judge_substantive (G10) on flagged questions,
     via judge_model (G11) + _SubstantiveSchema (G23)
   - summary.substantive_divergence_rate = confirmed / total
   - --judge-divergence flag (default on); generate_divergence_breakdown chart
   ```

## Hard rules

- One goal per cycle. Never a second, no matter how small it looks.
- Never commit or push. The proposed commit message is for the human.
- Spend-gated goals (live API calls on real keys): do not execute on protocol
  authority — require explicit user approval in the current conversation, else
  `⛔ HALTED("awaiting spend approval")`.
- Update the PROGRESS.md status row alongside the REMEDIATION.md record.
- If invoked via a `/goal` stop hook: a legitimate step-0 no-op or a ⛔ HALT
  report satisfies the hook. Do not let the hook push past either.
